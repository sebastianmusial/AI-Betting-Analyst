from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from betting_analyst.models.counts import (
    DEFAULT_TEAM_LINES,
    DEFAULT_TOTAL_LINES,
    fit_counts,
    over_probability,
    stat_columns,
    walk_forward,
)
from betting_analyst.sources.football_data import normalize_match_stats

TEAMS = [f"T{i:02d}" for i in range(12)]
AS_OF = pd.Timestamp("2026-06-01")


def _synthetic(n_rounds: int = 8, seed: int = 0, with_referee: bool = True) -> pd.DataFrame:
    """Podwójna runda każdy z każdym co tydzień, rogi i kartki z NB/Poissona o znanych efektach."""
    rng = np.random.default_rng(seed)
    att = {t: 0.25 if t == "T00" else (-0.25 if t == "T01" else 0.0) for t in TEAMS}
    rows = []
    day = pd.Timestamp("2025-08-01")
    for _ in range(n_rounds):
        for h in TEAMS:
            for a in TEAMS:
                if h == a:
                    continue
                ref = f"R{rng.integers(0, 6)}"
                card_boost = 0.4 if ref == "R0" else 0.0
                mu_hc = np.exp(np.log(5.4) + att[h] + 0.0)
                mu_ac = np.exp(np.log(4.6) + att[a])
                r = 12.0
                rows.append(
                    {
                        "date": day,
                        "home_team": h,
                        "away_team": a,
                        "home_goals": int(rng.poisson(1.4)),
                        "away_goals": int(rng.poisson(1.1)),
                        "home_corners": int(rng.negative_binomial(r, r / (r + mu_hc))),
                        "away_corners": int(rng.negative_binomial(r, r / (r + mu_ac))),
                        "home_yellow": int(rng.poisson(1.8 * np.exp(card_boost))),
                        "away_yellow": int(rng.poisson(2.0 * np.exp(card_boost))),
                        "home_red": int(rng.random() < 0.05),
                        "away_red": int(rng.random() < 0.06),
                        **({"referee": ref} if with_referee else {}),
                    }
                )
            day += pd.Timedelta(days=1)
        day += pd.Timedelta(days=3)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return _synthetic()


@pytest.fixture(scope="module")
def corners(matches):
    return fit_counts(matches, "corners", AS_OF, "SYN")


@pytest.fixture(scope="module")
def cards(matches):
    return fit_counts(matches, "cards", AS_OF, "SYN", min_referee_matches=20)


def test_recovers_known_effects(corners, cards):
    assert np.exp(corners.base + corners.home_adv) == pytest.approx(5.4, rel=0.08)
    assert corners.home_adv == pytest.approx(np.log(5.4 / 4.6), abs=0.06)
    assert corners.attack["T00"] > 0.1 > -0.1 > corners.attack["T01"]
    assert cards.referee["R0"] > 0.15
    assert abs(cards.referee["R3"]) < 0.15


@pytest.mark.parametrize("stat_fixture", ["corners", "cards"])
def test_markets_sum_to_one_and_monotone(request, stat_fixture):
    model = request.getfixturevalue(stat_fixture)
    stat = model.stat
    markets = model.predict_markets("T00", "T05", referee="R0")
    for probs in markets.values():
        assert sum(probs.values()) == pytest.approx(1.0, abs=1e-9)
        assert all(0.0 <= p <= 1.0 for p in probs.values())
    for prefix, lines in ((stat, DEFAULT_TOTAL_LINES[stat]), (f"home_{stat}", DEFAULT_TEAM_LINES[stat])):
        overs = [markets[f"{prefix}_ou_{line:g}"]["over"] for line in lines]
        assert all(a > b for a, b in pairwise(overs)), overs
    _, _, total = model.distributions("T00", "T05")
    assert total.sum() == pytest.approx(1.0)


def test_total_is_convolution_of_team_distributions(matches):
    model = fit_counts(matches, "corners", AS_OF, "SYN", total_model="convolution")
    assert model.total_dispersion is None
    p_home, p_away, p_total = model.distributions("T02", "T03")
    mu_h, mu_a = model.expected("T02", "T03")
    assert (np.arange(len(p_total)) * p_total).sum() == pytest.approx(mu_h + mu_a, rel=1e-6)
    # P(suma > 0.5) = 1 − P(0, 0)
    assert over_probability(p_total, 0.5) == pytest.approx(1 - p_home[0] * p_away[0])


def test_nb_total_keeps_mean_and_fits_total_dispersion(corners):
    assert corners.total_model == "nb_total" and corners.total_dispersion is not None
    *_, p_total = corners.distributions("T02", "T03")
    mu_h, mu_a = corners.expected("T02", "T03")
    assert (np.arange(len(p_total)) * p_total).sum() == pytest.approx(mu_h + mu_a, rel=1e-6)
    # W danych syntetycznych drużyny są niezależne (r=12 per drużyna), więc suma ma r_suma ≈ 24.
    assert 10 < corners.total_dispersion < 80


def test_integer_line_rejected(corners):
    with pytest.raises(ValueError):
        corners.predict_markets("T00", "T01", lines=[10.0])


def test_no_look_ahead(matches):
    """Model as_of=D nie widzi meczów z datą ≥ D: podmiana przyszłości nie zmienia parametrów."""
    cutoff = pd.Timestamp("2025-10-15")
    tampered = matches.copy()
    future = tampered["date"] >= cutoff
    tampered.loc[future, ["home_corners", "away_corners", "home_yellow"]] = 30
    tampered.loc[future, "home_team"] = "T00"  # również rzeczy, które zmieniłyby zbiór drużyn
    a = fit_counts(matches, "cards", cutoff, "SYN", min_referee_matches=5)
    b = fit_counts(tampered, "cards", cutoff, "SYN", min_referee_matches=5)
    assert a.last_match < cutoff
    assert a.n_matches == int((matches["date"] < cutoff).sum())
    assert a.base == b.base and a.attack == b.attack and a.referee == b.referee
    c = fit_counts(matches, "corners", cutoff, "SYN")
    d = fit_counts(tampered, "corners", cutoff, "SYN")
    assert c.attack == d.attack and c.dispersion == d.dispersion


def test_too_few_matches_before_as_of(matches):
    with pytest.raises(ValueError):
        fit_counts(matches, "corners", matches["date"].min() + pd.Timedelta(days=2), "SYN")


def test_unknown_team_and_league_baseline(matches, corners):
    assert corners.predict_markets("T00", "Nowy Klub") is None
    fallback = corners.predict_markets("T00", "Nowy Klub", allow_unknown=True)
    assert fallback is not None
    flat = fit_counts(matches, "corners", AS_OF, "SYN", team_effects=False)
    assert flat.attack == {} and flat.knows("X", "Y")
    assert flat.expected("T00", "T01") == flat.expected("T05", "T07")


def test_referee_requires_min_matches(matches):
    strict = fit_counts(matches, "cards", AS_OF, "SYN", min_referee_matches=10_000)
    assert strict.referee == {}
    no_ref_col = fit_counts(matches.drop(columns="referee"), "cards", AS_OF, "SYN")
    assert no_ref_col.referee == {}
    corners = fit_counts(matches, "corners", AS_OF, "SYN", min_referee_matches=1)
    assert corners.referee == {}  # sędzia tylko dla kartek


def test_card_count_convention(matches):
    home, _ = stat_columns(matches, "cards")
    np.testing.assert_array_equal(home, matches["home_yellow"] + matches["home_red"])
    home_bp, _ = stat_columns(matches, "cards", red_weight=2)
    np.testing.assert_array_equal(home_bp, matches["home_yellow"] + 2 * matches["home_red"])


def test_walk_forward_uses_only_past(matches):
    preds = walk_forward(matches, "corners", "2025-10-01", "2025-11-01", refit_days=14, lines=[9.5], league="SYN")
    assert not preds.empty
    assert (preds["date"] >= preds["refit"]).all()
    assert (preds["date"] < preds["refit"] + pd.Timedelta(days=14)).all()
    assert preds[["p_team", "p_league", "p_freq"]].apply(lambda s: s.between(0, 1)).all().all()


def test_normalize_match_stats_maps_columns():
    raw = pd.DataFrame(
        {
            "Date": ["14/08/2026", "15/08/2026"],
            "HomeTeam": ["Wolves", "Leeds"],
            "AwayTeam": ["Blackburn", "Hull"],
            "FTHG": [2, 1],
            "FTAG": [2, 0],
            "Referee": ["F Hallam ", "R Madley"],
            "HC": [5, 7],
            "AC": [5, 2],
            "HY": [1, 2],
            "AY": [3, None],
            "HR": [0, 1],
            "AR": [0, 0],
            "HF": [10, 12],
            "AF": [16, 9],
        }
    )
    out = normalize_match_stats(raw)
    assert len(out) == 1  # wiersz bez kartek gościa odpada
    row = out.iloc[0]
    assert row["home_corners"] == 5 and row["away_yellow"] == 3 and row["referee"] == "F Hallam"
    assert row["home_goals"] == 2 and row["date"] == pd.Timestamp("2026-08-14")
