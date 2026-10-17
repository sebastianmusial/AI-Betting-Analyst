import math

import pytest

from betting_analyst.config import WinningsTax
from betting_analyst.decision.ev import (
    AkoLeg,
    TaxContext,
    apply_daily_exposure,
    build_ako_proposals,
    effective_odds,
    evaluate,
    expected_value,
    kelly_fraction,
    kelly_stake,
    required_edge,
    stake_tax_rate,
)


def test_ev_negative_after_12pct_tax_positive_without_tax():
    # kurs 2.10, p = 0.52: bez podatku +9.2%, po 12% podatku od stawki −3.9%
    assert effective_odds(2.10, 0.12) == pytest.approx(1.848)
    assert expected_value(0.52, effective_odds(2.10, 0.12)) == pytest.approx(-0.03904)
    assert expected_value(0.52, effective_odds(2.10, 0.0)) == pytest.approx(0.092)


def test_evaluate_applies_threshold(strategy):
    taxed = evaluate(0.52, 2.10, 0.12, strategy)
    free = evaluate(0.52, 2.10, 0.0, strategy)
    assert not taxed.is_value
    assert free.is_value
    assert free.edge == pytest.approx(0.52 - 1 / 2.10)


def test_required_edge_higher_for_long_odds(strategy):
    assert required_edge(2.5, strategy) == strategy.min_edge
    assert required_edge(3.5, strategy) == strategy.min_edge_high_odds


def test_winnings_tax_above_threshold():
    wt = WinningsTax(rate=0.10, threshold_pln=2280)
    # wypłata 100 × 2.0 × 0.88 = 176 zł < 2280 → bez podatku od wygranej
    assert effective_odds(2.0, 0.12, stake=100, winnings_tax=wt) == pytest.approx(1.76)
    # wypłata 2000 × 1.76 = 3520 zł > 2280 → −10%
    assert effective_odds(2.0, 0.12, stake=2000, winnings_tax=wt) == pytest.approx(1.76 * 0.9)


def test_stake_tax_rules_per_bookmaker(bookmakers):
    sts = bookmakers.bookmakers["sts"]
    betclic = bookmakers.bookmakers["betclic"]
    assert stake_tax_rate(sts, "single") == 0.12
    assert stake_tax_rate(sts, "ako") == 0.12
    assert stake_tax_rate(betclic, "single", TaxContext(period_single_stakes_pln=500), stake=15) == 0.0
    assert stake_tax_rate(betclic, "single", TaxContext(period_single_stakes_pln=995), stake=15) == 0.06
    assert stake_tax_rate(betclic, "ako", TaxContext(period_single_stakes_pln=5000)) == 0.0
    # ≥50% AKO w okresie → wszystko bez podatku
    ctx = TaxContext(period_single_stakes_pln=5000, period_ako_share=0.5)
    assert stake_tax_rate(betclic, "single", ctx, stake=15) == 0.0


def test_kelly_fraction():
    assert kelly_fraction(0.52, 2.10) == pytest.approx((0.52 * 2.10 - 1) / 1.10)
    assert kelly_fraction(0.40, 2.0) == 0.0


def test_kelly_stake_capped_at_max_stake_pct():
    # pełny Kelly 8.36% → ¼ = 2.09% bankrolla = 20.9 zł → cap 1.5% = 15 zł
    assert kelly_stake(0.52, 2.10, 1000, 0.25, 0.015) == 15
    # ¼ Kelly 1.14% = 11.36 zł → zaokrąglenie w dół do 11 zł
    assert kelly_stake(0.50, 2.10, 1000, 0.25, 0.015) == 11
    assert kelly_stake(0.40, 2.10, 1000, 0.25, 0.015) == 0


def test_daily_exposure_cap():
    assert apply_daily_exposure([15, 15, 15, 15], 1000, 0.05) == [15, 15, 15, 5]
    assert apply_daily_exposure([15, 15], 1000, 0.05, already_staked=40) == [10, 0]
    assert apply_daily_exposure([15], 1000, 0.05, already_staked=60) == [0]


def test_ako_proposals_free_bookmaker(strategy, bookmakers):
    legs = [
        AkoLeg("e1", "A–B: 1", 2.10, 0.52),
        AkoLeg("e1", "A–B: 2", 3.60, 0.25),  # ujemne EV, ten sam mecz
        AkoLeg("e2", "C–D: O2.5", 1.95, 0.54),
        AkoLeg("e3", "E–F: X", 3.40, 0.31),
        AkoLeg("e4", "G–H: 1", 1.50, 0.60),  # ujemne EV → pominięte
    ]
    proposals = build_ako_proposals(legs, bookmakers.bookmakers["betclic"], strategy)
    assert [len(p.legs) for p in proposals] == [2, 3]
    for p in proposals:
        assert len({leg.event_id for leg in p.legs}) == len(p.legs)  # różne mecze
        assert all(leg.ev > 0 for leg in p.legs)
        assert p.combined_odds == pytest.approx(math.prod(leg.odds for leg in p.legs))
        assert p.ev == pytest.approx(p.combined_prob * p.combined_odds - 1)
        assert 0 < p.stake <= strategy.bankroll_pln * strategy.max_stake_pct
    three = proposals[1]
    assert {leg.event_id for leg in three.legs} == {"e1", "e2", "e3"}


def test_ako_not_proposed_where_ako_is_taxed(strategy, bookmakers):
    legs = [AkoLeg("e1", "x", 2.10, 0.52), AkoLeg("e2", "y", 1.95, 0.54)]
    assert build_ako_proposals(legs, bookmakers.bookmakers["sts"], strategy) == []
