from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import penaltyblog as pb
import pytest

from betting_analyst.models.dixon_coles import fit_dixon_coles, markets_from_grid

TEAMS = [f"T{i}" for i in range(8)]


@pytest.fixture(scope="module")
def forecaster():
    rng = np.random.default_rng(1)
    strength = {t: 0.3 - 0.08 * i for i, t in enumerate(TEAMS)}
    rows = []
    day = pd.Timestamp("2025-08-01")
    for _ in range(3):
        for h in TEAMS:
            for a in TEAMS:
                if h != a:
                    rows.append(
                        {
                            "date": day,
                            "home_team": h,
                            "away_team": a,
                            "home_goals": int(rng.poisson(np.exp(0.3 + strength[h] - strength[a]))),
                            "away_goals": int(rng.poisson(np.exp(0.1 + strength[a] - strength[h]))),
                        }
                    )
                    day += pd.Timedelta(hours=12)
    return fit_dixon_coles(pd.DataFrame(rows), "SYN")


def test_predict_markets_consistent_with_grid(forecaster):
    grid = forecaster.model.predict("T0", "T5")
    markets = forecaster.predict_markets("T0", "T5", lines=(0.5, 1.5, 2.5, 3.5, 4.5))
    assert markets["1x2"]["home"] == pytest.approx(grid.home_win)
    assert markets["1x2"]["draw"] == pytest.approx(grid.draw)
    assert markets["btts"]["yes"] == pytest.approx(grid.btts_yes)
    assert markets["double_chance"]["1x"] == pytest.approx(grid.double_chance_1x)
    for line in (1.5, 2.5, 3.5):
        under, _, over = grid.totals(line)
        assert markets[f"goals_ou_{line:g}"]["over"] == pytest.approx(over)
        assert markets[f"goals_ou_{line:g}"]["under"] == pytest.approx(under)
    # O/U 0.5 = 1 − P(0:0), BTTS no ≥ P(0:0)
    p00 = grid.grid[0, 0] / grid.grid.sum()
    assert markets["goals_ou_0.5"]["under"] == pytest.approx(p00)
    assert markets["btts"]["no"] >= p00


def test_markets_sum_to_one_and_monotone(forecaster):
    markets = forecaster.predict_markets("T3", "T1")
    for key in ("1x2", "btts", "goals_ou_1.5", "goals_ou_2.5", "goals_ou_3.5", "goals_ou_4.5"):
        assert sum(markets[key].values()) == pytest.approx(1.0)
    dc = markets["double_chance"]
    assert sum(dc.values()) == pytest.approx(2.0)
    overs = [markets[f"goals_ou_{line}"]["over"] for line in ("1.5", "2.5", "3.5", "4.5")]
    assert all(a > b for a, b in pairwise(overs))


def test_predict_backward_compatible(forecaster):
    old = forecaster.predict("T0", "T5")
    new = forecaster.predict_markets("T0", "T5")
    assert set(old) == {"home", "draw", "away", "over", "under"}
    assert old["home"] == pytest.approx(new["1x2"]["home"])
    assert old["over"] == pytest.approx(new["goals_ou_2.5"]["over"])
    assert forecaster.predict("T0", "Obcy") is None
    assert forecaster.predict_markets("Obcy", "T0") is None


def test_markets_from_grid_hand_made():
    # Niezależne Poissony 1.0 / 1.0 → BTTS yes = (1 − e^-1)², P(0 goli) = e^-2
    k = np.arange(16)
    pmf = np.exp(-1.0) / np.array([float(np.prod(range(1, i + 1))) for i in k])
    grid = pb.models.FootballProbabilityGrid(np.outer(pmf, pmf), 1.0, 1.0)
    markets = markets_from_grid(grid, lines=(0.5,))
    assert markets["btts"]["yes"] == pytest.approx((1 - np.exp(-1)) ** 2, rel=1e-6)
    assert markets["goals_ou_0.5"]["under"] == pytest.approx(np.exp(-2), rel=1e-6)
    assert markets["1x2"]["home"] == pytest.approx(markets["1x2"]["away"])
    with pytest.raises(ValueError):
        markets_from_grid(grid, lines=(2.0,))
