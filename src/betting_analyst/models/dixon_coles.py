"""Dixon-Coles z zanikaniem wagi w czasie (penaltyblog) — druga opinia obok rynku (ADR 0011).

Model dopasowujemy per liga na wynikach z ostatnich N sezonów (football-data). Daje pełny
rozkład wyników, więc z jednej macierzy liczymy 1X2, podwójną szansę, BTTS i O/U dowolnej linii.

Klucze rynków (wspólne z `models.counts`): `{rynek: {wynik: p}}`, np.
`{"1x2": {"home", "draw", "away"}, "double_chance": {"1x", "x2", "12"},
"btts": {"yes", "no"}, "goals_ou_2.5": {"over", "under"}}`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import penaltyblog as pb

log = logging.getLogger(__name__)

MODEL_VERSION = "dc-v0"

DEFAULT_GOAL_LINES: tuple[float, ...] = (1.5, 2.5, 3.5, 4.5)


def ou_key(prefix: str, line: float) -> str:
    """('goals', 2.5) -> 'goals_ou_2.5'."""
    return f"{prefix}_ou_{line:g}"


def markets_from_grid(grid: pb.models.FootballProbabilityGrid, lines=DEFAULT_GOAL_LINES) -> dict[str, dict[str, float]]:
    """Rynki bramkowe z macierzy wyników. Linie połówkowe (bez zwrotu), więc over + under = 1."""
    m = grid.grid / grid.grid.sum()
    home_g, away_g = np.indices(m.shape)
    total = home_g + away_g
    home = float(m[home_g > away_g].sum())
    draw = float(np.trace(m))
    away = float(m[home_g < away_g].sum())
    btts_yes = float(m[1:, 1:].sum())
    out: dict[str, dict[str, float]] = {
        "1x2": {"home": home, "draw": draw, "away": away},
        "double_chance": {"1x": home + draw, "x2": draw + away, "12": home + away},
        "btts": {"yes": btts_yes, "no": 1.0 - btts_yes},
    }
    for line in lines:
        if float(line).is_integer():
            raise ValueError(f"Obsługujemy tylko linie połówkowe (bez zwrotu), dostałem {line}")
        over = float(m[total > line].sum())
        out[ou_key("goals", line)] = {"over": over, "under": 1.0 - over}
    return out


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

    def predict_markets(self, home: str, away: str, lines=DEFAULT_GOAL_LINES) -> dict[str, dict[str, float]] | None:
        """Rynki bramkowe (1X2, podwójna szansa, BTTS, O/U `lines`); None, gdy drużyna nieznana."""
        if home not in self.teams or away not in self.teams:
            return None
        return markets_from_grid(self.model.predict(home, away), lines)


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
