"""Snapshot kursów tuż przed meczem → zdewigowane zamknięcie Pinnacle → CLV w ledgerze.

    uv run python -m betting_analyst.closing [--minutes-before 20] [--all-open]

Uruchamiaj kilka–kilkanaście minut przed startem meczów z otwartymi zakładami paper
(np. co 15 min z launchd). Kredyty zużywa tylko wtedy, gdy w oknie są mecze z zakładami:
2 kredyty (h2h + totals) na ligę. Po rozpoczęciu meczu The Odds API zwraca kursy live,
więc snapshot robimy wyłącznie dla meczów, które jeszcze się nie zaczęły.
Limit dzienny i rezerwa kredytów: config/strategy.yaml → odds_api, log zużycia: data/logs/ (budget.py, ADR 0022).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from betting_analyst import budget, ledger
from betting_analyst.config import DB_PATH, get_env, load_bookmakers, load_strategy
from betting_analyst.domain import SELECTIONS, selections_for
from betting_analyst.models.devig import devig
from betting_analyst.scan import fair_price
from betting_analyst.sources import sts
from betting_analyst.sources.the_odds_api import MISSING_KEY_HELP, TheOddsApiClient, parse_events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m betting_analyst.closing",
        description="Snapshot kursów zamknięcia (Pinnacle, devig) i przeliczenie CLV zakładów paper.",
    )
    parser.add_argument("--minutes-before", type=int, default=20, help="okno: mecze startujące w ciągu N minut")
    parser.add_argument("--all-open", action="store_true", help="wszystkie przyszłe mecze z otwartymi zakładami")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--usage-log", type=Path, default=budget.USAGE_LOG, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _leagues_within_budget(pending, strategy, usage_log: Path, console: Console) -> list[str]:
    """Ligi do odpytania w limicie kredytów (budget.py); priorytet: najwcześniejszy start meczu."""
    first_kickoff = pending.groupby("league")["commence_time"].min().sort_values()
    leagues = list(first_kickoff.index)
    cost = len(strategy.odds_api.regions) * len(strategy.odds_api.markets)
    today = datetime.now(budget.LOCAL_TZ).date()
    spent = budget.spent_on(today, "closing", usage_log)
    plan = budget.plan_closing(
        leagues,
        cost,
        spent,
        strategy.odds_api.daily_closing_credits,
        budget.last_remaining(usage_log),
        strategy.odds_api.reserve_credits,
    )
    for league_key in plan.skipped:
        console.print(f"[yellow]Budżet kredytów: pomijam zamknięcie {league_key} — {plan.reason}[/]")
        budget.log_usage(usage_log, "closing", strategy.leagues[league_key].odds_api_key, 0, None, "skipped:budget")
    console.print(
        f"[dim]Budżet zamknięć dziś: zużyto {spent}/{strategy.odds_api.daily_closing_credits} kredytów, "
        f"plan: {len(plan.allowed)} lig × {cost}[/]"
    )
    return plan.allowed


def close_sts_model_bets(con, now: datetime, until: datetime, console: Console) -> int:
    """Zamknięcie STS dla zakładów wycenianych modelem (rogi, kartki, inne linie goli — ADR 0021).

    Pinnacle nie ma tych rynków, więc CLV liczymy względem zdewigowanego (multiplicative)
    zamknięcia samego STS. To słabsza miara niż CLV vs Pinnacle — raportowana osobno.
    """
    pending = ledger.open_sts_model_bets(con, now, until)
    if pending.empty:
        return 0
    fixtures = [
        sts.StsFixture(
            str(row.event_id).removeprefix("sts:"), 0, row.league, row.home_team, row.away_team,
            row.commence_time.to_pydatetime() if hasattr(row.commence_time, "to_pydatetime") else row.commence_time,
        )
        for row in pending.itertuples()
    ]  # fmt: skip
    bodies, captured_at = sts.fetch_snapshots([sts.fixture_topic(f.fixture_id) for f in fixtures])
    market_map = sts.load_market_map()
    total = 0
    for f in fixtures:
        body = bodies.get(sts.fixture_topic(f.fixture_id))
        if body is None:
            console.print(f"[yellow]STS: brak oferty zamknięcia dla {f.home_team} – {f.away_team}[/]")
            continue
        quotes = sts.parse_fixture_quotes(body, f, captured_at, market_map)
        ledger.insert_snapshots(con, quotes, is_closing=True)
        by_market: dict[str, dict[str, float]] = {}
        for q in quotes:
            by_market.setdefault(q.market, {})[q.selection] = q.odds
        for market, odds in by_market.items():
            sels = selections_for(market)
            if not all(s in odds for s in sels):
                continue
            probs = dict(zip(sels, devig([odds[s] for s in sels], "multiplicative"), strict=True))
            total += ledger.record_closing(con, f.event_id, market, probs, captured_at, model_only=True)
    console.print(f"[dim]Zamknięcie STS (rynki model-only): zaktualizowano CLV dla {total} zakładów[/]")
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    console = Console()
    strategy, bookmakers = load_strategy(), load_bookmakers()

    con = ledger.connect(args.db)
    now = datetime.now(UTC)
    until = now + (timedelta(days=30) if args.all_open else timedelta(minutes=args.minutes_before))
    pending = ledger.open_bets_for_closing(con, now, until)
    total_sts = close_sts_model_bets(con, now, until, console)
    if pending.empty:
        msg = "Brak otwartych zakładów (rynek/Pinnacle) z meczem w oknie — 0 kredytów."
        console.print(msg if not total_sts else f"{msg} Zamknięcie STS: {total_sts} zakładów.")
        con.close()
        return 0

    if not get_env("ODDS_API_KEY"):
        console.print(Panel(MISSING_KEY_HELP, title="Brak klucza The Odds API", style="yellow"))
        return 2

    client = TheOddsApiClient(usage_log=args.usage_log, job="closing")
    wanted_events = set(pending["event_id"])
    leagues = _leagues_within_budget(pending, strategy, args.usage_log, console)
    table = Table(title="Zamknięcie (fair Pinnacle) i CLV", header_style="bold")
    for col in ("Mecz", "Rynek", "Źródło fair", "Zaktualizowane zakłady"):
        table.add_column(col)

    total = 0
    for league_key in leagues:
        league = strategy.leagues[league_key]
        result = client.fetch_odds(league.odds_api_key, strategy.odds_api.regions, strategy.odds_api.markets)
        quotes = [q for q in parse_events(result.events, league_key, result.fetched_at) if q.event_id in wanted_events]
        quotes = [q for q in quotes if q.commence_time > result.fetched_at]  # tylko pre-match
        ledger.insert_snapshots(con, quotes, is_closing=True)
        if result.credits:
            console.print(
                f"[dim]{league.name}: kredyty zużyte {result.credits.last}, pozostało {result.credits.remaining}[/]"
            )

        for event_id in sorted({q.event_id for q in quotes}):
            event_quotes = [q for q in quotes if q.event_id == event_id]
            label = f"{event_quotes[0].home_team} – {event_quotes[0].away_team}"
            for market in SELECTIONS:
                fair = fair_price(
                    event_quotes,
                    market,
                    strategy.reference_bookmaker,
                    strategy.devig_method,
                    set(bookmakers.reference_bookmakers),
                )
                if fair is None:
                    continue
                n = ledger.record_closing(con, event_id, market, fair.probs, result.fetched_at)
                total += n
                if n:
                    table.add_row(label, market, f"{fair.source}:{fair.method}", str(n))

    console.print(table)
    console.print(f"Zaktualizowano CLV dla {total} zakładów. Raport: uv run python -m betting_analyst.report")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
