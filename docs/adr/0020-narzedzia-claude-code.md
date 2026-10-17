# ADR 0020: Narzędzia Claude Code (budowa i runtime)

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [08-claude-code-tooling.md](../research/08-claude-code-tooling.md)

## Decyzja
**Pluginy do budowy** (instalacja za zgodą właściciela):
- `claude-plugins-official`: `superpowers` (TDD, plan → wykonanie), `feature-dev`, `code-review`, `commit-commands`, `pyright-lsp`, `context7`, `hookify`, `skill-creator`, `plugin-dev`, `security-guidance`;
- `anthropics/skills`: `mcp-builder`;
- `duckdb/duckdb-skills`;
- katalog organizacji: **Data** (Anthropic), **Probabl Skills** (ML/scikit-learn).

**Runtime MCP** (`.mcp.json`):
- `duckdb` (`mcp-server-motherduck`, tylko odczyt),
- `sportsbet-mcp`,
- później `betting-mcp`.

Gotowe MCP z danymi sportowymi są niedojrzałe, więc ich nie używamy, poza eksploracją.

**Własne elementy:**
- **skille:** zob. ADR 0016;
- **subagenci** (`.claude/agents/`):
  - `data-engineer`,
  - `quant-modeler`,
  - `backtest-auditor` (tylko odczyt: patrzenie w przyszłość, przeuczenie),
  - `news-analyst`,
  - `report-writer`;
- **hooki** (`.claude/settings.json`):
  - PostToolUse: ruff i pytest na zmienionych plikach,
  - PreToolUse: blokada edycji `.env` i produkcyjnego `data/betting.duckdb`.

**Harmonogram:** `launchd` + `claude -p "/daily-scan"` (subskrypcja, bez `--bare`). Cloud routines odpadają.

## Konsekwencje
- Skille i subagenci są częścią repo i wersjonowane jak kod.
- Docelowo całość można spakować jako plugin (`.claude-plugin/`).
