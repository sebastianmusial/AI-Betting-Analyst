# 02. Źródła danych

> Stan na 2026-10-17. Dwie ważne zmiany w 2025–2026:
> - **Pinnacle zamknął publiczne API** (23.07.2025).
> - **FBref stracił zaawansowane statystyki Opta, w tym xG** (20.01.2026).

## A. Kursy

| Źródło | Zakres | Darmowy plan / cena | Uwagi |
|---|---|---|---|
| **The Odds API** | około 40 bukmacherów; region EU zawiera Pinnacle | free: 500 kredytów/mies.; $30/20K, $59/100K | historia (płatna) od 06.2020, snapshoty co 5–10 min. Brak polskich buków. Ostatni snapshot przed meczem = kurs zamknięcia do CLV |
| **OddsPapi** | ponad 350 bukmacherów, w tym Pinnacle; **Fortuna PL, Superbet PL** | free: około 250 zapytań/mies. | nie ma STS ani Betclic |
| **Odds-API.io** | STS PL, eFortuna PL, Betclic PL, Betfan PL, LVbet PL | od $65/mies.; nowe darmowe klucze wstrzymane | historia zamknięć dopiero od 12.2025 |
| **Pinnacle API** | — | zamknięte dla publiki | wyjątki: partnerzy i projekty akademickie (api@pinnacle.com) |
| **Betfair Exchange** | — | klucz opóźniony za darmo, live £299 | wymaga konta, a Betfair nie ma licencji w PL |
| **football-data.co.uk** | około 22 ligi; **kursy Pinnacle przedmeczowe i zamknięcia** (PSCH/PSCD/PSCA), O/U, AH, max/avg | darmowe CSV | standard do backtestów i CLV. **POL.csv (extra leagues) ma tylko kursy zamknięcia 1X2.** Sprawdzić, czy kolumny Pinnacle są wypełniane w sezonie 2025/26 |
| **OddsPortal / BetExplorer** | ogromna historia, wielu bukmacherów (polscy przy polskim IP) | scraping (OddsHarvester) | regulamin ogranicza ponowne użycie danych |

**Polscy bukmacherzy nie mają publicznych API.**
- Fortuna PL i Superbet PL: OddsPapi.
- STS: tylko scraping (OddsPortal albo strona STS).
- Betclic: OddsPortal albo płatne Odds-API.io.

## B. Statystyki piłkarskie

| Źródło | Co daje | Cena |
|---|---|---|
| **API-Football** | terminarz, składy, kontuzje, statystyki | free: 100 zapytań/dzień; Pro od $19 |
| **Sportmonks** | pełne dane, dodatek xG | od 29 €/mies. (5 lig); xG od 24 € |
| **football-data.org** | 12 rozgrywek, opóźnione wyniki | free; składy od 29 € |
| **Understat** | xG na poziomie strzałów | free, ale **tylko top 5 lig + Rosja, bez naszych lig** |
| **FBref** | dane podstawowe i historyczne | free; **bez xG od 01.2026** |
| **Sofascore / FotMob** | xG, składy, przewidywane składy | nieoficjalne JSON, często za Cloudflare |
| **StatsBomb open data** | darmowe dane zdarzeń z wybranych rozgrywek | do budowy własnego modelu xG |
| **Transfermarkt** | wartości rynkowe, kontuzje | scraping (WAF); `transfermarkt-datasets` na licencji CC0 |
| **ClubElo** | ratingi Elo | darmowe CSV `api.clubelo.com/<data>` |
| **Open-Meteo** | pogoda | free do użytku niekomercyjnego |

## C. Tenis (na później)
- **Jeff Sackmann:** `tennis_atp` / `tennis_wta`, licencja CC BY-NC-SA. Sprawdzić, czy wciąż jest aktualizowany.
- **tennis-data.co.uk:** ATP od 2000, WTA od 2007, kursy Pinnacle. Tylko do użytku prywatnego.
- **Sportradar:** ponad $10 tys./mies., poza zasięgiem.

## D. Live
- Odpytywanie REST co ≥1 s wystarcza do analizy, ale nie do łapania kursów przed zmianą (snipingu).
- WebSocket daje opóźnienia poniżej 100 ms, ale za $100–300/mies.
- Bukmacherzy opóźniają akceptację zakładów live o kilka sekund.

## E. Zasady prawne i regulaminowe
- Scraping (OddsPortal, Transfermarkt, Sofascore, FBref) zwykle narusza regulaminy. Przy prywatnym, niekomercyjnym użyciu, niskim tempie zapytań i cache'owaniu ryzyko jest niskie. **Niczego nie publikujemy ani nie sprzedajemy.**
- football-data.co.uk i tennis-data.co.uk są przeznaczone do użytku prywatnego. StatsBomb wymaga podania źródła.

## Starter stack (piłka, od 0 do około 50 €/mies.)
1. **Za darmo:**
   - football-data.co.uk (historia i kursy zamknięcia Pinnacle),
   - ClubElo,
   - API-Football free (składy, kontuzje),
   - Open-Meteo,
   - OddsHarvester (kursy polskich buków, O/U dla Ekstraklasy),
   - The Odds API free (bieżące kursy Pinnacle),
   - OddsPapi free (Fortuna PL, Superbet PL).
2. **Około $30–60/mies.:** płatny plan The Odds API z historią i większą liczbą snapshotów.
3. **Upgrade:** API-Football Pro, dodatek xG w Sportmonks (xG dla naszych lig), Odds-API.io z polskimi bukmacherami.
