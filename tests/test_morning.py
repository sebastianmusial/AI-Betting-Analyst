from datetime import UTC, datetime

from betting_analyst import morning
from betting_analyst.sources.sts import StsFixture

KO = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)


def _fx(i: int) -> StsFixture:
    return StsFixture(f"f{i}", 201, "ekstraklasa", f"H{i}", f"A{i}", KO)


def _pick(i, market="1x2", sel="home", odds=2.0, p=0.5, source="pinnacle", model=None, sts_p=None, fx=None):
    return morning.Pick(
        fixture=fx or _fx(i), market=market, selection=sel, odds=odds, fair_prob=p, fair_source=source,
        fair_method="power", model_prob=model, model_version=None, sts_prob=sts_p, stake_tax=0.12,
    )  # fmt: skip


def test_edge_and_tax(strategy):
    p = _pick(1, odds=2.2, p=0.5)
    assert round(p.edge, 4) == 0.1
    assert round(p.odds_eff, 3) == 1.936
    assert round(p.ev_after_tax, 3) == -0.032
    assert not morning.value_after_tax(p, strategy)
    assert morning.value_after_tax(_pick(2, odds=2.6, p=0.5), strategy)  # 0.5×2.288−1 = +14.4%


def test_qualifies_rules(strategy):
    assert morning.qualifies(_pick(1, odds=2.1, p=0.5), strategy)  # edge +5%
    assert not morning.qualifies(_pick(1, odds=1.9, p=0.5), strategy)  # edge < 0
    model = dict(market="corners_ou_9.5", sel="over", source="model:counts")
    assert morning.qualifies(_pick(1, odds=2.3, p=0.5, model=0.55, sts_p=0.45, **model), strategy)  # +15%
    assert not morning.qualifies(_pick(1, odds=2.1, p=0.5, model=0.55, sts_p=0.45, **model), strategy)  # < 8%
    assert not morning.qualifies(_pick(1, odds=2.3, p=0.5, model=0.70, sts_p=0.45, **model), strategy)  # gap 25 pp
    assert not morning.qualifies(_pick(1, odds=4.0, p=0.3, model=0.32, sts_p=0.25, **model), strategy)  # kurs > 3.5
    assert not morning.qualifies(_pick(1, odds=2.3, p=0.5, model=0.55, sts_p=None, **model), strategy)


def test_one_pick_per_match_and_top_n(strategy):
    fx = _fx(1)
    picks = [
        _pick(1, odds=2.1, p=0.5, fx=fx),  # +5%
        _pick(1, market="ou25", sel="over", odds=2.2, p=0.5, fx=fx),  # +10% — lepszy w tym meczu
        _pick(2, odds=2.15, p=0.5),
        _pick(3, odds=2.05, p=0.5),
        _pick(4, odds=1.8, p=0.5),  # edge < 0 — odpada
    ]
    daily = morning.select_daily_picks(picks, strategy, top=2)
    assert len(daily) == 2
    assert daily[0].fixture.fixture_id == "f1" and daily[0].market == "ou25"
    assert len({p.fixture.fixture_id for p in daily}) == 2


def test_value_picks_ranked_first_and_stakes(strategy):
    value = _pick(1, odds=2.6, p=0.5)  # ✅
    daily = _pick(2, odds=2.15, p=0.5)  # typ dnia
    ranked = morning.select_daily_picks([daily, value], strategy, top=5)
    assert ranked[0] is value
    morning.assign_stakes(ranked, strategy, already_staked=0.0)
    assert value.stake > 0
    assert daily.stake == round(strategy.bankroll_pln * strategy.pick_flat_stake_pct)
    assert sum(p.stake for p in ranked) <= strategy.bankroll_pln * strategy.daily_exposure_pct


def test_paper_bet_fields(strategy):
    p = _pick(1, odds=2.6, p=0.5)
    p.stake = 10
    bet = morning._paper_bet(p, strategy, KO.date())
    assert bet.pick_type == "value" and bet.fair_source == "pinnacle"
    assert bet.bookmaker == "sts" and bet.event_id == "sts:f1"
    assert bet.flags.startswith("VALUE")


def test_count_totals_disabled_by_default(strategy):
    counts = {"corners_ou_9.5": {"over": 0.6, "under": 0.4}, "home_corners_ou_4.5": {"over": 0.5, "under": 0.5}}
    cm = {("ekstraklasa", "corners"): object()}
    args = ([], None, None, counts, cm, "ekstraklasa", strategy, set())
    assert morning._fair_for_market("corners_ou_9.5", "corners", *args) is None
    assert morning._fair_for_market("home_corners_ou_4.5", "home_corners", *args)[1] == "model:counts"
