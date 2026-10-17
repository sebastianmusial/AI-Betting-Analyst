"""Adapter The Odds API (v4): bieżące kursy h2h + totals dla naszych lig.

Dlaczego własny adapter zamiast `sportsbet.sources.OddsApi`: loader z sports-betting
wymaga harmonogramu meczów ze źródła statystyk (needs_schedule), ma własny cache i nie
udostępnia nagłówków z licznikiem kredytów. Tu potrzebujemy prostego „pobierz dziś,
zapisz surowy JSON, zaloguj kredyty”. Parsowanie rynków jest zgodne z tamtym loaderem.

Koszt: 1 kredyt × liczba rynków × liczba regionów na ligę (4 ligi × 2 rynki × eu = 8).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from betting_analyst.config import RAW_DIR, get_env
from betting_analyst.domain import Quote

log = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
SOURCE = "the_odds_api"
TOTALS_POINT = 2.5
CACHE_DIR = RAW_DIR / SOURCE

MISSING_KEY_HELP = """\
Brak klucza ODDS_API_KEY w pliku .env.

Jak założyć darmowy klucz (500 kredytów/miesiąc, bez karty):
  1. Wejdź na https://the-odds-api.com/#get-access i wybierz plan „Starter” (free).
  2. Podaj e-mail — klucz przyjdzie mailem.
  3. Skopiuj .env.example do .env i wpisz:  ODDS_API_KEY=twój_klucz
  4. Uruchom ponownie skan. Jeden skan 4 lig × 2 rynki (region eu) ≈ 8 kredytów.

Bez klucza możesz użyć ostatnich zapisanych odpowiedzi:  --from-cache
"""


class MissingApiKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(MISSING_KEY_HELP)


@dataclass(frozen=True)
class Credits:
    remaining: int | None
    used: int | None
    last: int | None

    @classmethod
    def from_headers(cls, headers: httpx.Headers | dict) -> Credits:
        def _int(name: str) -> int | None:
            value = headers.get(name)
            try:
                return int(float(value)) if value is not None else None
            except ValueError:
                return None

        return cls(
            _int("x-requests-remaining"),
            _int("x-requests-used"),
            _int("x-requests-last"),
        )


@dataclass
class FetchResult:
    sport_key: str
    fetched_at: datetime
    events: list[dict]
    credits: Credits | None
    cache_path: Path | None
    from_cache: bool = False


class TheOddsApiClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = CACHE_DIR,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or get_env("ODDS_API_KEY")
        self.cache_dir = cache_dir
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport)

    def fetch_odds(self, sport_key: str, regions: list[str], markets: list[str]) -> FetchResult:
        """Pobiera bieżące kursy (pre-match i live) i zapisuje surową odpowiedź w data/raw/."""
        if not self.api_key:
            raise MissingApiKeyError
        params = {
            "regions": ",".join(regions),
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        response = self._client.get(f"/sports/{sport_key}/odds", params={**params, "apiKey": self.api_key})
        credits = Credits.from_headers(response.headers)
        log.info(
            "The Odds API %s: HTTP %s, kredyty: zużyte teraz=%s, łącznie=%s, pozostało=%s",
            sport_key,
            response.status_code,
            credits.last,
            credits.used,
            credits.remaining,
        )
        if response.status_code == 401:
            raise RuntimeError(f"The Odds API odrzuciło klucz (401): {response.text[:200]}")
        if response.status_code == 422:
            # Liga poza sezonem / nieznany klucz sportu — zwracamy pustą listę.
            log.warning("The Odds API %s: %s", sport_key, response.text[:200])
            return FetchResult(sport_key, datetime.now(UTC), [], credits, None)
        response.raise_for_status()

        fetched_at = datetime.now(UTC)
        events = response.json()
        cache_path = self._save_raw(sport_key, fetched_at, params, credits, events)
        return FetchResult(sport_key, fetched_at, events, credits, cache_path)

    def _save_raw(
        self,
        sport_key: str,
        fetched_at: datetime,
        params: dict,
        credits: Credits,
        events: list[dict],
    ) -> Path:
        folder = self.cache_dir / sport_key
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        payload = {
            "fetched_at": fetched_at.isoformat(),
            "sport_key": sport_key,
            "params": params,  # bez klucza API
            "credits": credits.__dict__,
            "data": events,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return path


def load_latest_cached(sport_key: str, cache_dir: Path = CACHE_DIR) -> FetchResult | None:
    """Ostatnia zapisana odpowiedź dla ligi (tryb --from-cache, nie zużywa kredytów)."""
    folder = cache_dir / sport_key
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if not files:
        return None
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    credits = Credits(**payload["credits"]) if payload.get("credits") else None
    return FetchResult(
        sport_key=sport_key,
        fetched_at=datetime.fromisoformat(payload["fetched_at"]),
        events=payload["data"],
        credits=credits,
        cache_path=files[-1],
        from_cache=True,
    )


def parse_events(events: list[dict], league: str, captured_at: datetime) -> list[Quote]:
    """Zamienia odpowiedź API na listę notowań (rynki 1x2 i ou25)."""
    quotes: list[Quote] = []
    for event in events:
        home, away = event["home_team"], event["away_team"]
        commence = datetime.fromisoformat(event["commence_time"])
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    selection = _selection(market["key"], outcome, home, away)
                    if selection is None:
                        continue
                    market_key = "1x2" if market["key"] == "h2h" else "ou25"
                    quotes.append(
                        Quote(
                            event_id=event["id"],
                            league=league,
                            commence_time=commence,
                            home_team=home,
                            away_team=away,
                            bookmaker=bookmaker["key"],
                            market=market_key,
                            selection=selection,
                            odds=float(outcome["price"]),
                            source=SOURCE,
                            captured_at=captured_at,
                        )
                    )
    return quotes


def _selection(market_key: str, outcome: dict, home: str, away: str) -> str | None:
    name = outcome.get("name")
    if market_key == "h2h":
        return {home: "home", away: "away", "Draw": "draw"}.get(name)
    if market_key == "totals" and outcome.get("point") == TOTALS_POINT:
        return {"Over": "over", "Under": "under"}.get(name)
    return None
