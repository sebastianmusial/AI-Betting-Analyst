import math
from datetime import UTC, date, datetime, timedelta

import pytest

from betting_analyst import ledger
from betting_analyst.domain import Quote


@pytest.fixture
def con():
    c = ledger.connect(":memory:")
    yield c
    c.close()


def _bet(**overrides) -> ledger.PaperBet:
    data = dict(
        scan_date=date(2026, 10, 17),
        event_id="evt1",
        league="ekstraklasa",
        commence_time=datetime(2026, 10, 17, 16, 30, tzinfo=UTC),
        home_team="Legia",
        away_team="Lech",
        market="1x2",
        selection="home",
        bookmaker="betclic",
        source="manual",
        is_proxy=False,
        odds=2.10,
        stake_tax=0.0,
        odds_eff=2.10,
        fair_prob=0.52,
        fair_method="pinnacle:power",
        ev=0.092,
        stake=15,
    )
    data.update(overrides)
    return ledger.PaperBet(**data)


def test_clv_formula():
    clv_log, clv_pct = ledger.clv(2.10, 0.5)  # fair zamknięcia = 2.00
    assert clv_pct == pytest.approx(0.05)
    assert clv_log == pytest.approx(math.log(1.05))
    clv_log, clv_pct = ledger.clv(1.90, 0.5)
    assert clv_pct == pytest.approx(-0.05)
    assert clv_log < 0


def test_record_closing_updates_clv(con):
    ledger.log_paper_bet(con, _bet())
    ledger.log_paper_bet(con, _bet(selection="away", odds=3.6, odds_eff=3.6, fair_prob=0.3, ev=0.08))
    captured = datetime(2026, 10, 17, 16, 20, tzinfo=UTC)
    n = ledger.record_closing(con, "evt1", "1x2", {"home": 0.5, "draw": 0.25, "away": 0.25}, captured)
    assert n == 2
    row = con.execute(
        "SELECT closing_fair_odds, clv_pct, clv_log, clv_eff_pct FROM paper_bets WHERE selection='home'"
    ).fetchone()
    assert row[0] == pytest.approx(2.0)
    assert row[1] == pytest.approx(0.05)
    assert row[2] == pytest.approx(math.log(1.05))
    assert row[3] == pytest.approx(0.05)

    # starszy snapshot nie nadpisuje nowszego
    older = captured - timedelta(hours=1)
    assert ledger.record_closing(con, "evt1", "1x2", {"home": 0.4, "draw": 0.3, "away": 0.3}, older) == 0


def test_clv_report_and_exposure(con):
    ledger.log_paper_bet(con, _bet())
    ledger.log_paper_bet(con, _bet(event_id="evt2", bookmaker="sts", stake=10))
    ledger.record_closing(con, "evt1", "1x2", {"home": 0.5}, datetime.now(UTC))
    report = ledger.clv_report(con)
    assert int(report["bets"].iloc[0]) == 2
    assert int(report["with_closing"].iloc[0]) == 1
    assert report["avg_clv_pct"].iloc[0] == pytest.approx(0.05)
    by_bm = ledger.clv_report(con, "bookmaker")
    assert set(by_bm["bookmaker"]) == {"betclic", "sts"}
    assert ledger.staked_on(con, date(2026, 10, 17)) == 25
    assert ledger.period_single_stakes(con, "betclic", date(2026, 10, 30)) == 15
    assert ledger.already_logged(con, date(2026, 10, 17)) == {
        ("evt1", "1x2", "home", "betclic"),
        ("evt2", "1x2", "home", "sts"),
    }


def test_snapshots_deduplicated(con):
    now = datetime.now(UTC)
    q = Quote("evt1", "ekstraklasa", now, "Legia", "Lech", "pinnacle", "1x2", "home", 2.2, "the_odds_api", now)
    assert ledger.insert_snapshots(con, [q, q]) == 1
    assert ledger.insert_snapshots(con, [q]) == 0
    assert ledger.insert_snapshots(con, [q], is_closing=True) == 1


def test_veto_keeps_bet_and_excludes_from_exposure(con):
    ledger.log_paper_bet(con, _bet())
    with pytest.raises(ValueError):
        ledger.veto(con, date(2026, 10, 17), "evt1", "1x2", "home", "", "")
    n = ledger.veto(con, date(2026, 10, 17), "evt1", "1x2", "home", "„X out” — kontuzja", "https://example.com/n")
    assert n == 1
    assert con.execute("SELECT status FROM paper_bets").fetchone()[0] == "vetoed"
    assert ledger.staked_on(con, date(2026, 10, 17)) == 0
    # zawetowane nadal dostają zamknięcie i CLV
    now = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    pending = ledger.open_bets_for_closing(con, now, now + timedelta(days=1))
    assert list(pending["event_id"]) == ["evt1"]


def test_shadow_bets_excluded_from_strategy(con):
    ledger.log_paper_bet(con, _bet())
    ledger.log_paper_bet(con, _bet(event_id="evt2", is_shadow=True, stake=0.0))
    ledger.record_closing(con, "evt2", "1x2", {"home": 0.5}, datetime.now(UTC))
    assert int(ledger.clv_report(con)["bets"].iloc[0]) == 1
    shadow = ledger.clv_report(con, shadow=True)
    assert int(shadow["bets"].iloc[0]) == 1
    assert int(shadow["with_closing"].iloc[0]) == 1
    assert int(ledger.clv_report(con, shadow=None)["bets"].iloc[0]) == 2
    assert ledger.staked_on(con, date(2026, 10, 17)) == 15


def test_connect_migrates_old_db_without_shadow_column(tmp_path):
    db = tmp_path / "old.duckdb"
    con = ledger.connect(db)
    con.execute("ALTER TABLE paper_bets DROP COLUMN is_shadow")
    con.close()
    con = ledger.connect(db)
    cols = {r[0] for r in con.execute("DESCRIBE paper_bets").fetchall()}
    assert "is_shadow" in cols
    con.close()
