"""Brak patrzenia w przyszłość w backteście F2 (ADR 0015)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_analyst.backtest.selections import build_selections
from betting_analyst.backtest.strategies import SingleSpec, single_bets
from betting_analyst.backtest.walkforward import walk_forward_dc

TEAMS = [f"T{i}" for i in range(10)]


def synthetic_results(n_rounds: int = 60, seed: int = 1) -> pd.DataFrame:
    """Liga 10 drużyn, kolejka co 7 dni (sobota), losowe wyniki Poissona."""
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2020-08-01")  # sobota
    for r in range(n_rounds):
        date = start + pd.Timedelta(days=7 * r)
        order = rng.permutation(TEAMS)
        for i in range(0, len(order), 2):
            home, away = order[i], order[i + 1]
            rows.append(
                {
                    "match_id": f"X:{date:%Y%m%d}:{home}:{away}",
                    "date": date,
                    "home_team": home,
                    "away_team": away,
                    "home_goals": int(rng.poisson(1.5)),
                    "away_goals": int(rng.poisson(1.1)),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def results() -> pd.DataFrame:
    return synthetic_results()


@pytest.fixture(scope="module")
def predictions(results) -> pd.DataFrame:
    return walk_forward_dc(results, "X", min_matches=100)


def test_model_for_day_d_never_sees_matches_on_or_after_d(results, predictions):
    preds = predictions.merge(results[["match_id", "date"]], on="match_id")
    fitted = preds.dropna(subset=["dc_home"])
    assert len(fitted) > 100
    assert (fitted["train_max_date"] < fitted["date"]).all()
    assert (fitted["fit_date"] <= fitted["date"]).all()


def test_future_results_do_not_change_prediction(results, predictions):
    """Zmiana wyników meczów ≥ D nie może zmienić prognozy dla meczu w dniu D."""
    cutoff = results["date"].sort_values().unique()[40]
    tampered = results.copy()
    future = tampered["date"] >= cutoff
    tampered.loc[future, "home_goals"] = 9
    tampered.loc[future, "away_goals"] = 0
    preds_t = walk_forward_dc(tampered, "X", min_matches=100)
    day = results.loc[results["date"] == cutoff, "match_id"]
    a = predictions.set_index("match_id").loc[day, ["dc_home", "dc_draw", "dc_away"]]
    b = preds_t.set_index("match_id").loc[day, ["dc_home", "dc_draw", "dc_away"]]
    assert a.notna().all().all()
    pd.testing.assert_frame_equal(a, b)
    # sanity: po dniu D prognozy już się różnią (model faktycznie uczy się z nowych wyników)
    later = results.loc[results["date"] == results["date"].sort_values().unique()[45], "match_id"]
    assert not np.allclose(
        predictions.set_index("match_id").loc[later, "dc_home"], preds_t.set_index("match_id").loc[later, "dc_home"]
    )


def test_too_little_history_gives_no_prediction(results):
    preds = walk_forward_dc(results.head(50), "X", min_matches=100)
    assert preds["dc_home"].isna().all()


def _matches_with_odds() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = 40
    base = pd.DataFrame(
        {
            "league": "X",
            "match_id": [f"M{i}" for i in range(n)],
            "season": "2022/2023",
            "date": pd.date_range("2022-08-01", periods=n, freq="D"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": rng.integers(0, 4, n),
            "away_goals": rng.integers(0, 4, n),
        }
    )
    for prefix in ("pin_open", "pin_close", "avg", "max", "max_soft"):
        bump = {"max": 1.12, "max_soft": 1.06, "avg": 0.97}.get(prefix, 1.0)
        base[f"{prefix}_home"] = rng.uniform(1.6, 3.2, n) * bump
        base[f"{prefix}_draw"] = rng.uniform(3.0, 3.8, n) * bump
        base[f"{prefix}_away"] = rng.uniform(2.2, 5.0, n) * bump
        base[f"{prefix}_over"] = rng.uniform(1.7, 2.2, n) * bump
        base[f"{prefix}_under"] = rng.uniform(1.7, 2.2, n) * bump
    return base


def test_strategy_selection_ignores_closing_odds(strategy):
    """Kurs zamknięcia służy wyłącznie do CLV: zmiana PSCH nie zmienia zbioru zakładów."""
    matches = _matches_with_odds()
    sel = build_selections(matches)
    sel["p_dc"] = np.nan
    spec = SingleSpec("B", "p_open_power", "max", 0.0, 0.0)
    bets = single_bets(sel, spec, strategy, "power")
    garbage = matches.copy()
    for o in ("home", "draw", "away", "over", "under"):
        garbage[f"pin_close_{o}"] = garbage[f"pin_close_{o}"].sample(frac=1.0, random_state=5).to_numpy()
    sel_g = build_selections(garbage)
    sel_g["p_dc"] = np.nan
    bets_g = single_bets(sel_g, spec, strategy, "power")
    assert len(bets) > 0
    key = ["match_id", "market", "outcome", "odds", "ev"]
    pd.testing.assert_frame_equal(bets[key].reset_index(drop=True), bets_g[key].reset_index(drop=True))
    assert not np.allclose(bets["clv"], bets_g["clv"])
