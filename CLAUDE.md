# CLAUDE.md: AI Betting Analyst

Asystent analizy zakładów piłkarskich pre-match dla legalnych polskich bukmacherów. Przed zmianą kierunku przeczytaj [docs/adr/README.md](docs/adr/README.md).

## Twarde zasady (nie łamać bez nowego ADR)
- **Nie stawiamy zakładów automatycznie.** Nie instaluj ani nie używaj `sports-betting[execution]` ani żadnych narzędzi stawiających zakłady (ADR 0001, 0019).
- **Gramy tylko u licencjonowanych bukmacherów PL.** Pinnacle i Betfair wyłącznie jako dane referencyjne (ADR 0003).
- **LLM (Ty) nie generuje ani nie modyfikuje prawdopodobieństw, kursów fair ani stawek.** Liczy je deterministyczny kod. Możesz ekstrahować fakty, wyjaśniać, flagować i wetować typ, zawsze z cytatem i URL źródła (ADR 0012).
- **EV i Kelly zawsze po podatku**, wg `config/bookmakers.yaml` (ADR 0003, 0014).
- **Główny KPI to CLV względem zdewigowanego zamknięcia Pinnacle**, nie ROI ani trafność (ADR 0015).
- **Backtest:** tylko kursy dostępne w chwili decyzji, walk-forward, bez patrzenia w przyszłość (ADR 0015).
- **Guardrails** (limity stawek, stop-loss, zakaz odgrywania się) są częścią silnika i mają testy (ADR 0002).
- **Scraping:** niskie tempo zapytań, cache, nie obchodzimy CAPTCHA, niczego nie publikujemy (ADR 0009).
- **Sekrety tylko w `.env`.** Nie edytuj `.env` ani produkcyjnego `data/betting.duckdb` ręcznie.

## Konwencje
- Kod i identyfikatory po angielsku. Dokumentacja i komentarze domenowe po polsku.
- Python 3.12, `uv run ...`, `ruff`, `pytest`. Pakiet w `src/betting_analyst/`.
- Każda istotna decyzja = nowy ADR w `docs/adr/` + wpis w indeksie.
- Wyniki eksperymentów i backtestów zapisuj w `docs/experiments/`.

## Struktura (docelowa)
- `src/betting_analyst/sources/`: adaptery źródeł danych (cache, raw w `data/raw/`).
- `src/betting_analyst/models/`: devig, Dixon-Coles, Elo, stacking.
- `src/betting_analyst/decision/`: EV po podatku, Kelly, AKO, guardrails.
- `src/betting_analyst/ledger.py`: rejestr zakładów i CLV (DuckDB).
- `config/`: bukmacherzy (podatki, promocje), strategia (progi, bankroll).
- `.claude/skills/`, `.claude/agents/`: skille i subagenci projektu.
