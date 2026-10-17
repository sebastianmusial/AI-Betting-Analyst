---
name: daily-scan
description: Dzienny skan value (pre-match) — uruchamia Value Scanner, sprawdza newsy i dropping odds dla każdego kandydata, może zawetować typ z cytatem źródła i zapisuje raport reports/YYYY-MM-DD.md. Użyj, gdy właściciel prosi o dzisiejsze typy, skan, kandydatów albo raport dnia.
argument-hint: "[YYYY-MM-DD] (domyślnie dziś, czas PL)"
allowed-tools: Bash(uv run python -m betting_analyst.*), Read, Write, WebSearch, WebFetch
---

# /daily-scan

Dzienny skan kandydatów value dla 4 lig (Ekstraklasa, Championship, 2. Bundesliga, Eredivisie),
rynki 1X2 i O/U 2.5, tylko legalni polscy bukmacherzy. Tryb: **paper trading**.

## Twarde zasady (ADR 0003, 0012, 0013)

- **Nie generujesz ani nie zmieniasz prawdopodobieństw, kursów fair, EV ani stawek.** Liczy je
  wyłącznie kod (devig Pinnacle + Dixon-Coles). Liczby w raporcie kopiujesz z
  `data/scans/<DATA>.json` bez zmian.
- Twoja rola: **flagować** (informacja) i **wetować** (odrzucić kandydata) — wyłącznie na
  podstawie twardej, cytowanej informacji: potwierdzona absencja kluczowego zawodnika,
  zawieszenie, zmiana trenera, przełożenie meczu, której rynek (Pinnacle) jeszcze nie uwzględnił.
- Każde weto i każda flaga: **dosłowny krótki cytat + URL + data publikacji**. Bez źródła — brak weta.
- Plotka (tier 3: „podobno”, „media donoszą”, anonimowe konto) **nigdy nie daje weta**, najwyżej
  flagę „obniżony priorytet”.
- Nie stawiasz zakładów, nie logujesz się do bukmacherów, nie zakładasz kont.
- Kursy oznaczone **PROXY** to nie są kursy polskich buków — w raporcie zawsze to podkreśl.

## Kroki

### 1. Skan

Data: argument skilla albo dzisiejsza data (Europe/Warsaw).

```bash
uv run python -m betting_analyst.scan --date <DATA> --log-paper
```

- Kod wyjścia 2 = brak `ODDS_API_KEY` → przekaż właścicielowi komunikat ze skanera (jak założyć
  darmowy klucz na the-odds-api.com) i zakończ. Nie zakładaj konta sam.
- Jeśli ten dzień był już skanowany i chcesz oszczędzić kredyty: dodaj `--from-cache`.
- `--log-paper` zapisuje do ledgera tylko kandydatów z ręcznymi kursami polskich buków
  (`data/manual_odds/<DATA>.csv`). Kandydaci PROXY trafiają do raportu, ale nie do ledgera.
- Ostrzeżenia o niedopasowanych drużynach: wypisz je w raporcie z propozycją aliasu
  (do zatwierdzenia przez właściciela w `config/team_aliases.yaml`) — nie dopisuj aliasów sam.

### 2. Wczytaj kandydatów

Przeczytaj `data/scans/<DATA>.json` (pola: `candidates`, `ako`, `events`, `warnings`).
Jeśli `candidates` jest puste — przejdź do kroku 5 i napisz krótki raport „brak kandydatów”.

### 3. Newsy dla każdego kandydata (obie drużyny)

Dla każdego kandydata sprawdź informacje z ostatnich ~72 h:

**WebSearch** (w języku lokalnym + angielskim), np.:
- `"<drużyna>" kontuzja OR uraz OR zawieszony` (PL), `"<team>" injury OR suspended team news` (ENG),
  `"<Verein>" Verletzung OR gesperrt OR Ausfall` (GER), `"<club>" blessure OR geschorst` (NED),
- `"<home>" "<away>" przewidywany skład / predicted lineup / Aufstellung / opstelling`.

**RSS wg ligi** (WebFetch, filtruj po nazwach drużyn):

| Liga | Feedy |
|---|---|
| Ekstraklasa | `https://sportowefakty.wp.pl/rss.xml` (tylko linki zawierające `/pilka-nozna`), `https://weszlo.com/feed` |
| Championship | `https://www.skysports.com/rss/11688`, `https://www.footballleagueworld.co.uk/feed` |
| 2. Bundesliga | `https://newsfeed.kicker.de/news/2-bundesliga` |
| Eredivisie | `https://www.vi.nl/feed/news.xml`, `https://www.voetbalprimeur.nl/feed/news.xml` |

Dla każdej znalezionej informacji zapisz flagę w modelu ADR 0013:
`{team, player, flag_type, status: confirmed|doubtful|rumour, source_tier: 1|2|3, evidence_url, published_at, cytat}`.
Tier 1 = klub / oficjalny komunikat / konferencja trenera, tier 2 = uznane media, tier 3 = plotka.

### 4. Ruch kursów (ADR 0018)

- BetExplorer „dropping odds”: `https://www.betexplorer.com/odds-movements/soccer/` — sprawdź,
  czy mecz kandydata jest na liście i w którą stronę idzie kurs.
- Ruch **przeciwko** naszej selekcji bez publicznego newsa = flaga „niewyjaśniony ruch”
  → dodatkowe, celowane wyszukiwanie newsów dla obu drużyn. Sam ruch nie jest podstawą weta.
- Szanuj strony: pojedyncze zapytania, bez obchodzenia blokad/CAPTCHA (ADR 0009).

### 5. Decyzja: przepuść / flaguj / weto

- **Weto** (tylko tier 1–2, status confirmed, informacja nowsza niż prawdopodobny moment
  wyceny rynku i istotna dla naszej selekcji). Dla kandydatów zapisanych w ledgerze uruchom:

  ```bash
  uv run python -m betting_analyst.ledger veto --date <DATA> --event-id <event_id> \
      --market <1x2|ou25> --selection <home|draw|away|over|under> \
      --reason "„<dosłowny cytat>” — <1 zdanie dlaczego>" --url "<URL>"
  ```

  Zawetowany zakład zostaje w rejestrze ze statusem `vetoed` — jego CLV mierzymy osobno, żeby
  ocenić, czy weta pomagają (ADR 0012).
- **Flaga** (doubtful, tier 3, „DC≠rynek”, niewyjaśniony ruch): kandydat zostaje, opis w raporcie.
- Kandydaci z flagą `DC≠rynek: do ręcznej weryfikacji` — wyjaśnij w raporcie możliwą przyczynę
  (np. nowy trener, beniaminek, mało danych), ale **nie zmieniaj liczb**.

### 6. Raport `reports/<DATA>.md`

Utwórz katalog `reports/` jeśli nie istnieje. Struktura:

```markdown
# Skan value — <DATA>

> Tryb paper trading. Prawdopodobieństwa: rynek (devig Pinnacle) + Dixon-Coles; LLM tylko flaguje/wetuje.

## Podsumowanie
- Mecze: N, kandydaci: K (przepuszczeni: P, zawetowani: V), AKO: A
- Zużyte kredyty The Odds API / pozostało: … (z wyjścia skanera)
- Ostrzeżenia: …

## Kandydaci
| Start | Mecz | Typ | Buk (PROXY?) | Kurs | Kurs eff | p_fair | p_DC | EV | Stawka | Decyzja |
|---|---|---|---|---|---|---|---|---|---|---|

### <Mecz> — <Typ>
- Liczby (z JSON): …
- Newsy: flagi z cytatem i URL (lub „brak istotnych informacji”, z listą sprawdzonych źródeł)
- Ruch kursów: …
- Decyzja: przepuszczony / flaga / **WETO** + cytat i URL

## AKO
…(tylko buki z AKO bez podatku; nogi, kurs łączny, EV, stawka)

## Do zrobienia dla właściciela
- sprawdzić kursy PROXY u swojego buka i ewentualnie wpisać:
  `uv run python -m betting_analyst.sources.manual_odds add …`
- aliasy drużyn do zatwierdzenia
- `uv run python -m betting_analyst.closing` przed meczami (CLV)
```

Na koniec pokaż właścicielowi krótkie podsumowanie (kandydaci, weta z powodami, ścieżka raportu).
Przypomnij: przed każdym zakładem sprawdź kurs u buka — skaner pokazuje stan z chwili skanu.
