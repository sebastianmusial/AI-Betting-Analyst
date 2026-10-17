"""Dixon-Coles z zanikaniem wagi w czasie (penaltyblog) — druga opinia obok rynku (ADR 0011).

Model dopasowujemy per liga na wynikach z ostatnich N sezonów (football-data). Daje pełny
rozkład wyników, więc obsługuje zarówno 1X2, jak i O/U 2.5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
import penaltyblog as pb

log = logging.getLogger(__name__)

MODEL_VERSION = "dc-v0"


@dataclass
class DixonColesForecaster:
    league: str
    model: pb.models.DixonColesGoalModel
    teams: set[str]
    n_matches: int
    fitted_at: datetime
    last_match: pd.Timestamp

    @property
    def version(self) -> str:
        return f"{MODEL_VERSION}:{self.league}:{self.fitted_at:%Y%m%d}"

    def predict(self, home: str, away: str) -> dict[str, float] | None:
        """Prawdopodobieństwa {home, draw, away, over, under}; None, gdy drużyna nieznana."""
        if home not in self.teams or away not in self.teams:
            return None
        grid = self.model.predict(home, away)
        under, _push, over = grid.totals(2.5)
        return {
            "home": float(grid.home_win),
            "draw": float(grid.draw),
            "away": float(grid.away_win),
            "over": float(over),
            "under": float(under),
        }


def fit_dixon_coles(results: pd.DataFrame, league: str, xi: float = 0.0018) -> DixonColesForecaster:
    """Dopasowuje model na DataFrame z kolumnami: date, home_team, away_team, home_goals, away_goals."""
    if len(results) < 100:
        raise ValueError(f"Za mało meczów do dopasowania DC dla {league}: {len(results)}")
    weights = pb.models.dixon_coles_weights(results["date"], xi)
    model = pb.models.DixonColesGoalModel(
        results["home_goals"].to_numpy(),
        results["away_goals"].to_numpy(),
        results["home_team"].to_numpy(),
        results["away_team"].to_numpy(),
        weights,
    )
    model.fit()
    teams = set(results["home_team"]) | set(results["away_team"])
    log.info("DC %s: %d meczów, %d drużyn", league, len(results), len(teams))
    return DixonColesForecaster(
        league=league,
        model=model,
        teams=teams,
        n_matches=len(results),
        fitted_at=datetime.now(UTC),
        last_match=results["date"].max(),
    )
