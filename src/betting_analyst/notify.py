"""Powiadomienia Telegram (Bot API przez httpx) — skrót porannych typów i wieczorne CLV (ADR 0016).

    uv run python -m betting_analyst.notify test                 # wiadomość testowa (sprawdzenie bota)
    uv run python -m betting_analyst.notify morning [--date D]   # skrót typów dnia z data/scans/D-morning.json
    uv run python -m betting_analyst.notify evening [--date D]   # krótkie CLV zakładów STS
    uv run python -m betting_analyst.notify text "treść"         # dowolny tekst (np. błąd zadania launchd)

Token i chat id wyłącznie z .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Bota zakłada właściciel
w @BotFather. Brak tokenu = no-op z ostrzeżeniem (pipeline działa dalej bez powiadomień).

Zasady treści: zwykły tekst (bez parse_mode i tabel), maks. 10 linii, nigdy „pewniak” — to analiza
statystyczna w trybie paper, nie gwarancja (ADR 0001, 0002). Liczby kopiujemy z kodu bez zmian.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from betting_analyst.config import DB_PATH, SCANS_DIR, get_env

log = logging.getLogger("betting_analyst.notify")

API_URL = "https://api.telegram.org"
MAX_LINES = 10
MAX_CHARS = 4096  # limit Bot API na jedną wiadomość
LOCAL_TZ = ZoneInfo("Europe/Warsaw")
WEEKDAYS_PL = ("pon", "wt", "śr", "czw", "pt", "sob", "nd")
# Słowa, które sugerują pewność wyniku — nie wysyłamy ich nigdy (ADR 0002).
BANNED_WORDS = ("pewniak", "pewny zysk", "gwarantowan")

MISSING_TOKEN_HELP = (
    "Brak TELEGRAM_BOT_TOKEN lub TELEGRAM_CHAT_ID w .env — powiadomienie pominięte. "
    "Instrukcja: docs/automation.md (sekcja Telegram)."
)


class BannedWordingError(ValueError):
    pass


def check_wording(text: str) -> str:
    lowered = text.lower()
    for word in BANNED_WORDS:
        if word in lowered:
            raise BannedWordingError(f"Niedozwolone sformułowanie w powiadomieniu: {word!r}")
    return text


# --- Wysyłka ----------------------------------------------------------------------------


class TelegramNotifier:
    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token if token is not None else get_env("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else get_env("TELEGRAM_CHAT_ID")
        self._timeout = timeout
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        """Wysyła zwykły tekst. Zwraca True po sukcesie; brak tokenu lub błąd sieci → False (bez wyjątku)."""
        check_wording(text)
        if not self.enabled:
            log.warning(MISSING_TOKEN_HELP)
            return False
        payload = {"chat_id": self.chat_id, "text": text[:MAX_CHARS], "disable_web_page_preview": True}
        try:
            with httpx.Client(base_url=API_URL, timeout=self._timeout, transport=self._transport) as client:
                response = client.post(f"/bot{self.token}/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            log.warning("Telegram: błąd sieci (%s) — powiadomienie pominięte", type(exc).__name__)
            return False
        if response.status_code != 200 or not response.json().get("ok", False):
            # Bez treści URL-a — zawiera token.
            log.warning("Telegram: HTTP %s, %s", response.status_code, response.text[:200])
            return False
        return True


def send_message(text: str, notifier: TelegramNotifier | None = None) -> bool:
    return (notifier or TelegramNotifier()).send(text)


# --- Formatowanie: rano -----------------------------------------------------------------


def _when(commence_iso: str, today: date) -> str:
    start = datetime.fromisoformat(commence_iso).astimezone(LOCAL_TZ)
    if start.date() == today:
        day = "dziś"
    elif start.date() == today + timedelta(days=1):
        day = "jutro"
    else:
        day = WEEKDAYS_PL[start.weekday()]
    return f"{day} {start:%H:%M}"


def _pick_line(i: int, pick: dict, today: date, vetoed: bool) -> str:
    if vetoed:
        tag = "⛔ weto"
    elif pick.get("value_after_tax"):
        tag = "✅"
    else:
        tag = "typ dnia"
    stake = "0 zł (weto)" if vetoed else f"{pick['stake']:.0f} zł"
    parts = [f"{i}. {tag}", f"{pick['match']} ({_when(pick['commence_time'], today)})"]
    parts.append(f"{pick['label']} @{pick['odds']:.2f}")
    parts.append(stake)
    flags = [f for f in pick.get("flags", []) if f]
    if flags:
        parts.append(", ".join(flags))
    return " · ".join(parts)


def format_morning(picks: list[dict], today: date, vetoed: set[tuple[str, str, str]] | None = None) -> str:
    """Skrót typów dnia: nagłówek, maks. 8 typów, stopka — razem ≤ 10 linii, bez tabel.

    picks: wpisy z data/scans/D-morning.json (kolejność z raportu). vetoed: (event_id, market, selection).
    """
    vetoed = vetoed or set()
    header = f"⚽ Typy dnia STS — {WEEKDAYS_PL[today.weekday()]} {today:%d.%m} (paper)"
    if not picks:
        return check_wording(f"{header}\nBrak typów z przewagą nad ceną fair. Dziś nic nie gramy.")
    max_picks = MAX_LINES - 2
    shown = picks[:max_picks]
    lines = [header]
    total = 0.0
    for i, p in enumerate(shown, 1):
        is_vetoed = (p.get("event_id"), p.get("market"), p.get("selection")) in vetoed
        lines.append(_pick_line(i, p, today, is_vetoed))
        total += 0.0 if is_vetoed else float(p["stake"])
    more = f" (+{len(picks) - len(shown)} w raporcie)" if len(picks) > len(shown) else ""
    lines.append(f"Razem {total:.0f} zł{more}. ✅ = na plus po podatku 12%; typ dnia = mała stawka, EV < 0 po podatku.")
    return check_wording("\n".join(lines))


def load_morning_picks(day: date, scans_dir: Path = SCANS_DIR) -> list[dict] | None:
    path = scans_dir / f"{day.isoformat()}-morning.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def vetoed_for(con, day: date) -> set[tuple[str, str, str]]:
    rows = con.execute(
        "SELECT event_id, market, selection FROM paper_bets WHERE scan_date = ? AND status = 'vetoed'", [day]
    ).fetchall()
    return {tuple(r) for r in rows}


# --- Formatowanie: wieczór (CLV) --------------------------------------------------------


@dataclass(frozen=True)
class ClvStats:
    bets: int  # zakłady z zamknięciem
    avg_clv: float | None  # brutto (kurs / fair zamknięcia − 1)
    avg_clv_eff: float | None  # po podatku
    share_positive: float | None


def clv_stats(con, *, model_only: bool, start: datetime | None = None, end: datetime | None = None) -> ClvStats:
    """CLV zakładów STS strategii (bez shadow i wet). model_only=False → vs Pinnacle (główny KPI, ADR 0015);
    True → rynki wyceniane modelem, vs zdewigowane zamknięcie STS (słabsza miara, ADR 0021)."""
    source = "fair_source LIKE 'model:%'" if model_only else "(fair_source IS NULL OR fair_source NOT LIKE 'model:%')"
    sql = (
        "SELECT COUNT(clv_pct), AVG(clv_pct), AVG(clv_eff_pct), "
        "AVG(CASE WHEN clv_pct > 0 THEN 1.0 ELSE 0.0 END) FILTER (WHERE clv_pct IS NOT NULL) "
        "FROM paper_bets WHERE bookmaker = 'sts' AND NOT is_shadow AND status <> 'vetoed' "
        f"AND clv_pct IS NOT NULL AND {source}"
    )
    params: list = []
    if start is not None:
        sql += " AND commence_time >= ?"
        params.append(start)
    if end is not None:
        sql += " AND commence_time < ?"
        params.append(end)
    n, avg, avg_eff, share = con.execute(sql, params).fetchone()
    return ClvStats(int(n), avg, avg_eff, share)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.1f}%"


def _stats_text(s: ClvStats) -> str:
    if s.bets == 0:
        return "brak zamknięć"
    share = "" if s.share_positive is None else f", dodatnie {s.share_positive * 100:.0f}%"
    return f"{s.bets} zakł., śr. CLV {_pct(s.avg_clv)} (po podatku {_pct(s.avg_clv_eff)}){share}"


def format_evening(
    day: date, today_market: ClvStats, today_model: ClvStats, all_market: ClvStats, all_model: ClvStats
) -> str:
    lines = [
        f"📊 CLV STS — {WEEKDAYS_PL[day.weekday()]} {day:%d.%m} (paper)",
        f"Dziś vs Pinnacle: {_stats_text(today_market)}",
        f"Dziś model-only vs STS: {_stats_text(today_model)}",
        f"Łącznie vs Pinnacle: {_stats_text(all_market)}",
        f"Łącznie model-only vs STS: {_stats_text(all_model)}",
        "Pojedynczy dzień to szum; wnioski po ≥300 zakładach (ADR 0001).",
    ]
    return check_wording("\n".join(lines))


def evening_message(con, day: date) -> str:
    start = datetime.combine(day, datetime.min.time(), LOCAL_TZ).astimezone(UTC)
    end = start + timedelta(days=1)
    return format_evening(
        day,
        clv_stats(con, model_only=False, start=start, end=end),
        clv_stats(con, model_only=True, start=start, end=end),
        clv_stats(con, model_only=False),
        clv_stats(con, model_only=True),
    )


# --- Punkty wejścia używane przez morning/report ----------------------------------------


def notify_morning(
    day: date, db_path: Path = DB_PATH, notifier: TelegramNotifier | None = None, scans_dir: Path = SCANS_DIR
) -> bool:
    notifier = notifier or TelegramNotifier()
    if not notifier.enabled:
        log.warning(MISSING_TOKEN_HELP)
        return False
    picks = load_morning_picks(day, scans_dir)
    if picks is None:
        return notifier.send(f"⚠ Morning Scout {day:%d.%m}: brak pliku skanu — sprawdź data/logs/.")
    from betting_analyst import ledger

    con = ledger.connect(db_path)
    try:
        vetoed = vetoed_for(con, day)
    finally:
        con.close()
    return notifier.send(format_morning(picks, day, vetoed))


def notify_evening(day: date, db_path: Path = DB_PATH, notifier: TelegramNotifier | None = None) -> bool:
    notifier = notifier or TelegramNotifier()
    if not notifier.enabled:
        log.warning(MISSING_TOKEN_HELP)
        return False
    from betting_analyst import ledger

    con = ledger.connect(db_path)
    try:
        text = evening_message(con, day)
    finally:
        con.close()
    return notifier.send(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m betting_analyst.notify", description="Powiadomienia Telegram.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test", help="wiadomość testowa")
    for name in ("morning", "evening"):
        p = sub.add_parser(name)
        p.add_argument("--date", type=date.fromisoformat, default=None, help="RRRR-MM-DD (domyślnie dziś)")
        p.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    t = sub.add_parser("text", help="dowolny tekst (np. komunikat o błędzie zadania)")
    t.add_argument("text")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "test":
        ok = send_message("✅ AI Betting Analyst: bot działa. Tu będą poranne typy STS i wieczorne CLV.")
    elif args.cmd == "text":
        ok = send_message(args.text)
    else:
        day = args.date or datetime.now(LOCAL_TZ).date()
        ok = (notify_morning if args.cmd == "morning" else notify_evening)(day, args.db)
    print("Wysłano." if ok else "Nie wysłano (szczegóły wyżej).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
