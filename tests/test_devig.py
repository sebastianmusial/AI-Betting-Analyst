import pytest

from betting_analyst.models.devig import METHODS, consensus_devig, devig, devig_all, fair_odds, overround

ODDS_1X2 = [2.20, 3.50, 3.40]
ODDS_OU = [1.95, 1.87]


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("odds", [ODDS_1X2, ODDS_OU, [1.25, 6.0, 12.0]])
def test_devig_sums_to_one(method, odds):
    probs = devig(odds, method)
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert all(0 < p < 1 for p in probs)


def test_multiplicative_is_proportional():
    probs = devig([2.0, 2.0], "multiplicative")
    assert probs == pytest.approx([0.5, 0.5])
    probs = devig(ODDS_1X2, "multiplicative")
    inv = [1 / o for o in ODDS_1X2]
    assert probs == pytest.approx([i / sum(inv) for i in inv])


def test_power_and_shin_shift_margin_to_longshot():
    """Faworyt dostaje więcej, outsider mniej niż przy metodzie multiplikatywnej (favourite-longshot bias)."""
    odds = [1.25, 6.0, 12.0]
    mult = devig(odds, "multiplicative")
    for method in ("power", "shin"):
        probs = devig(odds, method)
        assert probs[0] > mult[0]
        assert probs[2] < mult[2]


def test_devig_all_and_overround():
    result = devig_all(ODDS_1X2)
    assert set(result) == set(METHODS)
    assert overround(ODDS_1X2) == pytest.approx(1 / 2.2 + 1 / 3.5 + 1 / 3.4 - 1)


def test_consensus_sums_to_one():
    probs = consensus_devig([ODDS_1X2, [2.10, 3.60, 3.50], [2.30, 3.40, 3.20]])
    assert sum(probs) == pytest.approx(1.0)


def test_invalid_odds_raise():
    with pytest.raises(ValueError):
        devig([1.0, 2.0])
    with pytest.raises(ValueError):
        devig([2.0])


def test_fair_odds():
    assert fair_odds(0.5) == 2.0
