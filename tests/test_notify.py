import json
import logging
from datetime import UTC, date, datetime

import httpx
import pytest

from betting_analyst import ledger, notify

TODAY = date(2026, 10, 17)  # sobota


def _pick(i: int, value: bool = False, flags: list[str] | None = None, day: int = 17) -> dict:
    return {
        "fixture_id": f"f{i}",
        "event_id": f"sts:f{i}",
        "league": "ekstraklasa",
        "commence_time": datetime(2026, 10, day, 16, 30, tzinfo=UTC).isoformat(),  # 18:30 PL
        "match": f"Gosp{i} – Gość{i}",
        "market": "1x2",
        "selection": "home",
        "label": "1",
        "odds": 2.2,
        "fair_prob": 0.5,
        "fair_source": "pinnacle",
        "edge": 0.1,
        "odds_eff": 1.936,
        "ev_after_tax": -0.03,
        "value_after_tax": value,
        "stake": 15.0 if value else 5.0,
        "flags": flags or [],
    }


def _mock(responses: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        responses.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    return httpx.MockTransport(handler)


# --- wysyłka ---


def test_send_posts_plain_text_to_bot_api():
    seen: list[httpx.Request] = []
    n = notify.TelegramNotifier(token="123:ABC", chat_id="42", transport=_mock(seen))
    assert n.send("Cześć")
    assert len(seen) == 1
    req = seen[0]
    assert req.url.path == "/bot123:ABC/sendMessage"
    body = json.loads(req.content)
    assert body["chat_id"] == "42" and body["text"] == "Cześć"
    assert "parse_mode" not in body  # zwykły tekst — bez escapowania Markdown/HTML


def test_missing_token_is_noop_with_warning(caplog):
    seen: list[httpx.Request] = []
    n = notify.TelegramNotifier(token="", chat_id="", transport=_mock(seen))
    with caplog.at_level(logging.WARNING, logger="betting_analyst.notify"):
        assert n.send("x") is False
    assert seen == []
    assert "TELEGRAM_BOT_TOKEN" in caplog.text


def test_reads_credentials_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t0k")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99")
    n = notify.TelegramNotifier()
    assert n.enabled and n.token == "t0k" and n.chat_id == "99"


def test_api_error_and_network_error_return_false():
    bad = httpx.MockTransport(lambda r: httpx.Response(400, json={"ok": False, "description": "chat not found"}))
    assert notify.TelegramNotifier(token="t", chat_id="1", transport=bad).send("x") is False

    def boom(request):
        raise httpx.ConnectError("offline")

    assert notify.TelegramNotifier(token="t", chat_id="1", transport=httpx.MockTransport(boom)).send("x") is False


def test_banned_wording_is_never_sent():
    seen: list[httpx.Request] = []
    n = notify.TelegramNotifier(token="t", chat_id="1", transport=_mock(seen))
    with pytest.raises(notify.BannedWordingError):
        n.send("Dzisiejszy PEWNIAK!")
    assert seen == []


# --- format: rano ---


def test_format_morning_lines_and_markers():
    picks = [_pick(1, value=True), _pick(2, flags=["MODEL_ONLY"], day=18)]
    text = notify.format_morning(picks, TODAY)
    lines = text.splitlines()
    assert lines[0].startswith("⚽ Typy dnia STS — sob 17.10")
    assert lines[1] == "1. ✅ · Gosp1 – Gość1 (dziś 18:30) · 1 @2.20 · 15 zł"
    assert lines[2] == "2. typ dnia · Gosp2 – Gość2 (jutro 18:30) · 1 @2.20 · 5 zł · MODEL_ONLY"
    assert lines[-1].startswith("Razem 20 zł.")
    assert "|" not in text  # bez tabel
    assert "pewn" not in text.lower()


def test_format_morning_max_ten_lines():
    picks = [_pick(i) for i in range(15)]
    text = notify.format_morning(picks, TODAY)
    assert len(text.splitlines()) == notify.MAX_LINES
    assert "(+7 w raporcie)" in text


def test_format_morning_vetoed_pick_has_zero_stake():
    picks = [_pick(1, value=True), _pick(2)]
    text = notify.format_morning(picks, TODAY, vetoed={("sts:f1", "1x2", "home")})
    assert "1. ⛔ weto" in text and "0 zł (weto)" in text
    assert "Razem 5 zł." in text


def test_format_morning_empty():
    text = notify.format_morning([], TODAY)
    assert len(text.splitlines()) == 2
    assert "nic nie gramy" in text


# --- format: wieczór ---


def _bet(con, bet_id, clv, source="pinnacle", status="open", kickoff=datetime(2026, 10, 17, 16, 30, tzinfo=UTC)):
    con.execute(
        """INSERT INTO paper_bets (bet_id, placed_at, scan_date, bet_type, event_id, league, commence_time,
           home_team, away_team, market, selection, bookmaker, source, is_proxy, odds, stake_tax, odds_eff,
           fair_prob, fair_method, ev, stake, fair_source, clv_pct, clv_eff_pct, status)
           VALUES (?, ?, ?, 'single', ?, 'ekstraklasa', ?, 'H', 'A', '1x2', 'home', 'sts', 'sts', FALSE,
                   2.0, 0.12, 1.76, 0.5, 'x', 0.0, 5, ?, ?, ?, ?)""",
        [bet_id, kickoff, kickoff.date(), bet_id, kickoff, source, clv, clv - 0.12, status],
    )


def test_evening_message_splits_pinnacle_and_model_only():
    con = ledger.connect(":memory:")
    _bet(con, "a", 0.04)
    _bet(con, "b", -0.02)
    _bet(con, "c", 0.10, source="model:counts")
    _bet(con, "d", 0.50, status="vetoed")  # weto — poza statystyką strategii
    _bet(con, "e", 0.06, kickoff=datetime(2026, 10, 10, 16, 30, tzinfo=UTC))  # wcześniejszy dzień
    text = notify.evening_message(con, TODAY)
    lines = text.splitlines()
    assert len(lines) <= notify.MAX_LINES
    assert lines[0] == "📊 CLV STS — sob 17.10 (paper)"
    assert lines[1] == "Dziś vs Pinnacle: 2 zakł., śr. CLV +1.0% (po podatku -11.0%), dodatnie 50%"
    assert lines[2].startswith("Dziś model-only vs STS: 1 zakł., śr. CLV +10.0%")
    assert lines[3].startswith("Łącznie vs Pinnacle: 3 zakł.")
    assert "|" not in text and "pewn" not in text.lower()


def test_evening_message_without_closings():
    con = ledger.connect(":memory:")
    text = notify.evening_message(con, TODAY)
    assert "Dziś vs Pinnacle: brak zamknięć" in text


def test_notify_morning_reads_scan_json_and_vetoes(tmp_path):
    (tmp_path / "2026-10-17-morning.json").write_text(json.dumps([_pick(1, value=True), _pick(2)]), encoding="utf-8")
    db = tmp_path / "t.duckdb"
    con = ledger.connect(db)
    _bet(con, "sts:f2", 0.0, status="vetoed")  # event_id = bet_id w helperze
    con.close()
    seen: list[httpx.Request] = []
    n = notify.TelegramNotifier(token="t", chat_id="1", transport=_mock(seen))
    assert notify.notify_morning(TODAY, db, n, scans_dir=tmp_path)
    text = json.loads(seen[0].content)["text"]
    assert "1. ✅ · Gosp1 – Gość1" in text and "2. ⛔ weto" in text


def test_notify_morning_missing_scan_sends_warning(tmp_path):
    seen: list[httpx.Request] = []
    n = notify.TelegramNotifier(token="t", chat_id="1", transport=_mock(seen))
    assert notify.notify_morning(TODAY, tmp_path / "t.duckdb", n, scans_dir=tmp_path)
    assert "brak pliku skanu" in json.loads(seen[0].content)["text"]
