# ADR 0000: Rejestrowanie decyzji architektonicznych jako ADR

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
Projekt łączy dane, statystykę, prawo/podatki i integrację z Claude Code. Decyzje (np. „dlaczego nie gramy live”, „dlaczego CLV, a nie ROI”) muszą być zapisane razem z uzasadnieniem, żeby dało się do nich wrócić, gdy zmienią się dane albo wyniki.

## Decyzja
- Używamy formatu MADR (wersja uproszczona): Status, Data, Kontekst, Decyzja, Konsekwencje, Rozważane opcje.
- Pliki leżą w `docs/adr/NNNN-slug.md` i są numerowane rosnąco. Indeks jest w [README.md](README.md).
- Treść piszemy po polsku, nazwy techniczne i kod po angielsku.
- Statusy:
  - `Proposed`: czeka na bramkę lub dane;
  - `Accepted`;
  - `Superseded by NNNN`;
  - `Deprecated`.
- Decyzji zaakceptowanej nie edytujemy merytorycznie. Zmiana oznacza nowy ADR, który zastępuje stary.
- Research, na którym opierają się decyzje, leży w `docs/research/`.

## Konsekwencje
- Łatwo prześledzić, skąd wzięła się każda reguła w kodzie (progi, podatki, źródła).
- Kosztem jest dyscyplina: każda istotna zmiana kierunku wymaga nowego ADR.
