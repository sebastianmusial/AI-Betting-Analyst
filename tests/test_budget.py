from datetime import UTC, date, datetime

import httpx
import pandas as pd
from rich.console import Console

from betting_analyst import budget, closing
from betting_analyst.sources.the_odds_api import TheOddsApiClient

DAY = date(2026, 10, 17)
NOON_PL = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)


def test_plan_closing_daily_limit():
    plan = budget.plan_closing(["a", "b", "c"], 2, spent_today=6, daily_limit=10, remaining=400, reserve=40)
    assert plan.allowed == ["a", "b"]
    assert plan.skipped == ["c"]
    assert "limit dzienny" in plan.reason


def test_plan_closing_reserve():
    plan = budget.plan_closing(["a", "b"], 2, spent_today=0, daily_limit=10, remaining=43, reserve=40)
    assert plan.allowed == ["a"] and plan.skipped == ["b"]
    assert "rezerwa" in plan.reason


def test_plan_closing_unknown_remaining_uses_only_daily_limit():
    plan = budget.plan_closing(["a", "b"], 2, spent_today=0, daily_limit=10, remaining=None, reserve=40)
    assert plan.allowed == ["a", "b"] and plan.reason is None


def test_usage_log_sums_per_local_day_and_job(tmp_path):
    log = tmp_path / "usage.jsonl"
    budget.log_usage(log, "morning", "soccer_x", 8, 492, 200, now=NOON_PL)
    budget.log_usage(log, "closing", "soccer_x", 2, 490, 200, now=NOON_PL)
    budget.log_usage(log, "closing", "soccer_y", 2, 488, 200, now=NOON_PL)
    # 23:30 UTC 16.10 = 01:30 czasu PL 17.10 — liczy się do 17.10
    budget.log_usage(log, "closing", "soccer_y", 2, 486, 200, now=datetime(2026, 10, 16, 23, 30, tzinfo=UTC))
    budget.log_usage(log, "closing", "soccer_y", 2, None, 200, now=datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    log.open("a").write("nie-json\n")
    assert budget.spent_on(DAY, "closing", log) == 6
    assert budget.spent_on(DAY, None, log) == 14
    assert budget.last_remaining(log) == 486


def test_client_logs_credits_without_api_key(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"x-requests-remaining": "480", "x-requests-last": "2"})

    log = tmp_path / "usage.jsonl"
    client = TheOddsApiClient(
        api_key="SECRET", cache_dir=tmp_path, transport=httpx.MockTransport(handler), usage_log=log, job="closing"
    )
    client.fetch_odds("soccer_x", ["eu"], ["h2h", "totals"])
    [entry] = budget.read_usage(log)
    assert entry["job"] == "closing" and entry["credits"] == 2 and entry["remaining"] == 480
    assert "SECRET" not in log.read_text()


def test_closing_skips_leagues_over_budget(tmp_path, strategy):
    log = tmp_path / "usage.jsonl"
    limit = strategy.odds_api.daily_closing_credits
    budget.log_usage(log, "closing", "soccer_x", limit - 2, 300, 200)  # zostało miejsca na 1 ligę
    pending = pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3"],
            "league": ["eredivisie", "ekstraklasa", "eredivisie"],
            "commence_time": pd.to_datetime(["2026-10-17T18:00Z", "2026-10-17T15:00Z", "2026-10-17T20:00Z"], utc=True),
        }
    )
    console = Console(file=open(tmp_path / "out.txt", "w"))  # noqa: SIM115
    allowed = closing._leagues_within_budget(pending, strategy, log, console)
    assert allowed == ["ekstraklasa"]  # najwcześniejszy mecz ma priorytet
    skipped = [e for e in budget.read_usage(log) if e["status"] == "skipped:budget"]
    assert len(skipped) == 1 and skipped[0]["credits"] == 0
