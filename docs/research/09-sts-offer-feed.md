# 09. Oferta STS: publiczny feed WebSocket

Rozpoznanie z 2026-10-17. Format jest nieoficjalny i może się zmienić; testy kontraktowe na
próbkach leżą w `tests/fixtures/sts/`.

## Dostęp
- Oferta pre-match jest publiczna, bez logowania. Strona ligi: `/zaklady-bukmacherskie/pilka-nozna/<kraj>/<liga>/1/<id_kategorii>/<id_turnieju>`, strona meczu: `/kursy/<slug>/f<id>`.
- Kursy nie przychodzą przez REST. Idą WebSocketem **`wss://www.sts.pl/sbk/api/sbk`**.
- Połączenie z czystego Pythona (`websockets`, nagłówki Origin i User-Agent) działa bez przeglądarki.
- Katalog nazw rynków: `content.sts.pl/devices/common/any/market_description/json/markets_description.json?lang=pl`.

## Protokół
- **Subskrypcja:** `{"t":1,"u":[{"s":"<temat>","n":0}, ...]}`. Kolejne wiadomości `t:1` zawierają pełną listę tematów.
- **Tematy:**
  - `i_pl`: indeks oferty, około 3,4 MB;
  - `t_<id_turnieju>_pl`: mecze turnieju i rynki główne, około 1,4 MB dla Ekstraklasy;
  - **`f_f<id_meczu>_pl`: pełna oferta meczu**, około 220 KB, ponad 500 rynków (nazwa z kodu aplikacji: `getMatchDetailsSubscriptionChannel`).
- **Wiadomość:** linia nagłówka `{"s":temat,"n":seq,"f":1}` (`f:1` = pełny snapshot, bez `f` = delta), potem `\n` i JSON body.
- **Body:**
  - `B.S[sport].C[kategoria].T[turniej].FX[id_meczu]`: `ft:"m"` mecz (`ft:"s"` sezon/outright), `H`/`A` gospodarz i gość (`n` nazwa), `t` start UTC, `sid`;
  - `P[grupa]`: grupy rynków meczu (`f` = id meczu). `m[id_rynku].l[id_linii]`: `n` nazwa, `D` linia × 100 (1050 → 10.5), `s` zawieszona; `o[id_wyniku].O` kurs, `o[..].n` etykieta (np. „+10.5”).

## Identyfikatory
- **Turnieje:** Ekstraklasa 201, Championship 18, 2. Bundesliga 44, Eredivisie 37.
- **Rynki (id → wyniki):**

| Id | Rynek | Wyniki |
|---|---|---|
| 1 | Mecz | 1/2/3 = 1/X/2 |
| 25 | Liczba goli | 12 = powyżej, 13 = poniżej |
| 43 | Obie drużyny strzelą | 26 = tak, 27 = nie |
| 228 | Liczba rzutów rożnych | 12/13 |
| 231 / 234 | Rogi gospodarza / gościa | 12/13 |
| 185 | Liczba kartek | 12/13 |
| 188 / 191 | Kartki gospodarza / gościa | 12/13 |
| 2111 | Liczba fauli | 12/13 |
| 1562 | Liczba celnych strzałów | 12/13 |

Mapowanie leży w `config/sts_markets.yaml`.

## Zasady
- Tylko odczyt, niskie tempo (paczki po 5 tematów, przerwy 1,5 s), cache surowych danych w `data/raw/sts/` (gzip).
- Niczego nie publikujemy i nie obchodzimy zabezpieczeń (ADR 0009).
- Pełny skan 32 meczów z 4 lig trwa około 13 s.

## Narzędzia rozpoznania
- Playwright, przechwytywanie ramek WebSocket.
- Chrome DevTools MCP, dodane w `.mcp.json` do przyszłych diagnoz (pokazuje ramki WS).
- Wbudowana przeglądarka Claude nie pokazuje ramek WebSocket.

## Do zrobienia
- **Boosty STS:** struktura „codzienny boost” w feedzie jeszcze nierozpoznana.
- **Regulamin STS:** czy druga żółta kartka liczy się podwójnie w rynku „liczba kartek” (zob. `docs/experiments/2026-10-counts-calibration.md`).
