# ADR 0015: Ewaluacja i backtest

- **Status:** Accepted
- **Data:** 2026-10-17

## Decyzja
- **Główny KPI: CLV** względem zdewigowanego kursu zamknięcia Pinnacle (ostatni snapshot przed rozpoczęciem meczu):
  - `clv = odds_taken_eff / closing_fair_odds − 1` (oraz w wersji logarytmicznej);
  - raportujemy średnią, odsetek zakładów, które pobiły zamknięcie, i t-test średniego CLV.
- **Metryki modeli:** Brier, log loss, RPS, krzywe kalibracji. Zawsze porównujemy ze zdewigowanym rynkiem.
- **Backtest (F2):**
  - walk-forward, model trenowany tylko na przeszłości;
  - **tylko kursy dostępne w chwili decyzji** (np. PSH, nie PSCH, jako kurs zagrania; PSCH jako zamknięcie do CLV);
  - kursy max/avg jako przybliżenie porównywania kursów, z ręczną korektą „realności” (polscy bukmacherzy są zwykle poniżej max);
  - podatek wg ADR 0003;
  - osobno: single z podatkiem, single bez podatku, AKO.
- **Bramka F2:** jeśli żadna strategia nie ma dodatniego EV po podatku na danych out-of-sample, nie idziemy dalej z modelowaniem. Zostaje narzędzie do dyscypliny i rejestru.
- **Bramka F6:** co najmniej 300 zakładów na papierze, średnie CLV > 0 przy p < 0,05, poprawna kalibracja. Wtedy dopiero prawdziwe pieniądze.
- **Shadow bets:** gdy brak kandydatów, można zapisać N selekcji najbliższych progu (`scan --log-shadow N`) ze stawką 0 i `is_shadow = TRUE`. Mierzą tylko CLV cen miękkich bukmacherów i proxy vs zamknięcie Pinnacle. Nie liczą się do strategii, ekspozycji, limitów promocji ani bramek.
- **Audyt:** subagent `backtest-auditor` przegląda każdy backtest pod kątem patrzenia w przyszłość, przeuczenia i znaczników czasu.

## Konsekwencje
- Rejestr musi zapisywać `captured_at` każdego kursu i wersję modelu.
- Wyniki backtestów zapisujemy w `docs/experiments/`, a kluczowe decyzje w ADR.
