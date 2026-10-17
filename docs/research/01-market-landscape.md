# 01. Rynek: narzędzia, open source, społeczności

> Stan na 2026-10-17. Ceny i dostępność trzeba weryfikować przed zakupem. Pozycje oznaczone **[niezweryfikowane]** pochodzą z drugiej ręki.

## Narzędzia komercyjne

| Narzędzie | Co robi | Cena | Polscy bukmacherzy |
|---|---|---|---|
| **RebelBetting** | value betting + surebety, ponad 120 bukmacherów, Pinnacle jako cena referencyjna | trial 14 dni; Starter 99 €/mies. (69 € rocznie), Pro 199 €/mies. (139 € rocznie) | lista widoczna dopiero po zalogowaniu |
| **Trademate Sports** | porównanie z ostrą linią, śledzenie CLV, sugerowane stawki (założyciel to zawodowy gracz) | „drogie” [niezweryfikowane] | ? |
| **OddsJam** | arbitraż i zakłady +EV, głównie rynek USA | trial 7 dni | raczej nie |
| **OddsMonkey** | matched betting w UK | ok. 15–18 £/mies. | nie |
| **BetBurger** | skaner surebetów i value | ? | niepotwierdzone |
| **Betaminic** | budowanie i backtest strategii piłkarskich, paper trading | ? | ? |

**Wniosek:** żadne narzędzie nie uwzględnia polskiego podatku 12% ani nie obsługuje dobrze STS, Betclic i Superbet. Dla polskiego gracza to luka, którą możemy wypełnić.

**Polscy bukmacherzy w API kursów:**
- odds-api.io: STS PL, eFortuna PL, Betclic PL, Betfan PL, LVbet PL; od 49 £/mies.; darmowe klucze wstrzymane.
- OddsPapi: Fortuna PL, Superbet PL.

## Open source (szczegóły: [07-github-tools.md](07-github-tools.md))
- `penaltyblog`: Poisson, Dixon-Coles, implied probabilities, usuwanie marży.
- `soccerdata`: scrapery FBref, Understat, Sofascore, ClubElo, football-data.
- `sports-betting` (georgedouzas): loadery danych, backtest, CLI, serwer MCP.
- `ProphitBet`: aplikacja ML do typowania.
- Tenis: dane Jeffa Sackmanna (`tennis_atp`, `tennis_wta`), biblioteka `skelo` (Elo), kursy z tennis-data.co.uk.
- **Asystenci LLM/agentowi:** znalazłem tylko mały projekt hackathonowy (LangChain + GPT-3). **Nie istnieje dojrzały asystent oparty na Claude**, więc ta nisza jest wolna.

## Społeczności i literatura (szczegóły: [05-community-tipsters.md](05-community-tipsters.md))
- **Reddit:**
  - r/algobetting: najbardziej techniczny.
  - r/sportsbook, r/SoccerBetting: głównie typy.
- **Pinnacle Betting Resources:** ponad 60 artykułów Josepha Buchdahla.
- **Football-Data.co.uk** (strona Buchdahla): standardowy darmowy zbiór do backtestów.
- **Książki:**
  - J. Buchdahl: *Squares & Sharps*, *Monte Carlo or Bust*, *Fixed Odds Sports Betting*.
  - S. Wong: *Sharp Sports Betting*.
- **Polskie społeczności:** zawodtyper.pl, Discordy „Forum Bukmacherskie” (ok. 1,2 tys. osób) i „Strzelecki Betting Tips” (ok. 9,3 tys. osób). Typy bez metodologii i bez audytowanych wyników.

## Lekcje od społeczności
1. **Value betting względem ostrej linii działa.** Symulacja na danych Buchdahla: +3,6% ROI w 14 sezonach i 22 ligach, przy kursie Pinnacle sprzed zamknięcia jako cenie fair. Przewagi są cienkie, więc liczy się wolumen.
2. **CLV to główna miara umiejętności.** Liczymy go względem zdewigowanego kursu zamknięcia Pinnacle. Sensowny sygnał daje po 50, a lepiej po 200 i więcej zakładach.
3. **Limitowanie kont jest realnym sufitem.** Bukmacherzy flagują:
   - wysoki CLV,
   - zakłady tuż po ruchu linii,
   - nietypowe stawki,
   - niszowe rynki.
4. **Typowe porażki:**
   - przeuczony model bez testu out-of-sample,
   - ocena po trafności zamiast po CLV,
   - ignorowanie marży i podatku,
   - zbyt agresywny staking,
   - grupy „AI picks” bez historii wyników.

## Rekomendacje dla projektu
- Planować wokół podatku 12%: duże przewagi, oferty bez podatku, AKO, boosty, porównywanie kursów.
- Claude ma być analitykiem, nie wyrocznią.
- Wbudować: tracker CLV, kalkulator EV po podatku, ułamkowy Kelly, monitor ryzyka limitów kont.
