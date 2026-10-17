"""Wspólne typy domenowe: rynki, selekcje, notowania kursów."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Market = Literal["1x2", "ou25"]
Selection = Literal["home", "draw", "away", "over", "under"]

SELECTIONS: dict[str, tuple[str, ...]] = {
    "1x2": ("home", "draw", "away"),
    "ou25": ("over", "under"),
}

SELECTION_LABELS = {"home": "1", "draw": "X", "away": "2", "over": "O2.5", "under": "U2.5"}


@dataclass(frozen=True)
class Quote:
    """Pojedynczy kurs: jeden bukmacher, jeden mecz, jedna selekcja."""

    event_id: str
    league: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmaker: str
    market: str
    selection: str
    odds: float
    source: str
    captured_at: datetime
