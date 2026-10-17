"""Rejestr w DuckDB (data/betting.duckdb): snapshoty kursów, zakłady paper, CLV (ADR 0008, 0015).

CLV liczymy względem zdewigowanego kursu zamknięcia Pinnacle:
    closing_fair_odds = 1 / p_fair_closing
    clv_log = ln(odds_taken / closing_fair_odds)
    clv_pct = odds_taken / closing_fair_odds − 1        (główny KPI, kurs brutto)
    clv_eff_pct = odds_eff / closing_fair_odds − 1      (po podatku — czy realnie bijemy rynek)
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from betting_analyst.config import DB_PATH
from betting_analyst.domain import Quote

SCHEMA = """
CREATE TABLE IF NOT EXISTS odds_snapshots (
    captured_at   TIMESTAMPTZ NOT NULL,
    source        VARCHAR NOT NULL,
    event_id      VARCHAR,
    league        VARCHAR NOT NULL,
    commence_time TIMESTAMPTZ,
    home_team     VARCHAR NOT NULL,
    away_team     VARCHAR NOT NULL,
    bookmaker     VARCHAR NOT NULL,
    market        VARCHAR NOT NULL,
    selection     VARCHAR NOT NULL,
    odds          DOUBLE NOT NULL,
    is_closing    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS paper_bets (
    bet_id              VARCHAR PRIMARY KEY,
    placed_at           TIMESTAMPTZ NOT NULL,
    scan_date           DATE NOT NULL,
    bet_type            VARCHAR NOT NULL,          -- single | ako_leg
    ako_id              VARCHAR,
    event_id            VARCHAR NOT NULL,
    league              VARCHAR NOT NULL,
    commence_time       TIMESTAMPTZ NOT NULL,
    home_team           VARCHAR NOT NULL,
    away_team           VARCHAR NOT NULL,
    market              VARCHAR NOT NULL,
    selection           VARCHAR NOT NULL,
    bookmaker           VARCHAR NOT NULL,
    source              VARCHAR NOT NULL,          -- manual | proxy:<klucz The Odds API>
    is_proxy            BOOLEAN NOT NULL,
    odds                DOUBLE NOT NULL,
    stake_tax           DOUBLE NOT NULL,
    odds_eff            DOUBLE NOT NULL,
    fair_prob           DOUBLE NOT NULL,
    fair_method         VARCHAR NOT NULL,
    model_prob          DOUBLE,
    model_version       VARCHAR,
    ev                  DOUBLE NOT NULL,
    stake               DOUBLE NOT NULL,
    flags               VARCHAR,
    is_shadow           BOOLEAN NOT NULL DEFAULT FALSE,  -- shadow: tylko pomiar CLV, poza strategią
    closing_captured_at TIMESTAMPTZ,
    closing_fair_prob   DOUBLE,
    closing_fair_odds   DOUBLE,
    clv_log             DOUBLE,
    clv_pct             DOUBLE,
    clv_eff_pct         DOUBLE,
    status              VARCHAR NOT NULL DEFAULT 'open',  -- open | vetoed | settled
    result              VARCHAR,
    pnl                 DOUBLE,
    veto_reason         VARCHAR,
    veto_url            VARCHAR,
    vetoed_at           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ako_slips (
    ako_id        VARCHAR PRIMARY KEY,
    placed_at     TIMESTAMPTZ NOT NULL,
    scan_date     DATE NOT NULL,
    bookmaker     VARCHAR NOT NULL,
    n_legs        INTEGER NOT NULL,
    combined_odds DOUBLE NOT NULL,
    combined_prob DOUBLE NOT NULL,
    stake_tax     DOUBLE NOT NULL,
    ev            DOUBLE NOT NULL,
    stake         DOUBLE NOT NULL,
    is_proxy      BOOLEAN NOT NULL
);
"""


def connect(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("SET TimeZone = 'UTC'")
    con.execute(SCHEMA)
    # Migracja baz sprzed kolumny is_shadow.
    con.execute("ALTER TABLE paper_bets ADD COLUMN IF NOT EXISTS is_shadow BOOLEAN DEFAULT FALSE")
    return con


def clv(odds_taken: float, closing_fair_prob: float) -> tuple[float, float]:
    """(clv_log, clv_pct) względem kursu fair zamknięcia."""
    closing_fair_odds = 1.0 / closing_fair_prob
    ratio = odds_taken / closing_fair_odds
    return math.log(ratio), ratio - 1.0


def insert_snapshots(con: duckdb.DuckDBPyConnection, quotes: Iterable[Quote], is_closing: bool = False) -> int:
    rows = [
        (
            q.captured_at,
            q.source,
            q.event_id or None,
            q.league,
            q.commence_time,
            q.home_team,
            q.away_team,
            q.bookmaker,
            q.market,
            q.selection,
            q.odds,
            is_closing,
        )
        for q in quotes
    ]
    if not rows:
        return 0
    # Deduplikacja: ten sam kurs z tym samym captured_at (np. ponowny skan z ręcznymi kursami) tylko raz.
    con.execute("CREATE OR REPLACE TEMP TABLE _new_snapshots AS SELECT * FROM odds_snapshots LIMIT 0")
    con.executemany("INSERT INTO _new_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    inserted = con.execute(
        """
        INSERT INTO odds_snapshots
        SELECT DISTINCT n.* FROM _new_snapshots n
        WHERE NOT EXISTS (
            SELECT 1 FROM odds_snapshots o
            WHERE o.captured_at = n.captured_at AND o.source = n.source AND o.bookmaker = n.bookmaker
              AND o.league = n.league AND o.home_team = n.home_team AND o.away_team = n.away_team
              AND o.market = n.market AND o.selection = n.selection AND o.is_closing = n.is_closing
        )
        """
    ).fetchone()
    con.execute("DROP TABLE _new_snapshots")
    return int(inserted[0]) if inserted else 0


@dataclass
class PaperBet:
    scan_date: date
    event_id: str
    league: str
    commence_time: datetime
    home_team: str
    away_team: str
    market: str
    selection: str
    bookmaker: str
    source: str
    is_proxy: bool
    odds: float
    stake_tax: float
    odds_eff: float
    fair_prob: float
    fair_method: str
    ev: float
    stake: float
    model_prob: float | None = None
    model_version: str | None = None
    flags: str = ""
    bet_type: str = "single"
    ako_id: str | None = None
    is_shadow: bool = False
    bet_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    placed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def log_paper_bet(con: duckdb.DuckDBPyConnection, bet: PaperBet) -> str:
    data = asdict(bet)
    cols = ", ".join(data)
    placeholders = ", ".join("?" for _ in data)
    con.execute(f"INSERT INTO paper_bets ({cols}) VALUES ({placeholders})", list(data.values()))
    return bet.bet_id


def log_ako_slip(
    con: duckdb.DuckDBPyConnection,
    scan_date: date,
    bookmaker: str,
    combined_odds: float,
    combined_prob: float,
    stake_tax: float,
    ev: float,
    stake: float,
    is_proxy: bool,
    legs: list[PaperBet],
) -> str:
    ako_id = "ako-" + uuid.uuid4().hex[:10]
    con.execute(
        "INSERT INTO ako_slips VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ako_id,
            datetime.now(UTC),
            scan_date,
            bookmaker,
            len(legs),
            combined_odds,
            combined_prob,
            stake_tax,
            ev,
            stake,
            is_proxy,
        ],
    )
    for leg in legs:
        leg.bet_type, leg.ako_id, leg.stake = "ako_leg", ako_id, 0.0
        log_paper_bet(con, leg)
    return ako_id


def already_logged(con: duckdb.DuckDBPyConnection, scan_date: date) -> set[tuple[str, str, str, str]]:
    """(event_id, market, selection, bookmaker) singli zapisanych już dla dnia — bez duplikatów."""
    rows = con.execute(
        "SELECT event_id, market, selection, bookmaker FROM paper_bets WHERE scan_date = ? AND bet_type = 'single'",
        [scan_date],
    ).fetchall()
    return {tuple(r) for r in rows}


def staked_on(con: duckdb.DuckDBPyConnection, scan_date: date) -> float:
    """Suma stawek (single + AKO) zapisanych dla dnia — do limitu dziennej ekspozycji (bez zawetowanych)."""
    singles = con.execute(
        "SELECT COALESCE(SUM(stake), 0) FROM paper_bets "
        "WHERE scan_date = ? AND bet_type = 'single' AND status <> 'vetoed' AND NOT is_shadow",
        [scan_date],
    ).fetchone()[0]
    akos = con.execute("SELECT COALESCE(SUM(stake), 0) FROM ako_slips WHERE scan_date = ?", [scan_date]).fetchone()[0]
    return float(singles) + float(akos)


def period_single_stakes(con: duckdb.DuckDBPyConnection, bookmaker: str, day: date) -> float:
    """Suma stawek single u buka w bieżącym miesiącu (limit promocji bez podatku)."""
    start = day.replace(day=1)
    return float(
        con.execute(
            "SELECT COALESCE(SUM(stake), 0) FROM paper_bets "
            "WHERE bookmaker = ? AND bet_type = 'single' AND NOT is_shadow AND scan_date >= ? AND scan_date <= ?",
            [bookmaker, start, day],
        ).fetchone()[0]
    )


def open_bets_for_closing(con: duckdb.DuckDBPyConnection, now: datetime, until: datetime) -> pd.DataFrame:
    """Mecze z otwartymi (i zawetowanymi — CLV wet też mierzymy, ADR 0012) zakładami w (now, until]."""
    return con.execute(
        "SELECT DISTINCT event_id, league, commence_time, home_team, away_team FROM paper_bets "
        "WHERE status IN ('open', 'vetoed') AND commence_time > ? AND commence_time <= ?",
        [now, until],
    ).df()


def record_closing(
    con: duckdb.DuckDBPyConnection,
    event_id: str,
    market: str,
    fair_probs: dict[str, float],
    captured_at: datetime,
) -> int:
    """Zapisuje fair zamknięcia i CLV dla zakładów na dany rynek. Późniejszy snapshot nadpisuje wcześniejszy."""
    updated = 0
    for selection, prob in fair_probs.items():
        fair_odds = 1.0 / prob
        result = con.execute(
            """
            UPDATE paper_bets SET
                closing_captured_at = ?,
                closing_fair_prob = ?,
                closing_fair_odds = ?,
                clv_log = ln(odds / ?),
                clv_pct = odds / ? - 1,
                clv_eff_pct = odds_eff / ? - 1
            WHERE event_id = ? AND market = ? AND selection = ?
              AND (closing_captured_at IS NULL OR closing_captured_at <= ?)
            RETURNING bet_id
            """,
            [captured_at, prob, fair_odds, fair_odds, fair_odds, fair_odds, event_id, market, selection, captured_at],
        ).fetchall()
        updated += len(result)
    return updated


def clv_report(
    con: duckdb.DuckDBPyConnection, group_by: str | None = None, shadow: bool | None = False
) -> pd.DataFrame:
    """Agregaty CLV. group_by: league | market | bookmaker | is_proxy | bet_type | source | status | is_shadow.

    shadow=False (domyślnie): tylko zakłady strategii; True: tylko shadow; None: wszystkie.
    """
    allowed = {None, "league", "market", "bookmaker", "is_proxy", "bet_type", "source", "status", "is_shadow"}
    if group_by not in allowed:
        raise ValueError(f"group_by musi być jednym z {allowed}")
    key = f"{group_by}," if group_by else ""
    group = f"GROUP BY {group_by} ORDER BY {group_by}" if group_by else ""
    where = "" if shadow is None else f"WHERE is_shadow = {'TRUE' if shadow else 'FALSE'}"
    return con.execute(
        f"""
        SELECT {key}
            COUNT(*) AS bets,
            COUNT(clv_pct) AS with_closing,
            AVG(clv_pct) AS avg_clv_pct,
            AVG(clv_log) AS avg_clv_log,
            AVG(clv_eff_pct) AS avg_clv_eff_pct,
            AVG(CASE WHEN clv_pct > 0 THEN 1.0 ELSE 0.0 END) FILTER (WHERE clv_pct IS NOT NULL) AS share_positive,
            AVG(ev) AS avg_ev_at_bet,
            SUM(stake) AS total_stake
        FROM paper_bets
        {where}
        {group}
        """
    ).df()


def veto(
    con: duckdb.DuckDBPyConnection,
    scan_date: date,
    event_id: str,
    market: str,
    selection: str,
    reason: str,
    url: str,
) -> int:
    """Oznacza zakłady jako zawetowane (LLM/człowiek, z cytatem i URL źródła — ADR 0012).

    Zakład zostaje w rejestrze: CLV wet liczymy osobno, żeby ocenić, czy weta pomagają.
    """
    if not reason.strip() or not url.strip():
        raise ValueError("Weto wymaga powodu (cytatu) i URL źródła")
    rows = con.execute(
        """
        UPDATE paper_bets SET status = 'vetoed', veto_reason = ?, veto_url = ?, vetoed_at = ?
        WHERE scan_date = ? AND event_id = ? AND market = ? AND selection = ? AND status = 'open'
        RETURNING bet_id
        """,
        [reason, url, datetime.now(UTC), scan_date, event_id, market, selection],
    ).fetchall()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m betting_analyst.ledger", description="Operacje na rejestrze.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("veto", help="zawetuj kandydata (zakład zostaje w rejestrze ze statusem vetoed)")
    v.add_argument("--date", type=date.fromisoformat, required=True)
    v.add_argument("--event-id", required=True)
    v.add_argument("--market", required=True, choices=["1x2", "ou25"])
    v.add_argument("--selection", required=True, choices=["home", "draw", "away", "over", "under"])
    v.add_argument("--reason", required=True, help="cytat ze źródła + krótkie uzasadnienie")
    v.add_argument("--url", required=True, help="URL źródła")
    v.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    con = connect(args.db)
    n = veto(con, args.date, args.event_id, args.market, args.selection, args.reason, args.url)
    con.close()
    print(f"Zawetowano {n} zakład(ów).")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
