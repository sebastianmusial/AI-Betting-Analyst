# ADR 0001: Cel, zakres i kryteria sukcesu

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
Właściciel chce narzędzia wspierającego racjonalne i opłacalne decyzje bukmacherskie u legalnych polskich bukmacherów. Ma działać jako agent w Claude Code, z powiadomieniami i raportem dziennym. Większość graczy na dłuższą metę traci, więc projekt musi uczciwie mierzyć, czy w ogóle ma przewagę.

## Decyzja
- **To narzędzie decyzyjne, nie automat.** System nie stawia zakładów sam. Proponuje, uzasadnia, liczy stawkę i zapisuje, a decyzję i postawienie zakładu podejmuje człowiek.
- **Zakres MVP:**
  - piłka nożna pre-match (ADR 0004, 0005),
  - rynki 1X2 i O/U 2.5,
  - 4 ligi,
  - paper trading.
- **Kryteria sukcesu (w tej kolejności):**
  1. **Średnie CLV > 0, istotne statystycznie** (t-test, p < 0,05) na co najmniej 300 zakładach na papierze, po podatku (ADR 0015).
  2. Poprawna kalibracja modeli (Brier i log loss nie gorsze niż zdewigowany rynek; sensowne krzywe kalibracji).
  3. ROI po podatku: obserwowane, ale nie jest kryterium przy małej próbie.
- **Bramka do prawdziwych pieniędzy:** spełnione kryteria 1 i 2 oraz mały, z góry ustalony bankroll (ADR 0002).
- **Kryterium porażki:** jeśli backtest (F2) lub paper trading nie pokaże przewagi po podatku, projekt zostaje narzędziem do analizy i dyscypliny (rejestr, limity, CLV), a nie źródłem typów.

## Konsekwencje
- Najpierw budujemy pomiar (rejestr zakładów, CLV), dopiero potem coraz lepsze modele.
- Wynik „nie ma przewagi” jest pełnoprawnym, wartościowym wynikiem.

## Rozważane opcje
- **Bot stawiający automatycznie:** odrzucony. Łamie regulaminy bukmacherów, grozi szybkimi limitami i odbiera kontrolę.
- **Kryterium ROI:** odrzucone. Przy małych próbach wariancja ROI jest zbyt duża.
