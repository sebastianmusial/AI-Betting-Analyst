"""EV po podatku, ułamkowy Kelly z limitami i propozycje AKO (ADR 0003, 0014, 0002).

Wzory:
- kurs efektywny: odds_eff = odds × (1 − stake_tax) [× (1 − winnings_tax) przy wypłacie > progu],
- EV = p × odds_eff − 1,
- edge (przewaga w pp) = p − 1 / odds_eff,
- Kelly = (p × odds_eff − 1) / (odds_eff − 1), stawka = bankroll × frakcja × Kelly, z capem.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from betting_analyst.config import Bookmaker, Strategy, WinningsTax

BetType = Literal["single", "ako"]


@dataclass(frozen=True)
class TaxContext:
    """Stan okresu rozliczeniowego promocji (np. Betclic „Gra bez podatku 2.0”)."""

    period_single_stakes_pln: float = 0.0
    period_ako_share: float | None = None


def stake_tax_rate(
    bookmaker: Bookmaker,
    bet_type: BetType = "single",
    ctx: TaxContext | None = None,
    stake: float = 0.0,
) -> float:
    """Stawka podatku od stawki dla danego buka, typu zakładu i stanu okresu.

    Uproszczenie: jeśli nowa stawka przekroczyłaby limit promocji, cała jest liczona po
    stawce „powyżej limitu” (konserwatywnie).
    """
    ctx = ctx or TaxContext()
    share_rule = bookmaker.all_free_if_ako_share_gte
    if share_rule is not None and ctx.period_ako_share is not None and ctx.period_ako_share >= share_rule:
        return 0.0
    if bet_type == "ako" and bookmaker.ako is not None:
        return bookmaker.ako.stake_tax
    if bet_type == "single" and bookmaker.single is not None:
        rule = bookmaker.single
        limit = rule.free_stake_limit_pln
        if limit is not None and ctx.period_single_stakes_pln + stake > limit:
            return rule.stake_tax_above if rule.stake_tax_above is not None else bookmaker.stake_tax
        return rule.stake_tax
    return bookmaker.stake_tax


def effective_odds(
    odds: float,
    stake_tax: float,
    stake: float | None = None,
    winnings_tax: WinningsTax | None = None,
) -> float:
    """Kurs po podatku od stawki; opcjonalnie także po 10% podatku od wygranej > 2280 zł."""
    eff = odds * (1.0 - stake_tax)
    if stake is not None and winnings_tax is not None and stake * eff > winnings_tax.threshold_pln:
        eff *= 1.0 - winnings_tax.rate
    return eff


def expected_value(prob: float, odds_eff: float) -> float:
    return prob * odds_eff - 1.0


def edge(prob: float, odds_eff: float) -> float:
    return prob - 1.0 / odds_eff


def required_edge(odds: float, strategy: Strategy) -> float:
    """Próg EV: wyższy dla kursów > high_odds_threshold (niepewność devig przy outsiderach)."""
    return strategy.min_edge_high_odds if odds > strategy.high_odds_threshold else strategy.min_edge


def kelly_fraction(prob: float, odds_eff: float) -> float:
    """Pełny Kelly (ułamek bankrolla); 0 gdy EV ≤ 0."""
    if odds_eff <= 1.0:
        return 0.0
    return max(0.0, (prob * odds_eff - 1.0) / (odds_eff - 1.0))


def round_stake(stake: float, rounding: float) -> float:
    if rounding <= 0:
        return stake
    return math.floor(stake / rounding + 1e-9) * rounding


def kelly_stake(
    prob: float,
    odds_eff: float,
    bankroll: float,
    fraction: float,
    max_stake_pct: float,
    rounding: float = 1.0,
) -> float:
    """Ułamkowy Kelly z capem max_stake_pct bankrolla, zaokrąglony w dół."""
    raw = bankroll * fraction * kelly_fraction(prob, odds_eff)
    return round_stake(min(raw, bankroll * max_stake_pct), rounding)


def apply_daily_exposure(
    stakes: Sequence[float],
    bankroll: float,
    daily_exposure_pct: float,
    already_staked: float = 0.0,
    rounding: float = 1.0,
) -> list[float]:
    """Przycina stawki (w podanej kolejności — sortuj po EV malejąco) do dziennego limitu."""
    remaining = max(0.0, bankroll * daily_exposure_pct - already_staked)
    result = []
    for stake in stakes:
        allowed = round_stake(min(stake, remaining), rounding)
        result.append(allowed)
        remaining -= allowed
    return result


@dataclass(frozen=True)
class OfferEvaluation:
    odds: float
    stake_tax: float
    odds_eff: float
    prob: float
    ev: float
    edge: float
    required_edge: float

    @property
    def is_value(self) -> bool:
        return self.ev >= self.required_edge


def evaluate(prob: float, odds: float, stake_tax: float, strategy: Strategy) -> OfferEvaluation:
    odds_eff = effective_odds(odds, stake_tax)
    return OfferEvaluation(
        odds=odds,
        stake_tax=stake_tax,
        odds_eff=odds_eff,
        prob=prob,
        ev=expected_value(prob, odds_eff),
        edge=edge(prob, odds_eff),
        required_edge=required_edge(odds, strategy),
    )


# --- AKO -------------------------------------------------------------------------------


@dataclass(frozen=True)
class AkoLeg:
    event_id: str
    label: str
    odds: float
    prob: float
    market: str = ""
    selection: str = ""

    @property
    def ev(self) -> float:
        return expected_value(self.prob, self.odds)


@dataclass
class AkoProposal:
    bookmaker: str
    legs: list[AkoLeg]
    stake_tax: float
    stake: float = 0.0
    combined_odds: float = field(init=False)
    combined_prob: float = field(init=False)

    def __post_init__(self) -> None:
        self.combined_odds = math.prod(leg.odds for leg in self.legs)
        self.combined_prob = math.prod(leg.prob for leg in self.legs)

    @property
    def odds_eff(self) -> float:
        return effective_odds(self.combined_odds, self.stake_tax)

    @property
    def ev(self) -> float:
        return expected_value(self.combined_prob, self.odds_eff)


def build_ako_proposals(
    legs: Sequence[AkoLeg],
    bookmaker: Bookmaker,
    strategy: Strategy,
    ctx: TaxContext | None = None,
    pool_size: int = 8,
) -> list[AkoProposal]:
    """Propozycje AKO dla buka, u którego AKO jest bez podatku.

    Nogi: dodatnie EV na kursie tego buka, z RÓŻNYCH meczów (zakładamy niezależność),
    najlepsza noga per mecz. Zwraca najlepszą kombinację dla każdej liczby nóg
    (min_legs..max_legs), stawka ⅛ Kelly z capem.
    """
    stake_tax = stake_tax_rate(bookmaker, "ako", ctx)
    if stake_tax > 0:
        return []

    best_per_event: dict[str, AkoLeg] = {}
    for leg in legs:
        if leg.ev <= 0:
            continue
        current = best_per_event.get(leg.event_id)
        if current is None or leg.ev > current.ev:
            best_per_event[leg.event_id] = leg
    pool = sorted(best_per_event.values(), key=lambda leg: leg.ev, reverse=True)[:pool_size]

    proposals: list[AkoProposal] = []
    for n_legs in range(strategy.ako.min_legs, strategy.ako.max_legs + 1):
        combos = [AkoProposal(bookmaker.key, list(c), stake_tax) for c in itertools.combinations(pool, n_legs)]
        if not combos:
            continue
        best = max(combos, key=lambda p: p.ev)
        best.stake = kelly_stake(
            best.combined_prob,
            best.odds_eff,
            strategy.bankroll_pln,
            strategy.kelly_fraction_ako,
            strategy.max_stake_pct,
            strategy.stake_rounding_pln,
        )
        proposals.append(best)
    return proposals[: strategy.ako.max_proposals]
