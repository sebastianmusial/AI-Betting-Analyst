import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from betting_analyst.domain import pick_label, selections_for
from betting_analyst.sources import sts

FIX = Path(__file__).parent / "fixtures" / "sts"
NOW = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)


@pytest.fixture
def market_map():
    return sts.load_market_map()


@pytest.fixture
def fixtures():
    return sts.parse_tournament(json.loads((FIX / "tournament_201.json").read_text()), 201, "ekstraklasa")


def test_split_message():
    header, body = sts.split_message('{"s":"t_201_pl","n":1,"f":1}\n{"B":{},"P":{}}')
    assert header == {"s": "t_201_pl", "n": 1, "f": 1}
    assert body == {"B": {}, "P": {}}


def test_topics():
    assert sts.tournament_topic(201) == "t_201_pl"
    assert sts.fixture_topic("f2915834") == "f_f2915834_pl"


def test_parse_tournament_only_matches(fixtures):
    assert len(fixtures) == 16
    motor = next(f for f in fixtures if f.fixture_id == "f2915834")
    assert (motor.home_team, motor.away_team) == ("Motor Lublin", "Śląsk Wrocław")
    assert motor.commence_time == datetime(2026, 10, 17, 12, 45, tzinfo=UTC)
    assert motor.event_id == "sts:f2915834"
    assert all(f.commence_time.tzinfo is not None for f in fixtures)


def test_parse_fixture_quotes(fixtures, market_map):
    motor = next(f for f in fixtures if f.fixture_id == "f2915834")
    body = json.loads((FIX / "fixture_f2915834.json").read_text())
    quotes = {(q.market, q.selection): q.odds for q in sts.parse_fixture_quotes(body, motor, NOW, market_map)}
    # wartości zgodne ze stroną STS w chwili zapisu próbki
    assert quotes[("1x2", "home")] == 1.9 and quotes[("1x2", "draw")] == 3.7 and quotes[("1x2", "away")] == 4.1
    assert quotes[("ou25", "over")] == 1.75  # gole 2.5 mapujemy na rynek Pinnacle "ou25"
    assert quotes[("goals_ou_3.5", "under")] == 1.45
    assert quotes[("btts", "yes")] == 1.67 and quotes[("btts", "no")] == 2.2
    assert quotes[("corners_ou_9.5", "over")] == 1.8
    assert quotes[("cards_ou_4.5", "under")] == 1.55
    assert ("fouls_ou_25.5", "over") in quotes
    assert all(
        q.bookmaker == "sts" and q.source == "sts" for q in sts.parse_fixture_quotes(body, motor, NOW, market_map)
    )


def test_suspended_lines_and_other_fixtures_ignored(fixtures, market_map):
    motor = next(f for f in fixtures if f.fixture_id == "f2915834")
    body = {
        "P": {
            "g1": {"f": "f2915834", "m": {"228": {"l": {"x": {"D": 950, "s": True, "o": {"12": {"O": 1.8}}}}}}},
            "g2": {"f": "f9999999", "m": {"1": {"l": {"1": {"o": {"1": {"O": 2.0}}}}}}},
        }
    }
    assert sts.parse_fixture_quotes(body, motor, NOW, market_map) == []


def test_domain_helpers():
    assert selections_for("corners_ou_9.5") == ("over", "under")
    assert selections_for("btts") == ("yes", "no")
    assert pick_label("corners_ou_9.5", "over") == "Rogi +9.5"
    assert pick_label("away_cards_ou_1.5", "under") == "Kartki gości -1.5"
    assert pick_label("btts", "no") == "BTTS nie"
