# ADR 0022: Wyniki F2: przewaga tylko bez podatku i przy kursach z górnej granicy rynku

- **Status:** Accepted
- **Data:** 2026-10-17
- **Eksperyment:** [2026-10-f2-backtest.md](../experiments/2026-10-f2-backtest.md)

## Kontekst
Bramka F2 (ADR 0015) pyta, czy jakakolwiek strategia ma dodatnie EV po podatku na danych out-of-sample. Pierwszy realny skan (2026-10-17) nie znalazł żadnego kandydata. Najlepszy miał EV ok. −4,5% po podatku. Backtest walk-forward objął E1/D2/N1 w sezonach 2015/16–2025/26 (12 tys. meczów) oraz Ekstraklasę, dla której są tylko kursy zamknięcia. Fair dawał Pinnacle przedmeczowy, a KPI było CLV wobec zdewigowanego zamknięcia.

Wyniki:
- **Podatek 12%:** brak jakiejkolwiek konfiguracji z dodatnim CLV, nawet przy rynkowym Max (od −4% do −13%).
- **Kursy Avg** (typowy bukmacher): brak okazji nawet bez podatku. Średni kurs ma ok. 7% marży wobec fair.
- **Single 0% przy rynkowym Max**, próg ADR 0014: CLV +2,9% na holdoucie (n = 190, p_Holm = 0,002) i +4,1% na 11 sezonach. Wynik nie przechodzi testu głównego (próg strojony na dev). Okazji ubywa od 2022/23, a CLV maleje.
- **Przy kursie 1–2% poniżej Max** przewaga słabnie i traci istotność. 6% podatku (Betclic powyżej limitu) ją zjada.
- **Dixon-Coles** jest istotnie gorszy od rynku we wszystkich ligach (Δ log loss ≈ +0,02–0,035). Kaunitz (konsensus Avg) ma ujemne CLV.
- **Metody devig** (multiplicative / power / shin) są nierozróżnialne na kalibracji.

## Decyzja
1. **Werdykt F2: NO-GO dla zakładów z podatkiem 12% i dla modelowania jako źródła przewagi.** Warunkowe GO wyłącznie dla ścieżki „0% podatku + kurs blisko maksimum rynku”: Betclic single do limitu promocji oraz AKO 0%.
2. **Przejście do F6 wymaga najpierw dowodu z kursów PL** (F3): snapshoty kursów Betclic (i pozostałych buków właściciela) z czasem oraz rozkład `kurs_PL / max_rynkowy`. Jeśli Betclic rzadko jest w odległości ≤ 1–2% od Max, projekt zostaje narzędziem do dyscypliny i rejestru (ADR 0001, kryterium porażki).
3. **Domyślna metoda devig: `power`** (bez zmian w `strategy.yaml`). Wybór nie ma znaczenia praktycznego. `multiplicative` i `shin` zostają do porównań.
4. **Dixon-Coles nie wpływa na decyzje.** Zostaje wyłącznie jako flaga „do ręcznej weryfikacji” (ADR 0014). Etapy 3–4 ADR 0011 (xG, stacking) są zawieszone do czasu, aż pojawi się przewaga rynkowa wymagająca potwierdzenia.
5. **Progi ADR 0014** (3%, a przy kursie > 3,0 5%) zostają. W teście bez strojenia dały najlepszy kompromis między liczbą zakładów a CLV. Wyższe progi zostawiają za mało zakładów do weryfikacji.
6. **Skaner i raport dzienny** pokazują kandydatów z podatkiem 12% tylko informacyjnie. Priorytet mają oferty 0% (Betclic single, AKO), a shadow bets (ADR 0015) dalej mierzą CLV.

## Konsekwencje
- F3 zmienia priorytet: najważniejsze są kursy polskich bukmacherów z czasem, potem reszta danych (składy, xG).
- Oczekiwana skala przewagi to w najlepszym razie ok. 2–4% CLV, a okazji jest ok. 1 tygodniowo na 3 ligi (próba z ostatnich sezonów). Przy bankrollu 1000 zł i capie 1,5% to kwoty symboliczne. Celem jest weryfikacja przewagi, nie zysk.
- Limit Betclic 1000 zł/mies. przy obecnym bankrollu nie jest wiążący.
- Ekstraklasa nie ma dowodu przewagi (zakład w chwili zamknięcia przy Max 0%: ROI ok. −2%). Bez własnych snapshotów kursów przedmeczowych nie da się tego zweryfikować.
- Kod backtestu (`ba-backtest`) służy do ponownej weryfikacji, gdy pojawią się kursy PL (wariant „kurs PL” zamiast Avg/Max).

## Rozważane opcje
- **Kontynuować modelowanie (DC, stacking) w nadziei na przewagę modelu:** odrzucone. DC przegrywa z rynkiem o kilka setnych log loss, a do pokonania jest kilkanaście procent po podatku.
- **Uznać pełne GO na podstawie wariantu Max:** odrzucone. Max nie jest kursem dostępnym u polskiego bukmachera, a test główny go nie potwierdził.
- **Pełne NO-GO i koniec projektu jako źródła typów:** przedwczesne. Ścieżka 0% przy kursach blisko Max jest istotna w teście wtórnym i da się ją tanio zweryfikować w F3.
