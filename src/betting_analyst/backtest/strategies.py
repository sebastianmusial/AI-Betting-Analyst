"""Strategie backtestu: wybór zakładów na danych z chwili decyzji, potem CLV i rozliczenie.

Decyzja widzi tylko `DECISION_COLUMNS` (kursy przedmeczowe, Avg/Max, devig PSH…, konsensus, DC).
Zamknięcie Pinnacle (`p_close_*`) dołączamy dopiero po wyborze — wyłącznie do CLV.

Wspólna warstwa EV/podatek/Kelly: `decision/ev.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_analyst.config import Bookmaker, Strategy
from betting_analyst.decision.ev import AkoLeg, build_ako_proposals, effective_odds, expected_value, required_edge
from betting_analyst.models.devig import METHODS

ODDS_VARIANTS = {
    "avg": "Avg (realistyczny)",
    "max_soft": "MaxSoft (pośredni: max z B365/BW/WH/1XB)",
    "max": "Max rynkowy (optymistyczny)",
}

DECISION_COLUMNS = [
    "league",
    "match_id",
    "season",
    "date",
    "market",
    "outcome",
    "pin_open",
    "avg",
    "max",
    "max_soft",
    "p_cons",
    "p_dc",
    *[f"p_open_{m}" for m in METHODS],
]
OUTCOME_COLUMNS = ["match_id", "market", "outcome", "won"]

# Próg None = reguła ADR 0014 (min_edge, a przy kursie > high_odds_threshold min_edge_high_odds).
Threshold = float | None


@dataclass(frozen=True)
class SingleSpec:
    family: str
    prob: str
    odds: str
    stake_tax: float
    threshold: Threshold
    markets: tuple[str, ...] = ("1x2", "ou25")
    dc_filter_pp: float | None = None

    @property
    def label(self) -> str:
        return f"{self.family}|{self.odds}|{threshold_label(self.threshold)}"


@dataclass(frozen=True)
class AkoSpec:
    family: str
    prob: str
    odds: str
    n_legs: int
    threshold: Threshold
    markets: tuple[str, ...] = ("1x2", "ou25")
    stake_tax: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.family}|{self.odds}|{threshold_label(self.threshold)}"


def threshold_label(threshold: Threshold) -> str:
    return "ADR" if threshold is None else f"{threshold:.0%}"


def thresholds_for(odds: np.ndarray, threshold: Threshold, strategy: Strategy) -> np.ndarray:
    if threshold is not None:
        return np.full(len(odds), float(threshold))
    return np.array([required_edge(float(o), strategy) for o in odds])


def _candidates(
    decide: pd.DataFrame,
    prob: str,
    odds_col: str,
    stake_tax: float,
    threshold: Threshold,
    markets: tuple[str, ...],
    strategy: Strategy,
    dc_filter_pp: float | None = None,
) -> pd.DataFrame:
    """Selekcje spełniające próg EV po podatku; najlepsza (max EV) per mecz × rynek."""
    df = decide[decide["market"].isin(markets)].copy()
    df = df[np.isfinite(df[prob]) & np.isfinite(df[odds_col])]
    if dc_filter_pp is not None:
        df = df[np.isfinite(df["p_dc"]) & ((df[prob] - df["p_dc"]).abs() <= dc_filter_pp)]
    odds = df[odds_col].to_numpy(dtype=float)
    p = df[prob].to_numpy(dtype=float)
    odds_eff = effective_odds(odds, stake_tax)  # działa wektorowo (stake=None)
    df["odds"] = odds
    df["odds_eff"] = odds_eff
    df["stake_tax"] = stake_tax
    df["p"] = p
    df["ev"] = expected_value(p, odds_eff)
    df["threshold"] = thresholds_for(odds, threshold, strategy)
    df = df[df["ev"] >= df["threshold"]]
    df = df.sort_values("ev", ascending=False, kind="stable").drop_duplicates(["match_id", "market"])
    return df.sort_values(["date", "match_id", "market"], kind="stable")


def _attach_results(bets: pd.DataFrame, selections: pd.DataFrame, close_method: str) -> pd.DataFrame:
    """Dołącza wynik i zamknięcie (po decyzji). CLV = kurs efektywny × p_fair_zamknięcia − 1."""
    close_col = f"p_close_{close_method}"
    post = selections[[*OUTCOME_COLUMNS, close_col]].rename(columns={close_col: "p_close"})
    out = bets.merge(post, on=["match_id", "market", "outcome"], how="left", validate="one_to_one")
    out["profit"] = np.where(out["won"] == 1, out["odds_eff"] - 1.0, -1.0)
    out["clv"] = out["odds_eff"] * out["p_close"] - 1.0
    out["clv_pre_tax"] = out["odds"] * out["p_close"] - 1.0
    out["n_legs"] = 1
    return out


def single_bets(selections: pd.DataFrame, spec: SingleSpec, strategy: Strategy, close_method: str) -> pd.DataFrame:
    decide = selections[DECISION_COLUMNS]
    cand = _candidates(
        decide, spec.prob, spec.odds, spec.stake_tax, spec.threshold, spec.markets, strategy, spec.dc_filter_pp
    )
    out = _attach_results(cand, selections, close_method)
    out.insert(0, "strategy", spec.label)
    return out


def ako_bets(
    selections: pd.DataFrame,
    spec: AkoSpec,
    strategy: Strategy,
    bookmaker: Bookmaker,
    close_method: str,
) -> pd.DataFrame:
    """Jedno AKO dziennie (najlepsza kombinacja `n_legs` nóg z różnych meczów, `build_ako_proposals`).

    Nogi: EV ≥ próg na kursie bez podatku (AKO 0%), najlepsza noga per mecz.
    CLV kuponu = Π kursów × Π p_fair_zamknięcia − 1 (NaN, gdy brak zamknięcia którejś nogi).
    """
    decide = selections[DECISION_COLUMNS]
    legs = _candidates(decide, spec.prob, spec.odds, spec.stake_tax, spec.threshold, spec.markets, strategy)
    legs = _attach_results(legs, selections, close_method)
    ako_cfg = strategy.ako.model_copy(update={"min_legs": spec.n_legs, "max_legs": spec.n_legs, "max_proposals": 1})
    one_size = strategy.model_copy(update={"ako": ako_cfg})
    by_key = legs.set_index(["match_id", "market", "outcome"])
    rows = []
    for date, day in legs.groupby("date", sort=True):
        ako_legs = [
            AkoLeg(event_id=r.match_id, label=r.match_id, odds=r.odds, prob=r.p, market=r.market, selection=r.outcome)
            for r in day.itertuples(index=False)
        ]
        proposals = build_ako_proposals(ako_legs, bookmaker, one_size)
        if not proposals:
            continue
        best = proposals[0]
        info = [by_key.loc[(leg.event_id, leg.market, leg.selection)] for leg in best.legs]
        p_close = [float(i["p_close"]) for i in info]
        won = int(all(int(i["won"]) == 1 for i in info))
        rows.append(
            {
                "strategy": spec.label,
                "league": "+".join(sorted({str(i["league"]) for i in info})),
                "match_id": ";".join(leg.event_id for leg in best.legs),
                "season": str(info[0]["season"]),
                "date": date,
                "market": "ako",
                "outcome": ";".join(leg.selection for leg in best.legs),
                "odds": best.combined_odds,
                "odds_eff": best.odds_eff,
                "stake_tax": best.stake_tax,
                "p": best.combined_prob,
                "ev": best.ev,
                "threshold": float(np.max([i["threshold"] for i in info])),
                "won": won,
                "p_close": math.prod(p_close),
                "profit": best.odds_eff - 1.0 if won else -1.0,
                "clv": best.odds_eff * math.prod(p_close) - 1.0,
                "clv_pre_tax": best.combined_odds * math.prod(p_close) - 1.0,
                "n_legs": len(best.legs),
            }
        )
    return pd.DataFrame(rows)
