# ADR 0009: Źródła danych i ingestion

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [02-data-sources.md](../research/02-data-sources.md)

## Decyzja
**Najpierw darmowe źródła.** Każde źródło ma osobny adapter w `src/betting_analyst/sources/` z cache, limitem tempa zapytań i zapisem surowych danych.

| Potrzeba | Źródło startowe | Upgrade |
|---|---|---|
| Historia wyników i kursy zamknięcia Pinnacle | football-data.co.uk (E1, D2, N1, POL) | — |
| Bieżące kursy Pinnacle i EU | The Odds API (free, 500 kredytów/mies.) | płatny plan $30–59 |
| Kursy polskich bukmacherów | OddsPapi free (Fortuna, Superbet), OddsHarvester (OddsPortal), ręczne wpisanie | Odds-API.io (STS, Betclic, Fortuna) |
| O/U historyczne dla Ekstraklasy | OddsHarvester | — |
| Terminarz, składy, kontuzje | API-Football free (100 zapytań/dzień), FotMob/Sofascore | API-Football Pro |
| Ratingi | ClubElo | — |
| xG | Sofascore/FotMob (do weryfikacji) | Sportmonks, dodatek xG |
| Wartości składów | transfermarkt-datasets (CC0) | — |
| Pogoda | Open-Meteo | — |

**Zasady scrapingu** (zgoda właściciela: tylko na prywatny użytek):
- niskie tempo zapytań, user agent przeglądarki tam, gdzie wymagany, agresywny cache;
- niczego nie publikujemy ani nie odsprzedajemy;
- szanujemy blokady: nie obchodzimy CAPTCHA.

**Budżet kredytów The Odds API:** jedno pobranie 4 lig × 2 rynki × region EU to około 8 kredytów. Rano jeden skan plus snapshot przed meczami to około 300 kredytów/mies.

## Konsekwencje
- Scrapery będą się psuć przy zmianach stron, więc potrzebne są testy kontraktowe na zapisanych próbkach i alert, gdy źródło zwróci pusty wynik.
- Ścieżka upgrade'u jest jawna. Płacimy dopiero wtedy, gdy darmowe źródło blokuje postęp.
