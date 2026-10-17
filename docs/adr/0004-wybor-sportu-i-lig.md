# ADR 0004: Wybór sportu i lig

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [03-modeling-strategy.md](../research/03-modeling-strategy.md), [02-data-sources.md](../research/02-data-sources.md)

## Kontekst
Startujemy wąsko, od jednego sportu. Kandydaci: piłka nożna, tenis, koszykówka. Liczą się efektywność rynku, darmowe dane (zwłaszcza historyczne kursy zamknięcia), głębokość oferty polskich bukmacherów, wolumen zdarzeń i możliwość przetestowania od razu.

## Decyzja
- **Sport:** piłka nożna.
- **Ligi:**
  - **Ekstraklasa:** przewaga lokalna (polskie newsy, atmosfera w klubach); kursy zamknięcia Pinnacle w football-data (tylko 1X2).
  - **Championship, 2. Bundesliga, Eredivisie:** ligi średniego szczebla, mniej efektywne niż top 5, z dobrymi danymi; opcjonalnie Serie B.
- **Rynki:** 1X2 i Over/Under 2.5. Asian Handicap później.
- **Drugi sport (F7):** tenis ATP/WTA, Elo po nawierzchni. Bez ITF i Challengerów, ze względu na ryzyko ustawiania meczów.
- **Koszykówka:** odłożona. NBA to rynek efektywny, darmowych danych dla lig europejskich jest mało.

## Uzasadnienie
- Piłka ma najlepsze darmowe dane historyczne z kursami Pinnacle, co od razu umożliwia backtest i CLV.
- Polscy bukmacherzy mają najgłębszą ofertę na piłkę.
- Marże rosną w dół piramidy lig, więc w ligach średniego szczebla jest więcej nieefektywności niż w top 5.
- Weekendowa kolejka daje od razu kilkadziesiąt meczów do testu.

## Konsekwencje
- Understat nie obejmuje naszych lig, więc xG jest trudniej dostępne (ADR 0011).
- Dla Ekstraklasy brak darmowej historii O/U, więc potrzebny OddsHarvester (ADR 0009).
