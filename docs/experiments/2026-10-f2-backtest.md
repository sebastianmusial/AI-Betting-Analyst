# F2: walk-forward backtest, czyli czy po polskim podatku istnieje przewaga

- **Data:** 2026-10-17
- **Kod:** `src/betting_analyst/backtest/`, uruchomienie `uv run ba-backtest [--refresh]`
- **Pełne tabele (generowane):** [2026-10-f2-backtest-tables.md](2026-10-f2-backtest-tables.md)
- **Decyzja:** [ADR 0022](../adr/0022-wyniki-f2-przewaga-tylko-bez-podatku.md)
- **Audyt:** `backtest-auditor`, sekcja 9; poprawki naniesione

## Werdykt w skrócie

**NO-GO dla przewagi po podatku 12%, dla kursów typowego bukmachera i dla modelowania (Dixon-Coles).** Dodatnie CLV widać tylko dla hipotetycznej najlepszej ceny rynku (Max z football-data) przy 0% podatku. **Nie ma dowodu, że jest ona osiągalna u polskiego bukmachera.**

| Pytanie | Odpowiedź |
|---|---|
| Single z podatkiem 12% | **Nie.** Żadna konfiguracja z sensowną liczbą zakładów nie ma dodatniego CLV. Pojedyncze komórki siatki z n ≤ 9 to szum. Przy rynkowym Max CLV po podatku wynosi od −4% do −13%. |
| Kursy Avg, nawet bez podatku | **Nie.** Przy progu ≥ 1% nie ma praktycznie żadnych zakładów. Mediana marży Avg wobec fair to 5,4–6,9%. |
| Single 0% przy rynkowym Max (próg ADR) | **Tylko jako górna granica.** Holdout: CLV +2,9% [blokowe 95% CI +1,1%; +4,6%], n = 190, p_Holm = 0,002. Po odrzuceniu górnych 5% CLV zostaje +1,3% [−0,4%; +2,9%]. |
| Single 0% przy MaxSoft (B365/BW/WH/1XB) | CLV +3,0% na holdoucie przy n = 47. Nieistotne po korekcie (p_Holm = 0,58), CI obejmuje 0. |
| Przy 6% podatku (Betclic powyżej limitu) | **Nie.** Ponowna selekcja przy 6% daje holdout n = 21, CLV −0,9%, a całość n = 79, +0,8%, p = 0,33. Te same zakłady co przy 0% miałyby ok. −2%. |
| AKO 2 nogi, 0%, Max | CLV +10% przy n = 34. To ten sam sygnał co single (te same nogi, ok. 5% na nogę), z większą wariancją, a Max w każdej nodze u innego buka jest niewykonalny. Na Avg i MaxSoft prawie zero kuponów. |
| Kaunitz (konsensus Avg → Max) | **Nie.** CLV od −3% do −14%. |
| Dixon-Coles | **Gorszy od rynku** o ok. 0,02–0,035 log loss w każdej lidze (p ≤ 0,004 poza Eredivisie O/U na dev, gdzie p = 0,08). |
| Metoda devig | Nierozróżnialne na kalibracji. Zostaje `power`, najbardziej konserwatywna dla CLV outsiderów (sekcja 4.5). |

Główna niewiadoma, i warunek przejścia dalej, to pytanie, czy Betclic PL bywa najlepszą ceną rynku, zwłaszcza dla outsiderów, od których pochodzi duża część sygnału. Dowód może dać tylko F3 (snapshoty kursów PL), a potem F6 (paper trading).

## 1. Protokół

- **Dane:** football-data.co.uk, E1 / D2 / N1, sezony 2015/16–2025/26 (11 sezonów, 12 022 mecze z Pinnacle przedmeczowym). O/U 2,5 od 2019/20, bo wcześniej brak Pinnacle O/U. Ekstraklasa tylko z kursami zamknięcia (sekcja 6). W 2025/26 Pinnacle zniknął z plików w trakcie sezonu.
- **Chwila decyzji = migawka przedmeczowa football-data** (wg opisu źródła zwykle piątek po południu dla weekendu, wtorek dla środka tygodnia). Prawdopodobieństwo fair to devig PSH/PSD/PSA (i P>2.5). Kurs zagrania pochodzi z tej samej migawki: Avg, MaxSoft = max(B365, BW, WH, 1XB) albo Max rynkowy (od 2019/20 oddsportal, wcześniej Betbrain BbMx). **Żaden z tych buków nie ma licencji MF.** To przybliżenia rynku, nie kursy PL, a polscy bukmacherzy są zwykle *poniżej* Avg. „Avg” jest więc raczej optymistyczny niż realistyczny, co tylko wzmacnia NO-GO. Skład MaxSoft zmienia się w czasie (1XB tylko w części plików, w 2025/26 brak WH).
- **Zamknięcie PSCH/PSCD/PSCA służy wyłącznie do CLV** i jest dołączane po wyborze zakładu. Decyzja widzi tylko `DECISION_COLUMNS`; test `test_strategy_selection_ignores_closing_odds` tasuje wszystkie kolumny `*close*`.
- **CLV** = `kurs_po_podatku × p_fair_zamknięcia − 1`, devig zamknięcia tą samą metodą co otwarcia. t-test jednostronny liczę na średnich per mecz, a dla kluczowych wyników podaję też CI z bootstrapu blokowego po tygodniach.
- **Strategie** (wspólna warstwa `decision/ev.py`):
  - A: single 12%;
  - B: single 0% (w symulacji bankrolla miesięczny limit Betclic 1000 zł, potem 6%);
  - C2/C3: AKO 2/3 nogi 0% (`build_ako_proposals`, jedno AKO dziennie, nogi z różnych meczów);
  - D: Kaunitz;
  - E1: value wg Dixon-Colesa;
  - E2: rynek + filtr zgodności z DC (|Δp| ≤ 8 pp).

  Na każdy mecz i rynek najwyżej jeden zakład. Progi EV: 0, 1, 2, 3, 5, 7, 10% oraz reguła ADR 0014. Razem 192 konfiguracje.
- **Dixon-Coles walk-forward:** refit co tydzień (bloki pt–czw), trening tylko na meczach z datą < początek bloku, okno 3 lata, ξ = 0,0018 (wartości z `strategy.yaml`, niestrojone), pokrycie ok. 99%. Testy: `test_model_for_day_d_never_sees_matches_on_or_after_d`, `test_future_results_do_not_change_prediction`.
- **Podział:** dev = 2015/16–2021/22, holdout = 2022/23–2025/26.
  - **Test główny:** próg wybrany na dev (najwyższe średnie CLV przy n ≥ 100), jeden test na holdoucie, korekta Holma w obrębie grupy wariantów.
  - **Test wtórny:** progi ADR 0014, ustalone przed F2, sprawdzane wprost na holdoucie, z korektą Holma.
- **Kryterium GO** (w planie nie przypisano go do konkretnego testu, co audytor słusznie wytknął): co najmniej jedna strategia na Avg lub MaxSoft ma na holdoucie CLV > 0 przy p_Holm < 0,05 i n ≥ 100. Wynik spełniony tylko na Max oznacza warunkowe GO, zależne od kursów PL.
- **Odstępstwa od planu:** dev wydłużyłem z 2019/20–2022/23 do 2015/16–2021/22 po stwierdzeniu, że Pinnacle 1X2 jest dostępny od 2015/16. Zmiana zapadła przed uruchomieniem strategii, ale nie da się tego zweryfikować z zewnątrz.

## 2. Kalibracja metod devig (Pinnacle przedmeczowy, E1/D2/N1)

| rynek | okres | n | multiplicative LL | power LL | shin LL | RPS (power) |
|---|---|---|---|---|---|---|
| 1X2 | dev | 8039 | 1,0160 | 1,0160 | 1,0160 | 0,2085 |
| 1X2 | holdout | 3983 | 1,0067 | 1,0066 | 1,0065 | 0,2073 |
| O/U 2,5 | dev | 3405 | 0,6772 | 0,6771 | 0,6772 | — |
| O/U 2,5 | holdout | 3983 | 0,6744 | 0,6742 | 0,6743 | — |

Sparowane różnice log loss są rzędu 10⁻⁵, p od 0,47 do 0,95. **Na kalibracji wybór metody nie ma znaczenia.** To samo widać na zamknięciach i w Ekstraklasie. Ma natomiast znaczenie dla CLV wybranych zakładów na outsiderach (sekcja 4.5). Krzywe kalibracji leżą na przekątnej.

![kalibracja](img/f2-calibration.png)

## 3. Dixon-Coles vs rynek

| liga | 1X2 LL rynek | 1X2 LL DC | Δ (DC − rynek) | O/U Δ |
|---|---|---|---|---|
| Championship | 1,0343 | 1,0568 | +0,0225 | +0,0141 |
| 2. Bundesliga | 1,0506 | 1,0765 | +0,0259 | +0,0185 |
| Eredivisie | 0,9349 | 0,9564 | +0,0215 | +0,0135 |
| Ekstraklasa (vs zamknięcie) | 1,0379 | 1,0726 | +0,0347 | — |

- DC jest istotnie gorszy od rynku we wszystkich ligach i okresach (p ≤ 0,004; wyjątek: Eredivisie O/U na dev, p = 0,08) i zbyt pewny na krańcach.
- E1 (value wg DC) daje CLV od −5% do −19%. E2 (filtr DC) nie poprawia CLV.
- Zgodnie z ADR 0011 DC nie wchodzi do decyzji.

## 4. Strategie: wyniki

Sanity, czyli granie wszystkiego (CLV przed podatkiem): po PSH −3,8%, po Avg −6,8%, po MaxSoft −4,4%, po Max −1,5%. Z 12% podatkiem wychodzi od −13% do −18%.

### 4.1 Test główny (próg strojony na dev → holdout, Holm)

| strategia | kurs | próg (dev) | dev n / CLV | holdout n / CLV | % bije zamkn. | p_Holm | GO? |
|---|---|---|---|---|---|---|---|
| A single 12% | Avg, MaxSoft | — | brak progu z n ≥ 100 | — | — | — | ✗ |
| B single 0% | Avg | — | brak progu z n ≥ 100 | — | — | — | ✗ |
| B single 0% | MaxSoft | 5% | 107 / +4,4% | 37 / +2,7% | 68% | 1,00 | ✗ |
| C2 AKO 0% | MaxSoft | 2% | 133 / +3,8% | 29 / −1,5% | 45% | 1,00 | ✗ |
| C3 AKO 0% | MaxSoft | 1% | 150 / +4,3% | 28 / +1,5% | 54% | 1,00 | ✗ |
| D Kaunitz 0% | MaxSoft | 10% | 176 / −1,0% | 25 / 0,0% | 52% | 1,00 | ✗ |
| E2 rynek+DC 0% | MaxSoft | ADR | 119 / +3,6% | 43 / +2,9% | 74% | 0,84 | ✗ |
| *B single 0%* | *Max* | *7%* | *200 / +6,0%* | *69 / +3,6%* | *59%* | *0,15* | ✗ |
| *C2 AKO 0%* | *Max* | *ADR* | *246 / +9,2%* | *34 / +10,2%* | *74%* | *0,001* | ✗ (n < 100) |

**NO-GO we wszystkich wariantach.** Test był jednak strukturalnie trudny do zdania: n ≥ 100 na dev przy holdoucie mniej więcej 3 razy mniejszym zwykle daje n < 100 na holdoucie. Holm liczy też puste konfiguracje (p = 1), co jest konserwatywne.

### 4.2 Test wtórny (progi ADR 0014, bez strojenia)

| strategia | kurs | holdout n | CLV | % bije | ROI płaska stawka [95% CI] | p | p_Holm | GO? |
|---|---|---|---|---|---|---|---|---|
| B single 0% | MaxSoft | 47 | +3,0% | 72% | −17% | 0,032 | 0,58 | ✗ |
| E2 rynek+DC 0% | MaxSoft | 43 | +2,9% | 74% | −9% | 0,047 | 0,79 | ✗ |
| **B single 0%** | **Max** | **190** | **+2,9%** | **67%** | −5% [−30%; +24%] | 0,0004 | **0,002** | **✓ tylko Max** |
| C2 AKO 0% | Max | 34 | +10,2% | 74% | −14% | 0,0002 | 0,001 | ✗ (n < 100) |
| A single 12% | dowolny | 0–1 | — | — | — | — | — | ✗ |

Wynik B/Max/ADR (p = 0,0004) przetrwałby nawet korektę Bonferroniego na wszystkich 48 testach holdoutu. To jednak wynik **po** porażce testu głównego (ścieżka rozwidleń). Kolejna weryfikacja musi być na nowych danych, a nie na tym samym holdoucie.

**Kelly** (¼, cap 1,5%, ekspozycja 5%/dzień, start 1000 zł): na holdoucie 1000 → **951 zł** (ROI −4,2%, maks. obsunięcie 11,8%, 187 zakładów). Na całości 1000 → 1668 zł, ale ten wynik pochodzi głównie z dev i jest zawyżony przez jakość kolumny Max (4.4). Limit Betclic 1000 zł/mies. przy tym bankrollu nigdy nie zadziałał.

### 4.3 Odporność wyniku B / Max / ADR (holdout)

| wariant | n | CLV | blokowe 95% CI | p (klastry) | % kursów > 5 |
|---|---|---|---|---|---|
| wszystkie | 190 | +2,9% | [+1,1%; +4,6%] | 0,0004 | 33% |
| bez meczów z arbitrażem w Max | 104 | +2,7% | [+0,1%; +5,0%] | 0,023 | 46% |
| bez górnych 5% CLV | 180 | +1,3% | [−0,4%; +2,9%] | 0,032 | 31% |

- Sygnał jest istotny, ale kruchy.
- 10 ze 190 zakładów daje ponad połowę sumy CLV, na przykład skrajne kursy Max na outsiderów (NAC–Ajax, Max 10,5 przy PSH 7,73).
- Wybrane zakłady mają Max w medianie ok. 8–10% powyżej PSH, a nazwani bukmacherzy są w medianie 5,6–6% poniżej Max. Polscy bukmacherzy najmocniej obcinają właśnie outsiderów, a stały haircut w 4.6 tego nie modeluje.

### 4.4 Jakość danych: wyniki z całości i trend są skonfundowane

| sezon | 15/16 | 16/17 | 17/18 | 18/19 | 19/20 | 20/21 | 21/22 | 22/23 | 23/24 | 24/25 | 25/26 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mecze z arbitrażem w Max (Σ1/Max < 1) | 16% | 26% | 19% | 21% | 18% | 16% | 19% | 4,6% | 3,7% | 0,9% | 0,7% |
| mediana marży PSH | 2,5% | 2,5% | 2,5% | 3,1% | 3,5% | 2,9% | 2,9% | 2,9% | 3,0% | **5,0%** | **5,0%** |
| mediana marży PSCH | 2,4% | 2,4% | 2,5% | 3,1% | 3,4% | 2,9% | 2,9% | 2,9% | 2,9% | 3,4% | 3,4% |
| n zakładów B/Max/ADR | 126 | 179 | 162 | 117 | 158 | 116 | 132 | 62 | 57 | 48 | 23 |
| CLV B/Max/ADR | +3,6% | +3,9% | +5,6% | +5,4% | +3,9% | +4,1% | +3,9% | +4,1% | +2,7% | +2,4% | +1,4% |

- Do 2021/22 co piąty mecz ma w kolumnie Max kursy dające arbitraż, czyli najpewniej nieaktualne lub błędne ceny. Od 2022/23 takich meczów jest kilka razy mniej, co wskazuje na zmianę źródła lub składu Max.
- 66% zakładów B/Max/ADR z całości (78–89% w erze Betbrain) pochodzi z takich meczów.
- Od 2024/25 marża PSH skacze do ok. 5% przy niezmienionej marży PSCH, więc migawka przedmeczowa pochodzi najpewniej z innego momentu lub źródła.
- **Wniosek:** wynik z całości (+4,1%, n = 1180, Kelly 1668 zł) jest zawyżony, a spadek liczby okazji od 2022/23 to w dużej mierze artefakt danych, nie tylko efekt wyrównywania się rynku. Jako miarę przewagi traktuję wyłącznie holdout.

### 4.5 Wrażliwość na metodę devig (B / Max / ADR, holdout)

| devig | n | CLV | blokowe 95% CI |
|---|---|---|---|
| power | 190 | +2,9% | [+1,1%; +4,6%] |
| shin | 218 | +3,4% | [+1,6%; +5,0%] |
| multiplicative | 430 | +6,4% | [+4,9%; +8,0%] |

Multiplicative przypisuje outsiderom za dużo prawdopodobieństwa, więc „znajduje” więcej value na długich kursach (64% zakładów po kursie > 5). `power` jest najbardziej konserwatywny i to on jest użyty w werdykcie, więc wynik nie jest zawyżony wyborem metody.

### 4.6 Jak blisko Max musi być polski bukmacher

Kurs = Max × (1 − h), single, próg ADR, selekcja powtarzana dla każdego h. p klastrowane, **bez korekty na 15 kombinacji**.

| h | 0%: holdout n / CLV / p | 0%: całość n / CLV | 6%: całość n / CLV | 12%: całość n / CLV |
|---|---|---|---|---|
| 0% | 190 / +2,9% / 0,0004 | 1180 / +4,1% | 79 / +0,8% | 14 / −4,5% |
| 1% | 108 / +2,5% / 0,02 | 630 / +3,8% | 58 / −1,3% | 11 / −1,1% |
| 2% | 75 / +1,7% / 0,17 | 373 / +3,6% | 40 / −2,6% | 9 / −1,8% |
| 3% | 53 / +1,4% / 0,27 | 247 / +2,9% | 31 / −3,6% | 5 / — |
| 5% | 32 / +2,1% / 0,25 | 110 / +3,0% | 22 / −6,1% | 3 / — |

Każdy procent poniżej Max mniej więcej połowi liczbę okazji. Już przy h = 1% wynik nie przetrwałby korekty. W praktyce warunek przewagi brzmi: **Betclic musi być najlepszą ceną na rynku, często dla outsiderów, i to przy 0% podatku.**

## 5. Dlaczego ROI ≠ CLV

ROI na holdoucie jest ujemne przy dodatnim CLV, a 95% CI ROI ma szerokość ok. 50 pp. Przy ok. 50 zakładach rocznie i średnim kursie ok. 6 ROI to szum (ADR 0001, 0015). Werdykt opiera się na CLV.

## 6. Ekstraklasa (tylko kursy zamknięcia, to NIE jest backtest decyzyjny)

POL.csv nie ma kursów przedmeczowych, więc nie da się zmierzyć CLV.
- **Kalibracja:** metody devig zamknięcia są nierozróżnialne (LL 1,0377–1,0379). DC jest gorszy od zamknięcia o 0,035 LL, najwięcej spośród lig.
- **Zakład w chwili zamknięcia** (Avg/Max zamknięcia vs fair zamknięcia Pinnacle z tej samej chwili; tu CLV ≡ EV):

| | Avg zamkn., 12% | Avg zamkn., 0% | Max zamkn., 12% | Max zamkn., 0% |
|---|---|---|---|---|
| średnie EV wszystkich selekcji | −18,6% | −7,5% | −12,8% | −0,9% |
| odsetek selekcji z EV ≥ 0 | 0,01% | 0,46% | 0,65% | 32,8% |
| ROI zakładów z EV ≥ 3% (n) | — (0) | −18% (10) | −30% (28) | −2,0% [−11%; +7%] (1001) |

W E1/D2/N1 ta sama reguła daje zrealizowane ROI ≈ EV (od +5% do +7%, CI obejmują 0). W Ekstraklasie ROI (−2%) jest dużo niższe od deklarowanego EV (ok. +6,5%). To ostrzeżenie, że EV liczone z Max bywa zawyżone, i brak przesłanek, że Ekstraklasa jest „miękka”. Bez własnych snapshotów kursów przedmeczowych nie ma tu żadnego dowodu przewagi.

## 7. Wiarygodność i ograniczenia

- **NO-GO dla podatku 12%, kursów Avg, Kaunitza i DC: bardzo wiarygodne.** Zero lub prawie zero okazji w 11 sezonach, margines kilkunastu punktów procentowych, a przybliżenia kursów (Avg, MaxSoft) są dla polskich bukmacherów raczej optymistyczne.
- **Dodatnie CLV przy 0% i Max: wiarygodne tylko jako własność kolumny Max na holdoucie.** Jest istotne i odporne na klastrowanie, ale kruche (ogony, outsiderzy), pochodzi z testu wtórnego, a Max to nie polski bukmacher. Nie przenosi się wprost na Betclic.
- **Chwila decyzji jest przybliżona:** brak znaczników czasu, a od 2024/25 zmiana charakteru PSH.
- **Wielokrotne porównania:** 192 konfiguracje. Holm działa w obrębie testu, pełna siatka jest opisowa.
- **Holdout jest mały:** 3,5 sezonu, w 2025/26 częściowy.
- **AKO nie jest niezależnym dowodem:** te same nogi co single, a warunki AKO 0% w Betclic (min. liczba nóg, min. kurs nogi) nie są zweryfikowane.
- **Podatek od wygranej (10% > 2280 zł):** pominięty. Dla singli nie występuje, ale dla C3 (średni kurs 59–147 przy stawce ok. 15 zł) wypłaty są na granicy progu.
- **Symulacja bankrolla** aktualizuje bankroll po każdej dacie meczu, a decyzja zapada w piątek. Efekt pomijalny.

## 8. Co dalej

1. **F3: snapshoty kursów Betclic PL (i STS, Fortuna, Superbet) z czasem.** Metryki: rozkład `kurs_PL / PSH` i `kurs_PL / Max` osobno dla kursów ≤ 3 i > 3 oraz odsetek selekcji, w których Betclic jest najlepszą ceną rynku. Bez tego nie ma podstaw do F6.
2. Skaner i raport dzienny: kandydaci z podatkiem 12% praktycznie nie wystąpią. Priorytet mają ścieżki 0% (Betclic single do limitu, AKO 0%), a shadow bets dalej mierzą CLV.
3. Dixon-Coles, Elo i stacking (ADR 0011, etapy 3–4) zawieszone jako źródło przewagi.
4. Następny test hipotezy „0% + najlepsza cena” musi powstać na nowych danych (paper trading po kursach PL), a nie na tym samym holdoucie.

## 9. Audyt (backtest-auditor)

Audytor nie znalazł patrzenia w przyszłość ani błędów w kursach zagrania, podatku i CLV. Niezależnie przeliczył p-wartości z klastrowaniem po meczu, dniu i tygodniu. Uwagi i to, co z nimi zrobiłem:
- **K1 (krytyczne), arbitraże i nieaktualne kursy w kolumnie Max zawyżają wynik z całości i trend:** dodałem diagnostykę danych (4.4) i wariant bez arbitraży (4.3). Werdykt opieram wyłącznie na holdoucie, a wynik z całości i Kelly 1668 zł oznaczyłem jako zawyżone.
- **W1, zmiana marży PSH od 2024/25:** odnotowana w 4.4 i w ograniczeniach.
- **W2, ścieżka rozwidleń, test główny trudny do zdania:** opisane w 1, 4.1 i 4.2. ADR 0022 nie twierdzi już, że progi ADR „wygrały”.
- **W3, ciężkie ogony:** dodałem blokowy bootstrap i wariant bez górnych 5% (4.3).
- **W4, Kelly na holdoucie:** podany (951 zł).
- **W5, warunek „≤ 1–2% od Max” był za łagodny:** przeformułowany na „najlepsza cena rynku, często dla outsiderów”. p w haircut są klastrowane i oznaczone jako nieskorygowane.
- **W6, Avg i MaxSoft to nie kursy PL:** opisane w 1.
- **W7, AKO nie jest niezależnym dowodem:** opisane w werdykcie i ograniczeniach.
- **W8, devig wpływa na CLV:** dodana sekcja 4.5.
- **Drobne:** poprawione sformułowania o podatku 6% i 12% oraz o p-wartościach DC. Udział opodatkowanych stawek w symulacji liczę teraz po przycięciu ekspozycji. Test zamknięcia obejmuje teraz także `avg_close`/`max_close`.
