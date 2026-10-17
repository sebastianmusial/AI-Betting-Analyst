"""Adapter football-data.co.uk: wyniki historyczne (do Dixon-Coles) i kursy zamknięcia.

- ligi główne (E1, D2, N1): https://www.football-data.co.uk/mmz4281/{2526}/{E1}.csv
- ligi dodatkowe (POL):      https://www.football-data.co.uk/new/POL.csv (wszystkie sezony,
  tylko kursy zamknięcia 1X2 — brak O/U).

Uwaga: od sezonu 2026/27 w plikach brakuje kolumn Pinnacle (PSH/PSCH) — historyczny CLV
dla nowych meczów liczymy z własnych snapshotów (ledger), nie z football-data.
"""

from __future__ import annotations

import io
import logging
import time
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from betting_analyst.config import RAW_DIR, League

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk"
CACHE_DIR = RAW_DIR / "football_data"
CURRENT_SEASON_MAX_AGE_S = 12 * 3600

RESULT_COLUMNS = ["date", "home_team", "away_team", "home_goals", "away_goals"]

# Statystyki meczowe (tylko ligi "main"; POL.csv ich nie ma). Referee jest wyłącznie w E1.
STAT_COLUMNS = {
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellow",
    "AY": "away_yellow",
    "HR": "home_red",
    "AR": "away_red",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_target",
    "AST": "away_shots_target",
}


def season_code(start_year: int) -> str:
    """2025 -> '2526'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season_start(today: date | None = None) -> int:
    """Sezon startuje w lipcu (Ekstraklasa, Championship, 2. BL, Eredivisie)."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def recent_seasons(n: int, today: date | None = None) -> list[int]:
    start = current_season_start(today)
    return list(range(start - n + 1, start + 1))


def _download(url: str, path: Path, max_age_s: float | None) -> Path:
    """Pobiera plik, jeśli nie ma go w cache lub jest starszy niż max_age_s (None = nigdy)."""
    if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Pobieram %s", url)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def fetch_league_csvs(league: League, seasons: list[int], cache_dir: Path = CACHE_DIR) -> list[Path]:
    fd = league.football_data
    current = current_season_start()
    if fd.kind == "extra":
        path = cache_dir / f"{fd.code}.csv"
        return [_download(f"{BASE_URL}/new/{fd.code}.csv", path, CURRENT_SEASON_MAX_AGE_S)]
    paths = []
    for season in seasons:
        code = season_code(season)
        path = cache_dir / f"{fd.code}_{code}.csv"
        max_age = CURRENT_SEASON_MAX_AGE_S if season >= current else None
        try:
            paths.append(_download(f"{BASE_URL}/mmz4281/{code}/{fd.code}.csv", path, max_age))
        except httpx.HTTPError as exc:
            log.warning("Nie udało się pobrać %s %s: %s", fd.code, code, exc)
    return paths


def _read_csv(path: Path) -> pd.DataFrame:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    return pd.read_csv(io.StringIO(raw), on_bad_lines="skip")


def normalize_results(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Ujednolica kolumny obu formatów football-data do RESULT_COLUMNS (+ kursy zamknięcia)."""
    if kind == "extra":
        mapping = {
            "Home": "home_team",
            "Away": "away_team",
            "HG": "home_goals",
            "AG": "away_goals",
        }
    else:
        mapping = {
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            "FTHG": "home_goals",
            "FTAG": "away_goals",
        }
    closing = {
        "PSCH": "pin_close_home",
        "PSCD": "pin_close_draw",
        "PSCA": "pin_close_away",
        "PC>2.5": "pin_close_over",
        "PC<2.5": "pin_close_under",
    }
    wanted = ["Date", "Season", *mapping, *closing]
    out = df[[c for c in wanted if c in df.columns]].rename(columns={**mapping, **closing})
    out["date"] = pd.to_datetime(out["Date"], dayfirst=True, errors="coerce")
    keep = RESULT_COLUMNS + [c for c in closing.values() if c in out.columns]
    if "Season" in out.columns:
        keep.append("Season")
    out = out[keep].dropna(subset=RESULT_COLUMNS)
    out["home_goals"] = out["home_goals"].astype(int)
    out["away_goals"] = out["away_goals"].astype(int)
    return out.sort_values("date").reset_index(drop=True)


def normalize_match_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Wyniki + statystyki (rogi, kartki, faule, strzały, sędzia) z pliku ligi "main".

    Kolumny statystyk, których brak w pliku, są pomijane; wiersze bez rogów i kartek odpadają.
    """
    base = normalize_results(df, "main")
    named = df.rename(columns={"HomeTeam": "home_team", "AwayTeam": "away_team"}).copy()
    named["date"] = pd.to_datetime(named["Date"], dayfirst=True, errors="coerce")
    stats = [c for c in STAT_COLUMNS if c in named.columns]
    extra = named[["date", "home_team", "away_team", *stats]].rename(columns=STAT_COLUMNS)
    if "Referee" in named.columns:
        extra["referee"] = named["Referee"].astype("string").str.strip()
    out = base.merge(extra, on=["date", "home_team", "away_team"], how="left")
    required = [c for c in ("home_corners", "away_corners", "home_yellow", "away_yellow") if c in out.columns]
    out = out.dropna(subset=required)
    for col in STAT_COLUMNS.values():
        if col in out.columns:
            out[col] = out[col].fillna(0).astype(int)
    return out.sort_values("date").reset_index(drop=True)


def load_results(league: League, n_seasons: int = 3, today: date | None = None) -> pd.DataFrame:
    """Rozegrane mecze z ostatnich n sezonów (ze świeżym cache dla bieżącego sezonu)."""
    seasons = recent_seasons(n_seasons, today)
    frames = []
    for path in fetch_league_csvs(league, seasons):
        frames.append(normalize_results(_read_csv(path), league.football_data.kind))
    if not frames:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    if league.football_data.kind == "extra":
        first = pd.Timestamp(year=seasons[0], month=7, day=1)
        df = df[df["date"] >= first]
    return df.drop(columns=["Season"], errors="ignore").reset_index(drop=True)


def load_match_stats(league: League, n_seasons: int = 3, today: date | None = None) -> pd.DataFrame:
    """Mecze ze statystykami (rogi, kartki, faule, strzały, sędzia) do modeli liczebności.

    Ligi "extra" (POL) nie mają statystyk w football-data, więc zwracamy pusty DataFrame.
    """
    if league.football_data.kind == "extra":
        log.info("Brak statystyk meczowych w football-data dla %s", league.football_data.code)
        return pd.DataFrame(columns=[*RESULT_COLUMNS, *STAT_COLUMNS.values()])
    frames = [normalize_match_stats(_read_csv(p)) for p in fetch_league_csvs(league, recent_seasons(n_seasons, today))]
    if not frames:
        return pd.DataFrame(columns=[*RESULT_COLUMNS, *STAT_COLUMNS.values()])
    return pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
