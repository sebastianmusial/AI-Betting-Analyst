"""Ręczne kursy polskich bukmacherów (fallback: brak darmowego API dla STS/Betclic).

Plik: data/manual_odds/YYYY-MM-DD.csv, kolumny:
    league,home_team,away_team,bookmaker,market,selection,odds,captured_at
- league: klucz z config/strategy.yaml (ekstraklasa, championship, bundesliga2, eredivisie)
- bookmaker: klucz z config/bookmakers.yaml (sts, fortuna, betclic, superbet)
- market: 1x2 | ou25,  selection: home|draw|away  /  over|under
- captured_at: opcjonalnie (ISO); puste = moment wpisania

CLI:
    uv run python -m betting_analyst.sources.manual_odds template --date 2026-10-17
        → szablon z meczami z ostatniego skanu (puste kursy do uzupełnienia)
    uv run python -m betting_analyst.sources.manual_odds add --date 2026-10-17 \\
        --league ekstraklasa --home "Legia" --away "Lech" --bookmaker sts \\
        --market 1x2 --selection home --odds 2.15
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from betting_analyst.config import MANUAL_ODDS_DIR, SCANS_DIR, load_bookmakers, load_strategy
from betting_analyst.domain import SELECTIONS, Quote

SOURCE = "manual"
COLUMNS = ["league", "home_team", "away_team", "bookmaker", "market", "selection", "odds", "captured_at"]


class PolishOddsProvider(Protocol):
    """Interfejs dla źródeł kursów polskich bukmacherów.

    TODO: adaptery OddsHarvester (OddsPortal) i OddsPapi free (Fortuna, Superbet) — ADR 0009.
    Muszą zwracać Quote z bookmaker = klucz z config/bookmakers.yaml i source = nazwa adaptera.
    """

    name: str

    def fetch(self, day: date, leagues: list[str]) -> list[Quote]: ...


def manual_path(day: date, folder: Path = MANUAL_ODDS_DIR) -> Path:
    return folder / f"{day.isoformat()}.csv"


def validate_row(row: dict) -> None:
    bookmakers = load_bookmakers().bookmakers
    leagues = load_strategy().leagues
    if row["league"] not in leagues:
        raise ValueError(f"Nieznana liga '{row['league']}', dozwolone: {sorted(leagues)}")
    if row["bookmaker"] not in bookmakers:
        raise ValueError(f"Nieznany bukmacher '{row['bookmaker']}', dozwolone: {sorted(bookmakers)}")
    if row["market"] not in SELECTIONS:
        raise ValueError(f"Nieznany rynek '{row['market']}', dozwolone: {sorted(SELECTIONS)}")
    if row["selection"] not in SELECTIONS[row["market"]]:
        raise ValueError(f"Selekcja '{row['selection']}' nie pasuje do rynku {row['market']}")
    if float(row["odds"]) <= 1.0:
        raise ValueError(f"Kurs musi być > 1.0: {row['odds']}")


def load_manual_quotes(day: date, folder: Path = MANUAL_ODDS_DIR) -> list[Quote]:
    """Wczytuje kursy z pliku dnia. Wiersze z pustym kursem (szablon) są pomijane."""
    path = manual_path(day, folder)
    if not path.exists():
        return []
    quotes = []
    with path.open(encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if not (row.get("odds") or "").strip():
                continue
            try:
                validate_row(row)
            except ValueError as exc:
                raise ValueError(f"{path}:{i}: {exc}") from exc
            captured = row.get("captured_at") or ""
            captured_at = (
                datetime.fromisoformat(captured) if captured else datetime.fromtimestamp(path.stat().st_mtime, UTC)
            )
            if captured_at.tzinfo is None:
                captured_at = captured_at.astimezone(UTC)
            quotes.append(
                Quote(
                    event_id="",  # dopasowanie do meczu po (liga, drużyny) w skanerze
                    league=row["league"],
                    commence_time=datetime.combine(day, datetime.min.time(), UTC),
                    home_team=row["home_team"].strip(),
                    away_team=row["away_team"].strip(),
                    bookmaker=row["bookmaker"],
                    market=row["market"],
                    selection=row["selection"],
                    odds=float(row["odds"]),
                    source=SOURCE,
                    captured_at=captured_at,
                )
            )
    return quotes


def append_row(day: date, row: dict, folder: Path = MANUAL_ODDS_DIR) -> Path:
    validate_row(row)
    path = manual_path(day, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in COLUMNS})
    return path


def write_template(day: date, folder: Path = MANUAL_ODDS_DIR, scans_dir: Path = SCANS_DIR) -> Path:
    """Szablon CSV z meczami z ostatniego skanu dnia (data/scans/YYYY-MM-DD.json)."""
    scan_file = scans_dir / f"{day.isoformat()}.json"
    if not scan_file.exists():
        raise FileNotFoundError(f"Brak {scan_file} — najpierw uruchom skan dla {day}")
    events = json.loads(scan_file.read_text(encoding="utf-8"))["events"]
    path = manual_path(day, folder)
    if path.exists():
        raise FileExistsError(f"{path} już istnieje — uzupełnij go albo usuń ręcznie")
    path.parent.mkdir(parents=True, exist_ok=True)
    bookmakers = list(load_bookmakers().bookmakers)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for ev in events:
            for bm in bookmakers:
                for market, selections in SELECTIONS.items():
                    for sel in selections:
                        writer.writerow(
                            {
                                "league": ev["league"],
                                "home_team": ev["home_team"],
                                "away_team": ev["away_team"],
                                "bookmaker": bm,
                                "market": market,
                                "selection": sel,
                                "odds": "",
                                "captured_at": "",
                            }
                        )
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="manual_odds", description="Ręczne kursy polskich bukmacherów")
    sub = parser.add_subparsers(dest="cmd", required=True)

    tpl = sub.add_parser("template", help="Szablon CSV z meczami z ostatniego skanu")
    tpl.add_argument("--date", type=date.fromisoformat, default=date.today())

    add = sub.add_parser("add", help="Dopisz jeden kurs")
    add.add_argument("--date", type=date.fromisoformat, default=date.today())
    add.add_argument("--league", required=True)
    add.add_argument("--home", required=True)
    add.add_argument("--away", required=True)
    add.add_argument("--bookmaker", required=True)
    add.add_argument("--market", required=True, choices=sorted(SELECTIONS))
    add.add_argument("--selection", required=True)
    add.add_argument("--odds", required=True, type=float)

    args = parser.parse_args(argv)
    if args.cmd == "template":
        print(f"Zapisano szablon: {write_template(args.date)}")
    else:
        row = {
            "league": args.league,
            "home_team": args.home,
            "away_team": args.away,
            "bookmaker": args.bookmaker,
            "market": args.market,
            "selection": args.selection,
            "odds": args.odds,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        print(f"Dopisano do: {append_row(args.date, row)}")


if __name__ == "__main__":
    main()
