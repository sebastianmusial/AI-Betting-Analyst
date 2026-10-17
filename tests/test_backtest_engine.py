"""Silnik backtestu: metryki, podatek, CLV, AKO, symulacja bankrolla, loader historii."""

from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd
import pytest

from betting_analyst.backtest import metrics
from betting_analyst.backtest.selections import build_selections
from betting_analyst.backtest.simulate import simulate_bankroll
from betting_analyst.backtest.strategies import AkoSpec, SingleSpec, ako_bets, single_bets
from betting_analyst.sources.football_data import normalize_odds_history

# --- metryki ---------------------------------------------------------------------------


def test_brier_logloss_rps_known_values():
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    y = np.array([[1, 0, 0], [0, 0, 1]])
    assert metrics.brier(p, y) == pytest.approx(0.25 + 0.09 + 0.04)
    assert metrics.log_loss(p, y) == pytest.approx(-math.log(0.5))
    # RPS dla [0.5,0.3,0.2] i wyniku 1: ((0.5−1)² + (0.8−1)²)/2 = 0.145; drugi mecz symetrycznie
    assert metrics.rps(p, y) == pytest.approx(0.145)


def test_clv_stats_and_holm():
    st = metrics.clv_stats(np.array([0.05, 0.02, -0.01, 0.04, np.nan]))
    assert st.n == 4
    assert st.mean == pytest.approx(0.025)
    assert st.share_beat == pytest.approx(0.75)
    assert 0 < st.p_one_sided < 0.5
    assert metrics.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_max_drawdown():
    assert metrics.max_drawdown(np.array([100, 120, 90, 130, 65])) == pytest.approx(0.5)


# --- strategie, podatek, CLV ----------------------------------------------------------


def _one_match_selections(home_won: bool = True) -> pd.DataFrame:
    matches = pd.DataFrame(
        {
            "league": ["X"],
            "match_id": ["M1"],
            "season": ["2022/2023"],
            "date": [pd.Timestamp("2022-09-03")],
            "home_team": ["A"],
            "away_team": ["B"],
            "home_goals": [2 if home_won else 0],
            "away_goals": [0 if home_won else 1],
            "pin_open_home": [2.0],
            "pin_open_draw": [3.6],
            "pin_open_away": [4.2],
            "pin_close_home": [1.9],
            "pin_close_draw": [3.7],
            "pin_close_away": [4.6],
            "avg_home": [1.95],
            "avg_draw": [3.4],
            "avg_away": [3.9],
            "max_home": [2.25],
            "max_draw": [3.7],
            "max_away": [4.3],
            "max_soft_home": [2.1],
            "max_soft_draw": [3.6],
            "max_soft_away": [4.2],
        }
    )
    sel = build_selections(matches, ("1x2",))
    sel["p_dc"] = np.nan
    return sel


def test_tax_reduces_effective_odds_and_clv(strategy):
    sel = _one_match_selections()
    no_tax = single_bets(sel, SingleSpec("B", "p_open_multiplicative", "max", 0.0, 0.0), strategy, "multiplicative")
    taxed = single_bets(sel, SingleSpec("A", "p_open_multiplicative", "max", 0.12, -1.0), strategy, "multiplicative")
    bet = no_tax.iloc[0]
    assert bet["outcome"] == "home"
    p_close = (1 / 1.9) / (1 / 1.9 + 1 / 3.7 + 1 / 4.6)
    assert bet["clv"] == pytest.approx(2.25 * p_close - 1)
    assert bet["profit"] == pytest.approx(1.25)
    t = taxed[taxed["outcome"] == "home"].iloc[0]
    assert t["odds_eff"] == pytest.approx(2.25 * 0.88)
    assert t["clv"] == pytest.approx(2.25 * 0.88 * p_close - 1)
    assert t["clv_pre_tax"] == pytest.approx(bet["clv"])


def test_one_bet_per_match_and_market(strategy):
    sel = _one_match_selections()
    bets = single_bets(sel, SingleSpec("B", "p_open_power", "max", 0.0, -1.0), strategy, "power")
    assert len(bets) == 1  # najlepsza selekcja w meczu × rynku


def test_ako_combines_legs_from_different_matches(strategy, bookmakers):
    a = _one_match_selections(home_won=True)
    b = _one_match_selections(home_won=False).assign(match_id="M2")
    sel = pd.concat([a, b], ignore_index=True)
    spec = AkoSpec("C2", "p_open_multiplicative", "max", 2, 0.0)
    ako = ako_bets(sel, spec, strategy, bookmakers.bookmakers["betclic"], "multiplicative")
    assert len(ako) == 1
    row = ako.iloc[0]
    assert row["n_legs"] == 2
    assert row["odds"] == pytest.approx(2.25**2)
    assert row["stake_tax"] == 0.0
    assert row["won"] == 0  # druga noga przegrana
    assert row["profit"] == -1.0
    p_close = (1 / 1.9) / (1 / 1.9 + 1 / 3.7 + 1 / 4.6)
    assert row["clv"] == pytest.approx(2.25**2 * p_close**2 - 1)


# --- symulacja bankrolla ----------------------------------------------------------------


def _bets(n: int, date: str = "2022-09-03", **kw) -> pd.DataFrame:
    base = {
        "date": pd.Timestamp(date),
        "p": 0.55,
        "odds": 2.0,
        "odds_eff": 2.0,
        "ev": 0.10,
        "threshold": 0.03,
        "won": 1,
    }
    base.update(kw)
    return pd.DataFrame([base] * n)


def test_kelly_cap_and_daily_exposure():
    # pełny Kelly = 0.1; ¼ → 2.5% > cap 1.5% → 15 zł; 5% dziennie → maks. 3 zakłady po 15 zł + 5 zł
    res = simulate_bankroll(_bets(5), kelly_fraction=0.25, max_stake_pct=0.015, daily_exposure_pct=0.05)
    assert res.staked == pytest.approx(50.0)
    assert res.profit == pytest.approx(50.0)
    assert res.n_placed == 4


def test_betclic_limit_switches_to_6pct(bookmakers):
    betclic = bookmakers.bookmakers["betclic"]
    days = pd.concat([_bets(3, f"2022-09-{d:02d}", won=0) for d in range(1, 29)], ignore_index=True)
    res = simulate_bankroll(
        days,
        kelly_fraction=0.25,
        max_stake_pct=0.015,
        daily_exposure_pct=0.05,
        bankroll=100_000,
        rounding=1.0,
        promo_bookmaker=betclic,
    )
    # stawki 1500 zł > limit 1000 zł w miesiącu → wszystkie po 6%: EV = 0.55×1.88 − 1 = 3.4% ≥ 3% → grane
    assert res.taxed_stake_share > 0.9
    assert res.n_placed > 0


def test_betclic_limit_skips_bets_below_threshold_after_tax(bookmakers):
    betclic = bookmakers.bookmakers["betclic"]
    bets = _bets(1, ev=0.045, p=0.5225, threshold=0.03)  # po 6%: 0.5225×1.88 − 1 = −1.8%
    res = simulate_bankroll(
        bets,
        kelly_fraction=0.25,
        max_stake_pct=0.015,
        daily_exposure_pct=0.05,
        bankroll=100_000,
        promo_bookmaker=betclic,
    )
    assert res.n_placed == 0


# --- loader historii -------------------------------------------------------------------

NEW_FORMAT = {
    "Div": "E1", "Date": "09/08/2024", "Time": "20:00", "HomeTeam": "Leeds", "AwayTeam": "Portsmouth",
    "FTHG": 3, "FTAG": 3, "PSH": 1.40, "PSD": 4.9, "PSA": 8.0, "PSCH": 1.38, "PSCD": 5.0, "PSCA": 8.5,
    "MaxH": 1.45, "MaxD": 5.2, "MaxA": 8.8, "AvgH": 1.39, "AvgD": 4.7, "AvgA": 7.6,
    "B365H": 1.40, "B365D": 4.75, "B365A": 8.0, "BWH": 1.42, "BWD": 4.6, "BWA": 7.5,
    "P>2.5": 1.75, "P<2.5": 2.15, "Max>2.5": 1.80, "Max<2.5": 2.20, "Avg>2.5": 1.72, "Avg<2.5": 2.10,
    "B365>2.5": 1.73, "B365<2.5": 2.10,
}  # fmt: skip
OLD_FORMAT = {
    "Div": "E1", "Date": "08/08/15", "HomeTeam": "Brentford", "AwayTeam": "Ipswich", "FTHG": 2, "FTAG": 2,
    "PSH": 2.10, "PSD": 3.4, "PSA": 3.9, "PSCH": 2.05, "PSCD": 3.5, "PSCA": 4.0,
    "BbMxH": 2.20, "BbMxD": 3.6, "BbMxA": 4.1, "BbAvH": 2.05, "BbAvD": 3.3, "BbAvA": 3.7,
    "B365H": 2.10, "B365D": 3.3, "B365A": 3.6, "WHH": 2.15, "WHD": 3.25, "WHA": 3.5,
    "BbMx>2.5": 2.0, "BbMx<2.5": 1.9,
}  # fmt: skip


def _csv(row: dict) -> pd.DataFrame:
    """Przepuszcza wiersz przez CSV, żeby typy były jak przy wczytaniu pliku football-data."""
    text = ",".join(row) + "\n" + ",".join(str(v) for v in row.values()) + "\n"
    return pd.read_csv(io.StringIO(text))


def test_normalize_new_format():
    df = normalize_odds_history(_csv(NEW_FORMAT), "main", season="2024/2025")
    row = df.iloc[0]
    assert row["date"] == pd.Timestamp("2024-08-09")
    assert row["pin_open_home"] == 1.40 and row["pin_close_home"] == 1.38
    assert row["max_home"] == 1.45 and row["avg_away"] == 7.6
    assert row["max_soft_home"] == 1.42  # max(B365 1.40, BW 1.42)
    assert row["pin_open_over"] == 1.75 and row["max_soft_over"] == 1.73
    assert row["season"] == "2024/2025"


def test_normalize_old_betbrain_format():
    df = normalize_odds_history(_csv(OLD_FORMAT), "main", season="2015/2016")
    row = df.iloc[0]
    assert row["date"] == pd.Timestamp("2015-08-08")
    assert row["max_home"] == 2.20 and row["avg_home"] == 2.05
    assert row["max_soft_away"] == 3.6
    assert np.isnan(row["pin_open_over"])  # brak Pinnacle O/U przed 2019/20
