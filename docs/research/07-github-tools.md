# 07. Narzędzia open source na GitHubie

Gwiazdki, daty i licencje pochodzą z GitHub API (2026-10-17).

## georgedouzas/sports-betting (★820, MIT, v0.15.1 z 2026-07-28; ostatni push 2026-09-24)
https://github.com/georgedouzas/sports-betting

- **Architektura** (`src/sportsbet/`):
  - `sources/`: osobne źródła statystyk i kursów (football-data.co.uk, The Odds API, koszykówka).
  - `dataloaders/`: `DataLoader(param_grid, stats=, odds=)` zwraca ramki `X, Y, O` przez `extract_train_data(odds_type=...)` i `extract_fixtures_data()`.
  - `evaluation/`:
    - `ClassifierBettor` opakowuje dowolny estymator scikit-learn;
    - `OddsComparisonBettor` gra przeciw konsensusowi kursów wielu bukmacherów (metoda Kaunitza);
    - `BettorGridSearchCV` stroi parametry;
    - `backtest(bettor, X, Y, O, cv=TimeSeriesSplit)` to walk-forward.
  - `execution/`: stawia zakłady przez API lub automatyzację przeglądarki. **Łamie regulaminy, więc nie instalujemy.**
  - `mcp/`: narzędzia `available_params`, `odds_types`, `extract_train_data`, `extract_fixtures_data`, `backtest`, `fit`, `bet`.
    - Instalacja: `pip install 'sports-betting[mcp]'`, potem `claude mcp add sportsbet -- sportsbet-mcp`.
- **Interfejsy:** Python, CLI (`sportsbet dataloader ...`, `sportsbet evaluation backtest|fit|bet`), MCP.
- **Nasze ligi:**
  - football-data: E1 (Championship), D2, N1, POL (`new/POL.csv`);
  - The Odds API: `soccer_efl_champ`, `soccer_germany_bundesliga2`, `soccer_netherlands_eredivisie`, `soccer_poland_ekstraklasa`.
- **Kolumny Pinnacle:** PSH/PSCH (kurs przedmeczowy i zamknięcia), P>2.5 i PC>2.5, Max i Avg.
- **Ograniczenia:**
  - POL.csv ma tylko kursy zamknięcia 1X2: brak O/U, kursów otwarcia i statystyk strzałów.
  - Staking tylko stałą stawką, bez Kelly'ego, bez CLV, bez devig.
  - Modele to klasyfikatory scikit-learn; brak Poissona, DC i Elo.
  - Jeden maintainer, API często się zmienia.
- **Jak używamy:** jako przypiętej zależności do loaderów i backtestu. Własny bettor (Dixon-Coles) przez dziedziczenie po `BaseBettor`. CLV, Kelly, devig i podatek w naszej warstwie.

## Modele i statystyka
- **martineastwood/penaltyblog** (★241, MIT, v1.13.1, aktywny): Poisson, bivariate Poisson, Dixon-Coles (Cython), modele bayesowskie hierarchiczne, implied probabilities (usuwanie marży), Elo, Pi, Massey, Colley, RPS, scrapery (ClubElo, Understat). Ma plik `.claude/skills`. **Najważniejsza biblioteka.**
- **wdm0006/elote** (★33, MIT): Elo, Glicko, TrueSkill, Bradley-Terry.
- **opisthokonta/goalmodel, implied** (R): implementacje referencyjne, tylko do weryfikacji matematyki.
- **socceraction, kloppy, mplsoccer:** dane zdarzeń i wykresy; dla 1X2 i O/U pre-match mało przydatne.

## Dane
- **probberechts/soccerdata** (★2,1 tys., Apache-2.0, aktywny): FBref, ClubElo, ESPN, football-data, Sofascore, SoFIFA, Understat, WhoScored.
- **Understat obejmuje tylko top 5 lig + Rosję, czyli żadnej z naszych.** xG trzeba brać z Sofascore lub FotMob.
- **jordantete/OddsHarvester** (★259, MIT, aktywny): scraper OddsPortal (Playwright), mecze nadchodzące i historyczne, 1X2 i O/U. Uzupełnia braki w POL.csv. Scraping narusza regulamin OddsPortal.
- **dcaribou/transfermarkt-datasets** (★519, CC0): wartości składów jako cechy.
- **felipeall/transfermarkt-api** (★463, MIT).
- **oseymour/ScraperFC** (★417, GPL-3.0; OK do użytku prywatnego): Sofascore, ClubElo, FBref, Transfermarkt.
- **EasySoccerData** (MIT), **sofascore-wrapper** (MIT).
- **Unikamy:** LanusStats (bez licencji), worldfootballR (zarchiwizowany).

## Matematyka zakładów i kursy
- **mberk/shin** (★105, MIT): devig metodą Shina.
- **betcode-org/betfair i flumine** (MIT): dobre wzorce frameworku strategii, ale Betfair jest niedostępny w PL.
- **odds-api/odds-api** (Apache-2.0): spec OpenAPI, SDK, MCP, tryb mock.
- **Nieaktualne:** rozzac90/pinnacle, sbrscrape (USA).

## Agenci i serwery MCP
- **withqwerty/football-docs i nutmeg** (bez licencji): wzorce dla Claude Code. Tylko czytamy.
- **DanielTomaro13/sportsdata-mcp** (MIT): około 841 narzędzi. Umie stawiać zakłady u australijskich bukmacherów, co trzeba wyłączyć.
- **WFord26/BetTrack** (MIT): FastMCP z kursami i panelem śledzenia zakładów. Inspiracja dla rejestru zakładów.
- **Haemon-Yang/FootballBettingAgent** (MIT): agent LangGraph.
- Serwery MCP dla API-Football: niedojrzałe.

## Rekomendacja
**Top 10 zależności:**
1. penaltyblog
2. soccerdata
3. sports-betting (bez `execution`)
4. shin
5. OddsHarvester
6. transfermarkt-datasets
7. ScraperFC lub EasySoccerData
8. elote
9. The Odds API (przez sports-betting albo własny adapter)
10. mplsoccer (opcjonalnie)

Pod spodem: scikit-learn, statsmodels, PyMC.

**Inspiracje:** projekt sports-betting (przepływ dataloader → bettor → backtest → MCP), blog penaltyblog (pena.lt/y/blog), nutmeg i football-docs, BetTrack, goalmodel i implied.

**Unikamy:**
- repozytoriów nieaktualnych i bez licencji (kopiowanie kodu),
- modułów stawiających zakłady,
- pipeline'ów opartych na Understat.
