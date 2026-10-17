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

# Rynki z linią (STS, ADR 0021): "<rodzaj>_ou_<linia>", np. corners_ou_9.5, home_cards_ou_1.5.
OU_PREFIX_LABELS = {
    "goals": "Gole",
    "corners": "Rogi",
    "home_corners": "Rogi gosp.",
    "away_corners": "Rogi gości",
    "cards": "Kartki",
    "home_cards": "Kartki gosp.",
    "away_cards": "Kartki gości",
    "fouls": "Faule",
    "sot": "Celne strzały",
}


def selections_for(market: str) -> tuple[str, ...]:
    """Selekcje rynku: 1x2, ou25, btts albo dowolny rynek z linią "<rodzaj>_ou_<linia>"."""
    if market in SELECTIONS:
        return SELECTIONS[market]
    if market == "btts":
        return ("yes", "no")
    if "_ou_" in market:
        return ("over", "under")
    raise KeyError(f"Nieznany rynek: {market}")


def ou_line(market: str) -> float | None:
    """Linia rynku over/under (ou25 → 2.5, corners_ou_9.5 → 9.5)."""
    if market == "ou25":
        return 2.5
    if "_ou_" in market:
        return float(market.rsplit("_ou_", 1)[1])
    return None


def market_kind(market: str) -> str:
    """Rodzaj rynku: 1x2 | btts | goals | corners | cards | ... (dla ou25 → goals)."""
    if market == "ou25":
        return "goals"
    if "_ou_" in market:
        return market.rsplit("_ou_", 1)[0]
    return market


def pick_label(market: str, selection: str) -> str:
    """Czytelna etykieta typu, np. "Rogi +9.5", "BTTS tak", "1"."""
    if market == "1x2":
        return SELECTION_LABELS[selection]
    if market == "btts":
        return "BTTS " + ("tak" if selection == "yes" else "nie")
    line = ou_line(market)
    if line is not None:
        name = OU_PREFIX_LABELS.get(market_kind(market), market_kind(market))
        return f"{name} {'+' if selection == 'over' else '-'}{line:g}"
    return f"{market}:{selection}"


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
