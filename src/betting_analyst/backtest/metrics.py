"""Metryki kalibracji, CLV i wyników (ADR 0015)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

EPS = 1e-15


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Wieloklasowy Brier: średnia po meczach z sumy (p − y)² po wynikach."""
    return float(np.mean(np.sum((probs - outcomes) ** 2, axis=1)))


def log_loss(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean(per_match_log_loss(probs, outcomes)))


def per_match_log_loss(probs: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    p_true = np.sum(probs * outcomes, axis=1)
    return -np.log(np.clip(p_true, EPS, 1.0))


def rps(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Ranked Probability Score dla wyników uporządkowanych (1X2: gosp., remis, gość)."""
    k = probs.shape[1]
    cum_p = np.cumsum(probs, axis=1)[:, :-1]
    cum_y = np.cumsum(outcomes, axis=1)[:, :-1]
    return float(np.mean(np.sum((cum_p - cum_y) ** 2, axis=1) / (k - 1)))


def calibration_table(p: np.ndarray, y: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Krzywa kalibracji: biny po prawdopodobieństwie, średnie p vs częstość."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(p)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p[mask], edges) - 1, 0, bins - 1)
    df = pd.DataFrame({"bin": idx, "p": p[mask], "y": y[mask]})
    out = df.groupby("bin").agg(n=("p", "size"), p_mean=("p", "mean"), freq=("y", "mean")).reset_index()
    out["bin_lo"] = edges[out["bin"]]
    out["bin_hi"] = edges[out["bin"] + 1]
    return out[["bin_lo", "bin_hi", "n", "p_mean", "freq"]]


def paired_test(loss_a: np.ndarray, loss_b: np.ndarray) -> tuple[float, float, float]:
    """Sparowany t-test różnicy strat (a − b). Zwraca (średnia różnica, t, p dwustronne)."""
    diff = np.asarray(loss_a) - np.asarray(loss_b)
    diff = diff[np.isfinite(diff)]
    if len(diff) < 3 or np.allclose(diff, diff[0]):
        return float(np.mean(diff)) if len(diff) else float("nan"), float("nan"), float("nan")
    res = stats.ttest_1samp(diff, 0.0)
    return float(np.mean(diff)), float(res.statistic), float(res.pvalue)


@dataclass(frozen=True)
class ClvStats:
    n: int
    mean: float
    mean_log: float
    t: float
    p_one_sided: float
    share_beat: float


def clv_stats(clv: np.ndarray) -> ClvStats:
    """CLV: średnia, średnia log(1+clv), t-test jednostronny H1: średnia > 0, odsetek > 0."""
    x = np.asarray(clv, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return ClvStats(0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    mean_log = float(np.mean(np.log1p(x)))
    if len(x) < 3 or np.allclose(x, x[0]):
        return ClvStats(len(x), float(np.mean(x)), mean_log, float("nan"), float("nan"), float(np.mean(x > 0)))
    res = stats.ttest_1samp(x, 0.0, alternative="greater")
    return ClvStats(len(x), float(np.mean(x)), mean_log, float(res.statistic), float(res.pvalue), float(np.mean(x > 0)))


def roi_with_ci(profit: np.ndarray, stake: np.ndarray, n_boot: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """ROI = Σ zysk / Σ stawka z bootstrapowym 95% CI (resampling zakładów)."""
    profit = np.asarray(profit, dtype=float)
    stake = np.asarray(stake, dtype=float)
    if len(profit) == 0 or stake.sum() <= 0:
        return float("nan"), float("nan"), float("nan")
    roi = float(profit.sum() / stake.sum())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(profit), size=(n_boot, len(profit)))
    boot = profit[idx].sum(axis=1) / stake[idx].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return roi, float(lo), float(hi)


def max_drawdown(equity: np.ndarray) -> float:
    """Maksymalny spadek od szczytu, jako ułamek szczytu."""
    equity = np.asarray(equity, dtype=float)
    if len(equity) == 0:
        return 0.0
    peaks = np.maximum.accumulate(equity)
    return float(np.max((peaks - equity) / peaks))


def holm(pvalues: list[float]) -> list[float]:
    """Korekta Holma–Bonferroniego (p skorygowane, monotoniczne)."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(np.where(np.isfinite(p), p, np.inf))
    adjusted = np.full(m, np.nan)
    running = 0.0
    for rank, i in enumerate(order):
        if not np.isfinite(p[i]):
            continue
        running = max(running, min(1.0, (m - rank) * p[i]))
        adjusted[i] = running
    return adjusted.tolist()
