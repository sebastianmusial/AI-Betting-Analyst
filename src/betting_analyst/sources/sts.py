"""Oferta STS (pre-match) z publicznego feedu WebSocket strony sts.pl (ADR 0021).

Protokół (rozpoznanie: docs/research/09-sts-offer-feed.md):
- połączenie: wss://www.sts.pl/sbk/api/sbk (bez logowania),
- subskrypcja: {"t":1,"u":[{"s":"<temat>","n":0}, ...]},
- tematy: t_<id_turnieju>_pl (lista meczów + rynki główne), f_f<id_meczu>_pl (pełna oferta meczu),
- wiadomość: linia nagłówka JSON {"s":temat,"n":seq,"f":1 dla pełnego snapshotu} + "\\n" + JSON body,
- body: B (struktura S→C→T→FX mecze), P (grupy rynków: m[id_rynku].l[id_linii].o[id_wyniku].O = kurs;
  linia.D = linia × 100; grupa.f = id meczu).

Zasady (ADR 0009): niskie tempo (paczki tematów, przerwy), cache surowych danych, tylko odczyt,
nic nie publikujemy, nie obchodzimy zabezpieczeń.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import websockets
import yaml

from betting_analyst.config import CONFIG_DIR, RAW_DIR
from betting_analyst.domain import Quote

log = logging.getLogger("betting_analyst.sts")

WS_URL = "wss://www.sts.pl/sbk/api/sbk"
ORIGIN = "https://www.sts.pl"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)
LANG = "pl"
CACHE_DIR = RAW_DIR / "sts"
SOURCE = "sts"
BOOKMAKER = "sts"


def tournament_topic(tournament_id: int) -> str:
    return f"t_{tournament_id}_{LANG}"


def fixture_topic(fixture_id: str) -> str:
    return f"f_{fixture_id}_{LANG}"


@dataclass(frozen=True)
class StsFixture:
    fixture_id: str  # np. "f2915834"
    tournament_id: int
    league: str  # klucz ligi z strategy.yaml
    home_team: str
    away_team: str
    commence_time: datetime

    @property
    def event_id(self) -> str:
        return f"sts:{self.fixture_id}"

    @property
    def url(self) -> str:
        return f"{ORIGIN}/kursy/x/{self.fixture_id}"


@dataclass(frozen=True)
class MarketSpec:
    market: str  # szablon, np. "corners_ou_{line}"
    outcomes: dict[str, str]


def load_market_map(path: Path = CONFIG_DIR / "sts_markets.yaml") -> dict[str, MarketSpec]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(k): MarketSpec(v["market"], {str(o): s for o, s in v["outcomes"].items()})
        for k, v in data["markets"].items()
    }


# --- Parsowanie -------------------------------------------------------------------------


def split_message(raw: str) -> tuple[dict, dict]:
    """Rozdziela wiadomość feedu na (nagłówek, body)."""
    header, _, body = raw.partition("\n")
    return json.loads(header), (json.loads(body) if body.strip() else {})


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def parse_tournament(body: dict, tournament_id: int, league: str) -> list[StsFixture]:
    """Mecze (ft == "m") turnieju z pełnego snapshotu tematu t_<id>_pl."""
    fixtures: list[StsFixture] = []
    for sport in (body.get("B", {}).get("S") or {}).values():
        for category in (sport.get("C") or {}).values():
            tournament = (category.get("T") or {}).get(str(tournament_id))
            if not tournament:
                continue
            for fid, fx in (tournament.get("FX") or {}).items():
                if fx.get("ft") != "m" or not fx.get("H") or not fx.get("A") or not fx.get("t"):
                    continue
                fixtures.append(
                    StsFixture(
                        fid, tournament_id, league, fx["H"]["n"].strip(), fx["A"]["n"].strip(), _parse_time(fx["t"])
                    )
                )
    return sorted(fixtures, key=lambda f: f.commence_time)


def _market_key(template: str, line_d: object) -> str | None:
    if "{line}" not in template:
        return template
    if not isinstance(line_d, int | float):
        return None
    key = template.format(line=f"{line_d / 100:.1f}")
    return "ou25" if key == "goals_ou_2.5" else key  # zgodność z rynkiem Pinnacle (The Odds API)


def parse_fixture_quotes(
    body: dict,
    fixture: StsFixture,
    captured_at: datetime,
    market_map: dict[str, MarketSpec],
) -> list[Quote]:
    """Kursy z pełnej oferty meczu (temat f_f<id>_pl) dla rynków z config/sts_markets.yaml."""
    quotes: list[Quote] = []
    seen: set[tuple[str, str]] = set()
    for group in (body.get("P") or {}).values():
        if not isinstance(group, dict) or group.get("f") != fixture.fixture_id:
            continue
        for market_id, market in (group.get("m") or {}).items():
            spec = market_map.get(str(market_id))
            if spec is None:
                continue
            for line in (market.get("l") or {}).values():
                if not isinstance(line, dict) or line.get("s"):  # s = linia zawieszona
                    continue
                key = _market_key(spec.market, line.get("D"))
                if key is None:
                    continue
                for outcome_id, outcome in (line.get("o") or {}).items():
                    selection = spec.outcomes.get(str(outcome_id))
                    odds = outcome.get("O") if isinstance(outcome, dict) else None
                    if selection is None or not isinstance(odds, int | float) or odds <= 1.0:
                        continue
                    if (key, selection) in seen:
                        continue
                    seen.add((key, selection))
                    quotes.append(
                        Quote(
                            fixture.event_id,
                            fixture.league,
                            fixture.commence_time,
                            fixture.home_team,
                            fixture.away_team,
                            BOOKMAKER,
                            key,
                            selection,
                            float(odds),
                            SOURCE,
                            captured_at,
                        )
                    )
    return quotes


# --- Pobieranie --------------------------------------------------------------------------


def _cache_write(topic: str, raw: str, captured_at: datetime, cache_dir: Path) -> None:
    path = cache_dir / topic / f"{captured_at:%Y%m%dT%H%M%S}.txt.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(raw)


def load_cached(topic: str, cache_dir: Path = CACHE_DIR) -> tuple[dict, datetime] | None:
    """Ostatni zapisany snapshot tematu (body, captured_at) — tryb --from-cache."""
    files = sorted((cache_dir / topic).glob("*.txt.gz"))
    if not files:
        return None
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        _, body = split_message(f.read())
    captured = datetime.strptime(files[-1].name.split(".")[0], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return body, captured


async def _fetch_snapshots(topics: list[str], timeout_s: float, batch: int, pause_s: float) -> dict[str, str]:
    """Pełne snapshoty ("f":1) tematów — jedno połączenie, subskrypcje paczkami."""
    got: dict[str, str] = {}
    async with websockets.connect(
        WS_URL, origin=ORIGIN, user_agent_header=USER_AGENT, max_size=None, open_timeout=20
    ) as ws:
        for i in range(0, len(topics), batch):
            chunk = topics[i : i + batch]
            await ws.send(json.dumps({"t": 1, "u": [{"s": t, "n": 0} for t in chunk]}))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_s
            pending = set(chunk)
            while pending and loop.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), max(0.1, deadline - loop.time()))
                except TimeoutError:
                    break
                if not isinstance(raw, str):
                    continue
                header_line = raw.partition("\n")[0]
                try:
                    header = json.loads(header_line)
                except json.JSONDecodeError:
                    continue
                topic = header.get("s")
                if topic in pending and header.get("f") == 1:
                    got[topic] = raw
                    pending.discard(topic)
            for t in pending:
                log.warning("STS: brak snapshotu tematu %s w %ss", t, timeout_s)
            # Kolejne paczki dokładamy do subskrypcji; poprzednie tematy przestają nas interesować.
            if i + batch < len(topics):
                await asyncio.sleep(pause_s)
    return got


def fetch_snapshots(
    topics: list[str],
    timeout_s: float = 20.0,
    batch: int = 5,
    pause_s: float = 1.5,
    cache_dir: Path = CACHE_DIR,
) -> tuple[dict[str, dict], datetime]:
    """Pobiera i cache'uje snapshoty tematów. Zwraca ({temat: body}, captured_at)."""
    captured_at = datetime.now(UTC)
    raw = asyncio.run(_fetch_snapshots(topics, timeout_s, batch, pause_s))
    out: dict[str, dict] = {}
    for topic, message in raw.items():
        _cache_write(topic, message, captured_at, cache_dir)
        out[topic] = split_message(message)[1]
    return out, captured_at


@dataclass
class StsOffer:
    fixtures: list[StsFixture]
    quotes: list[Quote]
    captured_at: datetime
    warnings: list[str]


def fetch_offer(
    leagues: dict[str, int],
    start: datetime,
    end: datetime,
    from_cache: bool = False,
    market_map: dict[str, MarketSpec] | None = None,
    cache_dir: Path = CACHE_DIR,
) -> StsOffer:
    """Oferta STS dla lig {klucz_ligi: id_turnieju} i meczów z okna (start, end]."""
    market_map = market_map or load_market_map()
    warnings: list[str] = []
    t_topics = {tournament_topic(tid): (key, tid) for key, tid in leagues.items()}

    if from_cache:
        bodies, captured_at = {}, datetime.now(UTC)
        for topic in t_topics:
            cached = load_cached(topic, cache_dir)
            if cached:
                bodies[topic], captured_at = cached
            else:
                warnings.append(f"STS: brak cache dla {topic}")
    else:
        bodies, captured_at = fetch_snapshots(list(t_topics), cache_dir=cache_dir)

    fixtures: list[StsFixture] = []
    for topic, (key, tid) in t_topics.items():
        if topic not in bodies:
            warnings.append(f"STS: brak oferty turnieju {key} ({topic})")
            continue
        fixtures += [f for f in parse_tournament(bodies[topic], tid, key) if start < f.commence_time <= end]

    f_topics = [fixture_topic(f.fixture_id) for f in fixtures]
    if from_cache:
        f_bodies = {}
        for topic in f_topics:
            cached = load_cached(topic, cache_dir)
            if cached:
                f_bodies[topic] = cached[0]
    else:
        f_bodies, captured_at = fetch_snapshots(f_topics, cache_dir=cache_dir) if f_topics else ({}, captured_at)

    quotes: list[Quote] = []
    for f in fixtures:
        body = f_bodies.get(fixture_topic(f.fixture_id))
        if body is None:
            warnings.append(f"STS: brak pełnej oferty meczu {f.home_team} – {f.away_team}")
            continue
        quotes += parse_fixture_quotes(body, f, captured_at, market_map)
    return StsOffer(fixtures, quotes, captured_at, warnings)
