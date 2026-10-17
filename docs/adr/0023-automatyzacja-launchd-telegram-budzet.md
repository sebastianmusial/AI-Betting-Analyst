# ADR 0023: Automatyzacja lokalna — launchd, Telegram, budżet kredytów

- **Status:** Accepted
- **Data:** 2026-10-17
- **Doprecyzowuje:** [ADR 0016](0016-interfejsy-runtime.md) (runtime i powiadomienia), [ADR 0021](0021-sts-typy-dnia-rynki-dodatkowe.md) (Morning Scout)

## Kontekst
Morning Scout (`morning`, `closing`, `report`) działa, ale tylko gdy właściciel uruchomi go ręcznie. CLV wymaga snapshotu zamknięcia kilkanaście minut przed każdym meczem z zakładem, czego ręcznie nie da się robić codziennie. Baza DuckDB jest lokalna, więc cloud routines odpadają. Darmowy plan The Odds API ma 500 kredytów miesięcznie, a zamknięcie odpalane co 15 minut mogłoby je wyczerpać bez ostrzeżenia.

## Decyzja
- **Harmonogram: launchd** (LaunchAgents użytkownika), szablony w `scripts/launchd/`, jeden wrapper `scripts/run_job.sh`:
  - 08:00 `morning --log-paper --notify`,
  - 11:00–23:00 co 15 min (`StartCalendarInterval`, pełne kwadranse) `closing --minutes-before 20`,
  - 23:30 `report --notify`, raport do `reports/RRRR-MM-DD-clv.txt`.
  Zadania serializuje `lockf`, bo DuckDB pozwala na jeden proces zapisujący. Logi trafiają do `data/logs/`. Instaluje właściciel (`scripts/launchd/install.sh`), nie agent.
- **Powiadomienia: `notify.py`**, czyli Bot API przez httpx, zwykły tekst. Token i chat id wyłącznie w `.env`. Brak tokenu oznacza no-op z ostrzeżeniem. Treść składa kod, nie LLM: rano maks. 10 linii (typ, kurs, stawka, ✅ albo typ dnia, flagi, weta), wieczorem CLV vs Pinnacle i osobno model-only vs STS. Moduł blokuje sformułowania sugerujące pewność. Przy błędzie zadania wysyłamy jedno powiadomienie dziennie na zadanie.
- **Budżet kredytów:** każde zapytanie do The Odds API trafia do `data/logs/odds_api_usage.jsonl`. Zamknięcie ma limit dzienny `odds_api.daily_closing_credits` (domyślnie 10) i rezerwę `odds_api.reserve_credits` (domyślnie 40, liczoną od ostatniego `x-requests-remaining`). Pierwszeństwo ma liga z najwcześniejszym meczem. Poranny skan nie jest ograniczany, bo bez niego nie ma typów.
- **Wariant z Claude** (`claude -p "/morning-scout --notify"`, subskrypcja, wąskie `--allowedTools`) jest opcjonalną alternatywą dla zadania `morning`, nie domyślną: kosztuje limit subskrypcji, trwa dłużej i jest niedeterministyczny.

## Konsekwencje
- CLV liczy się bez ręcznej pracy, pod warunkiem że Mac działa w godzinach meczów. Uśpiony Mac nadrabia zadania po wybudzeniu, a wyłączony je traci.
- Gdy budżet się kończy, część zakładów nie dostaje CLV vs Pinnacle. Widać to w logu, a odsetek zakładów bez zamknięcia trzeba monitorować w raporcie (`with_closing`).
- Proces trzymający otwartą bazę, np. MCP `duckdb`, może zablokować zapis zadania. Zadanie kończy się wtedy błędem i powiadomieniem.
- Weta pojawiają się w porannym skrócie tylko w wariancie z Claude albo po ręcznym `notify morning` po wecie.

## Rozważane opcje
- **Cloud routines / zaplanowane zadania w chmurze:** brak dostępu do lokalnej bazy.
- **`StartInterval` co 900 s:** dryfuje po uśpieniu i nie trafia w pełne kwadranse, przez co mecz o 20:45 mógłby dostać snapshot 19 albo 4 minuty przed startem.
- **cron:** na macOS gorzej obsługuje uśpienie niż launchd.
- **Limit liczony tylko z nagłówka `x-requests-remaining`:** nie chroni dziennego tempa zużycia, dlatego potrzebny jest własny log.
