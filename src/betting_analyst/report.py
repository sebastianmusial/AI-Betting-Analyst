"""Raport CLV zakładów paper (główny KPI: CLV vs zdewigowane zamknięcie Pinnacle).

uv run python -m betting_analyst.report [--last 20]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from betting_analyst import ledger
from betting_analyst.config import DB_PATH


def _fmt(value: object, pct: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if pct:
        return f"{float(value) * 100:+.2f}%"
    if isinstance(value, float):
        return f"{value:.4f}" if abs(value) < 1 else f"{value:.2f}"
    return str(value)


def df_table(df: pd.DataFrame, title: str, pct_cols: set[str]) -> Table:
    table = Table(title=title, header_style="bold")
    for col in df.columns:
        table.add_column(col)
    for row in df.itertuples(index=False):
        table.add_row(*(_fmt(v, col in pct_cols) for col, v in zip(df.columns, row, strict=True)))
    return table


PCT_COLS = {"avg_clv_pct", "avg_clv_eff_pct", "share_positive", "avg_ev_at_bet", "clv_pct", "clv_eff_pct", "ev"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m betting_analyst.report", description="Raport CLV (paper).")
    parser.add_argument("--last", type=int, default=20, help="ile ostatnich zakładów pokazać")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    console = Console()
    con = ledger.connect(args.db)
    overall = ledger.clv_report(con)
    shadow = ledger.clv_report(con, shadow=True)
    n_strategy, n_shadow = int(overall["bets"].iloc[0]), int(shadow["bets"].iloc[0])
    if n_strategy == 0 and n_shadow == 0:
        console.print("Ledger jest pusty. Najpierw: uv run python -m betting_analyst.scan --log-paper")
        return 0

    console.rule("Raport CLV — paper trading (strategia)")
    if n_strategy:
        console.print(df_table(overall, "Łącznie", PCT_COLS))
        for key in ("league", "market", "bookmaker", "is_proxy", "status"):
            console.print(df_table(ledger.clv_report(con, key), f"Wg {key}", PCT_COLS))
    else:
        console.print("Brak zakładów strategii (żaden kandydat nie przeszedł progu EV po podatku).")
    if n_shadow:
        console.rule("Shadow bets — tylko pomiar CLV, poza strategią")
        console.print(df_table(shadow, "Shadow łącznie", PCT_COLS))
        console.print(df_table(ledger.clv_report(con, "market", shadow=True), "Shadow wg market", PCT_COLS))

    last = con.execute(
        """
        SELECT CAST(scan_date AS VARCHAR) AS scan_date, league, home_team || ' – ' || away_team AS match,
               market, selection, bookmaker, is_proxy, odds, odds_eff, ev,
               closing_fair_odds, clv_pct, clv_eff_pct, stake, bet_type, is_shadow
        FROM paper_bets ORDER BY placed_at DESC LIMIT ?
        """,
        [args.last],
    ).df()
    console.print(df_table(last, f"Ostatnie {args.last} zakładów", PCT_COLS))
    console.print(
        "[dim]clv_pct = kurs wzięty / fair zamknięcia − 1 (brutto); clv_eff_pct = po podatku. "
        "Wnioski dopiero po ≥300 zakładach (ADR 0001).[/]"
    )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
