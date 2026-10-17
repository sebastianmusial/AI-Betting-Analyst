from datetime import UTC, date, datetime

import pytest

from betting_analyst import scan
from betting_analyst.decision.ev import TaxContext
from betting_analyst.domain import Quote
from betting_analyst.sources.the_odds_api import parse_events

DAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)


@pytest.fixture
def quotes(odds_api_events):
    return parse_events(odds_api_events, "ekstraklasa", NOW)


def _manual(selection: str, odds: float, bookmaker: str = "betclic", market: str = "1x2") -> Quote:
    return Quote("", "ekstraklasa", NOW, "Legia", "Lech Poznań", bookmaker, market, selection, odds, "manual", NOW)


class FakeDC:
    teams = frozenset({"Legia", "Lech Poznan"})
    version = "dc-test"

    def predict(self, home, away):
        return {"home": 0.40, "draw": 0.28, "away": 0.32, "over": 0.50, "under": 0.50}


def _run(quotes, manual, strategy, bookmakers, models=None, use_proxy=True, already_staked=0.0):
    leagues = [strategy.leagues["ekstraklasa"]]
    return scan.run_scan(
        DAY,
        leagues,
        quotes,
        manual,
        models or {},
        strategy,
        bookmakers,
        {k: TaxContext() for k in bookmakers.bookmakers},
        already_staked=already_staked,
        use_proxy=use_proxy,
        now=NOW,
    )


def test_parse_events(quotes):
    assert {q.event_id for q in quotes} == {"evt1", "evt2"}
    pin = {(q.market, q.selection): q.odds for q in quotes if q.bookmaker == "pinnacle" and q.event_id == "evt1"}
    assert pin == {
        ("1x2", "home"): 2.20,
        ("1x2", "draw"): 3.50,
        ("1x2", "away"): 3.40,
        ("ou25", "over"): 1.95,
        ("ou25", "under"): 1.95,
    }


def test_only_todays_prematch_events(quotes, strategy, bookmakers):
    result = _run(quotes, [], strategy, bookmakers)
    assert [e.event_id for e in result.events] == ["evt1"]


def test_fair_price_from_pinnacle(quotes, strategy, bookmakers):
    event_quotes = [q for q in quotes if q.event_id == "evt1"]
    fair = scan.fair_price(event_quotes, "1x2", "pinnacle", "power", set(bookmakers.reference_bookmakers))
    assert fair.source == "pinnacle"
    assert sum(fair.probs.values()) == pytest.approx(1.0)
    assert set(fair.by_method) == {"multiplicative", "power", "shin"}


def test_fair_price_consensus_without_pinnacle(quotes, bookmakers):
    event_quotes = [q for q in quotes if q.event_id == "evt1" and q.bookmaker != "pinnacle"]
    assert scan.fair_price(event_quotes, "1x2", "pinnacle", "power") is None  # tylko 2 buki < 3
    extra = [
        Quote("evt1", "ekstraklasa", q.commence_time, q.home_team, q.away_team, "x", q.market, q.selection, q.odds,
              q.source, q.captured_at)
        for q in event_quotes if q.bookmaker == "unibet_eu"
    ]  # fmt: skip
    fair = scan.fair_price(event_quotes + extra, "1x2", "pinnacle", "power")
    assert fair.source == "consensus(3)"


def test_manual_betclic_odds_are_value_after_tax_rules(quotes, strategy, bookmakers):
    # Pinnacle 2.20/3.50/3.40 → p(home) ≈ 0.44. Betclic single 0% podatku: 2.45 → EV ≈ +8%.
    # STS z 12% podatku przy tym samym kursie: 2.156 → EV ujemne.
    manual = [_manual("home", 2.45), _manual("home", 2.45, "sts")]
    result = _run(quotes, manual, strategy, bookmakers, models={"ekstraklasa": FakeDC()}, use_proxy=False)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert (cand.offer.bookmaker, cand.selection, cand.offer.is_proxy) == ("betclic", "home", False)
    assert cand.evaluation.stake_tax == 0.0
    assert cand.evaluation.ev > strategy.min_edge
    assert cand.dc_prob == 0.40
    assert cand.diff_pp == pytest.approx(cand.fair_prob - 0.40)
    assert 0 < cand.stake <= strategy.bankroll_pln * strategy.max_stake_pct


def test_proxy_offers_flagged(quotes, strategy, bookmakers):
    result = _run(quotes, [], strategy, bookmakers)
    assert result.evaluated, "powinny być oceny z kursów proxy"
    assert all(c.offer.is_proxy for c in result.evaluated)
    for c in result.candidates:
        assert "PROXY" in c.flags
        assert "brak DC" in c.flags


def test_daily_exposure_respected(quotes, strategy, bookmakers):
    manual = [_manual("home", 2.45)]
    limit = strategy.bankroll_pln * strategy.daily_exposure_pct
    result = _run(quotes, manual, strategy, bookmakers, use_proxy=False, already_staked=limit)
    assert result.candidates[0].stake == 0
    assert "limit dzienny" in result.candidates[0].flags


def test_main_without_api_key_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(scan, "get_env", lambda name: None)
    assert scan.main(["--date", "2026-10-17"]) == 2
    out = capsys.readouterr().out
    assert "the-odds-api.com" in out
    assert "ODDS_API_KEY" in out


def test_select_shadow_one_per_event_best_ev(quotes, strategy, bookmakers):
    result = _run(quotes, [], strategy, bookmakers)
    picked = scan.select_shadow(result, 10, NOW)
    events = [c.event.event_id for c in picked]
    assert len(events) == len(set(events))
    value_keys = {(c.event.event_id, c.market, c.selection, c.offer.bookmaker) for c in result.candidates}
    for c in picked:
        assert (c.event.event_id, c.market, c.selection, c.offer.bookmaker) not in value_keys
        same_event = [
            e
            for e in result.evaluated
            if e.event.event_id == c.event.event_id
            and (e.event.event_id, e.market, e.selection, e.offer.bookmaker) not in value_keys
        ]
        assert c.evaluation.ev == max(e.evaluation.ev for e in same_event)
    assert [c.evaluation.ev for c in picked] == sorted((c.evaluation.ev for c in picked), reverse=True)
    assert len(scan.select_shadow(result, 1, NOW)) <= 1


def test_select_shadow_skips_events_starting_soon(quotes, strategy, bookmakers):
    result = _run(quotes, [], strategy, bookmakers)
    late = max(e.commence_time for e in result.events)
    assert scan.select_shadow(result, 10, late) == []
