"""Symulacja bankrolla: ułamkowy Kelly z capem i dzienną ekspozycją (ADR 0002, 0014).

Chronologicznie po dacie meczu: stawki liczone od bankrolla na początek dnia, w kolejności
EV malejąco, przycięte do dziennego limitu, rozliczane na koniec dnia.
Wariant Betclic: podatek od singli wg miesięcznego limitu promocji (`stake_tax_rate`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_analyst.backtest.metrics import max_drawdown
from betting_analyst.config import Bookmaker
from betting_analyst.decision.ev import (
    TaxContext,
    apply_daily_exposure,
    effective_odds,
    expected_value,
    kelly_stake,
    stake_tax_rate,
)


@dataclass(frozen=True)
class BankrollResult:
    n_placed: int
    staked: float
    profit: float
    roi: float
    final_bankroll: float
    max_drawdown: float
    taxed_stake_share: float


def simulate_bankroll(
    bets: pd.DataFrame,
    *,
    kelly_fraction: float,
    max_stake_pct: float,
    daily_exposure_pct: float,
    bankroll: float = 1000.0,
    rounding: float = 1.0,
    promo_bookmaker: Bookmaker | None = None,
) -> BankrollResult:
    """`bets`: date, p, odds, odds_eff, ev, threshold, won. Przy `promo_bookmaker` (single bez podatku
    do limitu) podatek liczony dynamicznie; po przekroczeniu limitu zakład z EV < progu jest pomijany.
    """
    start = bankroll
    equity = [bankroll]
    staked_total = 0.0
    taxed_total = 0.0
    n_placed = 0
    month_stakes: dict[pd.Period, float] = {}
    if bets.empty:
        return BankrollResult(0, 0.0, 0.0, float("nan"), bankroll, 0.0, 0.0)
    for date, day in bets.sort_values("date", kind="stable").groupby("date", sort=True):
        day = day.sort_values("ev", ascending=False, kind="stable")
        month = pd.Timestamp(date).to_period("M")
        planned: list[tuple[float, float, int, bool]] = []  # (stawka, kurs efektywny, wygrana, opodatkowany)
        for r in day.itertuples(index=False):
            odds_eff = float(r.odds_eff)
            stake = kelly_stake(float(r.p), odds_eff, bankroll, kelly_fraction, max_stake_pct, rounding)
            taxed = False
            if promo_bookmaker is not None and stake > 0:
                used = month_stakes.get(month, 0.0) + sum(p[0] for p in planned)
                tax = stake_tax_rate(promo_bookmaker, "single", TaxContext(period_single_stakes_pln=used), stake)
                if tax > 0:
                    odds_eff = effective_odds(float(r.odds), tax)
                    if expected_value(float(r.p), odds_eff) < float(r.threshold):
                        continue
                    stake = kelly_stake(float(r.p), odds_eff, bankroll, kelly_fraction, max_stake_pct, rounding)
                    taxed = True
            planned.append((stake, odds_eff, int(r.won), taxed))
        stakes = apply_daily_exposure([p[0] for p in planned], bankroll, daily_exposure_pct, rounding=rounding)
        day_profit = 0.0
        for stake, (_, odds_eff, won, taxed) in zip(stakes, planned, strict=True):
            if stake <= 0:
                continue
            n_placed += 1
            staked_total += stake
            if taxed:
                taxed_total += stake
            day_profit += stake * (odds_eff - 1.0) if won else -stake
        month_stakes[month] = month_stakes.get(month, 0.0) + sum(stakes)
        bankroll += day_profit
        equity.append(bankroll)
    profit = bankroll - start
    return BankrollResult(
        n_placed=n_placed,
        staked=staked_total,
        profit=profit,
        roi=profit / staked_total if staked_total > 0 else float("nan"),
        final_bankroll=bankroll,
        max_drawdown=max_drawdown(np.array(equity)),
        taxed_stake_share=taxed_total / staked_total if staked_total > 0 else 0.0,
    )
