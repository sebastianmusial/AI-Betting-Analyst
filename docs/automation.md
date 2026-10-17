# Automatyzacja Morning Scout (launchd + Telegram)

Codzienny cykl działa lokalnie na Macu ([ADR 0016](adr/0016-interfejsy-runtime.md), [ADR 0023](adr/0023-automatyzacja-launchd-telegram-budzet.md)). Cloud routines odpadają, bo nie mają dostępu do lokalnej bazy `data/betting.duckdb`.

| Kiedy | Zadanie | Co robi | Koszt The Odds API |
|---|---|---|---|
| 08:00 | `morning` | `morning --log-paper --notify`: oferta STS, Pinnacle, typy dnia jako paper bets, raport `reports/RRRR-MM-DD-morning.md`, skrót na Telegram | ≈ 8 kredytów |
| co 15 min, 11:00–23:00 | `closing` | `closing --minutes-before 20`: zamknięcie Pinnacle dla typów rynkowych, zamknięcie STS dla typów model-only, CLV w ledgerze | 0, gdy w oknie nie ma zakładów; 2 na ligę, gdy są; limit dzienny |
| 23:30 | `report` | `report --notify`: raport CLV do `reports/RRRR-MM-DD-clv.txt`, krótkie CLV na Telegram | 0 |

Wszystkie zadania uruchamia [scripts/run_job.sh](../scripts/run_job.sh). Logi trafiają do `data/logs/<zadanie>-RRRR-MM-DD.log`, a zużycie kredytów do `data/logs/odds_api_usage.jsonl`. Zadania czekają na siebie nawzajem (blokada `lockf`), bo DuckDB pozwala na jeden proces zapisujący. Gdy zadanie się wysypie, Telegram dostaje jedno powiadomienie o błędzie dziennie na zadanie.

Pipeline niczego nie obstawia. To analiza i paper trading ([ADR 0001](adr/0001-cel-zakres-kryteria-sukcesu.md), [ADR 0019](adr/0019-wykorzystanie-open-source.md)).

## 1. Telegram (robi właściciel)

1. W Telegramie otwórz **@BotFather**, wyślij `/newbot`, podaj nazwę i login bota (musi kończyć się na `bot`). Dostaniesz token w formie `123456789:AA...`.
2. Napisz do swojego bota dowolną wiadomość, np. `/start`. Bez tego bot nie może do Ciebie pisać.
3. Odczytaj swój `chat_id`: otwórz w przeglądarce `https://api.telegram.org/bot<TOKEN>/getUpdates` i znajdź `"chat":{"id":...}`.
4. Dopisz do `.env` w głównym katalogu repo:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=123456789
   ```
5. Sprawdź:
   ```bash
   uv run python -m betting_analyst.notify test
   ```

Bez tokenu powiadomienia są pomijane z ostrzeżeniem w logu, a reszta pipeline'u działa normalnie.

### Jak wyglądają wiadomości

Rano (maks. 10 linii, bez tabel, liczby prosto z kodu):
```
⚽ Typy dnia STS — sob 17.10 (paper)
1. ✅ · Legia Warszawa – Lech Poznań (dziś 18:30) · 1 @2.45 · 14 zł
2. typ dnia · Ajax – PSV (dziś 21:00) · Gole +2.5 @1.95 · 5 zł
3. typ dnia · Hamburger SV – Hertha (jutro 14:30) · Rogi gosp. +4.5 @2.10 · 5 zł · MODEL_ONLY
Razem 24 zł. ✅ = na plus po podatku 12%; typ dnia = mała stawka, EV < 0 po podatku.
```
Zawetowany typ (wariant z Claude, krok 3 skilla) pokazuje się jako `⛔ weto` ze stawką 0 zł.

Wieczorem:
```
📊 CLV STS — sob 17.10 (paper)
Dziś vs Pinnacle: 3 zakł., śr. CLV +2.1% (po podatku -10.1%), dodatnie 67%
Dziś model-only vs STS: 1 zakł., śr. CLV +4.0% (po podatku -8.5%), dodatnie 100%
Łącznie vs Pinnacle: 37 zakł., śr. CLV +1.4% (po podatku -10.8%), dodatnie 58%
Łącznie model-only vs STS: 12 zakł., śr. CLV +0.9% (po podatku -11.2%), dodatnie 50%
Pojedynczy dzień to szum; wnioski po ≥300 zakładach (ADR 0001).
```
Główny KPI to CLV vs Pinnacle ([ADR 0015](adr/0015-ewaluacja-backtest.md)). CLV typów model-only liczymy względem zamknięcia samego STS, więc to słabsza miara i pokazujemy ją osobno ([ADR 0021](adr/0021-sts-typy-dnia-rynki-dodatkowe.md)). Zawetowane i shadow bets nie wchodzą do statystyki.

Moduł odrzuca wiadomość ze słowami sugerującymi pewność („pewniak” itp.).

## 2. Budżet kredytów The Odds API

Darmowy plan daje 500 kredytów miesięcznie. Skan poranny kosztuje około 8 kredytów (4 ligi × 2 rynki), więc około 240 miesięcznie. Zamknięcie kosztuje 2 kredyty na każdą ligę, która ma otwarty zakład w oknie 20 minut. Ochrona w `config/strategy.yaml` → `odds_api`:

- `daily_closing_credits: 10`: maksymalna liczba kredytów na zamknięcia w ciągu dnia (czas PL). Gdy wszystkie ligi się nie mieszczą, pierwszeństwo ma liga z najwcześniejszym meczem.
- `reserve_credits: 40`: gdy ostatni znany stan konta (`x-requests-remaining`) spadnie poniżej tej wartości, zamknięcia są pomijane, żeby zostało na poranne skany.

Liga pominięta z powodu budżetu jest widoczna w logu `closing-*.log` i jako wpis `skipped:budget` w `odds_api_usage.jsonl`. Jej zakłady zostają w ledgerze bez CLV vs Pinnacle. Zamknięcia STS (rynki model-only) nie kosztują kredytów i działają zawsze.

Szybki podgląd zużycia:
```bash
tail -20 data/logs/odds_api_usage.jsonl
```

Uwaga: przy 30 dniach × (8 + 10) wychodzi 540 kredytów, czyli limit dzienny to sufit. W praktyce typów rynkowych jest mniej niż 5 lig dziennie. Gdy miesięczny stan spada za szybko, obniż `daily_closing_credits` albo `daily_picks`.

## 3. Instalacja launchd (robi właściciel)

Szablony są w [scripts/launchd/](../scripts/launchd/). Instalator podmienia ścieżkę repo i rejestruje zadania dla Twojego użytkownika (`~/Library/LaunchAgents`). Uruchamiaj go **z głównego checkoutu repo**, czyli tam, gdzie leży `data/betting.duckdb` i `.env`, a nie z worktree.

```bash
uv sync
scripts/run_job.sh closing
```
Najpierw ręczny test: w `data/logs/closing-<data>.log` powinno pojawić się „0 kredytów” albo lista zamknięć.

```bash
scripts/launchd/install.sh
```
Instaluje `morning`, `closing` i `report`.

Sprawdzenie i ręczne odpalenie:
```bash
launchctl print gui/$(id -u)/local.betting-analyst.morning | head -20
```
```bash
launchctl kickstart gui/$(id -u)/local.betting-analyst.report
```

Odinstalowanie:
```bash
scripts/launchd/uninstall.sh
```

Po zmianie szablonów albo przeniesieniu repo uruchom `install.sh` jeszcze raz.

### Zachowanie launchd, które warto znać
- **Mac uśpiony o 08:00:** launchd odpali zadanie po wybudzeniu, a zaległe uruchomienia sklei w jedno. Mac wyłączony: zadanie przepada. Jeśli chcesz, żeby Mac sam się budził, ustaw to sam (wymaga hasła administratora): `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`.
- **Klapa zamknięta bez zasilania:** zadania nie biegną. Zamknięcia przed wieczornymi meczami wymagają działającego Maca.
- **Blokada DuckDB:** gdy w tym samym czasie masz otwartą bazę w innym procesie, np. w serwerze MCP `duckdb` albo w notebooku, zapis może się nie udać („Could not set lock”). Zadanie zakończy się błędem i wyśle powiadomienie. Zamknij tamten proces albo przenieś pracę z bazą poza godziny zadań.
- **PATH:** `run_job.sh` dodaje `/opt/homebrew/bin` i `~/.local/bin`. Jeśli `uv` lub `claude` masz gdzie indziej, popraw linię `export PATH=...`.
- Logi samego launchd (np. gdy skrypt w ogóle nie wystartuje): `data/logs/launchd-<zadanie>.log`.

## 4. Alternatywa: poranny skan przez Claude (`/morning-scout`)

Zamiast samego skanu Python o 08:00 można uruchomić pełny skill: skan, newsy dla typów, ewentualne weto z cytatem, skrót na Telegram (z oznaczonymi wetami).

```bash
scripts/launchd/install.sh claude-morning closing report
```
To jest zamiast `morning`. Nie instaluj obu, bo typy zapisałyby się dwa razy, a instalator na to nie pozwoli.

Zadanie wywołuje:
```bash
claude -p "/morning-scout --notify" --allowedTools "Bash(uv run python -m betting_analyst.*)" Read Write WebSearch WebFetch
```

Bez `--bare`, w ramach subskrypcji Claude, przy zalogowanym `claude` w Twoim koncie użytkownika.

**Ostrzeżenia:**
- **Koszt:** każde uruchomienie zużywa limit subskrypcji (kilka wyszukiwań i pobrań stron na typ). Przy 5 typach dziennie to zauważalna część dziennego limitu. Przy planie z rozliczeniem API to realny koszt w dolarach.
- **Czas:** kilka do kilkunastu minut zamiast około minuty. Zamknięcia czekają w tym czasie na blokadę (maks. 15 minut).
- **Niedeterminizm:** treść newsów i decyzje o wecie mogą się różnić między uruchomieniami. Liczby (kursy, p fair, stawki) nadal liczy kod ([ADR 0012](adr/0012-rola-llm.md)), a weto wymaga cytatu i URL.
- **Uprawnienia:** w trybie `-p` nikt nie zatwierdza narzędzi. Lista `--allowedTools` ogranicza Claude do komend projektu i odczytu stron. Nie rozszerzaj jej o ogólny `Bash`.
- **Autoryzacja:** jeśli sesja `claude` wygaśnie, zadanie skończy się błędem. Dostaniesz powiadomienie, a typów tego dnia nie będzie. Wtedy uruchom ręcznie `scripts/run_job.sh morning`.

Rozsądny kompromis: zostaw `morning` w launchd, a `/morning-scout` uruchamiaj ręcznie w Claude Code w dni, w których faktycznie grasz. Gdy poranny skan już jest, skill bierze kursy z cache (`--from-cache`, 0 kredytów), a weta zapisuje w ledgerze. Poprawiony skrót możesz wysłać ponownie: `uv run python -m betting_analyst.notify morning`.
