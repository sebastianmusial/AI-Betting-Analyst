"""Runner F2: dane → kalibracja → walk-forward DC → siatka strategii → protokół go/no-go → tabele.

Uruchomienie: `uv run ba-backtest` (wyniki: data/backtest/*.csv, docs/experiments/2026-10-f2-backtest-tables.md,
docs/experiments/img/*.png). Interpretację i werdykt piszemy ręcznie w docs/experiments/2026-10-f2-backtest.md.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd

from betting_analyst.backtest.metrics import (
    brier,
    calibration_table,
    clv_stats,
    holm,
    log_loss,
    paired_test,
    per_match_log_loss,
    roi_with_ci,
    rps,
)
from betting_analyst.backtest.selections import MARKETS, build_selections, market_matrix
from betting_analyst.backtest.simulate import simulate_bankroll
from betting_analyst.backtest.strategies import ODDS_VARIANTS, AkoSpec, SingleSpec, ako_bets, single_bets
from betting_analyst.backtest.walkforward import walk_forward_dc
from betting_analyst.config import DATA_DIR, PROJECT_ROOT, load_bookmakers, load_strategy
from betting_analyst.models.devig import METHODS
from betting_analyst.sources.football_data import load_history

log = logging.getLogger(__name__)

OUT_DIR = DATA_DIR / "backtest"
EXPERIMENTS_DIR = PROJECT_ROOT / "docs" / "experiments"
TABLES_PATH = EXPERIMENTS_DIR / "2026-10-f2-backtest-tables.md"
IMG_DIR = EXPERIMENTS_DIR / "img"

MAIN_LEAGUES = ("championship", "bundesliga2", "eredivisie")
CLOSING_ONLY_LEAGUES = ("ekstraklasa",)
DC_SEASONS = list(range(2012, 2026))  # 2012–2014 tylko rozgrzewka DC
EVAL_SEASONS = list(range(2015, 2026))
DEV_SEASONS = [f"{y}/{y + 1}" for y in range(2015, 2022)]
HOLDOUT_SEASONS = [f"{y}/{y + 1}" for y in range(2022, 2026)]
THRESHOLDS: list[float | None] = [0.0, 0.01, 0.02, 0.03, 0.05, 0.07, 0.10, None]
MIN_BETS = 100
ALPHA = 0.05


# --- dane -------------------------------------------------------------------------------


def build_dataset(refresh: bool = False) -> pd.DataFrame:
    """Selekcje wszystkich lig z p_dc z walk-forward; cache parquet."""
    path = OUT_DIR / "selections.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    strategy = load_strategy()
    frames = []
    for key in (*MAIN_LEAGUES, *CLOSING_ONLY_LEAGUES):
        league = strategy.leagues[key]
        hist = load_history(league, DC_SEASONS)
        log.info("%s: %d meczów", key, len(hist))
        dc = walk_forward_dc(
            hist,
            key,
            xi=strategy.dixon_coles.xi,
            window_days=strategy.dixon_coles.seasons * 365,
            predict_from=pd.Timestamp(EVAL_SEASONS[0], 7, 1),
        )
        labels = {f"{y}/{y + 1}" for y in EVAL_SEASONS}
        eval_matches = hist[hist["season"].isin(labels)]
        markets = ("1x2", "ou25") if key in MAIN_LEAGUES else ("1x2",)
        sel = build_selections(eval_matches, markets)
        dc_long = dc.melt(
            id_vars=["match_id", "train_max_date", "fit_date"],
            value_vars=[c for c in dc.columns if c.startswith("dc_")],
            var_name="outcome",
            value_name="p_dc",
        )
        dc_long["outcome"] = dc_long["outcome"].str.removeprefix("dc_")
        sel = sel.merge(dc_long, on=["match_id", "outcome"], how="left", validate="many_to_one")
        frames.append(sel)
    data = pd.concat(frames, ignore_index=True)
    data["period"] = np.where(data["season"].isin(HOLDOUT_SEASONS), "holdout", "dev")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data.to_parquet(path, index=False)
    return data


# --- kalibracja -------------------------------------------------------------------------


def _scores(probs: np.ndarray, outcomes: np.ndarray, market: str) -> dict[str, float]:
    return {
        "n": len(probs),
        "brier": brier(probs, outcomes),
        "log_loss": log_loss(probs, outcomes),
        "rps": rps(probs, outcomes) if market == "1x2" else float("nan"),
    }


def _matrices(sel: pd.DataFrame, market: str, columns: Iterable[str]) -> dict[str, np.ndarray]:
    """Macierze (mecz × wynik) na wspólnym zbiorze meczów, gdzie wszystkie kolumny są dostępne."""
    mats = {}
    index = None
    for col in [*columns, "won"]:
        wide, _ = market_matrix(sel, market, col)
        mats[col] = wide
        index = wide.index if index is None else index.intersection(wide.index)
    out = {col: wide.loc[index].to_numpy(dtype=float) for col, wide in mats.items()}
    mask = np.all([np.isfinite(m).all(axis=1) for m in out.values()], axis=0)
    return {col: m[mask] for col, m in out.items()}


def devig_calibration(sel: pd.DataFrame, side: str) -> pd.DataFrame:
    """Brier / log loss / RPS metod devig (side = open | close) per liga, rynek i okres."""
    rows = []
    cols = [f"p_{side}_{m}" for m in METHODS]
    for (league, market, period), group in _groups(sel):
        mats = _matrices(group, market, cols)
        if len(mats["won"]) == 0:
            continue
        for method, col in zip(METHODS, cols, strict=True):
            rows.append(
                {
                    "league": league,
                    "market": market,
                    "period": period,
                    "method": method,
                    **_scores(mats[col], mats["won"], market),
                }
            )
    return pd.DataFrame(rows)


def _groups(sel: pd.DataFrame):
    """(liga, rynek, okres) plus agregaty 'ALL' po ligach i 'all' po okresach."""
    for market in MARKETS:
        msel = sel[sel["market"] == market]
        if msel.empty:
            continue
        for league in [*sorted(msel["league"].unique()), "ALL"]:
            lsel = msel if league == "ALL" else msel[msel["league"] == league]
            for period in ("dev", "holdout", "all"):
                psel = lsel if period == "all" else lsel[lsel["period"] == period]
                if not psel.empty:
                    yield (league, market, period), psel


def method_pairs(sel: pd.DataFrame, side: str, period: str = "dev") -> pd.DataFrame:
    """Sparowane porównania log loss metod devig (ALL ligi)."""
    rows = []
    for market in MARKETS:
        msel = sel[(sel["market"] == market) & (sel["period"] == period)]
        if msel.empty:
            continue
        cols = [f"p_{side}_{m}" for m in METHODS]
        mats = _matrices(msel, market, cols)
        losses = {m: per_match_log_loss(mats[c], mats["won"]) for m, c in zip(METHODS, cols, strict=True)}
        for i, a in enumerate(METHODS):
            for b in METHODS[i + 1 :]:
                diff, t, p = paired_test(losses[a], losses[b])
                rows.append(
                    {"market": market, "pair": f"{a} − {b}", "n": len(losses[a]), "mean_diff": diff, "t": t, "p": p}
                )
    return pd.DataFrame(rows)


def dc_vs_market(sel: pd.DataFrame, method: str, side: str) -> pd.DataFrame:
    """DC vs zdewigowany rynek na wspólnych meczach (gdzie DC ma prognozę)."""
    rows = []
    market_col = f"p_{side}_{method}"
    for (league, market, period), group in _groups(sel):
        mats = _matrices(group, market, [market_col, "p_dc"])
        if len(mats["won"]) < 30:
            continue
        s_m = _scores(mats[market_col], mats["won"], market)
        s_dc = _scores(mats["p_dc"], mats["won"], market)
        diff, _t, p = paired_test(
            per_match_log_loss(mats["p_dc"], mats["won"]), per_match_log_loss(mats[market_col], mats["won"])
        )
        rows.append(
            {
                "league": league,
                "market": market,
                "period": period,
                "n": s_m["n"],
                "ll_market": s_m["log_loss"],
                "ll_dc": s_dc["log_loss"],
                "rps_market": s_m["rps"],
                "rps_dc": s_dc["rps"],
                "brier_market": s_m["brier"],
                "brier_dc": s_dc["brier"],
                "ll_diff_dc_minus_mkt": diff,
                "p": p,
            }
        )
    return pd.DataFrame(rows)


def plot_calibration(sel: pd.DataFrame, method: str) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    main = sel[sel["league"].isin(MAIN_LEAGUES) & (sel["market"] == "1x2")]
    pol = sel[sel["league"].isin(CLOSING_ONLY_LEAGUES)]
    panels = [
        ("Pinnacle przedmeczowy (E1/D2/N1), 1X2", main, [f"p_open_{m}" for m in METHODS]),
        ("Dixon-Coles walk-forward vs rynek (E1/D2/N1)", main, [f"p_open_{method}", "p_dc"]),
        ("Ekstraklasa: zamknięcie Pinnacle + DC", pol, [f"p_close_{method}", "p_dc"]),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (title, data, cols) in zip(axes, panels, strict=True):
        ax.plot([0, 1], [0, 1], color="0.6", lw=1, ls="--")
        for col in cols:
            sub = data[np.isfinite(data[col])]
            tab = calibration_table(sub[col].to_numpy(), sub["won"].to_numpy(), bins=10)
            tab = tab[tab["n"] >= 30]
            ax.plot(tab["p_mean"], tab["freq"], marker="o", ms=3, label=col)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("prognoza")
        ax.set_ylabel("częstość")
        ax.legend(fontsize=8)
    fig.tight_layout()
    path = IMG_DIR / "f2-calibration.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return [str(path.relative_to(EXPERIMENTS_DIR))]


# --- strategie --------------------------------------------------------------------------


def strategy_specs(method: str) -> list[SingleSpec | AkoSpec]:
    p_mkt = f"p_open_{method}"
    specs: list[SingleSpec | AkoSpec] = []
    for thr in THRESHOLDS:
        for odds in ODDS_VARIANTS:
            specs.append(SingleSpec("A_single_tax12", p_mkt, odds, 0.12, thr))
            specs.append(SingleSpec("B_single_tax0", p_mkt, odds, 0.0, thr))
            specs.append(AkoSpec("C2_ako2_tax0", p_mkt, odds, 2, thr))
            specs.append(AkoSpec("C3_ako3_tax0", p_mkt, odds, 3, thr))
        for odds in ("max_soft", "max"):
            specs.append(SingleSpec("D_kaunitz_tax12", "p_cons", odds, 0.12, thr))
            specs.append(SingleSpec("D_kaunitz_tax0", "p_cons", odds, 0.0, thr))
        for odds in ("avg", "max_soft"):
            specs.append(SingleSpec("E1_dc_tax12", "p_dc", odds, 0.12, thr))
            specs.append(SingleSpec("E1_dc_tax0", "p_dc", odds, 0.0, thr))
            specs.append(SingleSpec("E2_mkt+dcfilter_tax12", p_mkt, odds, 0.12, thr, dc_filter_pp=0.08))
            specs.append(SingleSpec("E2_mkt+dcfilter_tax0", p_mkt, odds, 0.0, thr, dc_filter_pp=0.08))
    return specs


def cluster_ids(bets: pd.DataFrame) -> pd.Series:
    """Klaster = mecz (dla AKO pierwsza noga); zakłady 1X2 i O/U z jednego meczu są skorelowane."""
    return bets["match_id"].str.split(";").str[0]


def clustered_clv(bets: pd.DataFrame):
    if bets.empty:
        return clv_stats(np.array([]))
    return clv_stats(bets.assign(cluster=cluster_ids(bets)).groupby("cluster")["clv"].mean().to_numpy())


def week_block_bootstrap(bets: pd.DataFrame, n_boot: int = 2000, seed: int = 11) -> tuple[float, float]:
    """95% CI średniego CLV z bootstrapu blokowego po tygodniach (korelacja w obrębie kolejki)."""
    if len(bets) < 3:
        return float("nan"), float("nan")
    weeks = bets["date"].dt.to_period("W-THU")
    groups = [g["clv"].dropna().to_numpy() for _, g in bets.groupby(weeks)]
    groups = [g for g in groups if len(g)]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        sample = np.concatenate([groups[i] for i in pick])
        means.append(sample.mean())
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def summarize_bets(bets: pd.DataFrame, spec: SingleSpec | AkoSpec, period: str, promo) -> dict:
    strategy = load_strategy()
    roi, lo, hi = roi_with_ci(bets["profit"].to_numpy(), np.ones(len(bets)))
    raw = clv_stats(bets["clv"].to_numpy())
    clustered = clustered_clv(bets)
    is_ako = isinstance(spec, AkoSpec)
    kelly = simulate_bankroll(
        bets,
        kelly_fraction=strategy.kelly_fraction_ako if is_ako else strategy.kelly_fraction,
        max_stake_pct=strategy.max_stake_pct,
        daily_exposure_pct=strategy.daily_exposure_pct,
        bankroll=strategy.bankroll_pln,
        rounding=strategy.stake_rounding_pln,
        promo_bookmaker=promo if spec.family.startswith("B_") else None,
    )
    return {
        "label": spec.label,
        "family": spec.family,
        "odds": spec.odds,
        "threshold": "ADR" if spec.threshold is None else spec.threshold,
        "period": period,
        "n": len(bets),
        "avg_odds": float(bets["odds"].mean()) if len(bets) else float("nan"),
        "roi": roi,
        "roi_lo": lo,
        "roi_hi": hi,
        "clv_n": raw.n,
        "clv_mean": raw.mean,
        "clv_log": raw.mean_log,
        "clv_pre_tax": float(bets["clv_pre_tax"].mean()) if len(bets) else float("nan"),
        "share_beat": raw.share_beat,
        "t": clustered.t,
        "p": clustered.p_one_sided,
        "kelly_n": kelly.n_placed,
        "kelly_final": kelly.final_bankroll,
        "kelly_roi": kelly.roi,
        "kelly_dd": kelly.max_drawdown,
        "kelly_taxed_share": kelly.taxed_stake_share,
    }


def run_strategies(sel: pd.DataFrame, method: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    strategy = load_strategy()
    betclic = load_bookmakers().bookmakers["betclic"]
    main = sel[sel["league"].isin(MAIN_LEAGUES)]
    rows = []
    all_bets: dict[str, pd.DataFrame] = {}
    for spec in strategy_specs(method):
        if isinstance(spec, AkoSpec):
            bets = ako_bets(main, spec, strategy, betclic, method)
        else:
            bets = single_bets(main, spec, strategy, method)
        all_bets[spec.label] = bets
        for period in ("dev", "holdout", "all"):
            if bets.empty or period == "all":
                part = bets
            else:
                seasons = DEV_SEASONS if period == "dev" else HOLDOUT_SEASONS
                part = bets[bets["season"].isin(seasons)]
            if part.empty:
                rows.append(
                    {
                        "label": spec.label,
                        "family": spec.family,
                        "odds": spec.odds,
                        "period": period,
                        "n": 0,
                        "threshold": "ADR" if spec.threshold is None else spec.threshold,
                    }
                )
                continue
            rows.append(summarize_bets(part, spec, period, betclic))
    return pd.DataFrame(rows), all_bets


def go_no_go(results: pd.DataFrame, odds_variants: tuple[str, ...]) -> pd.DataFrame:
    """Protokół: próg wybrany na dev (max średniego CLV przy n ≥ MIN_BETS), jeden test na holdoucie, Holm."""
    rows = []
    for (family, odds), group in results.groupby(["family", "odds"], sort=True):
        if odds not in odds_variants:
            continue
        dev = group[(group["period"] == "dev") & (group["n"] >= MIN_BETS)]
        if dev.empty or dev["clv_mean"].isna().all():
            rows.append({"family": family, "odds": odds, "threshold": None, "dev_n": 0})
            continue
        best = dev.loc[dev["clv_mean"].idxmax()]
        hold = group[(group["period"] == "holdout") & (group["label"] == best["label"])]
        h = hold.iloc[0] if not hold.empty else None
        rows.append(
            {
                "family": family,
                "odds": odds,
                "threshold": best["threshold"],
                "dev_n": int(best["n"]),
                "dev_clv": best["clv_mean"],
                "hold_n": int(h["n"]) if h is not None else 0,
                "hold_clv": h["clv_mean"] if h is not None else float("nan"),
                "hold_share_beat": h["share_beat"] if h is not None else float("nan"),
                "hold_roi": h["roi"] if h is not None else float("nan"),
                "hold_p": h["p"] if h is not None else float("nan"),
            }
        )
    out = pd.DataFrame(rows)
    if "hold_p" in out:
        out["hold_p_holm"] = holm(out["hold_p"].fillna(1.0).tolist())
        out["pass"] = (out["hold_clv"] > 0) & (out["hold_p_holm"] < ALPHA) & (out["hold_n"] >= MIN_BETS)
    return out


def adr_threshold_protocol(results: pd.DataFrame, odds_variants: tuple[str, ...]) -> pd.DataFrame:
    """Test wtórny bez strojenia: progi ADR 0014 ustalone przed F2, holdout, korekta Holma."""
    hold = results[
        (results["period"] == "holdout")
        & (results["threshold"].astype(str) == "ADR")
        & (results["odds"].isin(odds_variants))
    ].copy()
    hold = hold[["family", "odds", "n", "clv_mean", "share_beat", "roi", "p"]].rename(
        columns={
            "n": "hold_n",
            "clv_mean": "hold_clv",
            "share_beat": "hold_share_beat",
            "roi": "hold_roi",
            "p": "hold_p",
        }
    )
    hold["hold_p_holm"] = holm(hold["hold_p"].fillna(1.0).tolist())
    hold["pass"] = (hold["hold_clv"] > 0) & (hold["hold_p_holm"] < ALPHA) & (hold["hold_n"] >= MIN_BETS)
    return hold.reset_index(drop=True)


def haircut_sensitivity(sel: pd.DataFrame, method: str) -> pd.DataFrame:
    """Jak daleko od rynkowego Max może być kurs polskiego buka, by przewaga (CLV) przetrwała?

    Kurs zagrania = Max × (1 − h), podatek 0% (Betclic do limitu, AKO), 6% (Betclic powyżej limitu), 12%.
    Próg ADR 0014, single.
    """
    strategy = load_strategy()
    main = sel[sel["league"].isin(MAIN_LEAGUES)]
    rows = []
    for h in (0.0, 0.01, 0.02, 0.03, 0.05):
        shifted = main.assign(max=main["max"] * (1 - h))
        for tax in (0.0, 0.06, 0.12):
            spec = SingleSpec(f"haircut_{h:.0%}_tax{tax:.0%}", f"p_open_{method}", "max", tax, None)
            bets = single_bets(shifted, spec, strategy, method)
            for period, seasons in (("holdout", HOLDOUT_SEASONS), ("all", None)):
                part = bets if seasons is None else bets[bets["season"].isin(seasons)]
                st = clv_stats(part["clv"].to_numpy())
                st_cl = clustered_clv(part)
                roi, lo, hi = roi_with_ci(part["profit"].to_numpy(), np.ones(len(part)))
                rows.append(
                    {
                        "haircut": h,
                        "tax": tax,
                        "period": period,
                        "n": len(part),
                        "clv_mean": st.mean,
                        "share_beat": st.share_beat,
                        "p_clustered": st_cl.p_one_sided,
                        "roi": roi,
                        "roi_lo": lo,
                        "roi_hi": hi,
                    }
                )
    return pd.DataFrame(rows)


def data_quality(sel: pd.DataFrame) -> pd.DataFrame:
    """Diagnostyka danych per sezon: arbitraże w kolumnie Max i marża Pinnacle (otwarcie vs zamknięcie)."""
    rows = []
    main = sel[sel["league"].isin(MAIN_LEAGUES) & (sel["market"] == "1x2")]
    for season, g in main.groupby("season"):
        inv = g.assign(**{c: 1.0 / g[c] for c in ("max", "pin_open", "pin_close", "avg")})
        per_match = inv.groupby("match_id")[["max", "pin_open", "pin_close", "avg"]].sum(min_count=3)
        rows.append(
            {
                "season": season,
                "matches": len(per_match),
                "max_arb_share": float((per_match["max"] < 1.0).mean()),
                "pin_open_margin_median": float((per_match["pin_open"] - 1).median()),
                "pin_close_margin_median": float((per_match["pin_close"] - 1).median()),
                "avg_margin_median": float((per_match["avg"] - 1).median()),
            }
        )
    return pd.DataFrame(rows)


def arb_flags(sel: pd.DataFrame) -> pd.DataFrame:
    """Flaga mecz × rynek: suma 1/Max < 1 (arbitraż między bukmacherami → Max często nieaktualny/błędny)."""
    inv = sel.assign(inv=1.0 / sel["max"]).groupby(["match_id", "market"])["inv"].sum(min_count=2)
    return (inv < 1.0).rename("max_arb").reset_index()


ROBUST_LABELS = ("B_single_tax0|max|ADR", "B_single_tax0|max_soft|ADR", "C2_ako2_tax0|max|ADR")


def robustness(sel: pd.DataFrame, all_bets: dict[str, pd.DataFrame], method: str) -> pd.DataFrame:
    """Holdout kluczowych strategii: pełny, bez meczów z arbitrażem w Max, bez górnych 5% CLV; CI blokowe."""
    flags = arb_flags(sel[sel["league"].isin(MAIN_LEAGUES)])
    rows = []
    for label in ROBUST_LABELS:
        bets = all_bets.get(label, pd.DataFrame())
        if bets.empty:
            continue
        hold = bets[bets["season"].isin(HOLDOUT_SEASONS)].copy()
        if label.startswith("C2"):
            # rynek nogi nie jest zapisany w kuponie — flagujemy po meczu (arbitraż w dowolnym rynku)
            arb_matches = set(flags.loc[flags["max_arb"], "match_id"])
            hold["max_arb"] = [any(m in arb_matches for m in ms) for ms in hold["match_id"].str.split(";")]
        else:
            hold = hold.merge(flags, on=["match_id", "market"], how="left")
            hold["max_arb"] = hold["max_arb"].fillna(False).astype(bool)
        cut = hold["clv"].quantile(0.95)
        variants = {
            "holdout, wszystkie": hold,
            "holdout, bez arbitraży w Max": hold[~hold["max_arb"]],
            "holdout, bez górnych 5% CLV": hold[hold["clv"] <= cut],
        }
        for name, part in variants.items():
            st = clustered_clv(part)
            lo, hi = week_block_bootstrap(part)
            rows.append(
                {
                    "strategy": label,
                    "variant": name,
                    "n": len(part),
                    "clv_mean": float(part["clv"].mean()) if len(part) else float("nan"),
                    "ci_lo": lo,
                    "ci_hi": hi,
                    "p_clustered": st.p_one_sided,
                    "share_beat": float((part["clv"] > 0).mean()) if len(part) else float("nan"),
                    "avg_odds": float(part["odds"].mean()) if len(part) else float("nan"),
                    "share_odds_gt5": float((part["odds"] > 5).mean()) if len(part) else float("nan"),
                }
            )
    # Wrażliwość CLV na metodę devig (otwarcie i zamknięcie tą samą metodą), B / Max / ADR.
    strategy = load_strategy()
    main = sel[sel["league"].isin(MAIN_LEAGUES)]
    for m in METHODS:
        bets = single_bets(main, SingleSpec("B_single_tax0", f"p_open_{m}", "max", 0.0, None), strategy, m)
        hold = bets[bets["season"].isin(HOLDOUT_SEASONS)]
        st = clustered_clv(hold)
        lo, hi = week_block_bootstrap(hold)
        rows.append(
            {
                "strategy": "B_single_tax0|max|ADR",
                "variant": f"holdout, devig = {m}",
                "n": len(hold),
                "clv_mean": st.mean if len(hold) else float("nan"),
                "ci_lo": lo,
                "ci_hi": hi,
                "p_clustered": st.p_one_sided,
                "share_beat": st.share_beat,
                "avg_odds": float(hold["odds"].mean()) if len(hold) else float("nan"),
                "share_odds_gt5": float((hold["odds"] > 5).mean()) if len(hold) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def closing_snapshot_ev(sel: pd.DataFrame, method: str) -> pd.DataFrame:
    """Zakład w chwili zamknięcia: Avg/Max zamknięcia vs fair zamknięcia Pinnacle (to samo „teraz”).

    Jedyny test możliwy dla Ekstraklasy (brak kursów przedmeczowych). Tu CLV ≡ EV z definicji.
    """
    rows = []
    p_col = f"p_close_{method}"
    for league, lsel in sel[sel["market"] == "1x2"].groupby("league"):
        for odds_col in ("avg_close", "max_close"):
            for tax in (0.12, 0.0):
                df = lsel[np.isfinite(lsel[p_col]) & np.isfinite(lsel[odds_col])]
                if df.empty:
                    continue
                ev = df[odds_col] * (1 - tax) * df[p_col] - 1
                for thr in (0.0, 0.03):
                    pick = df[ev >= thr].assign(ev=ev[ev >= thr])
                    pick = pick.sort_values("ev", ascending=False).drop_duplicates("match_id")
                    profit = np.where(pick["won"] == 1, pick[odds_col] * (1 - tax) - 1, -1.0)
                    roi, lo, hi = roi_with_ci(profit, np.ones(len(pick)))
                    rows.append(
                        {
                            "league": league,
                            "odds": odds_col,
                            "tax": tax,
                            "threshold": thr,
                            "n_selections": len(df),
                            "mean_ev_all": float(ev.mean()),
                            "share_ev_ge_thr": float((ev >= thr).mean()),
                            "n_bets": len(pick),
                            "mean_ev_bets": float(pick["ev"].mean()) if len(pick) else float("nan"),
                            "roi": roi,
                            "roi_lo": lo,
                            "roi_hi": hi,
                        }
                    )
    return pd.DataFrame(rows)


def baseline_clv(sel: pd.DataFrame, method: str) -> pd.DataFrame:
    """Sanity: średni CLV, gdyby grać WSZYSTKO po danym kursie (powinien ≈ −marża)."""
    rows = []
    main = sel[sel["league"].isin(MAIN_LEAGUES)]
    for market in MARKETS:
        msel = main[main["market"] == market]
        for odds_col in ("pin_open", "avg", "max_soft", "max"):
            clv = msel[odds_col] * msel[f"p_close_{method}"] - 1
            rows.append(
                {
                    "market": market,
                    "odds": odds_col,
                    "n": int(clv.notna().sum()),
                    "clv_pre_tax": float(clv.mean()),
                    "clv_tax12": float((clv + 1).mul(0.88).sub(1).mean()),
                }
            )
    return pd.DataFrame(rows)


# --- markdown ---------------------------------------------------------------------------


def to_markdown(df: pd.DataFrame, pct: Iterable[str] = (), digits: int = 4) -> str:
    pct = set(pct)

    def fmt(col: str, v) -> str:
        if isinstance(v, float | np.floating):
            if not np.isfinite(v):
                return "—"
            return f"{v:+.2%}" if col in pct else f"{v:.{digits}f}"
        return str(v)

    header = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = [
        "| " + " | ".join(fmt(c, v) for c, v in zip(df.columns, row, strict=True)) + " |"
        for row in df.itertuples(index=False)
    ]
    return "\n".join([header, sep, *body])


def write_tables(sections: list[tuple[str, str]]) -> None:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    parts = [
        "# F2: tabele backtestu (wygenerowane automatycznie)",
        "",
        "Plik generuje `uv run ba-backtest`.",
        "Interpretacja i werdykt: [2026-10-f2-backtest.md](2026-10-f2-backtest.md).",
        "",
    ]
    for title, body in sections:
        parts += [f"## {title}", "", body, ""]
    TABLES_PATH.write_text("\n".join(parts), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest F2 (walk-forward, EV po podatku, CLV)")
    parser.add_argument("--refresh", action="store_true", help="przelicz selekcje i DC zamiast czytać cache")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    sel = build_dataset(args.refresh)
    main_sel = sel[sel["league"].isin(MAIN_LEAGUES)]
    pol_sel = sel[sel["league"].isin(CLOSING_ONLY_LEAGUES)]

    cal_open = devig_calibration(main_sel, "open")
    cal_close = devig_calibration(sel, "close")
    pairs_open = method_pairs(main_sel, "open", "dev")
    dev_1x2 = cal_open[(cal_open["league"] == "ALL") & (cal_open["market"] == "1x2") & (cal_open["period"] == "dev")]
    method = str(dev_1x2.loc[dev_1x2["log_loss"].idxmin(), "method"])
    log.info("Metoda devig wybrana na dev: %s", method)

    dc_open = dc_vs_market(main_sel, method, "open")
    dc_close_pol = dc_vs_market(pol_sel, method, "close")
    images = plot_calibration(sel, method)
    coverage = (
        sel[sel["market"] == "1x2"]
        .groupby("league")
        .agg(matches=("match_id", "nunique"), dc_coverage=("p_dc", lambda s: float(s.notna().mean())))
        .reset_index()
    )

    results, all_bets = run_strategies(sel, method)
    protocol_real = go_no_go(results, ("avg", "max_soft"))
    protocol_max = go_no_go(results, ("max",))
    adr_real = adr_threshold_protocol(results, ("avg", "max_soft"))
    adr_max = adr_threshold_protocol(results, ("max",))
    haircut = haircut_sensitivity(sel, method)
    quality = data_quality(sel)
    robust = robustness(sel, all_bets, method)
    closing = closing_snapshot_ev(sel, method)
    baseline = baseline_clv(sel, method)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUT_DIR / "strategy_results.csv", index=False)
    pd.concat(all_bets.values(), ignore_index=True).to_parquet(OUT_DIR / "bets.parquet", index=False)
    haircut.to_csv(OUT_DIR / "haircut.csv", index=False)
    robust.to_csv(OUT_DIR / "robustness.csv", index=False)
    quality.to_csv(OUT_DIR / "data_quality.csv", index=False)
    protocol_real.to_csv(OUT_DIR / "protocol_realistic.csv", index=False)
    protocol_max.to_csv(OUT_DIR / "protocol_max.csv", index=False)

    pct_cols = [
        "roi",
        "roi_lo",
        "roi_hi",
        "clv_mean",
        "clv_log",
        "clv_pre_tax",
        "share_beat",
        "kelly_roi",
        "kelly_dd",
        "dev_clv",
        "hold_clv",
        "hold_share_beat",
        "hold_roi",
        "mean_ev_all",
        "share_ev_ge_thr",
        "mean_ev_bets",
        "clv_tax12",
        "dc_coverage",
    ]
    cols_main = [
        "family",
        "odds",
        "threshold",
        "period",
        "n",
        "avg_odds",
        "roi",
        "roi_lo",
        "roi_hi",
        "clv_mean",
        "clv_pre_tax",
        "share_beat",
        "t",
        "p",
        "kelly_n",
        "kelly_final",
        "kelly_dd",
    ]
    adr_rows = results[results["threshold"].astype(str) == "ADR"][cols_main]
    sections = [
        ("Pokrycie danych", to_markdown(coverage, pct_cols)),
        ("Metoda devig wybrana na dev (min log loss, 1X2, Pinnacle przedmeczowy)", f"`{method}`"),
        (
            "Kalibracja devig — Pinnacle przedmeczowy (E1/D2/N1)",
            to_markdown(cal_open[cal_open["league"] == "ALL"], pct_cols),
        ),
        (
            "Kalibracja devig — per liga (przedmeczowy, all)",
            to_markdown(cal_open[(cal_open["league"] != "ALL") & (cal_open["period"] == "all")], pct_cols),
        ),
        (
            "Kalibracja devig — zamknięcie Pinnacle (w tym Ekstraklasa)",
            to_markdown(cal_close[cal_close["period"] == "all"], pct_cols),
        ),
        ("Sparowane porównania log loss metod devig (dev, ALL)", to_markdown(pairs_open)),
        ("Dixon-Coles walk-forward vs rynek (przedmeczowy)", to_markdown(dc_open, pct_cols)),
        ("Ekstraklasa: Dixon-Coles vs zamknięcie Pinnacle (tylko zamknięcia!)", to_markdown(dc_close_pol, pct_cols)),
        ("Krzywe kalibracji", "\n".join(f"![kalibracja]({p})" for p in images)),
        ("Sanity: CLV przy graniu wszystkiego", to_markdown(baseline, pct_cols)),
        ("Protokół go/no-go — warianty realistyczne (Avg, MaxSoft)", to_markdown(protocol_real, pct_cols)),
        ("Protokół — wariant optymistyczny (Max)", to_markdown(protocol_max, pct_cols)),
        ("Test wtórny: progi ADR 0014 (bez strojenia) — Avg, MaxSoft", to_markdown(adr_real, pct_cols)),
        ("Test wtórny: progi ADR 0014 — Max (optymistyczny)", to_markdown(adr_max, pct_cols)),
        (
            "Wrażliwość: kurs = Max × (1 − haircut), single, próg ADR",
            to_markdown(haircut, [*pct_cols, "haircut", "tax"]),
        ),
        (
            "Jakość danych per sezon (arbitraże w Max, marże)",
            to_markdown(
                quality,
                [*pct_cols, "max_arb_share", "pin_open_margin_median", "pin_close_margin_median", "avg_margin_median"],
            ),
        ),
        ("Odporność wyniku (holdout)", to_markdown(robust, [*pct_cols, "ci_lo", "ci_hi", "share_odds_gt5"])),
        ("Strategie przy progu ADR 0014 (3% / 5% dla kursu > 3,0)", to_markdown(adr_rows, pct_cols)),
        ("Pełna siatka progów — holdout", to_markdown(results[results["period"] == "holdout"][cols_main], pct_cols)),
        ("Pełna siatka progów — dev", to_markdown(results[results["period"] == "dev"][cols_main], pct_cols)),
        ("Zakład w chwili zamknięcia (closing snapshot; jedyny test dla Ekstraklasy)", to_markdown(closing, pct_cols)),
    ]
    write_tables(sections)
    summary = {
        "method": method,
        "go_realistic": bool(protocol_real.get("pass", pd.Series(dtype=bool)).any()),
        "go_max": bool(protocol_max.get("pass", pd.Series(dtype=bool)).any()),
        "go_adr_realistic": bool(adr_real["pass"].any()),
        "go_adr_max": bool(adr_max["pass"].any()),
        "n_specs": len(strategy_specs(method)),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0
