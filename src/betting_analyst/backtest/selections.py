"""Tabela selekcji do backtestu: jeden wiersz = mecz × rynek × wynik.

Kolumny kursów: `pin_open`, `pin_close`, `avg`, `max`, `max_soft` (+ `avg_close`, `max_close` dla POL),
prawdopodobieństwa: `p_open_{metoda}` (devig PSH…), `p_close_{metoda}` (devig PSCH… — tylko CLV),
`p_cons` (konsensus: multiplicative devig kursów Avg, wariant Kaunitza).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_analyst.models.devig import METHODS, devig
from betting_analyst.sources.football_data import OUTCOMES_1X2, OUTCOMES_OU

MARKETS: dict[str, tuple[str, ...]] = {"1x2": OUTCOMES_1X2, "ou25": OUTCOMES_OU}
ODDS_PREFIXES = ("pin_open", "pin_close", "avg", "max", "max_soft", "avg_close", "max_close")
ID_COLUMNS = ["league", "match_id", "season", "date", "home_team", "away_team", "home_goals", "away_goals"]


def devig_matrix(odds: np.ndarray, method: str) -> np.ndarray:
    """Devig wiersz po wierszu; wiersz z brakującym lub błędnym kursem (np. suma 1/kurs < 1) → NaN."""
    out = np.full(odds.shape, np.nan)
    for i, row in enumerate(odds):
        if not np.isfinite(row).all() or np.sum(1.0 / row) <= 1.0:
            continue
        try:
            out[i] = devig(row.tolist(), method)  # type: ignore[arg-type]
        except ValueError:
            continue
    return out


def outcome_flags(matches: pd.DataFrame, market: str) -> np.ndarray:
    hg = matches["home_goals"].to_numpy()
    ag = matches["away_goals"].to_numpy()
    if market == "1x2":
        return np.column_stack([hg > ag, hg == ag, hg < ag]).astype(int)
    total = hg + ag
    return np.column_stack([total > 2.5, total < 2.5]).astype(int)


def match_probabilities(matches: pd.DataFrame, market: str) -> dict[str, np.ndarray]:
    """Macierze prawdopodobieństw (n_meczów × n_wyników) dla wszystkich źródeł i metod."""
    outcomes = MARKETS[market]

    def odds(prefix: str) -> np.ndarray:
        cols = [f"{prefix}_{o}" for o in outcomes]
        if not all(c in matches.columns for c in cols):
            return np.full((len(matches), len(outcomes)), np.nan)
        return matches[cols].to_numpy(dtype=float)

    probs: dict[str, np.ndarray] = {}
    for method in METHODS:
        probs[f"p_open_{method}"] = devig_matrix(odds("pin_open"), method)
        probs[f"p_close_{method}"] = devig_matrix(odds("pin_close"), method)
    probs["p_cons"] = devig_matrix(odds("avg"), "multiplicative")
    return probs


def build_selections(matches: pd.DataFrame, markets: tuple[str, ...] = ("1x2", "ou25")) -> pd.DataFrame:
    """Rozwija tabelę meczów (wide) do selekcji (long) z prawdopodobieństwami i flagą `won`."""
    frames = []
    for market in markets:
        outcomes = MARKETS[market]
        probs = match_probabilities(matches, market)
        won = outcome_flags(matches, market)
        for j, outcome in enumerate(outcomes):
            sel = matches[ID_COLUMNS].copy()
            sel["market"] = market
            sel["outcome"] = outcome
            sel["won"] = won[:, j]
            for prefix in ODDS_PREFIXES:
                col = f"{prefix}_{outcome}"
                sel[prefix] = matches[col].to_numpy() if col in matches.columns else np.nan
            for name, mat in probs.items():
                sel[name] = mat[:, j]
            frames.append(sel)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["date", "match_id", "market", "outcome"], kind="stable").reset_index(drop=True)


def market_matrix(selections: pd.DataFrame, market: str, column: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Zwija selekcje z powrotem do macierzy (mecz × wynik) dla metryk kalibracji."""
    outcomes = list(MARKETS[market])
    sub = selections[selections["market"] == market]
    wide = sub.pivot_table(index="match_id", columns="outcome", values=column, aggfunc="first")[outcomes]
    return wide, wide.to_numpy(dtype=float)
