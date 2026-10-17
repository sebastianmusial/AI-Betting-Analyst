"""Budżet kredytów The Odds API: log zużycia i limit dzienny dla snapshotów zamknięcia.

Darmowy plan: 500 kredytów/mies. Poranny skan ≈ 8 kredytów (4 ligi × 2 rynki), zamknięcie
≈ 2 kredyty na ligę z otwartymi zakładami w oknie. Zamknięcie odpalane co 15 min z launchd
mogłoby po cichu zjeść miesięczny limit, dlatego:

- każde zapytanie do API trafia do data/logs/odds_api_usage.jsonl (kredyty z nagłówków),
- zamknięcie ma limit dzienny (`odds_api.daily_closing_credits`) i rezerwę
  (`odds_api.reserve_credits`): poniżej rezerwy pozostałych kredytów nie robimy zamknięć,
  żeby został budżet na poranne skany.

Pominięta liga = brak CLV vs Pinnacle dla jej zakładów (zakład zostaje w ledgerze bez zamknięcia).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from betting_analyst.config import LOGS_DIR

USAGE_LOG = LOGS_DIR / "odds_api_usage.jsonl"
LOCAL_TZ = ZoneInfo("Europe/Warsaw")


def log_usage(
    path: Path,
    job: str,
    sport_key: str,
    credits_last: int | None,
    remaining: int | None,
    status: int | str | None = None,
    now: datetime | None = None,
) -> None:
    """Dopisuje wpis do logu zużycia (JSON Lines, bez klucza API)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": (now or datetime.now(UTC)).isoformat(),
        "job": job,
        "sport_key": sport_key,
        "credits": credits_last,
        "remaining": remaining,
        "status": status,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_usage(path: Path = USAGE_LOG) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # uszkodzona linia nie blokuje budżetu
    return entries


def spent_on(day: date, job: str | None = None, path: Path = USAGE_LOG) -> int:
    """Kredyty zużyte danego dnia (czas PL), opcjonalnie tylko przez dane zadanie."""
    total = 0
    for e in read_usage(path):
        if job is not None and e.get("job") != job:
            continue
        if datetime.fromisoformat(e["ts"]).astimezone(LOCAL_TZ).date() == day:
            total += int(e.get("credits") or 0)
    return total


def last_remaining(path: Path = USAGE_LOG) -> int | None:
    """Ostatnia znana liczba pozostałych kredytów (nagłówek x-requests-remaining)."""
    for e in reversed(read_usage(path)):
        if e.get("remaining") is not None:
            return int(e["remaining"])
    return None


@dataclass(frozen=True)
class ClosingPlan:
    allowed: list[str]
    skipped: list[str]
    reason: str | None = None


def plan_closing(
    leagues: list[str],
    cost_per_league: int,
    spent_today: int,
    daily_limit: int,
    remaining: int | None,
    reserve: int,
) -> ClosingPlan:
    """Które ligi możemy odpytać (kolejność wejściowa = priorytet, np. najbliższy start meczu).

    Liga wchodzi, jeśli mieści się w limicie dziennym i nie zejdziemy poniżej rezerwy.
    """
    allowed: list[str] = []
    skipped: list[str] = []
    reason = None
    budget_day = daily_limit - spent_today
    budget_month = None if remaining is None else remaining - reserve
    for league in leagues:
        if cost_per_league > budget_day:
            skipped.append(league)
            reason = f"limit dzienny zamknięć {daily_limit} kredytów (zużyto {spent_today})"
            continue
        if budget_month is not None and cost_per_league > budget_month:
            skipped.append(league)
            reason = f"rezerwa {reserve} kredytów (pozostało {remaining})"
            continue
        allowed.append(league)
        budget_day -= cost_per_league
        if budget_month is not None:
            budget_month -= cost_per_league
    return ClosingPlan(allowed, skipped, reason)
