"""Ładowanie konfiguracji (config/*.yaml) i ścieżek projektu."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SCANS_DIR = DATA_DIR / "scans"
MANUAL_ODDS_DIR = DATA_DIR / "manual_odds"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "betting.duckdb"

DevigMethod = Literal["multiplicative", "power", "shin"]


class WinningsTax(BaseModel):
    rate: float = 0.10
    threshold_pln: float = 2280


class SingleTaxRule(BaseModel):
    stake_tax: float
    free_stake_limit_pln: float | None = None
    stake_tax_above: float | None = None
    period: str | None = None


class AkoTaxRule(BaseModel):
    stake_tax: float


class Bookmaker(BaseModel):
    key: str = ""
    name: str
    stake_tax: float = 0.12
    promo: str | None = None
    single: SingleTaxRule | None = None
    ako: AkoTaxRule | None = None
    all_free_if_ako_share_gte: float | None = None
    odds_api_proxies: list[str] = Field(default_factory=list)
    verified_at: str | None = None
    active: bool = True  # czy właściciel gra u tego buka (ADR 0021: domyślnie tylko STS)


class BookmakersConfig(BaseModel):
    winnings_tax: WinningsTax = WinningsTax()
    bookmakers: dict[str, Bookmaker]
    proxy_stake_tax: float = 0.12
    reference_bookmakers: list[str] = Field(default_factory=lambda: ["pinnacle"])


class FootballDataSource(BaseModel):
    kind: Literal["main", "extra"]
    code: str


class League(BaseModel):
    key: str = ""
    name: str
    odds_api_key: str
    football_data: FootballDataSource
    sts_tournament_id: int | None = None  # id turnieju w feedzie STS (temat t_{id}_pl)


class AkoConfig(BaseModel):
    min_legs: int = 2
    max_legs: int = 3
    max_proposals: int = 3


class OddsApiConfig(BaseModel):
    regions: list[str] = Field(default_factory=lambda: ["eu"])
    markets: list[str] = Field(default_factory=lambda: ["h2h", "totals"])
    daily_closing_credits: int = 10  # limit kredytów na snapshoty zamknięcia dziennie (budget.py)
    reserve_credits: int = 40  # poniżej tylu pozostałych kredytów nie robimy zamknięć (zostaje na skany)


class DixonColesConfig(BaseModel):
    seasons: int = 3
    xi: float = 0.0018


class Strategy(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    bankroll_pln: float
    min_edge: float = 0.03
    min_edge_high_odds: float = 0.05
    high_odds_threshold: float = 3.0
    kelly_fraction: float = 0.25
    kelly_fraction_ako: float = 0.125
    max_stake_pct: float = 0.015
    daily_exposure_pct: float = 0.05
    stake_rounding_pln: float = 1
    model_disagreement_pp: float = 0.08
    devig_method: DevigMethod = "power"
    reference_bookmaker: str = "pinnacle"
    ako: AkoConfig = AkoConfig()
    odds_api: OddsApiConfig = OddsApiConfig()
    dixon_coles: DixonColesConfig = DixonColesConfig()
    # Tryb „Typy dnia” (ADR 0021): ranking po edge przed podatkiem, podatek informacyjnie.
    default_bookmaker: str = "sts"
    daily_picks: int = 5
    pick_flat_stake_pct: float = 0.005  # stawka dla typów bez przewagi po podatku
    model_only_min_edge: float = 0.08  # próg edge dla rynków wycenianych tylko modelem
    model_weight: float = 0.5  # model-only: p_fair = w·p_model + (1−w)·p_STS (zakotwiczenie w rynku)
    count_totals_enabled: bool = False  # sumy rogów/kartek: model ≈ średnia ligi (kalibracja) → domyślnie off
    model_only_max_odds: float = 3.5  # model-only: wyższe kursy pomijamy (model najmniej pewny w ogonach)
    max_model_market_gap: float = 0.15  # |p_model − p_STS| powyżej → typ odrzucony (błąd modelu)
    morning_days: int = 2
    leagues: dict[str, League]


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_bookmakers(path: Path = CONFIG_DIR / "bookmakers.yaml") -> BookmakersConfig:
    cfg = BookmakersConfig.model_validate(_read_yaml(path))
    for key, bm in cfg.bookmakers.items():
        bm.key = key
    return cfg


@lru_cache
def load_strategy(path: Path = CONFIG_DIR / "strategy.yaml") -> Strategy:
    cfg = Strategy.model_validate(_read_yaml(path))
    for key, league in cfg.leagues.items():
        league.key = key
    return cfg


@lru_cache
def load_team_aliases(
    path: Path = CONFIG_DIR / "team_aliases.yaml",
) -> dict[str, list[str]]:
    """Mapa: nazwa kanoniczna (jak w football-data) -> lista aliasów z innych źródeł."""
    if not path.exists():
        return {}
    raw = _read_yaml(path)
    return {canonical: list(aliases or []) for canonical, aliases in raw.items()}


def get_env(name: str) -> str | None:
    load_dotenv(PROJECT_ROOT / ".env")
    value = os.environ.get(name, "").strip()
    return value or None
