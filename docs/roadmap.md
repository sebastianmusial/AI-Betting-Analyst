# Roadmapa

Fazy kończą się bramkami. Nie przechodzimy dalej, dopóki bramka nie jest spełniona (ADR 0001, 0015).

| Faza | Kiedy | Zakres | Bramka / wynik |
|---|---|---|---|
| **F0: fundament** | 2026-10-17 | repo, ADR 0000–0020, research | docs w repo |
| **F1: Value Scanner v0** | 2026-10-17 | kursy The Odds API (Pinnacle + EU), football-data, devig, Dixon-Coles jako druga opinia, EV po podatku, ¼ Kelly, rejestr zakładów na papierze w DuckDB, CLV, skill `/daily-scan` | pierwsze zakłady na papierze z dzisiejszej kolejki; CLV po meczach |
| **F2: backtest** | tydz. 1–2 | walk-forward na ponad 5 sezonach (E1, D2, N1, POL); porównanie metod devig; strategie: single z podatkiem, bez podatku, AKO | **go/no-go:** czy istnieje przewaga po podatku |
| **F3: automatyzacja danych** | tydz. 2–3 | kursy polskich bukmacherów (OddsPapi, OddsHarvester, scrapery), API-Football (składy, kontuzje), xG Sofascore/FotMob, ClubElo, Transfermarkt, rozpoznawanie encji, launchd | codzienny pipeline bez ręcznej pracy |
| **F4: integracja** | tydz. 3–4 | `betting-mcp` (FastMCP), skille `/daily-report`, `/match-deep-dive`, `/log-bet`, `/post-mortem`, bot Telegram | alerty i raport dzienny |
| **F5: sygnały** | tydz. 4–5 | pipeline newsów (RSS, WebSub, Google News, LLM → flagi), składy przed meczem, detektor steam, tracker typerów (Bet2Invest, konsensus) | flagi w raporcie, weto z cytatem |
| **F6: paper trading** | 2–3 mies. | ≥ 300 zakładów, monitoring CLV i kalibracji | **go/no-go:** CLV > 0 (p < 0,05) → mały bankroll real money |
| **F7: rozszerzenia** | potem | skaner boostów i promocji, Asian Handicap, stacking LightGBM, tenis ATP/WTA, alerty live, monitor ryzyka limitów kont, VPS z polskim IP | — |

## Wymagane od właściciela
- [ ] Darmowy klucz **The Odds API** (the-odds-api.com) w `.env` jako `ODDS_API_KEY` (F1).
- [ ] Opcjonalnie darmowy klucz **API-Football** jako `API_FOOTBALL_KEY` (F3).
- [ ] Opcjonalnie darmowy klucz **OddsPapi** (F3).
- [ ] Bot Telegram przez **@BotFather**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (F4).
- [ ] Lista kont u bukmacherów i aktualne zasady podatku i promocji w `config/bookmakers.yaml`.
- [ ] Ustalenie bankrolla (na start: papierowego).
