"""Model liczebności rogów i kartek: ujemny dwumian (NB) per drużyna (ADR 0011, plan Krok 2).

Dla meczu gospodarz h – gość a i statystyki X (rogi albo kartki):

    X_h ~ NB(mu_h, r),  log mu_h = baza + atak[h] + obrona[a] + gospodarz (+ sędzia)
    X_a ~ NB(mu_a, r),  log mu_a = baza + atak[a] + obrona[h]            (+ sędzia)

- „atak” to skłonność drużyny do generowania danej statystyki (rogi wywalczone, kartki
  otrzymane), „obrona” to to, ile tej statystyki drużyna „oddaje” rywalowi (rogi stracone,
  kartki wymuszone na przeciwniku).
- `r` to wspólny parametr nadrozproszenia: Var = mu + mu²/r (r → ∞ daje Poissona).
- Dopasowanie: ważona największa wiarygodność z karą L2 (prior N(0, sd²)) na efekty drużyn
  i sędziów, czyli ściąganie do średniej ligi drużyn z małą liczbą meczów. Wagi
  exp(-xi · dni przed as_of), jak w Dixon-Coles.
- **Brak patrzenia w przyszłość:** model widzi tylko mecze z datą < `as_of` (ADR 0015).
- Sędzia (tylko E1, gdzie football-data podaje `Referee`): efekt na kartki obu drużyn, tylko
  dla sędziów z ≥ `min_referee_matches` meczami w oknie; pozostali = 0 (średnia ligi).
- Rozkład sumy: domyślnie `total_model="nb_total"`, czyli NB(mu_h + mu_a, r_suma) z osobno
  dopasowanym r_suma. W danych rogi gospodarza i gościa są ujemnie skorelowane (ok. −0,3:
  kto atakuje, ten nie broni rożnych), a kartki dodatnio (ok. +0,15: „ostry” mecz), więc splot
  dwóch niezależnych NB (`total_model="convolution"`) przeszacowuje rozrzut sumy rogów
  i niedoszacowuje rozrzutu kartek. Rynki per drużyna i `*_most` używają brzegowych NB
  (przy `*_most` zakładamy niezależność, co jest uproszczeniem).

Konwencja kartek: domyślnie **liczba kartek = żółte + czerwone** (`red_weight=1`), tak jak
rynek „liczba kartek” u polskich bukmacherów. Regulaminu STS nie udało się potwierdzić (czy
druga żółta liczy się podwójnie); system „booking points” (Y=10, R=25) to inny rynek. Zob.
docs/experiments/2026-10-counts-calibration.md.

Klucze rynków: `{rynek: {wynik: p}}`, np. `"corners_ou_9.5": {"over", "under"}`,
`"home_cards_ou_1.5": {"over", "under"}`, `"corners_most": {"home", "draw", "away"}`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

import numpy as np
import pandas as pd
from scipy import optimize, special, stats

log = logging.getLogger(__name__)

MODEL_VERSION = "nb-counts-v0"

Stat = Literal["corners", "cards"]
TotalModel = Literal["nb_total", "convolution"]

DEFAULT_TOTAL_LINES: dict[str, tuple[float, ...]] = {
    "corners": (7.5, 8.5, 9.5, 10.5, 11.5, 12.5),
    "cards": (2.5, 3.5, 4.5, 5.5, 6.5),
}
DEFAULT_TEAM_LINES: dict[str, tuple[float, ...]] = {
    "corners": (2.5, 3.5, 4.5, 5.5, 6.5),
    "cards": (0.5, 1.5, 2.5, 3.5),
}
# Górna granica wsparcia rozkładu per drużyna (reszta masy jest pomijalna i renormalizowana).
MAX_COUNT: dict[str, int] = {"corners": 40, "cards": 20}


def ou_key(prefix: str, line: float) -> str:
    """('corners', 9.5) -> 'corners_ou_9.5'."""
    return f"{prefix}_ou_{line:g}"


def stat_columns(matches: pd.DataFrame, stat: Stat, red_weight: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Liczebności (gospodarz, gość) dla statystyki z DataFrame z `load_match_stats`."""
    if stat == "corners":
        return matches["home_corners"].to_numpy(float), matches["away_corners"].to_numpy(float)
    if stat == "cards":
        home = matches["home_yellow"].to_numpy(float) + red_weight * matches["home_red"].to_numpy(float)
        away = matches["away_yellow"].to_numpy(float) + red_weight * matches["away_red"].to_numpy(float)
        return home, away
    raise ValueError(f"Nieznana statystyka: {stat}")


def _as_timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def nb_pmf(mu: float, r: float, max_count: int) -> np.ndarray:
    """P(X = 0..max_count) dla NB(mu, r), renormalizowane do sumy 1."""
    k = np.arange(max_count + 1)
    p = stats.nbinom.pmf(k, r, r / (r + mu))
    return p / p.sum()


def over_probability(pmf: np.ndarray, line: float) -> float:
    """P(X > line) dla linii połówkowej."""
    if float(line).is_integer():
        raise ValueError(f"Obsługujemy tylko linie połówkowe (bez zwrotu), dostałem {line}")
    return float(pmf[int(np.floor(line)) + 1 :].sum())


def _ou(pmf: np.ndarray, line: float) -> dict[str, float]:
    over = over_probability(pmf, line)
    return {"over": over, "under": 1.0 - over}


@dataclass
class CountForecaster:
    league: str
    stat: Stat
    as_of: pd.Timestamp
    base: float
    home_adv: float
    attack: dict[str, float]
    defence: dict[str, float]
    dispersion: float
    referee: dict[str, float] = field(default_factory=dict)
    team_effects: bool = True
    total_model: TotalModel = "nb_total"
    total_dispersion: float | None = None
    n_matches: int = 0
    last_match: pd.Timestamp | None = None
    fitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def version(self) -> str:
        kind = "team" if self.team_effects else "league"
        return f"{MODEL_VERSION}:{self.stat}:{kind}:{self.league}:{self.as_of:%Y%m%d}"

    @property
    def teams(self) -> set[str]:
        return set(self.attack)

    def knows(self, home: str, away: str) -> bool:
        return not self.team_effects or (home in self.attack and away in self.attack)

    def expected(self, home: str, away: str, referee: str | None = None) -> tuple[float, float]:
        """Oczekiwane liczebności (gospodarz, gość). Nieznana drużyna/sędzia = średnia ligi (0)."""
        ref = self.referee.get(referee, 0.0) if referee else 0.0
        eta_h = self.base + self.home_adv + self.attack.get(home, 0.0) + self.defence.get(away, 0.0) + ref
        eta_a = self.base + self.attack.get(away, 0.0) + self.defence.get(home, 0.0) + ref
        return float(np.exp(eta_h)), float(np.exp(eta_a))

    def distributions(
        self, home: str, away: str, referee: str | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Rozkłady (gospodarz, gość, suma) jako wektory P(X = k)."""
        mu_h, mu_a = self.expected(home, away, referee)
        cap = MAX_COUNT[self.stat]
        p_home = nb_pmf(mu_h, self.dispersion, cap)
        p_away = nb_pmf(mu_a, self.dispersion, cap)
        if self.total_model == "nb_total" and self.total_dispersion is not None:
            return p_home, p_away, nb_pmf(mu_h + mu_a, self.total_dispersion, 2 * cap)
        return p_home, p_away, np.convolve(p_home, p_away)

    def predict_markets(
        self,
        home: str,
        away: str,
        referee: str | None = None,
        lines: Sequence[float] | None = None,
        team_lines: Sequence[float] | None = None,
        allow_unknown: bool = False,
    ) -> dict[str, dict[str, float]] | None:
        """Rynki O/U (łącznie i per drużyna) oraz „więcej rogów/kartek” (corners_most).

        None, gdy drużyna nie występuje w danych treningowych (chyba że `allow_unknown`,
        wtedy jej efekty = 0, czyli średnia ligi).
        """
        if not allow_unknown and not self.knows(home, away):
            return None
        lines = DEFAULT_TOTAL_LINES[self.stat] if lines is None else lines
        team_lines = DEFAULT_TEAM_LINES[self.stat] if team_lines is None else team_lines
        p_home, p_away, p_total = self.distributions(home, away, referee)
        out = {ou_key(self.stat, line): _ou(p_total, line) for line in lines}
        for side, pmf in (("home", p_home), ("away", p_away)):
            for line in team_lines:
                out[ou_key(f"{side}_{self.stat}", line)] = _ou(pmf, line)
        joint = np.outer(p_home, p_away)
        more_home = float(np.tril(joint, -1).sum())
        tie = float(np.trace(joint))
        out[f"{self.stat}_most"] = {"home": more_home, "draw": tie, "away": 1.0 - more_home - tie}
        return out


def fit_counts(
    matches: pd.DataFrame,
    stat: Stat,
    as_of: date | datetime | pd.Timestamp,
    league: str = "",
    xi: float = 0.0018,
    team_prior_sd: float = 0.05,
    referee_prior_sd: float = 0.15,
    min_referee_matches: int = 5,
    red_weight: float = 1.0,
    team_effects: bool = True,
    total_model: TotalModel = "nb_total",
    min_matches: int = 100,
) -> CountForecaster:
    """Dopasowuje model NB na meczach z datą < `as_of` (DataFrame z `load_match_stats`).

    `team_effects=False` daje baseline „średnia ligi”: tylko baza, gospodarz i nadrozproszenie.
    Efekt sędziego tylko dla kartek i tylko gdy jest kolumna `referee`.
    """
    as_of = _as_timestamp(as_of)
    train = matches[matches["date"] < as_of]
    if len(train) < min_matches:
        raise ValueError(f"Za mało meczów do dopasowania {stat} dla {league}: {len(train)} < {min_matches}")
    y_home, y_away = stat_columns(train, stat, red_weight)
    days = (as_of - train["date"]).dt.days.to_numpy(float)
    w = np.exp(-xi * days)

    teams = sorted(set(train["home_team"]) | set(train["away_team"])) if team_effects else []
    t_idx = {t: i for i, t in enumerate(teams)}
    referees: list[str] = []
    if stat == "cards" and "referee" in train.columns:
        counts = train["referee"].dropna().value_counts()
        referees = sorted(counts[counts >= min_referee_matches].index)
    r_idx = {r: i for i, r in enumerate(referees)}

    n_t, n_r = len(teams), len(referees)
    # Obserwacje: najpierw wszyscy gospodarze, potem wszyscy goście.
    y = np.concatenate([y_home, y_away])
    ww = np.concatenate([w, w])
    is_home = np.concatenate([np.ones(len(train)), np.zeros(len(train))])
    if team_effects:
        h = train["home_team"].map(t_idx).to_numpy()
        a = train["away_team"].map(t_idx).to_numpy()
        att_i = np.concatenate([h, a])
        def_i = np.concatenate([a, h])
    if n_r:
        ref = train["referee"].map(r_idx).fillna(-1).to_numpy(int)
        ref_i = np.concatenate([ref, ref])
        has_ref = ref_i >= 0
    lgamma_y1 = special.gammaln(y + 1)
    wsum = ww.sum()

    # Wektor parametrów: [baza, gospodarz, log r, atak(n_t), obrona(n_t), sędzia(n_r)].
    o_att, o_def, o_ref = 3, 3 + n_t, 3 + 2 * n_t

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        base, home_adv, log_r = theta[:3]
        att = theta[o_att:o_def]
        dfn = theta[o_def:o_ref]
        refs = theta[o_ref:]
        eta = base + home_adv * is_home
        if team_effects:
            eta = eta + att[att_i] + dfn[def_i]
        if n_r:
            eta = eta + np.where(has_ref, refs[np.maximum(ref_i, 0)], 0.0)
        mu = np.exp(eta)
        r = np.exp(log_r)
        ll = (
            special.gammaln(y + r)
            - special.gammaln(r)
            - lgamma_y1
            + r * (log_r - np.log(r + mu))
            + y * (eta - np.log(r + mu))
        )
        d_eta = ww * r * (y - mu) / (r + mu)
        d_r = ww * (special.digamma(y + r) - special.digamma(r) + log_r - np.log(r + mu) + (mu - y) / (r + mu))
        # Normalizujemy przez sumę wag, żeby siła priorów nie zależała od długości okna.
        nll = -(ww * ll).sum() / wsum
        grad = np.zeros_like(theta)
        grad[0] = -d_eta.sum() / wsum
        grad[1] = -(d_eta * is_home).sum() / wsum
        grad[2] = -(d_r.sum() * r) / wsum
        if team_effects:
            grad[o_att:o_def] = -np.bincount(att_i, d_eta, n_t) / wsum
            grad[o_def:o_ref] = -np.bincount(def_i, d_eta, n_t) / wsum
        if n_r:
            grad[o_ref:] = -np.bincount(ref_i[has_ref], d_eta[has_ref], n_r) / wsum
        # Prior N(0, sd²) (MAP) po tej samej normalizacji przez sumę wag obserwacji.
        team_pen = 1.0 / (team_prior_sd**2 * wsum)
        ref_pen = 1.0 / (referee_prior_sd**2 * wsum)
        nll += 0.5 * team_pen * (att @ att + dfn @ dfn) + 0.5 * ref_pen * (refs @ refs)
        grad[o_att:o_ref] += team_pen * theta[o_att:o_ref]
        grad[o_ref:] += ref_pen * refs
        return float(nll), grad

    mean_y = float(np.average(y, weights=ww))
    theta0 = np.zeros(3 + 2 * n_t + n_r)
    theta0[0] = np.log(max(mean_y, 1e-3))
    theta0[2] = np.log(20.0)
    bounds = [(None, None), (None, None), (np.log(0.5), np.log(1e4))] + [(None, None)] * (2 * n_t + n_r)
    res = optimize.minimize(objective, theta0, jac=True, method="L-BFGS-B", bounds=bounds)
    if not res.success:
        log.warning("NB %s %s: optymalizacja nie zbiegła: %s", league, stat, res.message)
    theta = res.x
    total_dispersion = None
    if total_model == "nb_total":
        # r_suma: NB dla sumy przy ustalonych mu_h, mu_a (ważona ML, jednowymiarowo).
        eta = theta[0] + theta[1] * is_home
        if team_effects:
            eta = eta + theta[o_att:o_def][att_i] + theta[o_def:o_ref][def_i]
        if n_r:
            eta = eta + np.where(has_ref, theta[o_ref:][np.maximum(ref_i, 0)], 0.0)
        mu = np.exp(eta)
        mu_tot = mu[: len(train)] + mu[len(train) :]
        y_tot = y_home + y_away
        lg_tot = special.gammaln(y_tot + 1)

        def nll_total(log_r: float) -> float:
            r = np.exp(log_r)
            ll = (
                special.gammaln(y_tot + r)
                - special.gammaln(r)
                - lg_tot
                + r * (log_r - np.log(r + mu_tot))
                + y_tot * (np.log(mu_tot) - np.log(r + mu_tot))
            )
            return float(-(w * ll).sum() / w.sum())

        total_dispersion = float(
            np.exp(optimize.minimize_scalar(nll_total, bounds=(np.log(0.5), np.log(1e4)), method="bounded").x)
        )
    log.info("NB %s %s as_of=%s: %d meczów, %d drużyn, %d sędziów", league, stat, as_of.date(), len(train), n_t, n_r)
    return CountForecaster(
        league=league,
        stat=stat,
        as_of=as_of,
        base=float(theta[0]),
        home_adv=float(theta[1]),
        dispersion=float(np.exp(theta[2])),
        attack={t: float(theta[o_att + i]) for t, i in t_idx.items()},
        defence={t: float(theta[o_def + i]) for t, i in t_idx.items()},
        referee={rf: float(theta[o_ref + i]) for rf, i in r_idx.items()},
        team_effects=team_effects,
        total_model=total_model,
        total_dispersion=total_dispersion,
        n_matches=len(train),
        last_match=train["date"].max(),
    )


# --- Walidacja walk-forward (ADR 0015) -----------------------------------------------------


def walk_forward(
    matches: pd.DataFrame,
    stat: Stat,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp | None = None,
    refit_days: int = 14,
    lines: Iterable[float] | None = None,
    league: str = "",
    **fit_kwargs,
) -> pd.DataFrame:
    """Prognozy out-of-sample: co `refit_days` dopasowanie na meczach sprzed daty refitu,
    prognoza meczów z następnego okna. Model „team” i baseline „league” (średnia ligi NB)
    oraz baseline „freq” (odsetek overów w ostatnich 365 dniach przed refitem).

    Zwraca wiersz na (mecz, linia) z kolumnami p_team, p_league, p_freq, over (0/1), total.
    Mecze z drużyną nieznaną modelowi „team” są pomijane (zostają w liczniku `skipped`).
    """
    lines = tuple(DEFAULT_TOTAL_LINES[stat] if lines is None else lines)
    start, end = _as_timestamp(start), _as_timestamp(end or matches["date"].max() + pd.Timedelta(days=1))
    rows = []
    skipped = 0
    refit = start
    while refit <= end:
        window = matches[(matches["date"] >= refit) & (matches["date"] < refit + pd.Timedelta(days=refit_days))]
        if window.empty:
            refit += pd.Timedelta(days=refit_days)
            continue
        team = fit_counts(matches, stat, refit, league, **fit_kwargs)
        flat = fit_counts(matches, stat, refit, league, team_effects=False, **fit_kwargs)
        past = matches[(matches["date"] < refit) & (matches["date"] >= refit - pd.Timedelta(days=365))]
        past_h, past_a = stat_columns(past, stat, fit_kwargs.get("red_weight", 1.0))
        freq = {line: float(((past_h + past_a) > line).mean()) for line in lines}
        y_h, y_a = stat_columns(window, stat, fit_kwargs.get("red_weight", 1.0))
        for (_, m), total in zip(window.iterrows(), y_h + y_a, strict=True):
            referee = m.get("referee") if isinstance(m.get("referee"), str) else None
            if not team.knows(m["home_team"], m["away_team"]):
                skipped += 1
                continue
            p_team = team.distributions(m["home_team"], m["away_team"], referee)[2]
            p_flat = flat.distributions(m["home_team"], m["away_team"], referee)[2]
            t = int(total)
            for line in lines:
                rows.append(
                    {
                        "date": m["date"],
                        "refit": refit,
                        "home_team": m["home_team"],
                        "away_team": m["away_team"],
                        "line": line,
                        "total": t,
                        "over": int(t > line),
                        "p_team": over_probability(p_team, line),
                        "p_league": over_probability(p_flat, line),
                        "p_freq": freq[line],
                        "logpmf_team": float(np.log(max(p_team[t] if t < len(p_team) else 0.0, 1e-12))),
                        "logpmf_league": float(np.log(max(p_flat[t] if t < len(p_flat) else 0.0, 1e-12))),
                    }
                )
        refit += pd.Timedelta(days=refit_days)
    out = pd.DataFrame(rows)
    out.attrs["skipped"] = skipped
    return out


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_table(p: np.ndarray, y: np.ndarray, bins: Sequence[float] = (0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0)):
    """Krzywa kalibracji: średnia prognoza vs odsetek trafień w koszykach p."""
    df = pd.DataFrame({"p": p, "y": y})
    df["bin"] = pd.cut(df["p"], bins=list(bins), include_lowest=True)
    return df.groupby("bin", observed=True).agg(n=("y", "size"), p_mean=("p", "mean"), hit_rate=("y", "mean"))
