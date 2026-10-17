# 08. Narzędzia Claude Code: budowa i runtime

## Oficjalne zasoby Anthropic
- **anthropics/skills:** `/plugin marketplace add anthropics/skills`
  - `skill-creator`: pisanie i benchmark skilli;
  - `mcp-builder`: przewodnik budowy serwerów MCP (Python FastMCP);
  - `xlsx`: eksport backtestów;
  - `webapp-testing`: przydatny, jeśli kiedyś powstanie dashboard.
- **claude-plugins-official** (dostępne domyślnie): `/plugin install <nazwa>@claude-plugins-official`
  - **Workflow:** `feature-dev`, `code-review`, `pr-review-toolkit`, `commit-commands`, `code-simplifier`, `superpowers`.
  - **Tooling:** `hookify`, `plugin-dev`, `claude-md-management`, `claude-code-setup`, `agent-sdk-dev`.
  - **Python i bezpieczeństwo:** `pyright-lsp`, `security-guidance`, `context7` (dokumentacja bibliotek dla konkretnych wersji).
  - **Runtime:** `duckdb-skills`, `playwright`, `firecrawl`, `exa`, `tavily`, `telegram`, `remember`, `logfire`.
- **Katalog organizacji (Anthropic Directory):**
  - **Data** (Anthropic): analiza statystyczna, walidacja danych, eksploracja, SQL.
  - **Probabl Skills** (zespół scikit-learn): budowa, ewaluacja i testy pipeline'ów ML.
  - `quick-gate-python`: ruff, pyright, pytest.

## Paczki społeczności
- **obra/superpowers** (MIT): przepływ brainstorm → plan → wykonanie, TDD red/green, systematyczne debugowanie. Dobre do modeli i backtestera pisanych test-first.
- **wshobson/agents:** plugin `python-development` (uv, packaging, wzorce). Instalujemy pojedyncze pluginy, nie cały zestaw.
- **K-Dense-AI/claude-scientific-skills:** statsmodels, scikit-learn, PyMC, wykresy. Tylko wybrane skille.
- **duckdb/duckdb-skills** (oficjalne DuckDB, 09.2026): `/plugin marketplace add duckdb/duckdb-skills`. Wymaga DuckDB CLI.
- **Listy:** hesreallyhim/awesome-claude-code, ComposioHQ/awesome-claude-skills.

## Serwery MCP do runtime
- **motherduckdb/mcp-server-motherduck** (oficjalny), na lokalnym pliku DuckDB tylko do odczytu:
  `claude mcp add duckdb --transport stdio -- uvx mcp-server-motherduck --db-path /abs/path/betting.duckdb`
  (`--read-write` tylko wtedy, gdy naprawdę potrzebne).
- **sportsbet-mcp** z `sports-betting[mcp]`.
- **Gotowe MCP z danymi sportowymi i kursami są niedojrzałe** (odds-api-mcp-server, SportWizzard, wrappery API-Football; 0–40 gwiazdek). Opakowujemy własne źródła we **własny `betting-mcp`** (FastMCP).
- **Fetch** (referencyjny) i **Playwright MCP** tylko dla stron wymagających przeglądarki.
- **RSS:** ingestujemy w Pythonie (`feedparser`) według harmonogramu, a przez MCP wystawiamy tylko wyniki. Daje to powtarzalność.
- **Telegram:** do raportów z harmonogramu wystarczy proste wywołanie Bot API z Pythona. Oficjalny plugin `telegram`, jeśli chcemy rozmowy w obie strony.

## Funkcje Claude Code
- **Tryb headless:**
  `claude -p "/daily-scan" --output-format json --permission-mode dontAsk --allowedTools "..." --max-budget-usd N`
  - Skille działają w `-p`, gdy wywołamy je jako `/nazwa`.
  - `--bare` daje powtarzalność, ale pomija CLAUDE.md, skille i hooki oraz wymaga `ANTHROPIC_API_KEY` (bez subskrypcji).
- **Harmonogram:**
  - zadania zaplanowane w aplikacji desktop działają lokalnie, ale Mac musi być włączony;
  - **cloud routines nie mają dostępu do lokalnego DuckDB, więc odpadają**;
  - `/loop` wygasa po 7 dniach;
  - **launchd + `claude -p`** to solidna opcja lokalna.
- **Gdzie co leży:**
  - skille: `.claude/skills/NAME/SKILL.md` (frontmatter `name`, `description`; `disable-model-invocation: true` dla skilli wywoływanych tylko ręcznie);
  - subagenci: `.claude/agents/*.md`;
  - hooki: `.claude/settings.json`;
  - plugin: `.claude-plugin/plugin.json`, do spakowania całości później.

## Do napisania samodzielnie

**Skille:**
- `/daily-scan`: terminarz → kursy → prawdopodobieństwa → filtr przewagi → sprawdzenie newsów → lista kandydatów.
- `/daily-report`: raport markdown i wiadomość na Telegram.
- `/backtest`: walk-forward z wynikami RPS, Brier, log loss, ROI, CLV.
- `/fit-model`: ponowne dopasowanie DC i kontrola kalibracji.
- `/ingest-news`: RSS → flagi przez LLM → deduplikacja.
- `/match-deep-dive`: analiza jednego meczu.
- `/log-bet`, `/post-mortem`.
- `/add-data-source`: szablon nowego źródła z testami i migracją.

**Subagenci:**
- `data-engineer`,
- `quant-modeler`,
- `backtest-auditor` (tylko odczyt: patrzenie w przyszłość, przeuczenie, znaczniki czasu kursów),
- `news-analyst`,
- `report-writer`.

**Hooki:**
- PostToolUse: ruff i pytest na zmienionych modułach.
- PreToolUse: blokada zapisu do `.env` i produkcyjnego DuckDB.
- Stop: powiadomienie po długich zadaniach.
