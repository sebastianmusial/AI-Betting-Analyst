# ADR 0019: Wykorzystanie open source

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [07-github-tools.md](../research/07-github-tools.md)

## Decyzja
- **`sports-betting`** (georgedouzas, MIT): zależność przypięta do wersji.
  - Używamy loaderów (football-data, The Odds API; nasze ligi są zmapowane), walk-forward `backtest()`, CLI i `sportsbet-mcp`.
  - **Nie instalujemy extra `execution`** (automatyczne stawianie zakładów łamie regulaminy i ADR 0001).
  - Własne modele dodajemy przez `BaseBettor`.
- **`penaltyblog`** (MIT): Dixon-Coles, modele bayesowskie, devig, Elo/Pi, RPS.
- **`soccerdata`** (Apache-2.0), **`shin`** (MIT), **`OddsHarvester`** (MIT), **`transfermarkt-datasets`** (CC0), **`ScraperFC`** (GPL-3.0, użytek prywatny) lub **`EasySoccerData`** (MIT), **`elote`** (MIT).
- **Własna warstwa** (tego nie ma w żadnej bibliotece):
  - wybór metody devig,
  - CLV,
  - Kelly z limitami,
  - polski podatek,
  - AKO,
  - rejestr zakładów,
  - guardrails.
- **Repozytoriów bez licencji** (nutmeg, football-docs, LanusStats, goalmodel) nie kopiujemy. Tylko czytamy dla inspiracji.
- **Unikamy:** repozytoriów nieaktualnych (worldfootballR, rozzac90/pinnacle) i modułów stawiających zakłady (sportsdata-mcp betting tools).

## Konsekwencje
- `sports-betting` często zmienia API (0.12 → 0.15 w 2026), dlatego przypinamy wersję i mamy testy integracyjne na próbkach.
- Gdy biblioteka przestanie pasować, adaptery w `sources/` pozwalają ją wymienić.
