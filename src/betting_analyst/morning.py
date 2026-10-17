"""Morning Scout — „Typy dnia” z oferty STS (ADR 0021).

    uv run python -m betting_analyst.morning [--days 2] [--log-paper] [--from-cache] [--top 5] [--notify]

Przepływ:
1. oferta STS (publiczny feed WebSocket) dla meczów z horyzontu — 1X2, gole, BTTS, rogi, kartki,
2. cena fair: rynki 1X2 / O/U 2.5 — zdewigowany Pinnacle (The Odds API, ~8 kredytów);
   pozostałe linie goli i BTTS — Dixon-Coles; rogi i kartki — model NB (models/counts.py),
3. ranking po edge = kurs_STS × p_fair − 1 (przed podatkiem), maks. 1 typ na mecz, top N,
4. podatek informacyjnie: kurs po podatku, EV po podatku i ✅ gdy typ jest na plus także po podatku,
5. stawka: ¼ Kelly dla ✅, mała stała stawka dla pozostałych; limity dzienne (ADR 0002).

Prawdopodobieństwa liczy wyłącznie kod (rynek + modele) — LLM ich nie zmienia (ADR 0012).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from betting_analyst import budget, ledger
from betting_analyst.config import (
    DB_PATH,
    REPORTS_DIR,
    SCANS_DIR,
    League,
    Strategy,
    get_env,
    load_bookmakers,
    load_strategy,
    load_team_aliases,
)
from betting_analyst.decision.ev import (
    TaxContext,
    apply_daily_exposure,
    effective_odds,
    kelly_stake,
    required_edge,
    round_stake,
    stake_tax_rate,
)
from betting_analyst.domain import Quote, market_kind, pick_label, selections_for
from betting_analyst.models.devig import devig
from betting_analyst.scan import LOCAL_TZ, collect_quotes, fair_price, fit_models
from betting_analyst.sources import football_data, sts
from betting_analyst.sources.the_odds_api import MISSING_KEY_HELP, TheOddsApiClient
from betting_analyst.teams import TeamResolver, team_key

log = logging.getLogger("betting_analyst.morning")

MARKET_SOURCES = ("1x2", "ou25")  # rynki z kursami Pinnacle w The Odds API
SOURCE_PRIORITY = {"pinnacle": 3, "consensus": 2, "model:dc": 1, "model:counts": 0}
COUNT_KINDS = {
    "corners": "corners",
    "home_corners": "corners",
    "away_corners": "corners",
    "cards": "cards",
    "home_cards": "cards",
    "away_cards": "cards",
}


@dataclass
class Pick:
    fixture: sts.StsFixture
    market: str
    selection: str
    odds: float
    fair_prob: float
    fair_source: str  # pinnacle | consensus(n) | model:dc | model:counts
    fair_method: str
    model_prob: float | None
    model_version: str | None
    sts_prob: float | None  # zdewigowane prawdopodobieństwo samego STS (porównanie)
    stake_tax: float
    ref_event_id: str | None = None
    flags: list[str] = field(default_factory=list)
    stake: float = 0.0

    @property
    def edge(self) -> float:
        """Przewaga kursu STS nad ceną fair, przed podatkiem."""
        return self.odds * self.fair_prob - 1.0

    @property
    def odds_eff(self) -> float:
        return effective_odds(self.odds, self.stake_tax)

    @property
    def ev_after_tax(self) -> float:
        return self.fair_prob * self.odds_eff - 1.0

    @property
    def is_model_only(self) -> bool:
        return self.fair_source.startswith("model:")

    @property
    def source_rank(self) -> int:
        return SOURCE_PRIORITY.get(self.fair_source.split("(")[0], 0)

    @property
    def label(self) -> str:
        return pick_label(self.market, self.selection)


def value_after_tax(p: Pick, strategy: Strategy) -> bool:
    """✅ — typ na plus także po podatku (próg jak w skanerze, ADR 0014)."""
    return p.ev_after_tax >= required_edge(p.odds, strategy)


def model_market_gap(p: Pick) -> float | None:
    """Rozbieżność surowego modelu i zdewigowanego STS (dla rynków model-only)."""
    if p.model_prob is None or p.sts_prob is None:
        return None
    return abs(p.model_prob - p.sts_prob)


def qualifies(p: Pick, strategy: Strategy) -> bool:
    """Minimalny sensowny próg: edge > 0; model-only — wyższy próg i bez dużej rozbieżności z rynkiem."""
    if p.is_model_only:
        gap = model_market_gap(p)
        if gap is None or gap > strategy.max_model_market_gap or p.odds > strategy.model_only_max_odds:
            return False
        return p.edge >= strategy.model_only_min_edge
    return p.edge > 0


def select_daily_picks(picks: list[Pick], strategy: Strategy, top: int) -> list[Pick]:
    """Maks. 1 typ na mecz (korelacja), ranking: edge, potem pewność źródła fair; top N."""
    best: dict[str, Pick] = {}
    for p in picks:
        if not qualifies(p, strategy):
            continue
        cur = best.get(p.fixture.fixture_id)
        if cur is None or (p.edge, p.source_rank) > (cur.edge, cur.source_rank):
            best[p.fixture.fixture_id] = p
    ranked = sorted(best.values(), key=lambda p: (value_after_tax(p, strategy), p.edge, p.source_rank), reverse=True)
    return ranked[:top]


def assign_stakes(picks: list[Pick], strategy: Strategy, already_staked: float) -> None:
    bankroll, rounding = strategy.bankroll_pln, strategy.stake_rounding_pln
    raw = []
    for p in picks:
        if value_after_tax(p, strategy):
            raw.append(
                kelly_stake(
                    p.fair_prob, p.odds_eff, bankroll, strategy.kelly_fraction, strategy.max_stake_pct, rounding
                )
            )
        else:
            raw.append(round_stake(bankroll * strategy.pick_flat_stake_pct, rounding))
    for p, stake in zip(
        picks, apply_daily_exposure(raw, bankroll, strategy.daily_exposure_pct, already_staked, rounding), strict=True
    ):
        p.stake = stake


# --- Ceny fair --------------------------------------------------------------------------


def _sts_market_probs(quotes: list[Quote]) -> dict[str, dict[str, float]]:
    """Zdewigowane (multiplicative) prawdopodobieństwa samego STS per rynek — do porównań."""
    by_market: dict[str, dict[str, float]] = defaultdict(dict)
    for q in quotes:
        by_market[q.market][q.selection] = q.odds
    out = {}
    for market, odds in by_market.items():
        sels = selections_for(market)
        if all(s in odds for s in sels):
            out[market] = dict(zip(sels, devig([odds[s] for s in sels], "multiplicative"), strict=True))
    return out


def fit_count_models(leagues: list[League], strategy: Strategy, warnings: list[str]) -> dict[tuple[str, str], object]:
    """Modele NB rogów i kartek (models/counts.py) per liga; brak modułu/danych → ostrzeżenie."""
    try:
        from betting_analyst.models.counts import fit_counts
    except Exception as exc:  # moduł rozwijany równolegle — brak nie zatrzymuje skanu
        warnings.append(f"Model rogów/kartek niedostępny ({exc})")
        return {}
    models: dict[tuple[str, str], object] = {}
    today = datetime.now(UTC)
    for league in leagues:
        try:
            stats = football_data.load_match_stats(league, strategy.dixon_coles.seasons)
        except Exception as exc:
            warnings.append(f"{league.name}: brak statystyk meczowych ({exc})")
            continue
        if stats is None or len(stats) == 0:
            warnings.append(f"{league.name}: brak statystyk rogów/kartek — rynki dodatkowe pominięte")
            continue
        for stat in ("corners", "cards"):
            try:
                models[(league.key, stat)] = fit_counts(stats, stat, as_of=today, league=league.key)
            except Exception as exc:
                warnings.append(f"{league.name}: model {stat} niedostępny ({exc})")
    return models


def build_picks(
    offer: sts.StsOffer,
    odds_api_quotes: list[Quote],
    leagues: dict[str, League],
    dc_models: dict,
    count_models: dict,
    strategy: Strategy,
    stake_tax: float,
    excluded_books: set[str],
    now: datetime,
    warnings: list[str],
) -> list[Pick]:
    alias_teams = set(load_team_aliases())
    resolvers = {k: TeamResolver(dc_models[k].teams if k in dc_models else alias_teams) for k in leagues}

    # Mecze z The Odds API po kluczu (liga, gospodarz, gość) — do ceny Pinnacle.
    ref_events: dict[tuple[str, str, str], list[Quote]] = defaultdict(list)
    for q in odds_api_quotes:
        r = resolvers.get(q.league)
        ref_events[(q.league, team_key(q.home_team, r), team_key(q.away_team, r))].append(q)

    quotes_by_fixture: dict[str, list[Quote]] = defaultdict(list)
    for q in offer.quotes:
        quotes_by_fixture[q.event_id].append(q)

    picks: list[Pick] = []
    unmatched: set[str] = set()
    for fx in offer.fixtures:
        if fx.commence_time <= now + timedelta(minutes=5):
            continue
        r = resolvers.get(fx.league)
        home_c = r.resolve(fx.home_team) if r else None
        away_c = r.resolve(fx.away_team) if r else None
        for name, canon in ((fx.home_team, home_c), (fx.away_team, away_c)):
            if canon is None:
                unmatched.add(f"{fx.league}: {name}")
        key = (fx.league, team_key(fx.home_team, r), team_key(fx.away_team, r))
        ref_quotes = [
            q for q in ref_events.get(key, []) if abs((q.commence_time - fx.commence_time).total_seconds()) <= 3 * 3600
        ]
        ref_event_id = ref_quotes[0].event_id if ref_quotes else None

        fx_quotes = quotes_by_fixture.get(fx.event_id, [])
        sts_probs = _sts_market_probs(fx_quotes)

        dc = dc_models.get(fx.league)
        dc_markets = None
        if dc is not None and home_c and away_c and hasattr(dc, "predict_markets"):
            try:
                dc_markets = dc.predict_markets(home_c, away_c)
            except Exception as exc:
                warnings.append(f"DC {fx.home_team} – {fx.away_team}: {exc}")

        count_markets: dict[str, dict[str, float]] = {}
        for stat in ("corners", "cards"):
            cm = count_models.get((fx.league, stat))
            if cm is not None and home_c and away_c:
                try:
                    count_markets.update(cm.predict_markets(home_c, away_c) or {})
                except Exception as exc:
                    warnings.append(f"Model {stat} {fx.home_team} – {fx.away_team}: {exc}")

        fair_cache: dict[str, tuple[dict[str, float], str, str, str | None] | None] = {}
        for q in fx_quotes:
            kind = market_kind(q.market)
            if kind in ("fouls", "sot"):
                continue  # zapisujemy kursy, ale w v1 nie oceniamy (brak modelu)
            if q.market not in fair_cache:
                fair_cache[q.market] = _fair_for_market(
                    q.market,
                    kind,
                    ref_quotes,
                    dc,
                    dc_markets,
                    count_markets,
                    count_models,
                    fx.league,
                    strategy,
                    excluded_books,
                )
            fair = fair_cache[q.market]
            if fair is None:
                continue
            probs, source, method, version = fair
            p_fair = probs.get(q.selection)
            if p_fair is None:
                continue
            p_sts = sts_probs.get(q.market, {}).get(q.selection)
            raw_model = p_fair
            if source.startswith("model:"):
                if p_sts is None:
                    continue  # bez pary kursów STS nie zakotwiczymy modelu w rynku
                p_fair = strategy.model_weight * raw_model + (1 - strategy.model_weight) * p_sts
            if source.startswith("model:"):
                model_prob = raw_model
            else:  # cena rynkowa — DC jako druga opinia
                dc_key = "goals_ou_2.5" if q.market == "ou25" else q.market
                model_prob = (dc_markets or {}).get(dc_key, {}).get(q.selection)
            pick = Pick(
                fixture=fx,
                market=q.market,
                selection=q.selection,
                odds=q.odds,
                fair_prob=p_fair,
                fair_source=source,
                fair_method=method,
                model_prob=model_prob,
                model_version=version,
                sts_prob=sts_probs.get(q.market, {}).get(q.selection),
                stake_tax=stake_tax,
                ref_event_id=ref_event_id,
            )
            pick.flags = _flags(pick, strategy)
            picks.append(pick)
    if unmatched:
        warnings.append(
            "Drużyny STS bez dopasowania do danych modeli (dopisz alias w config/team_aliases.yaml): "
            + ", ".join(sorted(unmatched))
        )
    return picks


def _fair_for_market(
    market, kind, ref_quotes, dc, dc_markets, count_markets, count_models, league, strategy, excluded_books
):
    """(probs, fair_source, method, model_version) albo None, gdy brak wiarygodnej ceny fair."""
    if market in MARKET_SOURCES and ref_quotes:
        fair = fair_price(ref_quotes, market, strategy.reference_bookmaker, strategy.devig_method, excluded_books)
        if fair is not None:
            source = "pinnacle" if fair.source == strategy.reference_bookmaker else fair.source
            return fair.probs, source, fair.method, None
    if kind in ("1x2", "btts", "goals") and dc_markets:
        dc_key = "goals_ou_2.5" if market == "ou25" else market
        probs = dc_markets.get(dc_key)
        if probs:
            return probs, "model:dc", "dixon-coles", getattr(dc, "version", None)
    if kind in COUNT_KINDS and market in count_markets:
        if not kind.startswith(("home_", "away_")) and not strategy.count_totals_enabled:
            return None  # sumy: model nie bije średniej ligi (kalibracja) — tylko linie per drużyna
        cm = count_models.get((league, COUNT_KINDS[kind]))
        return count_markets[market], "model:counts", "nb", getattr(cm, "version", None)
    return None


def _flags(p: Pick, strategy: Strategy) -> list[str]:
    flags = []
    if p.is_model_only:
        flags.append("MODEL_ONLY")
        gap = model_market_gap(p)
        if gap is not None and gap > strategy.max_model_market_gap:
            flags.append(f"model≠STS {gap * 100:.0f}pp: odrzucony")
    elif p.model_prob is not None and abs(p.fair_prob - p.model_prob) > strategy.model_disagreement_pp:
        flags.append("DC≠rynek")
    if p.fair_source.startswith("consensus"):
        flags.append(p.fair_source)
    return flags


# --- Wyjście ----------------------------------------------------------------------------


def _pct(x: float | None, signed: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"


def picks_table(picks: list[Pick], strategy: Strategy, title: str) -> Table:
    t = Table(title=title, header_style="bold", show_lines=False)
    for col in (
        "#",
        "Start",
        "Liga",
        "Mecz",
        "Typ",
        "Kurs STS",
        "p fair",
        "Źródło",
        "Edge",
        "Po podatku",
        "EV po pod.",
        "✅",
        "Stawka",
        "Uwagi",
    ):
        t.add_column(col, overflow="fold")
    for i, p in enumerate(picks, 1):
        ok = value_after_tax(p, strategy)
        t.add_row(
            str(i),
            f"{p.fixture.commence_time.astimezone(LOCAL_TZ):%a %H:%M}",
            p.fixture.league,
            f"{p.fixture.home_team} – {p.fixture.away_team}",
            p.label,
            f"{p.odds:.2f}",
            _pct(p.fair_prob),
            p.fair_source,
            _pct(p.edge, signed=True),
            f"{p.odds_eff:.2f}",
            _pct(p.ev_after_tax, signed=True),
            "✅" if ok else "",
            f"{p.stake:.0f} zł",
            ", ".join(p.flags),
        )
    return t


def markdown_report(
    picks: list[Pick], strategy: Strategy, offer: sts.StsOffer, n_evaluated: int, warnings: list[str]
) -> str:
    now_local = datetime.now(LOCAL_TZ)
    lines = [
        f"# Typy dnia — {now_local:%Y-%m-%d} (STS)",
        "",
        f"Wygenerowano {now_local:%H:%M}. Mecze w ofercie: {len(offer.fixtures)}, ocenione selekcje: {n_evaluated}.",
        "Ranking po przewadze kursu STS nad ceną fair (przed podatkiem). ✅ = na plus także po podatku 12%.",
        "",
        "| # | Start | Mecz | Typ | Kurs | p fair | Źródło | Edge | EV po podatku | ✅ | Stawka | Uwagi |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(picks, 1):
        start = f"{p.fixture.commence_time.astimezone(LOCAL_TZ):%a %H:%M}"
        ok = "✅" if value_after_tax(p, strategy) else ""
        cells = [
            str(i), start, f"{p.fixture.home_team} – {p.fixture.away_team}", p.label, f"{p.odds:.2f}",
            _pct(p.fair_prob), p.fair_source, _pct(p.edge, True), _pct(p.ev_after_tax, True), ok,
            f"{p.stake:.0f} zł", ", ".join(p.flags),
        ]  # fmt: skip
        lines.append("| " + " | ".join(cells) + " |")
    if not picks:
        lines.append("| — | | Brak typów z dodatnią przewagą nad ceną fair. | | | | | | | | | |")
    lines += [
        "",
        "**Jak czytać:** *Edge* to o ile kurs STS jest lepszy od „prawdziwej” wyceny (Pinnacle bez marży albo model). "
        "*MODEL_ONLY* — wycena tylko z naszego modelu (rogi/kartki, inne linie goli) — mniej pewna. "
        "Typ bez ✅ to „typ dnia” z małą stałą stawką; po podatku jest na minusie w oczekiwaniu.",
        "",
        "To analiza statystyczna, nie gwarancja zysku. Paper trading do czasu bramki CLV (ADR 0001, 0015).",
    ]
    if warnings:
        lines += ["", "## Ostrzeżenia", *[f"- {w}" for w in warnings]]
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m betting_analyst.morning", description="Typy dnia z oferty STS.")
    parser.add_argument("--days", type=int, default=None, help="horyzont w dniach (domyślnie strategy.morning_days)")
    parser.add_argument("--top", type=int, default=None, help="liczba typów (domyślnie strategy.daily_picks)")
    parser.add_argument("--leagues", help="klucze lig po przecinku (domyślnie wszystkie z sts_tournament_id)")
    parser.add_argument("--log-paper", action="store_true", help="zapisz typy jako zakłady paper")
    parser.add_argument("--from-cache", action="store_true", help="STS i The Odds API z cache (0 kredytów, bez sieci)")
    parser.add_argument("--no-pinnacle", action="store_true", help="bez The Odds API (tylko modele)")
    parser.add_argument("--notify", action="store_true", help="wyślij skrót typów na Telegram (notify.py)")
    parser.add_argument("--show-all", action="store_true", help="pokaż 30 najlepszych selekcji (przed regułą 1/mecz)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    console = Console()
    strategy, bookmakers = load_strategy(), load_bookmakers()
    days = args.days or strategy.morning_days
    top = args.top or strategy.daily_picks

    leagues = {k: lg for k, lg in strategy.leagues.items() if lg.sts_tournament_id}
    if args.leagues:
        wanted = {k.strip() for k in args.leagues.split(",")}
        leagues = {k: lg for k, lg in leagues.items() if k in wanted}

    now = datetime.now(UTC)
    end_local = (datetime.now(LOCAL_TZ) + timedelta(days=days - 1)).replace(hour=23, minute=59, second=59)
    warnings: list[str] = []

    console.rule(f"Morning Scout — STS, {datetime.now(LOCAL_TZ):%Y-%m-%d} (+{days - 1} d)")
    offer = sts.fetch_offer(
        {k: lg.sts_tournament_id for k, lg in leagues.items()},
        now,
        end_local.astimezone(UTC),
        from_cache=args.from_cache,
    )
    warnings += offer.warnings

    odds_api_quotes: list[Quote] = []
    if not args.no_pinnacle:
        client = None
        if not args.from_cache:
            if get_env("ODDS_API_KEY"):
                client = TheOddsApiClient(usage_log=budget.USAGE_LOG, job="morning")
            else:
                console.print(Panel(MISSING_KEY_HELP, title="Brak klucza The Odds API — tylko modele", style="yellow"))
        if client or args.from_cache:
            odds_api_quotes, used, remaining, fetch_warnings = collect_quotes(
                list(leagues.values()), strategy, args.from_cache, client
            )
            warnings += fetch_warnings
            if used:
                console.print(f"[dim]The Odds API: zużyto {used} kredytów, pozostało {remaining}[/]")

    dc_models = fit_models(list(leagues.values()), strategy, warnings)
    count_models = fit_count_models(list(leagues.values()), strategy, warnings)

    sts_bm = bookmakers.bookmakers.get(strategy.default_bookmaker)
    stake_tax = stake_tax_rate(sts_bm, "single", TaxContext()) if sts_bm else 0.12
    picks = build_picks(
        offer, odds_api_quotes, leagues, dc_models, count_models, strategy, stake_tax,
        set(bookmakers.reference_bookmakers), now, warnings,
    )  # fmt: skip

    con = ledger.connect(args.db)
    if not args.from_cache:
        ledger.insert_snapshots(con, offer.quotes)
        if odds_api_quotes:
            ledger.insert_snapshots(con, odds_api_quotes)
    today_local = datetime.now(LOCAL_TZ).date()
    daily = select_daily_picks(picks, strategy, top)
    assign_stakes(daily, strategy, ledger.staked_on(con, today_local))

    console.print(f"Mecze STS: {len(offer.fixtures)}, kursy: {len(offer.quotes)}, ocenione selekcje: {len(picks)}")
    for w in warnings:
        console.print(f"[yellow]! {w}[/]")
    if args.show_all:
        allp = sorted((p for p in picks if qualifies(p, strategy)), key=lambda p: p.edge, reverse=True)[:30]
        console.print(picks_table(allp, strategy, "Najlepsze selekcje (przed regułą 1 typ/mecz)"))
    console.print(picks_table(daily, strategy, f"Typy dnia (top {top}, maks. 1 na mecz)"))
    if not daily:
        console.print("Brak typów z dodatnią przewagą nad ceną fair.")
    console.print("[dim]Edge przed podatkiem; ✅ = na plus także po podatku. Prawdopodobieństwa liczy kod, nie LLM.[/]")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORTS_DIR / f"{today_local.isoformat()}-morning.md"
    report.write_text(markdown_report(daily, strategy, offer, len(picks), warnings), encoding="utf-8")
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    (SCANS_DIR / f"{today_local.isoformat()}-morning.json").write_text(
        json.dumps([_pick_json(p, strategy) for p in daily], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    console.print(f"[dim]Raport: {report}[/]")

    if args.log_paper:
        existing = ledger.already_logged(con, today_local)
        n = 0
        for p in daily:
            if (p.fixture.event_id, p.market, p.selection, "sts") in existing or p.stake <= 0:
                continue
            ledger.log_paper_bet(con, _paper_bet(p, strategy, today_local))
            n += 1
        console.print(f"[bold green]Zapisano {n} typów jako paper bets do {args.db}[/]")
    con.close()
    if args.notify:
        _send_notification(today_local, args.db, console)
    return 0


def _send_notification(day, db_path: Path, console: Console) -> None:
    """Skrót na Telegram; błąd powiadomienia nie psuje skanu (raport i ledger są już zapisane)."""
    from betting_analyst import notify

    try:
        sent = notify.notify_morning(day, db_path)
    except Exception as exc:
        log.warning("Telegram: nie wysłano skrótu (%s)", exc)
        sent = False
    console.print("[dim]Telegram: wysłano skrót typów[/]" if sent else "[dim]Telegram: pominięto[/]")


def _pick_json(p: Pick, strategy: Strategy) -> dict:
    return {
        "fixture_id": p.fixture.fixture_id,
        "event_id": p.fixture.event_id,
        "league": p.fixture.league,
        "commence_time": p.fixture.commence_time.isoformat(),
        "match": f"{p.fixture.home_team} – {p.fixture.away_team}",
        "market": p.market,
        "selection": p.selection,
        "label": p.label,
        "odds": p.odds,
        "fair_prob": p.fair_prob,
        "fair_source": p.fair_source,
        "edge": p.edge,
        "odds_eff": p.odds_eff,
        "ev_after_tax": p.ev_after_tax,
        "value_after_tax": value_after_tax(p, strategy),
        "stake": p.stake,
        "flags": p.flags,
    }


def _paper_bet(p: Pick, strategy: Strategy, day) -> ledger.PaperBet:
    ok = value_after_tax(p, strategy)
    return ledger.PaperBet(
        scan_date=day,
        event_id=p.fixture.event_id,
        league=p.fixture.league,
        commence_time=p.fixture.commence_time,
        home_team=p.fixture.home_team,
        away_team=p.fixture.away_team,
        market=p.market,
        selection=p.selection,
        bookmaker="sts",
        source="sts",
        is_proxy=False,
        odds=p.odds,
        stake_tax=p.stake_tax,
        odds_eff=p.odds_eff,
        fair_prob=p.fair_prob,
        fair_method=f"{p.fair_source}:{p.fair_method}",
        ev=p.ev_after_tax,
        stake=p.stake,
        model_prob=p.model_prob,
        model_version=p.model_version,
        flags=", ".join(["VALUE" if ok else "TYP_DNIA", *p.flags]),
        fair_source=p.fair_source,
        pick_type="value" if ok else "daily",
        ref_event_id=p.ref_event_id,
    )


if __name__ == "__main__":
    sys.exit(main())
