"""Rozpoznawanie drużyn między źródłami (ADR 0010).

Automatycznie akceptujemy tylko dopasowanie dokładne po normalizacji albo alias z
config/team_aliases.yaml. Dopasowania przybliżone są wyłącznie propozycjami do ręcznego
zatwierdzenia — nigdy nie zgadujemy po cichu.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from betting_analyst.config import load_team_aliases

# Tokeny bez znaczenia dla tożsamości klubu (formy prawne, skróty typu FC/SV).
_NOISE_TOKENS = {
    "fc", "afc", "cf", "sc", "sv", "ssv", "tsv", "fsv", "vfl", "vfb", "spvgg", "ks", "sk",
    "bk", "ac", "the", "club", "1", "07", "04", "96", "98",
}  # fmt: skip
_SPECIAL_CHARS = str.maketrans({"ł": "l", "Ł": "L", "ß": "ss", "ø": "o", "Ø": "O"})


def normalize_team(name: str) -> str:
    """Postać porównawcza nazwy: małe litery, bez diakrytyków, bez FC/SV itp."""
    text = unicodedata.normalize("NFKD", name.translate(_SPECIAL_CHARS))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    tokens = re.split(r"[^a-z0-9]+", text)
    kept = [t for t in tokens if t and t not in _NOISE_TOKENS]
    return " ".join(kept) if kept else " ".join(t for t in tokens if t)


@dataclass
class TeamResolver:
    """Mapuje nazwy z dowolnego źródła na nazwy kanoniczne (football-data) danej ligi."""

    known_teams: set[str]
    aliases: dict[str, list[str]] = field(default_factory=load_team_aliases)

    def __post_init__(self) -> None:
        self._by_norm: dict[str, str] = {normalize_team(t): t for t in self.known_teams}
        for canonical, alias_list in self.aliases.items():
            if canonical not in self.known_teams:
                continue
            for alias in [canonical, *alias_list]:
                self._by_norm.setdefault(normalize_team(alias), canonical)

    def resolve(self, name: str) -> str | None:
        return self._by_norm.get(normalize_team(name))

    def suggest(self, name: str, n: int = 2) -> list[str]:
        """Propozycje (do ręcznego zatwierdzenia) dla nazwy bez dopasowania."""
        norm = normalize_team(name)
        candidates = difflib.get_close_matches(norm, list(self._by_norm), n=n, cutoff=0.5)
        # Dopasowanie po tokenie (np. "legia warsaw" ~ "legia") jako dodatkowa podpowiedź.
        tokens = set(norm.split())
        for key in self._by_norm:
            if key not in candidates and tokens & set(key.split()):
                candidates.append(key)
        return list(dict.fromkeys(self._by_norm[c] for c in candidates))[:n]


def team_key(name: str, resolver: TeamResolver | None) -> str:
    """Klucz do łączenia meczów między źródłami: kanoniczna nazwa albo nazwa znormalizowana."""
    if resolver is not None and (canonical := resolver.resolve(name)):
        return canonical
    return normalize_team(name)


def unresolved(names: Iterable[str], resolver: TeamResolver) -> dict[str, list[str]]:
    return {n: resolver.suggest(n) for n in sorted(set(names)) if resolver.resolve(n) is None}
