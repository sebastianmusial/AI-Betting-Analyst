# ADR 0022: Wyniki F2: przewaga tylko bez podatku i przy kursach z górnej granicy rynku

- **Status:** Accepted
- **Data:** 2026-10-17
- **Eksperyment:** [2026-10-f2-backtest.md](../experiments/2026-10-f2-backtest.md)

## Kontekst
Bramka F2 (ADR 0015) pyta, czy jakakolwiek strategia ma dodatnie EV po podatku na danych out-of-sample. Pierwszy realny skan (2026-10-17) nie znalazł żadnego kandydata. Najlepszy miał EV ok. −4,5% po podatku. Backtest walk-forward objął E1/D2/N1 w sezonach 2015/16–2025/26 (12 tys. meczów) oraz Ekstraklasę, dla której są tylko kursy zamknięcia. Fair dawał Pinnacle przedmeczowy, a KPI było CLV wobec zdewigowanego zamknięcia.

Wyniki:
- **Podatek 12%:** żadna konfiguracja z sensowną liczbą zakładów nie ma dodatniego CLV (pojedyncze komórki z n ≤ 9 to szum). Przy rynkowym Max CLV wynosi od −4% do −13%.
- **Kursy Avg:** brak okazji nawet bez podatku (mediana marży Avg 5,4–6,9%). Avg, MaxSoft i Max to kursy buków bez licencji MF, a polscy bukmacherzy są zwykle poniżej Avg.
- **Single 0% przy rynkowym Max**, próg ADR 0014: CLV na holdoucie +2,9% [blokowe CI +1,1%; +4,6%], n = 190, p_Holm = 0,002. Wynik jest kruchy: bez górnych 5% CLV zostaje +1,3% [−0,4%; +2,9%], a duża część sygnału pochodzi z outsiderów. Nie przechodzi testu głównego (próg strojony na dev), więc pochodzi z testu wtórnego (ścieżka rozwidleń). Wynik z całych 11 sezonów (+4,1%) jest zawyżony przez nieaktualne lub arbitrażowe kursy w kolumnie Max do 2021/22 (16–26% meczów). Trend jest skonfundowany zmianami danych (także marża PSH od 2024/25).
- **Kelly ¼ na holdoucie:** 1000 → 951 zł (ROI ≈ szum).
- **Przy kursie 1% poniżej Max** przewaga traci istotność po korekcie. 6% podatku (Betclic powyżej limitu) ją zjada.
- **Dixon-Coles** jest istotnie gorszy od rynku we wszystkich ligach (Δ log loss ≈ +0,02–0,035). Kaunitz (konsensus Avg) ma ujemne CLV.
- **Metody devig** (multiplicative / power / shin) są nierozróżnialne na kalibracji.

## Decyzja
1. **Werdykt F2: NO-GO dla zakładów z podatkiem 12%, dla kursów typowego bukmachera i dla modelowania jako źródła przewagi.** Dodatnie CLV istnieje tylko dla hipotetycznej najlepszej ceny rynku przy 0% podatku. Warunkowe GO, zależne od dowodu z kursów PL, wyłącznie dla ścieżki „0% + najlepsza cena”: Betclic single do limitu promocji oraz AKO 0% (warunki AKO w Betclic do weryfikacji w regulaminie).
2. **Przejście do F6 wymaga najpierw dowodu z kursów PL** (F3): snapshoty kursów Betclic (i pozostałych buków właściciela) z czasem oraz rozkłady `kurs_PL / PSH` i `kurs_PL / Max` osobno dla kursów ≤ 3 i > 3. Warunek przewagi brzmi: Betclic bywa **najlepszą ceną rynku**, często dla outsiderów, przy 0% podatku. Jeśli tak nie jest, projekt zostaje narzędziem do dyscypliny i rejestru (ADR 0001, kryterium porażki).
3. **Domyślna metoda devig: `power`** (bez zmian w `strategy.yaml`). Metody są nierozróżnialne na kalibracji (log loss), ale różnią się CLV zakładów na outsiderach: holdout B/Max: power +2,9%, shin +3,4%, multiplicative +6,4%. `power` jest najbardziej konserwatywny i dlatego zostaje. `multiplicative` nie wolno używać do oceny value na długich kursach.
4. **Dixon-Coles nie wpływa na decyzje.** Zostaje wyłącznie jako flaga „do ręcznej weryfikacji” (ADR 0014). Etapy 3–4 ADR 0011 (xG, stacking) są zawieszone do czasu, aż pojawi się przewaga rynkowa wymagająca potwierdzenia.
5. **Progi ADR 0014** (3%, a przy kursie > 3,0 5%) zostają bez zmian. To jedyna konfiguracja ustalona przed F2, więc nie stroimy jej na holdoucie. Hipotezę „0% + najlepsza cena” trzeba zweryfikować na **nowych** danych (paper trading po kursach PL), a nie na tym samym holdoucie.
6. **Skaner i raport dzienny** pokazują kandydatów z podatkiem 12% tylko informacyjnie. Priorytet mają oferty 0% (Betclic single, AKO), a shadow bets (ADR 0015) dalej mierzą CLV.

## Konsekwencje
- F3 zmienia priorytet: najważniejsze są kursy polskich bukmacherów z czasem, potem reszta danych (składy, xG).
- Oczekiwana skala przewagi to w najlepszym razie ok. 1–3% CLV, a okazji jest ok. 1 tygodniowo na 3 ligi (holdout), i to przy kursach Max, a nie PL. Przy bankrollu 1000 zł i capie 1,5% to kwoty symboliczne. Celem jest weryfikacja przewagi, nie zysk.
- Limit Betclic 1000 zł/mies. przy obecnym bankrollu nie jest wiążący.
- Ekstraklasa nie ma dowodu przewagi (zakład w chwili zamknięcia przy Max 0%: ROI ok. −2%). Bez własnych snapshotów kursów przedmeczowych nie da się tego zweryfikować.
- Kod backtestu (`ba-backtest`) służy do ponownej weryfikacji, gdy pojawią się kursy PL (wariant „kurs PL” zamiast Avg/Max).

## Rozważane opcje
- **Kontynuować modelowanie (DC, stacking) w nadziei na przewagę modelu:** odrzucone. DC przegrywa z rynkiem o kilka setnych log loss, a do pokonania jest kilkanaście procent po podatku.
- **Uznać pełne GO na podstawie wariantu Max:** odrzucone. Max nie jest kursem dostępnym u polskiego bukmachera, test główny go nie potwierdził, a wynik jest wrażliwy na ogony i jakość danych.
- **Pełne NO-GO i koniec projektu jako źródła typów:** przedwczesne. Ścieżka 0% przy kursach blisko Max jest istotna w teście wtórnym i da się ją tanio zweryfikować w F3.
