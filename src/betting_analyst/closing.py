"""Snapshot kursów tuż przed meczem → zdewigowane zamknięcie Pinnacle → CLV w ledgerze.

    uv run python -m betting_analyst.closing [--minutes-before 20] [--all-open]

Uruchamiaj kilka–kilkanaście minut przed startem meczów z otwartymi zakładami paper
(np. co 15 min z launchd). Kredyty zużywa tylko wtedy, gdy w oknie są mecze z zakładami:
2 kredyty (h2h + totals) na ligę. Po rozpoczęciu meczu The Odds API zwraca kursy live,
więc snapshot robimy wyłącznie dla meczów, które jeszcze się nie zaczęły.
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

from betting_analyst import ledger
from betting_analyst.config import DB_PATH, get_env, load_bookmakers, load_strategy
from betting_analyst.domain import SELECTIONS
from betting_analyst.scan import fair_price
from betting_analyst.sources.the_odds_api import MISSING_KEY_HELP, TheOddsApiClient, parse_events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m betting_analyst.closing",
        description="Snapshot kursów zamknięcia (Pinnacle, devig) i przeliczenie CLV zakładów paper.",
    )
    parser.add_argument("--minutes-before", type=int, default=20, help="okno: mecze startujące w ciągu N minut")
    parser.add_argument("--all-open", action="store_true", help="wszystkie przyszłe mecze z otwartymi zakładami")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    console = Console()
    strategy, bookmakers = load_strategy(), load_bookmakers()

    con = ledger.connect(args.db)
    now = datetime.now(UTC)
    until = now + (timedelta(days=30) if args.all_open else timedelta(minutes=args.minutes_before))
    pending = ledger.open_bets_for_closing(con, now, until)
    if pending.empty:
        console.print("Brak otwartych zakładów z meczem w oknie — nic do zrobienia (0 kredytów).")
        return 0

    if not get_env("ODDS_API_KEY"):
        console.print(Panel(MISSING_KEY_HELP, title="Brak klucza The Odds API", style="yellow"))
        return 2

    client = TheOddsApiClient()
    wanted_events = set(pending["event_id"])
    table = Table(title="Zamknięcie (fair Pinnacle) i CLV", header_style="bold")
    for col in ("Mecz", "Rynek", "Źródło fair", "Zaktualizowane zakłady"):
        table.add_column(col)

    total = 0
    for league_key in sorted(set(pending["league"])):
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
