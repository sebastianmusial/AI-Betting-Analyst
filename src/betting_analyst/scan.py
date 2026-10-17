"""Value Scanner v0: dzisiejsze mecze → cena fair (Pinnacle) → DC → kursy PL → kandydaci.

    uv run python -m betting_analyst.scan --date 2026-10-17 [--log-paper] [--from-cache]

Przepływ:
1. The Odds API (h2h + totals, region eu) dla 4 lig; surowe odpowiedzi w data/raw/.
2. Devig Pinnacle → p_fair (gdy brak Pinnacle: konsensus wielu buków, z flagą).
3. Dixon-Coles (football-data, 3 sezony, time-decay) jako druga opinia: p_DC i różnica w pp.
4. Oferty: ręczne kursy polskich buków (data/manual_odds/DATA.csv) albo PROXY z The Odds API
   (buki nielegalne/niedostępne w PL — tylko przybliżenie, zawsze oznaczone).
5. Kurs po podatku, EV, ¼ Kelly z capami, limit dziennej ekspozycji, propozycje AKO.
6. Tabela kandydatów; data/scans/DATA.json dla skilla /daily-scan; --log-paper → ledger.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from betting_analyst import ledger
from betting_analyst.config import (
    DB_PATH,
    SCANS_DIR,
    BookmakersConfig,
    League,
    Strategy,
    get_env,
    load_bookmakers,
    load_strategy,
    load_team_aliases,
)
from betting_analyst.decision.ev import (
    AkoLeg,
    AkoProposal,
    OfferEvaluation,
    TaxContext,
    apply_daily_exposure,
    build_ako_proposals,
    evaluate,
    kelly_stake,
    stake_tax_rate,
)
from betting_analyst.domain import SELECTION_LABELS, SELECTIONS, Quote
from betting_analyst.models.devig import consensus_devig, devig, devig_all
from betting_analyst.models.dixon_coles import DixonColesForecaster, fit_dixon_coles
from betting_analyst.sources import football_data, manual_odds
from betting_analyst.sources.the_odds_api import (
    MISSING_KEY_HELP,
    TheOddsApiClient,
    load_latest_cached,
    parse_events,
)
from betting_analyst.teams import TeamResolver, team_key, unresolved

log = logging.getLogger("betting_analyst.scan")
LOCAL_TZ = ZoneInfo("Europe/Warsaw")


# --- Struktury --------------------------------------------------------------------------


@dataclass
class Event:
    event_id: str
    league: str
    commence_time: datetime
    home_team: str
    away_team: str
    quotes: list[Quote] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.home_team} – {self.away_team}"


@dataclass
class FairPrice:
    probs: dict[str, float]
    source: str  # pinnacle | consensus(n)
    method: str
    by_method: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class Offer:
    bookmaker: str  # klucz z bookmakers.yaml albo proxy:<klucz The Odds API>
    label: str
    odds: float
    source: str  # manual | proxy:<klucz>
    is_proxy: bool
    stake_tax: float


@dataclass
class Candidate:
    event: Event
    market: str
    selection: str
    fair: FairPrice
    dc_prob: float | None
    offer: Offer
    evaluation: OfferEvaluation
    flags: list[str] = field(default_factory=list)
    stake: float = 0.0

    @property
    def fair_prob(self) -> float:
        return self.fair.probs[self.selection]

    @property
    def diff_pp(self) -> float | None:
        return None if self.dc_prob is None else self.fair_prob - self.dc_prob


@dataclass
class ScanResult:
    day: date
    events: list[Event]
    evaluated: list[Candidate]
    candidates: list[Candidate]
    ako: list[AkoProposal]
    unmatched_teams: dict[str, dict[str, list[str]]]
    credits_used: int
    credits_remaining: int | None
    warnings: list[str]


# --- Pobieranie --------------------------------------------------------------------------


def collect_quotes(
    leagues: list[League], strategy: Strategy, from_cache: bool, client: TheOddsApiClient | None
) -> tuple[list[Quote], int, int | None, list[str]]:
    quotes: list[Quote] = []
    used, remaining, warnings = 0, None, []
    for league in leagues:
        if from_cache:
            result = load_latest_cached(league.odds_api_key)
            if result is None:
                warnings.append(f"{league.name}: brak zapisanej odpowiedzi w cache")
                continue
            warnings.append(f"{league.name}: kursy z cache z {result.fetched_at:%Y-%m-%d %H:%M} UTC")
        else:
            assert client is not None
            result = client.fetch_odds(league.odds_api_key, strategy.odds_api.regions, strategy.odds_api.markets)
            if result.credits:
                used += result.credits.last or 0
                remaining = result.credits.remaining
        quotes.extend(parse_events(result.events, league.key, result.fetched_at))
    return quotes, used, remaining, warnings


def group_events(quotes: list[Quote], day: date, now: datetime) -> list[Event]:
    """Mecze z danego dnia (czas PL), które jeszcze się nie zaczęły (tylko pre-match)."""
    events: dict[str, Event] = {}
    for q in quotes:
        if q.commence_time.astimezone(LOCAL_TZ).date() != day or q.commence_time <= now:
            continue
        ev = events.setdefault(q.event_id, Event(q.event_id, q.league, q.commence_time, q.home_team, q.away_team))
        ev.quotes.append(q)
    return sorted(events.values(), key=lambda e: (e.commence_time, e.league))


# --- Cena fair ---------------------------------------------------------------------------


def _market_odds(quotes: list[Quote], bookmaker: str, market: str) -> list[float] | None:
    by_sel = {q.selection: q.odds for q in quotes if q.bookmaker == bookmaker and q.market == market}
    selections = SELECTIONS[market]
    if not all(s in by_sel for s in selections):
        return None
    return [by_sel[s] for s in selections]


def fair_price(
    quotes: list[Quote], market: str, reference: str, method: str, exclude: set[str] | None = None
) -> FairPrice | None:
    """Devig kursów referencyjnych (Pinnacle); bez nich — konsensus pozostałych buków."""
    selections = SELECTIONS[market]
    ref_odds = _market_odds(quotes, reference, market)
    if ref_odds is not None:
        by_method = {m: dict(zip(selections, p, strict=True)) for m, p in devig_all(ref_odds).items()}
        probs = dict(zip(selections, devig(ref_odds, method), strict=True))  # type: ignore[arg-type]
        return FairPrice(probs, reference, method, by_method)

    exclude = exclude or set()
    bookmakers = {q.bookmaker for q in quotes if q.market == market and q.bookmaker not in exclude}
    markets = [m for b in sorted(bookmakers) if (m := _market_odds(quotes, b, market)) is not None]
    if len(markets) < 3:
        return None
    probs = dict(zip(selections, consensus_devig(markets), strict=True))
    return FairPrice(probs, f"consensus({len(markets)})", "multiplicative")


# --- Oferty ------------------------------------------------------------------------------


def build_offers(
    event: Event,
    market: str,
    selection: str,
    manual: list[Quote],
    bookmakers: BookmakersConfig,
    tax_ctx: dict[str, TaxContext],
    use_proxy: bool,
) -> list[Offer]:
    offers: list[Offer] = []
    for q in manual:
        if q.market == market and q.selection == selection:
            bm = bookmakers.bookmakers[q.bookmaker]
            tax = stake_tax_rate(bm, "single", tax_ctx.get(bm.key))
            offers.append(Offer(bm.key, bm.name, q.odds, "manual", False, tax))
    if not use_proxy:
        return offers

    mapped = {proxy: bm for bm in bookmakers.bookmakers.values() for proxy in bm.odds_api_proxies}
    excluded = set(bookmakers.reference_bookmakers)
    generic: list[Quote] = []
    for q in event.quotes:
        if q.market != market or q.selection != selection or q.bookmaker in excluded:
            continue
        if q.bookmaker in mapped:
            bm = mapped[q.bookmaker]
            tax = stake_tax_rate(bm, "single", tax_ctx.get(bm.key))
            offers.append(Offer(bm.key, f"~{bm.name} (proxy {q.bookmaker})", q.odds, f"proxy:{q.bookmaker}", True, tax))
        else:
            generic.append(q)
    if generic:
        best = max(generic, key=lambda q: q.odds)
        offers.append(
            Offer(
                f"proxy:{best.bookmaker}",
                f"PROXY {best.bookmaker}",
                best.odds,
                f"proxy:{best.bookmaker}",
                True,
                bookmakers.proxy_stake_tax,
            )
        )
    return offers


def match_manual(
    manual: list[Quote], events: list[Event], resolvers: dict[str, TeamResolver | None]
) -> tuple[dict[str, list[Quote]], list[Quote]]:
    """Przypisuje ręczne kursy do meczów po (liga, drużyny). Zwraca (event_id -> kursy, niedopasowane)."""
    index = {
        (e.league, team_key(e.home_team, resolvers.get(e.league)), team_key(e.away_team, resolvers.get(e.league))): e
        for e in events
    }
    matched: dict[str, list[Quote]] = defaultdict(list)
    orphans = []
    for q in manual:
        resolver = resolvers.get(q.league)
        ev = index.get((q.league, team_key(q.home_team, resolver), team_key(q.away_team, resolver)))
        if ev is None:
            orphans.append(q)
        else:
            matched[ev.event_id].append(q)
    return matched, orphans


# --- Skan --------------------------------------------------------------------------------


def fit_models(leagues: list[League], strategy: Strategy, warnings: list[str]) -> dict[str, DixonColesForecaster]:
    models = {}
    for league in leagues:
        try:
            results = football_data.load_results(league, strategy.dixon_coles.seasons)
            models[league.key] = fit_dixon_coles(results, league.key, strategy.dixon_coles.xi)
        except Exception as exc:  # brak danych nie może zatrzymać skanu — rynek jest bazą
            warnings.append(f"{league.name}: Dixon-Coles niedostępny ({exc})")
    return models


def run_scan(
    day: date,
    leagues: list[League],
    quotes: list[Quote],
    manual: list[Quote],
    models: dict[str, DixonColesForecaster],
    strategy: Strategy,
    bookmakers: BookmakersConfig,
    tax_ctx: dict[str, TaxContext],
    already_staked: float,
    use_proxy: bool = True,
    now: datetime | None = None,
) -> ScanResult:
    now = now or datetime.now(UTC)
    warnings: list[str] = []
    events = group_events(quotes, day, now)
    # Bez modelu DC (brak danych / --no-dc) dopasowujemy nazwy tylko przez aliasy z configu.
    alias_teams = set(load_team_aliases())
    resolvers: dict[str, TeamResolver | None] = {
        lg.key: TeamResolver(models[lg.key].teams if lg.key in models else alias_teams) for lg in leagues
    }

    unmatched: dict[str, dict[str, list[str]]] = {}
    for lg in leagues:
        resolver = resolvers[lg.key]
        if resolver is None or lg.key not in models:
            continue
        names = [n for e in events if e.league == lg.key for n in (e.home_team, e.away_team)]
        if missing := unresolved(names, resolver):
            unmatched[lg.key] = missing

    manual_by_event, orphans = match_manual(manual, events, resolvers)
    for q in orphans:
        warnings.append(f"Ręczny kurs bez meczu: {q.league} {q.home_team} – {q.away_team} ({q.bookmaker})")

    evaluated: list[Candidate] = []
    ako_legs: dict[str, list[AkoLeg]] = defaultdict(list)
    ako_proxy: dict[str, bool] = defaultdict(bool)
    excluded = set(bookmakers.reference_bookmakers)

    for ev in events:
        model = models.get(ev.league)
        resolver = resolvers.get(ev.league)
        dc = None
        if model is not None and resolver is not None:
            home, away = resolver.resolve(ev.home_team), resolver.resolve(ev.away_team)
            if home and away:
                dc = model.predict(home, away)

        for market, selections in SELECTIONS.items():
            fair = fair_price(ev.quotes, market, strategy.reference_bookmaker, strategy.devig_method, excluded)
            if fair is None:
                continue
            for sel in selections:
                offers = build_offers(
                    ev, market, sel, manual_by_event.get(ev.event_id, []), bookmakers, tax_ctx, use_proxy
                )
                if not offers:
                    continue
                p = fair.probs[sel]
                scored = [(o, evaluate(p, o.odds, o.stake_tax, strategy)) for o in offers]
                best_offer, best_eval = max(scored, key=lambda x: x[1].ev)
                cand = Candidate(ev, market, sel, fair, dc[sel] if dc else None, best_offer, best_eval)
                cand.flags = _flags(cand, strategy)
                evaluated.append(cand)

                for o in offers:
                    if o.bookmaker in bookmakers.bookmakers:
                        label = f"{ev.label}: {SELECTION_LABELS[sel]}"
                        ako_legs[o.bookmaker].append(AkoLeg(ev.event_id, label, o.odds, p, market, sel))
                        ako_proxy[o.bookmaker] |= o.is_proxy

    candidates = sorted((c for c in evaluated if c.evaluation.is_value), key=lambda c: c.evaluation.ev, reverse=True)
    for c in candidates:
        c.stake = kelly_stake(
            c.fair_prob,
            c.evaluation.odds_eff,
            strategy.bankroll_pln,
            strategy.kelly_fraction,
            strategy.max_stake_pct,
            strategy.stake_rounding_pln,
        )
    capped = apply_daily_exposure(
        [c.stake for c in candidates],
        strategy.bankroll_pln,
        strategy.daily_exposure_pct,
        already_staked,
        strategy.stake_rounding_pln,
    )
    for c, stake in zip(candidates, capped, strict=True):
        if stake < c.stake:
            c.flags.append("limit dzienny")
        c.stake = stake

    ako: list[AkoProposal] = []
    for bm_key, legs in ako_legs.items():
        for proposal in build_ako_proposals(legs, bookmakers.bookmakers[bm_key], strategy, tax_ctx.get(bm_key)):
            if ako_proxy[bm_key]:
                proposal.bookmaker = f"{bm_key} (PROXY)"
            ako.append(proposal)

    return ScanResult(day, events, evaluated, candidates, ako, unmatched, 0, None, warnings)


def _flags(c: Candidate, strategy: Strategy) -> list[str]:
    flags = []
    if c.offer.is_proxy:
        flags.append("PROXY")
    if c.fair.source != strategy.reference_bookmaker:
        flags.append(c.fair.source)
    if c.dc_prob is None:
        flags.append("brak DC")
    elif abs(c.diff_pp or 0) > strategy.model_disagreement_pp:
        flags.append("DC≠rynek: do ręcznej weryfikacji")
    return flags


# --- Wyjście -----------------------------------------------------------------------------


def _pct(x: float | None, digits: int = 1) -> str:
    return "—" if x is None else f"{x * 100:.{digits}f}%"


def _pp(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.1f}"


def candidates_table(rows: list[Candidate], title: str) -> Table:
    table = Table(title=title, show_lines=False, header_style="bold")
    for col in (
        "Start",
        "Liga",
        "Mecz",
        "Typ",
        "p_fair",
        "p_DC",
        "Δpp",
        "Buk",
        "Kurs",
        "Kurs eff",
        "EV",
        "Stawka",
        "Flagi",
    ):
        table.add_column(col, overflow="fold")
    for c in rows:
        ev_style = "green" if c.evaluation.is_value else ("yellow" if c.evaluation.ev > 0 else "red")
        table.add_row(
            c.event.commence_time.astimezone(LOCAL_TZ).strftime("%H:%M"),
            c.event.league,
            c.event.label,
            SELECTION_LABELS[c.selection],
            f"{_pct(c.fair_prob)} ({c.fair.method[:4]})",
            _pct(c.dc_prob),
            _pp(c.diff_pp),
            c.offer.label,
            f"{c.evaluation.odds:.2f}",
            f"{c.evaluation.odds_eff:.2f}",
            f"[{ev_style}]{_pct(c.evaluation.ev)}[/]",
            f"{c.stake:.0f} zł" if c.stake else "—",
            ", ".join(c.flags),
        )
    return table


def ako_table(proposals: list[AkoProposal]) -> Table:
    table = Table(title="Propozycje AKO (buki z AKO bez podatku)", header_style="bold")
    for col in ("Buk", "Nogi", "Kurs łączny", "p łączne", "EV", "Stawka ⅛ Kelly"):
        table.add_column(col, overflow="fold")
    for p in proposals:
        legs = "\n".join(f"{leg.label} @ {leg.odds:.2f} (p={leg.prob:.2f})" for leg in p.legs)
        table.add_row(
            p.bookmaker,
            legs,
            f"{p.combined_odds:.2f}",
            _pct(p.combined_prob),
            _pct(p.ev),
            f"{p.stake:.0f} zł",
        )
    return table


def print_result(console: Console, result: ScanResult, show_all: bool) -> None:
    console.rule(f"Value Scanner v0 — {result.day.isoformat()}")
    console.print(f"Mecze pre-match: {len(result.events)}, ocenione selekcje: {len(result.evaluated)}")
    if result.credits_used or result.credits_remaining is not None:
        console.print(
            f"The Odds API: zużyto {result.credits_used} kredytów, pozostało {result.credits_remaining}",
            style="dim",
        )
    for w in result.warnings:
        console.print(f"[yellow]![/] {w}")
    for league, names in result.unmatched_teams.items():
        for name, suggestions in names.items():
            hint = f" (propozycja: {', '.join(suggestions)})" if suggestions else ""
            console.print(
                f"[yellow]![/] {league}: drużyna '{name}' bez dopasowania do football-data{hint} — "
                "dopisz alias w config/team_aliases.yaml"
            )
    if any(c.offer.is_proxy for c in result.evaluated):
        console.print(
            Panel(
                "Kursy oznaczone PROXY pochodzą od bukmacherów z The Odds API, którzy NIE są polskimi "
                "legalnymi bukami. To tylko przybliżenie oferty STS/Fortuna/Betclic/Superbet — przed "
                "zakładem sprawdź kurs u swojego buka (albo wpisz go: manual_odds add).",
                style="yellow",
                title="Uwaga",
            )
        )
    if result.candidates:
        console.print(candidates_table(result.candidates, "Kandydaci (EV ≥ próg, po podatku)"))
    else:
        console.print("[bold]Brak kandydatów spełniających próg EV po podatku.[/]")
    if result.ako:
        console.print(ako_table(result.ako))
    if show_all and result.evaluated:
        rows = sorted(result.evaluated, key=lambda c: (c.event.commence_time, c.event.event_id, c.market))
        console.print(candidates_table(rows, "Wszystkie ocenione selekcje (najlepsza oferta)"))
    console.print("[dim]Prawdopodobieństwa liczy wyłącznie kod (rynek + Dixon-Coles). Tryb: paper trading.[/]")


def to_json(result: ScanResult) -> dict:
    def cand(c: Candidate) -> dict:
        return {
            "event_id": c.event.event_id,
            "league": c.event.league,
            "commence_time": c.event.commence_time.isoformat(),
            "home_team": c.event.home_team,
            "away_team": c.event.away_team,
            "market": c.market,
            "selection": c.selection,
            "fair_prob": c.fair_prob,
            "fair_source": c.fair.source,
            "fair_method": c.fair.method,
            "fair_by_method": {m: p[c.selection] for m, p in c.fair.by_method.items()},
            "dc_prob": c.dc_prob,
            "diff_pp": c.diff_pp,
            "bookmaker": c.offer.bookmaker,
            "bookmaker_label": c.offer.label,
            "source": c.offer.source,
            "is_proxy": c.offer.is_proxy,
            "odds": c.evaluation.odds,
            "stake_tax": c.evaluation.stake_tax,
            "odds_eff": c.evaluation.odds_eff,
            "ev": c.evaluation.ev,
            "required_edge": c.evaluation.required_edge,
            "stake": c.stake,
            "flags": c.flags,
        }

    return {
        "date": result.day.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "event_id": e.event_id,
                "league": e.league,
                "commence_time": e.commence_time.isoformat(),
                "home_team": e.home_team,
                "away_team": e.away_team,
            }
            for e in result.events
        ],
        "candidates": [cand(c) for c in result.candidates],
        "ako": [
            {
                "bookmaker": p.bookmaker,
                "legs": [leg.__dict__ for leg in p.legs],
                "combined_odds": p.combined_odds,
                "combined_prob": p.combined_prob,
                "ev": p.ev,
                "stake": p.stake,
            }
            for p in result.ako
        ],
        "warnings": result.warnings,
        "unmatched_teams": result.unmatched_teams,
    }


def log_to_ledger(con, result: ScanResult, include_proxy: bool, models: dict[str, DixonColesForecaster]) -> int:
    existing = ledger.already_logged(con, result.day)
    count = 0
    for c in result.candidates:
        if c.stake <= 0 or (c.offer.is_proxy and not include_proxy):
            continue
        if (c.event.event_id, c.market, c.selection, c.offer.bookmaker) in existing:
            continue
        model = models.get(c.event.league)
        ledger.log_paper_bet(con, _paper_bet(c, result.day, model))
        count += 1
    for p in result.ako:
        is_proxy = p.bookmaker.endswith("(PROXY)")
        if p.stake <= 0 or (is_proxy and not include_proxy):
            continue
        legs = [_ako_leg_bet(leg, p, result) for leg in p.legs]
        ledger.log_ako_slip(
            con, result.day, p.bookmaker, p.combined_odds, p.combined_prob, p.stake_tax, p.ev, p.stake, is_proxy, legs
        )
        count += 1
    return count


def select_shadow(result: ScanResult, n: int, now: datetime, min_lead_minutes: int = 10) -> list[Candidate]:
    """Selekcje najbliższe progu (najwyższe EV po podatku), które NIE są kandydatami — po jednej na mecz.

    Shadow bets służą wyłącznie do pomiaru CLV (czy ceny miękkich buków / proxy biją zamknięcie Pinnacle).
    Nie liczą się do strategii, ekspozycji ani limitów promocji.
    """
    value_keys = {(c.event.event_id, c.market, c.selection, c.offer.bookmaker) for c in result.candidates}
    cutoff = now + timedelta(minutes=min_lead_minutes)
    best: dict[str, Candidate] = {}
    for c in result.evaluated:
        if c.event.commence_time <= cutoff:
            continue
        if (c.event.event_id, c.market, c.selection, c.offer.bookmaker) in value_keys:
            continue
        cur = best.get(c.event.event_id)
        if cur is None or c.evaluation.ev > cur.evaluation.ev:
            best[c.event.event_id] = c
    return sorted(best.values(), key=lambda c: c.evaluation.ev, reverse=True)[:n]


def log_shadow(con, result: ScanResult, n: int, models: dict[str, DixonColesForecaster], now: datetime) -> int:
    existing = ledger.already_logged(con, result.day)
    count = 0
    for c in select_shadow(result, n, now):
        if (c.event.event_id, c.market, c.selection, c.offer.bookmaker) in existing:
            continue
        bet = _paper_bet(c, result.day, models.get(c.event.league))
        bet.is_shadow, bet.stake = True, 0.0
        bet.flags = ", ".join(filter(None, ["SHADOW", bet.flags]))
        ledger.log_paper_bet(con, bet)
        count += 1
    return count


def _paper_bet(c: Candidate, day: date, model: DixonColesForecaster | None) -> ledger.PaperBet:
    return ledger.PaperBet(
        scan_date=day,
        event_id=c.event.event_id,
        league=c.event.league,
        commence_time=c.event.commence_time,
        home_team=c.event.home_team,
        away_team=c.event.away_team,
        market=c.market,
        selection=c.selection,
        bookmaker=c.offer.bookmaker,
        source=c.offer.source,
        is_proxy=c.offer.is_proxy,
        odds=c.evaluation.odds,
        stake_tax=c.evaluation.stake_tax,
        odds_eff=c.evaluation.odds_eff,
        fair_prob=c.fair_prob,
        fair_method=f"{c.fair.source}:{c.fair.method}",
        ev=c.evaluation.ev,
        stake=c.stake,
        model_prob=c.dc_prob,
        model_version=model.version if model and c.dc_prob is not None else None,
        flags=", ".join(c.flags),
    )


def _ako_leg_bet(leg: AkoLeg, proposal: AkoProposal, result: ScanResult) -> ledger.PaperBet:
    cand = next(
        c
        for c in result.evaluated
        if (c.event.event_id, c.market, c.selection) == (leg.event_id, leg.market, leg.selection)
    )
    bet = _paper_bet(cand, result.day, None)
    bet.bookmaker = proposal.bookmaker.removesuffix(" (PROXY)")
    bet.odds, bet.stake_tax = leg.odds, proposal.stake_tax
    bet.odds_eff = leg.odds * (1 - proposal.stake_tax)
    bet.ev = leg.prob * bet.odds_eff - 1
    return bet


# --- CLI ---------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m betting_analyst.scan",
        description="Value Scanner v0: kandydaci value (pre-match) u polskich bukmacherów, po podatku.",
    )
    parser.add_argument(
        "--date", type=date.fromisoformat, default=datetime.now(LOCAL_TZ).date(), help="YYYY-MM-DD (czas PL)"
    )
    parser.add_argument("--log-paper", action="store_true", help="zapisz kandydatów do ledgera (paper trading)")
    parser.add_argument(
        "--include-proxy", action="store_true", help="z --log-paper zapisuj też kandydatów z kursów PROXY"
    )
    parser.add_argument(
        "--log-shadow",
        type=int,
        metavar="N",
        default=0,
        help="zapisz N selekcji najbliższych progu jako shadow bets (tylko pomiar CLV, poza strategią)",
    )
    parser.add_argument("--from-cache", action="store_true", help="użyj ostatnich odpowiedzi z data/raw/ (0 kredytów)")
    parser.add_argument("--leagues", help="lista kluczy lig, np. ekstraklasa,championship (domyślnie wszystkie)")
    parser.add_argument("--no-dc", action="store_true", help="pomiń Dixon-Coles")
    parser.add_argument("--no-proxy", action="store_true", help="tylko ręczne kursy polskich buków")
    parser.add_argument("--show-all", action="store_true", help="pokaż wszystkie ocenione selekcje")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    console = Console()
    strategy, bookmakers = load_strategy(), load_bookmakers()

    leagues = list(strategy.leagues.values())
    if args.leagues:
        wanted = {k.strip() for k in args.leagues.split(",")}
        leagues = [lg for lg in leagues if lg.key in wanted]

    client = None
    if not args.from_cache:
        if not get_env("ODDS_API_KEY"):
            console.print(Panel(MISSING_KEY_HELP, title="Brak klucza The Odds API", style="yellow"))
            return 2
        client = TheOddsApiClient()

    quotes, used, remaining, fetch_warnings = collect_quotes(leagues, strategy, args.from_cache, client)
    manual = manual_odds.load_manual_quotes(args.date)
    model_warnings: list[str] = []
    models = {} if args.no_dc else fit_models(leagues, strategy, model_warnings)

    con = ledger.connect(args.db)
    tax_ctx = {
        key: TaxContext(period_single_stakes_pln=ledger.period_single_stakes(con, key, args.date))
        for key in bookmakers.bookmakers
    }
    result = run_scan(
        args.date,
        leagues,
        quotes,
        manual,
        models,
        strategy,
        bookmakers,
        tax_ctx,
        already_staked=ledger.staked_on(con, args.date),
        use_proxy=not args.no_proxy,
    )
    result.credits_used, result.credits_remaining = used, remaining
    result.warnings = fetch_warnings + model_warnings + result.warnings

    if not args.from_cache:
        ledger.insert_snapshots(con, quotes)
    ledger.insert_snapshots(con, manual)

    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    scan_file = SCANS_DIR / f"{args.date.isoformat()}.json"
    scan_file.write_text(json.dumps(to_json(result), ensure_ascii=False, indent=1), encoding="utf-8")

    print_result(console, result, args.show_all)
    console.print(f"[dim]Zapisano: {scan_file}[/]")
    if args.log_paper:
        n = log_to_ledger(con, result, args.include_proxy, models)
        console.print(f"[bold green]Zapisano {n} zakładów paper do {args.db}[/]")
        if not args.include_proxy and any(c.offer.is_proxy for c in result.candidates):
            console.print("[dim]Kandydaci z PROXY pominięci (dodaj --include-proxy, by je logować).[/]")
    if args.log_shadow:
        n = log_shadow(con, result, args.log_shadow, models, datetime.now(UTC))
        console.print(f"[bold yellow]Zapisano {n} shadow bets (stawka 0, poza strategią) do {args.db}[/]")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
