from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from betting_analyst.config import load_bookmakers, load_strategy


@pytest.fixture
def strategy():
    return load_strategy()


@pytest.fixture
def bookmakers():
    return load_bookmakers()


KICKOFF = datetime(2026, 10, 17, 16, 30, tzinfo=UTC)  # 18:30 czasu PL


def _bookmaker(key: str, h2h: tuple[float, float, float], totals: tuple[float, float] | None = None) -> dict:
    markets = [
        {
            "key": "h2h",
            "outcomes": [
                {"name": "Legia Warsaw", "price": h2h[0]},
                {"name": "Lech Poznan", "price": h2h[2]},
                {"name": "Draw", "price": h2h[1]},
            ],
        }
    ]
    if totals:
        markets.append(
            {
                "key": "totals",
                "outcomes": [
                    {"name": "Over", "price": totals[0], "point": 2.5},
                    {"name": "Under", "price": totals[1], "point": 2.5},
                ],
            }
        )
    return {"key": key, "title": key, "last_update": "2026-10-17T08:00:00Z", "markets": markets}


@pytest.fixture
def odds_api_events() -> list[dict]:
    """Odpowiedź The Odds API: jeden mecz Ekstraklasy dziś, jeden jutro."""
    today = {
        "id": "evt1",
        "sport_key": "soccer_poland_ekstraklasa",
        "commence_time": KICKOFF.isoformat().replace("+00:00", "Z"),
        "home_team": "Legia Warsaw",
        "away_team": "Lech Poznan",
        "bookmakers": [
            _bookmaker("pinnacle", (2.20, 3.50, 3.40), (1.95, 1.95)),
            _bookmaker("unibet_eu", (2.15, 3.40, 3.30), (1.90, 1.90)),
            _bookmaker("marathonbet", (2.45, 3.30, 3.10), (2.02, 1.80)),
        ],
    }
    tomorrow = {**today, "id": "evt2", "commence_time": (KICKOFF + timedelta(days=1)).isoformat()}
    return [today, tomorrow]
