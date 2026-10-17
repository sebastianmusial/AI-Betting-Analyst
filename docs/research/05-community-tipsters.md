# 05. Społeczności, typerzy i „gorące” podpowiedzi

## Platformy typerów z weryfikacją

| Platforma | Weryfikacja | CLV | Dane |
|---|---|---|---|
| **Bet2Invest** | każdy typ certyfikowany po kursach Pinnacle | **tak** (od otwarcia do zamknięcia) | publiczne profile, dokumentacja na docs.bet2invest.com, bez API |
| **Blogabet** | „100% verified” to ich marketing | nie | blokuje automatyczny odczyt (403) |
| **Tipstrr (+ Pyckio, przejęte 11.2024)** | ? | brak dowodów | blokuje automatyczny odczyt |
| **OLBG** | ranking po zysku z 12 mies.; pokazuje tylko zyskownych | nie | błąd przeżywalności wbudowany w ranking |
| **Betaminic** | strategie użytkowników z backtestem | ograniczone | — |

**Jak rozpoznać prawdziwą umiejętność:**
- dodatni CLV względem zamknięcia Pinnacle (bez marży), a nie ROI,
- co najmniej 1000 typów przy realnych stawkach,
- rynek przesuwa się w stronę typu.

Odróżnienie przewagi 2% ROI od szczęścia wymaga tysięcy zakładów. Sam odsetek trafień nic nie mówi.

## Polskie społeczności
- **zawodtyper.pl:** dużo treści, „Typy Dnia” (88–106 dziennie), bez opisanej metodologii rankingu i bez RSS/API. Głównie afiliacja.
- **Discordy:** Forum Bukmacherskie (około 1,2 tys. osób), Strzelecki Betting Tips (około 9,3 tys.), SBT (płatne pakiety). Żaden nie pokazuje zweryfikowanych wyników.
- **Brak polskiego źródła z audytowanymi statystykami opartymi na kursie zamknięcia.**

## Źródła międzynarodowe
- **Dropping odds:** OddsPortal, BetExplorer (filtry 1/2/12/24/48 h, progi 30–70%).
- **Reddit:** wątki dzienne jako sentyment, nie jako przewaga. Darmowe API tylko do użytku niekomercyjnego (około 100 zapytań/min).
- **Płatni resellerzy kursów Pinnacle z alertami spadków:** PinnOdds, pinnapi, PinnWire (od około $99/mies.).

## Oszustwa i pułapki
- **Darmowe trafione typy jako przynęta** do płatnej grupy VIP. Do tego edytowane screeny kuponów i fałszywi członkowie chwalący się wygranymi.
- **„Ustawione mecze”:** zawsze oszustwo.
- **„Wpłać, żeby wypłacić wygraną”:** oszustwo.
- **Błąd przeżywalności:** rankingi tylko po zysku i hasła „największa grupa w Polsce”.
- **Badanie typerów-influencerów (Nigeria):** strata 25% stawianych pieniędzy.

## Dowody naukowe
- **Konsensus większości działa (lekko):** granie wyniku typowanego przez większość typerów OddsPortal dało +1,3% na 68 339 zdarzeniach. Wybieranie najlepszych typerów z przeszłości nie poprawiło wyniku (Brown & Reade, EJOR 2019).
- **Tłum z Blogabet:** dodatni yield. Badanie 1,5 mln typów: średnio 3,97%, z lepszymi podgrupami (Grüttner i in.).
- **Pojedynczy typerzy przegrywają z kursami** w Bundeslidze (Spann & Skiera).
- **Konsensus kursów (Kaunitz):** zyskowny do momentu limitów.
- **„Fade the public”:** brak bezpośrednich badań dla piłki.
- **Steam (gwałtowny ruch kursu):** brak recenzowanych dowodów, że przewiduje wynik. Działa natomiast jako detektor przecieku informacji.

## Integracja w asystencie
1. Każdy zewnętrzny typ zapisujemy ze źródłem, czasem i kursem. Kurs Pinnacle notujemy w momencie zapisu i na zamknięciu, a typ oceniamy przez CLV.
2. Źródła rankujemy po średnim CLV i odsetku typów, które pobiły zamknięcie (z przedziałami ufności). Źródło z CLV ≤ 0 po 200+ typach odrzucamy.
3. Sygnały:
   - liczba źródeł zgodnych co do typu (konsensus),
   - flaga steam (Pinnacle przesuwa się o więcej niż 3–5 pp prawdopodobieństwa),
   - miękki bukmacher spóźniony za Pinnacle.
4. **Bezpieczne źródła:** publiczne strony Bet2Invest, własny feed kursów, Reddit API do użytku prywatnego.
   **Szara strefa:** scraping OddsPortal, Blogabet, zawodtyper.
   **Unikamy:** prywatnych grup Telegram.

## Ranking rekomendacji
1. **Integrujemy:** feed kursów Pinnacle (steam i CLV) jako fundament.
2. **Integrujemy:** typerów z Bet2Invest ocenianych przez CLV.
3. **Integrujemy:** konsensus tłumu jako cechę modelu.
4. **Opcjonalnie:** sentyment z Reddita i zawodtypera, testowany również jako sygnał przeciwny.
5. **Ignorujemy:** płatne grupy VIP, „ustawione mecze”, polskie grupy na Discordzie i FB, rankingi tylko po zysku, screeny influencerów.
