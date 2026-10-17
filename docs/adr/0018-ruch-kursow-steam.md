# ADR 0018: Ruch kursów (steam) jako sygnał

- **Status:** Proposed (wdrożenie w F5)
- **Data:** 2026-10-17

## Kontekst
Nagły ruch kursów u ostrego bukmachera bez publicznego newsa zwykle oznacza przeciek informacji (skład, kontuzja). Nie ma recenzowanych dowodów, że steam sam w sobie przewiduje wynik. Jest jednak wiarygodnym detektorem nowej informacji, a miękcy bukmacherzy często reagują z opóźnieniem.

## Decyzja
- Przechowujemy historię snapshotów kursów Pinnacle (The Odds API) i konsensusu.
- **Flaga „niewyjaśniony ruch”:** zmiana prawdopodobieństwa fair o ≥ 3–5 pp w oknie ≤ 6 h bez flagi newsowej. Uruchamia celowane wyszukiwanie newsów dla obu drużyn (ADR 0013).
- **Kandydat value „spóźniony bukmacher”:** polski bukmacher nie zareagował na ruch Pinnacle, a EV po podatku przekracza próg (ADR 0014).
- Źródło pomocnicze: BetExplorer „dropping odds” (filtr kraju).

## Konsekwencje
- Wymaga częstszych snapshotów przed meczem, a to zużywa kredyty The Odds API. Możliwy upgrade planu.
- Zakłady „po ruchu linii” to też sygnał dla bukmachera do limitowania konta. Uwzględniamy to w monitorze ryzyka limitów (F7).
