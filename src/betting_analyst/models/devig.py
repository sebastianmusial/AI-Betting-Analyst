"""Usuwanie marży bukmachera (devig) — ADR 0011, etap 1 (rynek jako baza).

- multiplicative: proporcjonalne skalowanie 1/kurs (punkt odniesienia),
- power: p_i = (1/kurs_i)^k, k dobrane tak, by suma = 1 (penaltyblog),
- shin: model Shina z udziałem insiderów (pakiet `shin`).

Wynik zawsze sumuje się do 1. LLM nigdy nie generuje prawdopodobieństw — tylko ten moduł
(rynek) i modele statystyczne.
"""

from __future__ import annotations

from collections.abc import Sequence

import penaltyblog as pb
import shin

from betting_analyst.config import DevigMethod

METHODS: tuple[DevigMethod, ...] = ("multiplicative", "power", "shin")


def overround(odds: Sequence[float]) -> float:
    """Marża bukmachera: suma 1/kurs − 1."""
    return sum(1.0 / o for o in odds) - 1.0


def devig(odds: Sequence[float], method: DevigMethod = "power") -> list[float]:
    """Zamienia kursy dziesiętne kompletnego rynku na prawdopodobieństwa fair."""
    if len(odds) < 2:
        raise ValueError("Rynek musi mieć co najmniej 2 wyniki")
    if any(o <= 1.0 for o in odds):
        raise ValueError(f"Nieprawidłowe kursy: {list(odds)}")
    values = [float(o) for o in odds]

    if method == "multiplicative":
        inv = [1.0 / o for o in values]
        total = sum(inv)
        probs = [p / total for p in inv]
    elif method == "power":
        probs = list(pb.implied.calculate_implied(values, method="power").probabilities)
    elif method == "shin":
        probs = list(shin.calculate_implied_probabilities(values))
    else:
        raise ValueError(f"Nieznana metoda devig: {method}")

    total = sum(probs)
    return [p / total for p in probs]


def devig_all(odds: Sequence[float]) -> dict[str, list[float]]:
    """Wszystkie metody naraz — do porównań i raportu."""
    return {m: devig(odds, m) for m in METHODS}


def consensus_devig(markets: Sequence[Sequence[float]], method: DevigMethod = "multiplicative") -> list[float]:
    """Konsensus wielu bukmacherów (gdy brak Pinnacle): średnia zdewigowanych prawdopodobieństw."""
    if not markets:
        raise ValueError("Brak rynków do konsensusu")
    devigged = [devig(m, method) for m in markets]
    n = len(devigged[0])
    probs = [sum(d[i] for d in devigged) / len(devigged) for i in range(n)]
    total = sum(probs)
    return [p / total for p in probs]


def fair_odds(prob: float) -> float:
    return 1.0 / prob
