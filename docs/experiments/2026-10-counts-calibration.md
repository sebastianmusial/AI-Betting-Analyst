# Kalibracja modelu rogów i kartek (NB), walk-forward E1 / D2 / N1

- **Data:** 2026-10-17
- **Kod:** `src/betting_analyst/models/counts.py` (`fit_counts`, `walk_forward`, `calibration_table`), wersja `nb-counts-v0`
- **Dane:** football-data.co.uk E1, D2, N1, sezony 2024/25–2026/27 (do 2026-10-14). Kolumny HC/AC, HY/AY, HR/AR, a dla E1 także `Referee`.
- **Powiązane:** ADR 0011 (model musi pobić poprzednią warstwę out-of-sample), ADR 0015 (walk-forward, bez patrzenia w przyszłość), plan, Krok 2.

## Werdykt

| Rynek | Lepszy od baseline'u „średnia ligi”? | Zastosowanie w Morning Scout |
|---|---|---|
| **Rogi, suma** (O/U 7.5–12.5) | **Minimalnie.** Hold-out: ΔBrier ≈ −0,001 na liniach 7.5–10.5 (t od −1,1 do −2,2); przy 11.5–12.5 brak różnicy. Prognozy prawie nie odbiegają od średniej ligi (odch. std. p przy 9.5 = 0,023). | Tylko na papierze (`MODEL_ONLY`). Edge ≥ 8% z tego modelu oznacza, że kurs STS odstaje od średniej ligi, a nie że model zna mecz lepiej. |
| **Kartki, suma** (O/U 2.5–6.5) | **Tylko dzięki lidze i sędziemu.** Efekty drużyn dają ΔBrier od 0 do −0,0007 (t do −2,4 na 5.5/6.5). Rozrzut prognoz (std 0,12) pochodzi głównie z poziomu ligi i sędziego (E1). | Na papierze. W E1 z sędzią ma to sens, w D2/N1 to praktycznie średnia ligi. |
| **Per drużyna** (rogi gospodarza/gościa, kartki gospodarza/gościa) | **Tak, wyraźnie.** ΔBrier od −0,0013 do −0,0068, t od −2,6 do −5,6 dla wszystkich badanych linii. | Najbardziej obiecujące rynki model-only. Nadal papier, dopóki nie zbierzemy CLV/wyników na STS. |
| **„Więcej rogów/kartek”, wynik remis** (`*_most` = draw) | **Nie, źle skalibrowane.** Remis w kartkach: model 0,207, w rzeczywistości 0,267; w rogach: 0,105 vs 0,087. | **Nie używać** remisu `*_most`. Strona home/away jest lepsza od baseline'u (t ≈ −5), ale przez zły remis cały rynek 1X2 jest podejrzany. |

**Werdykt ogólny:** model NB jest out-of-sample **nie gorszy i zwykle lepszy** od baseline'u średniej ligi, więc spełnia warunek ADR 0011 i może wejść jako źródło `p_fair` dla rynków model-only. **Przewaga na sumach jest jednak bardzo mała.** Próg edge ≥ 8% i status „tylko papier” są uzasadnione. Do strategii (realne stawki) rogi i kartki **nie wchodzą**, dopóki rejestr papierowy nie pokaże dodatniego wyniku względem kursów STS. Pinnacle nie ma tych rynków, więc CLV vs Pinnacle odpada.

## Model (skrót)

- `X_h ~ NB(mu_h, r)`, `log mu_h = baza + atak[h] + obrona[a] + gospodarz (+ sędzia)`; dla gościa analogicznie, bez czynnika gospodarza.
- Ważona MAP: prior N(0, sd²) na efekty drużyn (`team_prior_sd`) i sędziów (`referee_prior_sd=0.15`). Wagi `exp(-xi · dni)`, `xi=0.0018` jak w DC.
- **Rozkład sumy:** `NB(mu_h + mu_a, r_suma)`, gdzie `r_suma` dopasowujemy osobno (`total_model="nb_total"`). Powód: w danych rogi gospodarza i gościa są **ujemnie** skorelowane, a kartki **dodatnio**:

  | Liga | corr(rogi H, rogi A) | corr(kartki H, kartki A) | suma rogów: średnia / wariancja | suma kartek: średnia / wariancja |
  |---|---|---|---|---|
  | E1 | −0,28 | +0,15 | 10,29 / 11,42 | 3,83 / 4,07 |
  | D2 | −0,23 | +0,14 | 10,32 / 11,40 | 4,82 / 5,26 |
  | N1 | −0,37 | +0,17 | 10,22 / 10,88 | 3,20 / 3,86 |

  Splot dwóch niezależnych NB (`total_model="convolution"`) zawyża więc rozrzut sumy rogów. W log score całego rozkładu wypadał o 0,01–0,03 nata gorzej (tabela siatki poniżej).
- Sędzia: tylko dla kartek, tylko E1 i tylko sędziowie z ≥ 5 meczami w oknie. Pozostali dostają 0, czyli średnią ligi.
- Baseline „league” to ten sam NB bez efektów drużyn (baza + gospodarz + dyspersja, **w E1 z sędzią**). Baseline „freq” to odsetek overów w 365 dniach przed refitem.

### Konwencja kartek

Domyślnie **liczba kartek = żółte + czerwone** (`red_weight=1`). Tak działa rynek „liczba kartek” u polskich bukmacherów, w odróżnieniu od „punktów karnych” (booking points: Y=10, R=25), który jest innym rynkiem. **Nie potwierdziłem w regulaminie STS**, jak liczona jest druga żółta prowadząca do czerwonej (jako 1 czy 2 kartki). Nie wiadomo też dokładnie, czy football-data wlicza drugą żółtą do HY. Przy czerwonych w ok. 5–10% meczów różnica to co najwyżej ~0,1 kartki na mecz, ale linia x.5 jest na to wrażliwa. **Do zrobienia:** sprawdzić regulamin STS (sekcja rozliczania kartek) i ewentualnie ustawić `red_weight`.

## Protokół

- `walk_forward(matches, stat, start="2025-08-01", end="2026-10-17", refit_days=14)`: refit co 14 dni wyłącznie na meczach z datą < data refitu, prognoza meczów z następnych 14 dni. Okno treningowe to wszystkie wcześniejsze mecze od 2024-08, przy wagach z zanikaniem.
- Pomijamy mecze, w których drużyna nie występowała w danych treningowych (beniaminek przed pierwszym meczem w oknie): E1 12, D2 11, N1 5.
- **Podział:** okres A (2025-08-01…2025-12-31, 577 meczów) służy do wyboru hiperparametrów. Okres B (2026-01-01…2026-10-17, 813 meczów: E1 377, D2 212, N1 224) to **hold-out**. Wszystkie tabele poniżej, poza siatką, są z B.
- Metryki: Brier i log loss dla P(over) na każdej linii, sparowana różnica Briera team − baseline z t-statystyką (ujemna = model lepszy) oraz log score całego rozkładu sumy.

## Wybór hiperparametrów (okres A, pooled E1+D2+N1, średnia po liniach sumy)

| stat | wariant | Brier team | Brier league | Brier freq | −log p(suma) team | −log p(suma) league |
|---|---|---|---|---|---|---|
| corners | **nb_total, sd 0.05** | **0,2141** | 0,2145 | 0,2154 | **2,6066** | 2,6079 |
| corners | nb_total, sd 0.08 | 0,2142 | 0,2145 | 0,2154 | 2,6078 | 2,6079 |
| corners | nb_total, sd 0.08, xi 0.0036 | 0,2145 | 0,2145 | 0,2154 | 2,6089 | 2,6083 |
| corners | convolution, sd 0.08 | 0,2146 | 0,2155 | 0,2154 | 2,6204 | 2,6357 |
| corners | nb_total, sd 0.15 | 0,2158 | 0,2145 | 0,2154 | 2,6168 | 2,6079 |
| cards | convolution, sd 0.05 | 0,1872 | 0,1873 | 0,1877 | 2,1535 | 2,1539 |
| cards | **nb_total, sd 0.05** | 0,1873 | 0,1874 | 0,1877 | **2,1531** | 2,1538 |
| cards | nb_total, sd 0.15 | 0,1884 | 0,1874 | 0,1877 | 2,1582 | 2,1538 |

Wybór: `total_model="nb_total"`, `team_prior_sd=0.05` (domyślne w kodzie). Przy sd 0.15 model przeucza się i przegrywa z baseline'em. Efekty drużyn trzeba mocno ściągać do średniej, bo sezon daje na drużynę tylko ok. 46 obserwacji. Dla kartek `convolution` i `nb_total` wypadają tak samo, więc dla prostoty zostaje jeden wariant.

## Hold-out B: sumy, pooled E1+D2+N1 (n = 813 meczów)

| stat | linia | odsetek overów | Brier team | Brier league | Brier freq | LL team | LL league | ΔB vs league (t) | ΔB vs freq (t) |
|---|---|---|---|---|---|---|---|---|---|
| corners | 7.5 | 0,800 | 0,1597 | 0,1606 | 0,1611 | 0,4993 | 0,5021 | −0,0009 (−2,2) | −0,0014 (−2,6) |
| corners | 8.5 | 0,685 | 0,2151 | 0,2159 | 0,2161 | 0,6213 | 0,6235 | −0,0009 (−1,5) | −0,0010 (−1,3) |
| corners | **9.5** | 0,562 | 0,2450 | 0,2463 | 0,2467 | 0,6830 | 0,6858 | −0,0014 (−1,8) | −0,0017 (−1,5) |
| corners | **10.5** | 0,460 | 0,2479 | 0,2487 | 0,2496 | 0,6888 | 0,6906 | −0,0009 (−1,1) | −0,0018 (−1,5) |
| corners | 11.5 | 0,372 | 0,2347 | 0,2349 | 0,2352 | 0,6625 | 0,6628 | −0,0002 (−0,2) | −0,0005 (−0,4) |
| corners | 12.5 | 0,262 | 0,1942 | 0,1940 | 0,1942 | 0,5776 | 0,5769 | +0,0002 (+0,3) | 0,0000 (0,0) |
| cards | 2.5 | 0,713 | 0,1959 | 0,1963 | 0,1982 | 0,5789 | 0,5801 | −0,0004 (−1,4) | −0,0024 (−1,7) |
| cards | **3.5** | 0,517 | 0,2340 | 0,2344 | 0,2371 | 0,6608 | 0,6617 | −0,0004 (−1,0) | −0,0031 (−1,9) |
| cards | **4.5** | 0,336 | 0,2099 | 0,2099 | 0,2142 | 0,6083 | 0,6081 | 0,0000 (0,0) | −0,0043 (−2,7) |
| cards | 5.5 | 0,201 | 0,1546 | 0,1554 | 0,1586 | 0,4823 | 0,4841 | −0,0007 (−2,4) | −0,0040 (−4,1) |
| cards | 6.5 | 0,101 | 0,0911 | 0,0915 | 0,0918 | 0,3224 | 0,3242 | −0,0004 (−2,4) | −0,0008 (−1,3) |

Log score rozkładu sumy w B (dodatni zysk = model lepszy od league):

| liga | rogi: zysk (t) | kartki: zysk (t) |
|---|---|---|
| E1 | +0,0014 (0,4) | +0,0036 (1,9) |
| D2 | +0,0025 (0,8) | +0,0030 (1,5) |
| N1 | +0,0014 (0,4) | −0,0003 (−0,2) |

Per liga (B) różnice mają ten sam znak co pooled. W N1 model jest dla sum praktycznie równy baseline'owi, a w D2 rogi 9.5/10.5 są najlepsze (t ≈ −2). Pełne tabele per liga i linia daje `walk_forward` z protokołu.

### Efekt sędziego (E1, kartki, wariant nb_total sd 0.08)

| | Brier, okres A | Brier, okres B | −log p(suma), okres B |
|---|---|---|---|
| z sędzią | 0,1785 | 0,1830 | 2,0877 |
| bez sędziego | 0,1811 | 0,1870 | 2,1064 |

Sędzia to największy pojedynczy czynnik w kartkach E1: ok. −0,003 do −0,004 Briera w obu okresach. Dla D2 i N1 football-data nie podaje sędziego, a to istotna luka, bo STS ogłasza sędziów przed meczem.

## Hold-out B: krzywe kalibracji, główne linie (pooled)

Rogi 9.5 (model): prawie wszystkie prognozy mieszczą się w 0,5–0,6 (n=764, p̄=0,561, trafienia 0,550). Koszyk 0,6–0,7 ma n=48, p̄=0,612 i trafienia 0,750, czyli mała próba z sygnałem w dobrą stronę. Baseline: jeden koszyk, p̄=0,565, trafienia 0,562.

Rogi 10.5 (model): koszyk 0,3–0,4: n=19, p̄=0,392, trafienia 0,263; koszyk 0,4–0,5: n=780, p̄=0,443, trafienia 0,463; koszyk 0,5–0,6: n=14, p̄=0,510, trafienia 0,571. Baseline: p̄=0,445, trafienia 0,460.

Kartki 3.5:

| koszyk p | n (model) | p̄ (model) | trafienia (model) | n (league) | p̄ (league) | trafienia (league) |
|---|---|---|---|---|---|---|
| 0,3–0,4 | 80 | 0,383 | 0,338 | 78 | 0,385 | 0,346 |
| 0,4–0,5 | 255 | 0,438 | 0,396 | 260 | 0,438 | 0,392 |
| 0,5–0,6 | 216 | 0,542 | 0,542 | 225 | 0,544 | 0,547 |
| 0,6–0,7 | 148 | 0,665 | 0,676 | 133 | 0,669 | 0,692 |
| 0,7–1,0 | 114 | 0,717 | 0,658 | 117 | 0,713 | 0,650 |

Kartki 4.5:

| koszyk p | n (model) | p̄ (model) | trafienia (model) | n (league) | p̄ (league) | trafienia (league) |
|---|---|---|---|---|---|---|
| 0–0,3 | 317 | 0,250 | 0,196 | 322 | 0,251 | 0,199 |
| 0,3–0,4 | 227 | 0,343 | 0,361 | 231 | 0,345 | 0,368 |
| 0,4–0,5 | 83 | 0,450 | 0,470 | 48 | 0,431 | 0,438 |
| 0,5–0,6 | 186 | 0,533 | 0,484 | 212 | 0,526 | 0,486 |

W kartkach widać lekki **overprediction w koszykach skrajnych** (0–0,3 i 0,7–1,0). Ma go też baseline, więc to efekt poziomu ligi: N1 w 2026/27 ma mniej kartek (2,78 na mecz) niż w 2025/26. Zanikanie wagi (`xi`) reaguje na to powoli. Ewentualna poprawka to szybszy `xi` dla bazy ligi przy wolniejszym dla drużyn.

## Hold-out B: rynki per drużyna i „więcej rogów/kartek” (pooled, n = 813)

| rynek | trafienia | p̄ model | p̄ league | Brier model | Brier league | ΔB (t) |
|---|---|---|---|---|---|---|
| home_corners_ou_4.5 | 0,630 | 0,616 | 0,610 | 0,2291 | 0,2342 | −0,0051 (−4,8) |
| home_corners_ou_5.5 | 0,475 | 0,473 | 0,471 | 0,2426 | 0,2494 | −0,0068 (−5,6) |
| away_corners_ou_3.5 | 0,609 | 0,627 | 0,622 | 0,2337 | 0,2385 | −0,0048 (−5,0) |
| away_corners_ou_4.5 | 0,486 | 0,464 | 0,462 | 0,2448 | 0,2498 | −0,0049 (−4,4) |
| home_cards_ou_1.5 | 0,515 | 0,522 | 0,521 | 0,2353 | 0,2373 | −0,0021 (−4,3) |
| away_cards_ou_1.5 | 0,627 | 0,631 | 0,631 | 0,2265 | 0,2279 | −0,0014 (−2,8) |
| away_cards_ou_2.5 | 0,342 | 0,368 | 0,368 | 0,2202 | 0,2215 | −0,0013 (−2,6) |
| corners_most = home | 0,550 | 0,555 | 0,553 | 0,2389 | 0,2474 | −0,0085 (−5,9) |
| corners_most = draw | 0,087 | 0,105 | 0,103 | 0,0799 | 0,0799 | 0,0000 (0,1) |
| cards_most = home | 0,287 | 0,320 | 0,320 | 0,2041 | 0,2064 | −0,0023 (−4,8) |
| cards_most = draw | 0,267 | 0,207 | 0,207 | 0,1990 | 0,1990 | 0,0000 (−0,5) |

Dlaczego rynki per drużyna wypadają lepiej niż sumy: efekty drużyn częściowo się znoszą w sumie (dobra drużyna ma więcej rogów, a rywal mniej), więc sygnał drużynowy widać dopiero w rynkach jednej drużyny i „kto więcej”. Remis w `*_most` jest źle skalibrowany, bo zakładamy niezależność, a korelacja w danych to −0,3 dla rogów i +0,15 dla kartek.

## Ograniczenia

1. **Brak kontekstu meczu.** Model zna tylko średnie siły drużyn, a nie oczekiwany przebieg meczu: faworyt przyciska, więc ma więcej rogów; derby i stawka meczu dają więcej kartek. Największy potencjalny zysk to kowarianty z rynku (zdewigowane 1X2 i O/U goli z Pinnacle) i sędzia dla D2/N1. To osobne zadanie.
2. **Niezależność H/A** w rozkładach brzegowych i `*_most`. Suma ma własne `r_suma`, ale łącznego rozkładu nie modelujemy. Bivariate NB lub kopuła to możliwy następny krok.
3. **Mało danych:** 2 sezony historii i hold-out 813 meczów. Różnice na sumach rzędu 0,001 Briera mają t ≈ 1–2, więc nie są rozstrzygające.
4. **Konwencja kartek STS niepotwierdzona** (patrz wyżej).
5. **Ekstraklasa wyłączona:** POL.csv nie ma statystyk, a `load_match_stats` zwraca dla lig „extra” pusty DataFrame.
6. Beniaminek przed pierwszym meczem w oknie dostaje `None` (domyślnie) albo średnią ligi (`allow_unknown=True`). Oba warianty są gorsze niż prior z poprzedniej ligi.
7. Kalibracja na wynikach, nie na kursach: nie wiemy, ile kosztuje marża STS na tych rynkach. Rejestr papierowy pokaże, czy edge ≥ 8% przekłada się na zysk.

## Reprodukcja

```python
from betting_analyst.config import load_strategy
from betting_analyst.sources.football_data import load_match_stats
from betting_analyst.models.counts import walk_forward, brier, calibration_table

df = load_match_stats(load_strategy().leagues["championship"], 3)
preds = walk_forward(df, "corners", "2025-08-01", "2026-10-17", refit_days=14, league="E1")
holdout = preds[preds.date >= "2026-01-01"]
g = holdout[holdout.line == 9.5]
brier(g.p_team.values, g.over.values), brier(g.p_league.values, g.over.values)
calibration_table(g.p_team.values, g.over.values)
```

Siatka hiperparametrów: `total_model` ∈ {nb_total, convolution} × `team_prior_sd` ∈ {0.05, 0.08, 0.15}, plus `xi=0.0036` i wariant bez sędziego. Każdy wariant to jedno wywołanie `walk_forward(..., **kwargs)`, a cała siatka liczy się w ok. 25 s. Rynki per drużyna: `fit_counts` co 14 dni i `predict_markets` (te same daty refitu, okres B).
