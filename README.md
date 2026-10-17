# AI Betting Analyst

Osobisty asystent analizy zakładów piłkarskich (pre-match) dla legalnych polskich bukmacherów. Działa jako agent w Claude Code. Opiera się na danych i statystyce, a podatek 12% od stawki traktuje jako główne ograniczenie.

> **To narzędzie decyzyjne, nie automat do obstawiania i nie porada finansowa.** Większość graczy na dłuższą metę traci. Dlatego projekt najpierw mierzy (CLV, kalibracja, zakłady na papierze), a prawdziwe pieniądze dopuszcza dopiero po spełnieniu bramek ([ADR 0001](docs/adr/0001-cel-zakres-kryteria-sukcesu.md), [ADR 0002](docs/adr/0002-odpowiedzialna-gra-guardrails.md)).

## Jak to działa (w skrócie)
1. **Cena fair z rynku:** zdewigowane kursy Pinnacle, wykorzystywane wyłącznie jako dane, bo Pinnacle nie ma licencji w PL.
2. **Druga opinia:** model Dixon-Coles i Elo na danych historycznych.
3. **Porównanie z kursami polskich bukmacherów po podatku:** EV, próg przewagi, ¼ Kelly z limitami, AKO tam, gdzie kupony są bez podatku.
4. **Newsy, składy i ruch kursów:** Claude zbiera je i może zawetować typ, podając źródło. Nie zmienia prawdopodobieństw.
5. **Rejestr zakładów i CLV:** każdy zakład (na papierze lub prawdziwy) jest porównywany z kursem zamknięcia.

## Zakres startowy
- **Ligi:** Ekstraklasa, Championship, 2. Bundesliga, Eredivisie.
- **Rynki:** 1X2 i Over/Under 2.5.
- **Tryb:** pre-match, paper trading.

## Dokumentacja
- [Decyzje architektoniczne (ADR)](docs/adr/README.md)
- [Roadmapa](docs/roadmap.md)
- Research:
  - [rynek](docs/research/01-market-landscape.md)
  - [źródła danych](docs/research/02-data-sources.md)
  - [modele i strategia](docs/research/03-modeling-strategy.md)
  - [prawo i podatki PL](docs/research/04-poland-legal-tax.md)
  - [społeczności i typerzy](docs/research/05-community-tipsters.md)
  - [newsy](docs/research/06-news-sources.md)
  - [GitHub](docs/research/07-github-tools.md)
  - [Claude Code](docs/research/08-claude-code-tooling.md)

## Stack
Python 3.12, uv, DuckDB, penaltyblog, sports-betting, soccerdata, pytest, ruff. Interfejs: Claude Code (skille + MCP), Telegram.

## Typy dnia (STS): poranny skan
```bash
uv run python -m betting_analyst.morning --log-paper     # dziś + jutro, top 5 typów, zapis na papierze
```
W Claude Code: **`/morning-scout`** (skan, newsy dla typów, ewentualne weto z cytatem, lista „na co i za ile”).

**Automatycznie (launchd + Telegram):** 08:00 skan i skrót typów na Telegram, co 15 minut w godz. 11–23 zamknięcie i CLV (z dziennym limitem kredytów The Odds API), 23:30 raport CLV i krótkie CLV na Telegram. Instalacja i założenie bota: [docs/automation.md](docs/automation.md).
```bash
uv run python -m betting_analyst.notify test     # test bota (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID w .env)
scripts/run_job.sh closing                        # ręczny przebieg zadania, log w data/logs/
```

Jak czytać raport (`reports/RRRR-MM-DD-morning.md`):
- **Edge:** o ile kurs STS jest lepszy od „prawdziwej” wyceny (Pinnacle bez marży albo model).
- **✅:** typ jest na plus także po 12% podatku. Typ bez ✅ to „typ dnia” z małą stałą stawką; po podatku w oczekiwaniu jest na minusie.
- **MODEL_ONLY:** wycena tylko z naszego modelu (rogi, kartki, inne linie goli), więc mniej pewna.
- **CLV:** czy wziąłeś kurs lepszy niż „prawdziwa” wycena tuż przed meczem. Przykład: kurs 2.10, zamknięcie Pinnacle bez marży 1.95, więc CLV = +7,7%. Pojedynczy mecz to loteria; średnie CLV po 200–300 zakładach pokazuje, czy masz przewagę.

## Szybki start
```bash
uv sync                                   # środowisko (Python 3.12)
cp .env.example .env                      # wklej darmowy klucz z the-odds-api.com
uv run python -m betting_analyst.scan --show-all          # dzisiejszy skan (około 8 kredytów)
uv run python -m betting_analyst.scan --log-paper         # zapis kandydatów jako paper bets
uv run python -m betting_analyst.scan --from-cache --log-shadow 8   # shadow bets do pomiaru CLV (0 kredytów)
uv run python -m betting_analyst.closing --minutes-before 10        # snapshot zamknięcia przed meczami
uv run python -m betting_analyst.report                   # raport CLV
uv run pytest
```
W Claude Code: `/daily-scan` (skan, newsy, weto z cytatem, raport `reports/RRRR-MM-DD.md`).
