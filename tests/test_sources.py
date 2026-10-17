import json
from datetime import date

import httpx
import pytest

from betting_analyst.sources import football_data
from betting_analyst.sources.manual_odds import append_row, load_manual_quotes
from betting_analyst.sources.the_odds_api import MissingApiKeyError, TheOddsApiClient, load_latest_cached
from betting_analyst.teams import TeamResolver, normalize_team


def test_odds_api_fetch_saves_raw_without_key_and_reads_credits(tmp_path, odds_api_events):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        headers = {"x-requests-remaining": "492", "x-requests-used": "8", "x-requests-last": "2"}
        return httpx.Response(200, json=odds_api_events, headers=headers)

    client = TheOddsApiClient(api_key="SECRET", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = client.fetch_odds("soccer_poland_ekstraklasa", ["eu"], ["h2h", "totals"])
    assert "apiKey=SECRET" in seen["url"] and "markets=h2h%2Ctotals" in seen["url"]
    assert (result.credits.remaining, result.credits.used, result.credits.last) == (492, 8, 2)
    raw = result.cache_path.read_text()
    assert "SECRET" not in raw
    assert json.loads(raw)["data"] == odds_api_events

    cached = load_latest_cached("soccer_poland_ekstraklasa", tmp_path)
    assert cached.from_cache and len(cached.events) == 2


def test_odds_api_requires_key(tmp_path, monkeypatch):
    monkeypatch.setattr("betting_analyst.sources.the_odds_api.get_env", lambda name: None)
    with pytest.raises(MissingApiKeyError):
        TheOddsApiClient(cache_dir=tmp_path).fetch_odds("x", ["eu"], ["h2h"])


def test_season_helpers():
    assert football_data.season_code(2025) == "2526"
    assert football_data.current_season_start(date(2026, 10, 17)) == 2026
    assert football_data.current_season_start(date(2027, 3, 1)) == 2026
    assert football_data.recent_seasons(3, date(2026, 10, 17)) == [2024, 2025, 2026]


def test_normalize_results_both_formats():
    import pandas as pd

    main = pd.DataFrame(
        {"Date": ["08/08/2025"], "HomeTeam": ["Birmingham"], "AwayTeam": ["Ipswich"], "FTHG": [1], "FTAG": [1],
         "PSCH": [2.5], "PSCD": [3.3], "PSCA": [2.9]}
    )  # fmt: skip
    out = football_data.normalize_results(main, "main")
    assert list(out.columns[:5]) == football_data.RESULT_COLUMNS
    assert out["date"].iloc[0] == pd.Timestamp("2025-08-08")
    assert "pin_close_home" in out.columns

    extra = pd.DataFrame(
        {"Season": ["2026/2027"], "Date": ["12/10/2026"], "Home": ["Radomiak Radom"], "Away": ["Motor Lublin"],
         "HG": [2], "AG": [3]}
    )  # fmt: skip
    out = football_data.normalize_results(extra, "extra")
    assert out[["home_team", "away_goals"]].iloc[0].tolist() == ["Radomiak Radom", 3]


def test_manual_odds_roundtrip(tmp_path):
    row = {
        "league": "ekstraklasa",
        "home_team": "Legia",
        "away_team": "Lech",
        "bookmaker": "sts",
        "market": "1x2",
        "selection": "home",
        "odds": 2.15,
        "captured_at": "2026-10-17T09:00:00+00:00",
    }
    append_row(date(2026, 10, 17), row, tmp_path)
    quotes = load_manual_quotes(date(2026, 10, 17), tmp_path)
    assert len(quotes) == 1 and quotes[0].odds == 2.15 and quotes[0].source == "manual"
    with pytest.raises(ValueError):
        append_row(date(2026, 10, 17), {**row, "bookmaker": "pinnacle"}, tmp_path)


def test_team_resolution_exact_or_alias_only():
    assert normalize_team("1. FC Köln") == normalize_team("FC Koln")
    assert normalize_team("Śląsk Wrocław") == "slask wroclaw"
    resolver = TeamResolver({"Legia", "Lech Poznan", "Hamburg"})
    assert resolver.resolve("Legia Warsaw") == "Legia"  # alias z config/team_aliases.yaml
    assert resolver.resolve("Lech Poznań") == "Lech Poznan"  # dokładne po normalizacji
    assert resolver.resolve("Hamburger SV") == "Hamburg"
    assert resolver.resolve("Legia II Warszawa") is None  # nie zgadujemy
    assert "Legia" in resolver.suggest("Legia II Warszawa")
