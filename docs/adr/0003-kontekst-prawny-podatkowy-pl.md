# ADR 0003: Kontekst prawny i podatkowy (Polska)

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [04-poland-legal-tax.md](../research/04-poland-legal-tax.md)

## Kontekst
- Rezydent Polski może legalnie grać tylko u bukmacherów z licencją Ministra Finansów.
- Pinnacle i Betfair, czyli standardowe „ostre” punkty odniesienia, nie mają licencji. Gra u nich grozi odpowiedzialnością z KKS.
- Podatek od gier wynosi 12% stawki; od wygranej powyżej 2280 zł na kupon pobierane jest 10%.
- Istnieją promocje bez podatku, np. Betclic „Gra bez podatku 2.0”: single 0% do 1000 zł stawek, potem 6%; AKO 0%.

## Decyzja
- **Gramy wyłącznie u licencjonowanych bukmacherów** (STS, Fortuna, Betclic, Superbet i in.).
- **Kursy Pinnacle i Betfair wykorzystujemy wyłącznie jako dane referencyjne** (cena fair, CLV), pozyskiwane od dostawców danych. Nigdy tam nie gramy i nie zakładamy kont.
- **Podatek modelujemy jawnie** w `config/bookmakers.yaml`:
  - stawka podatku od stawki per bukmacher i per typ zakładu (single/AKO),
  - progi promocji (np. 1000 zł),
  - podatek od wygranej (10% powyżej 2280 zł).
- EV i Kelly zawsze liczymy na **efektywnym kursie po podatku**.
- Zasady promocji podatkowych weryfikujemy u źródła (regulamin bukmachera) i datujemy w configu.
- Dokumentacja projektu nie jest poradą prawną ani podatkową.

## Konsekwencje
- Strategia „bij Pinnacle o 2–3%” w większości nie działa. Szukamy dużych przewag, ofert bez podatku, AKO i boostów (ADR 0006).
- Zmiana regulaminu promocji to zmiana konfiguracji, a nie kodu.
