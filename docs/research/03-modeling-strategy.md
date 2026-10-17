# 03. Sport, live vs pre-match, modele, decyzje, rola LLM

## 1. Wybór sportu i rynku
- **Piłka, ligi top:** najniższe marże i najbardziej efektywne ceny. Marże w EPL spadły z 9% do 4% (2005–2018). Marże rosną wraz ze schodzeniem w dół piramidy lig (Whelan 2026, 151 tys. meczów).
- **Piłka, ligi średniego szczebla:** Championship, 2. Bundesliga, Eredivisie, Ekstraklasa. Rozsądny kompromis: więcej błędów w cenach, a dane nadal dobre.
- **Rynki piłkarskie:**
  - 1X2 ma *favourite-longshot bias* (zakłady na outsiderów są przeszacowane).
  - Asian Handicap jest efektywniejszy (Hegarty & Whelan).
  - O/U i 1X2 u miękkich bukmacherów to łatwiejszy cel.
  - Zakłady na zawodników mają najsłabsze kursy, ale drogie dane i niskie limity.
- **Tenis:** dobry drugi wybór.
  - Rynek dwudrogowy, a Elo działa (Elo po nawierzchni około 76% trafności vs 68,6% dla zwykłego Elo; to blog, nie publikacja recenzowana).
  - Dużo meczów, więc szybko przybywa dowodów.
  - Turnieje ITF i Challenger: ryzyko ustawiania meczów.
- **Koszykówka (NBA):** rynek efektywny, a sezon jeszcze nie ruszył.
- **Hokej (KHL):** brak nieefektywności. **Esport:** szybkie zmiany patchy i ryzyko integralności.

## 2. Live vs pre-match
- Rynki live przesadnie reagują na zaskakujące gole (Angelini i in., IJF 2022), ale dowody pochodzą głównie z giełd zakładów.
- **Dla samodzielnego dewelopera live jest niekorzystny:**
  - streamy mają 5–8 s opóźnienia,
  - bukmacher dodaje opóźnienie akceptacji i zawiesza rynki,
  - feedy live są drogie,
  - marże live są wyższe.
- **Hybryda:** model pre-match plus kilka prostych, regułowych alertów live (np. outsider strzela wcześnie i kurs przestrzeliwuje). Zakład stawiany ręcznie, bez automatu.

## 3. Modele
- **Rynek jako baza:** zdewigowane kursy Pinnacle to najlepsza pojedyncza prognoza.
  - Metody devig różnią się najbardziej przy outsiderach. Przykład: kurs fair około 3,80 metodą multiplicative, 4,00 metodą Shin, 4,13 metodą power.
  - Domyślnie Shin lub power; obie testujemy na własnych danych.
  - Kaunitz i in.: grał przeciw konsensusowi wielu bukmacherów, był zyskowny w praktyce i został ograniczony przez bukmacherów.
- **Dixon-Coles / bivariate Poisson:**
  - Dixon-Coles najlepszy w Lidze Mistrzów (Brier, RPS, log loss); bivariate Poisson minimalnie lepszy w Lidze Europy.
  - Daje pełny rozkład wyników, więc obejmuje 1X2, O/U i AH.
  - Implementacja: `penaltyblog`.
- **Elo:** tani, odporny punkt odniesienia (ClubElo); podaje tylko prawdopodobieństwa wyniku.
- **xG:** bogatszy sygnał niż gole, ale dla naszych lig trzeba go pozyskać z Sofascore/FotMob albo z płatnego źródła.
- **Gradient boosting (LightGBM):** jako warstwa łącząca (stacking) Elo, DC, xG, odpoczynek, składy i rynek.
  - Hubáček i in. (IJF 2019): model trenowany tak, by był *mniej skorelowany* z kursami bukmachera, dał większy zysk mimo niższej trafności.
- **Hierarchiczne modele bayesowskie (PyMC):** dobre dla małych lig, bo ściągają skrajne oszacowania w stronę średniej (shrinkage).
- **Cechy w piłce** (od najważniejszych; konsensus z literatury, nie wynik jednego benchmarku):
  1. siła drużyny (xG i gole),
  2. potwierdzone składy i kontuzje,
  3. przewaga własnego boiska,
  4. odpoczynek i natłok meczów,
  5. motywacja pod koniec sezonu.
  
  Pogoda, sędzia i podróże mają znaczenie głównie dla liczby goli i kartek.
- **Cechy w tenisie:** Elo po nawierzchni, punkty wygrane przy serwisie i returnie, zmęczenie, ryzyko kreczu.

## 4. Warstwa decyzyjna
- **EV** = p × kurs_po_podatku − 1. U polskiego bukmachera z podatkiem 12%: kurs_po_podatku = kurs × 0,88.
- **CLV jako główny KPI**, liczony względem zdewigowanego zamknięcia Pinnacle.
  - Stabilizuje się dużo szybciej niż ROI.
  - Z grubsza: minimum 100 zakładów, dla pewności 200–500+.
  - Najlepiej t-test średniego CLV.
- **Kalibracja ważniejsza niż trafność.** Wybór modelu po kalibracji dał +34,7% ROI, a po trafności −35,2% (Walsh & Joshi 2024; NBA, wynik orientacyjny).
  - Mierniki: Brier, log loss, krzywe kalibracji (reliability curves).
- **Staking:** ¼–½ Kelly z limitem 1–2% bankrolla.
  - Połowa Kelly'ego zachowuje około 75% wzrostu przy znacznie mniejszej wariancji.
  - Stawka powyżej 2× Kelly ma ujemny oczekiwany wzrost.
- **Minimalna przewaga:** około 3% po podatku i marży; więcej przy outsiderach.
- **Porównywanie kursów** u wszystkich licencjonowanych bukmacherów. Wygrywające konta są limitowane.
- **Pułapki backtestu:**
  - tylko kursy dostępne w chwili decyzji (nigdy zamknięcia, których nie dało się zagrać),
  - ratingi z danego momentu, bez wycieku informacji z przyszłości,
  - walidacja walk-forward,
  - luki w archiwach kursów,
  - uwzględnienie limitów stawek.

## 5. Rola LLM
- **Szkodzi przy bezpośrednim przewidywaniu.**
  - Benchmark MŚ 2026 (arXiv 2607.17765): żaden z 4 frontier-LLM nie pobił rynku w Brier score; stała stawka na faworyta rynku pobiła wszystkie; ROI od −18% do +10%; w 92% meczów modele typowały to samo.
  - Brak związku między pewnością LLM a trafnością (arXiv 2608.03416).
- **Pomaga przy:**
  - ekstrakcji kontuzji, składów i newsów (PL/EN) do ustrukturyzowanych flag, z kontrolą halucynacji,
  - dopasowywaniu nazw drużyn i zawodników między źródłami,
  - wyjaśnianiu typów i post-mortemach,
  - orkiestracji pipeline'u.
- **Wynik LLM to cecha albo flaga dla modelu statystycznego, nigdy prawdopodobieństwo.**

## Rekomendacje (przyjęte w ADR)
1. Faza 1: piłka pre-match w 4 ligach, rynki 1X2 i O/U, zdewigowany rynek Pinnacle jako baza, Dixon-Coles i Elo jako druga opinia.
2. Pierwsze 300–500 zakładów na papierze; KPI to CLV.
3. Staking: ¼ Kelly, limit 1,5% bankrolla.
4. Faza 2: tenis ATP/WTA (bez ITF).
5. Live: tylko alerty.
6. LLM: tylko ekstrakcja i wyjaśnienia.

**Luki w literaturze:** brak badań porównujących efektywność linii zamknięcia między poziomami lig, wpływ wyboru metody devig na zysk oraz przewagi w siatkówce.
