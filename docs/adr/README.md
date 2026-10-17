# Architecture Decision Records

Format: uproszczony MADR, opisany w [ADR 0000](0000-rejestrowanie-decyzji-adr.md). Nową decyzję tworzymy, kopiując [szablon](#szablon) do pliku `NNNN-slug.md` z kolejnym numerem.

| # | Decyzja | Status |
|---|---|---|
| [0000](0000-rejestrowanie-decyzji-adr.md) | Rejestrowanie decyzji jako ADR | Accepted |
| [0001](0001-cel-zakres-kryteria-sukcesu.md) | Cel, zakres i kryteria sukcesu: narzędzie decyzyjne, KPI = CLV | Accepted |
| [0002](0002-odpowiedzialna-gra-guardrails.md) | Odpowiedzialna gra i guardrails | Accepted |
| [0003](0003-kontekst-prawny-podatkowy-pl.md) | Kontekst prawny i podatkowy PL | Accepted |
| [0004](0004-wybor-sportu-i-lig.md) | Wybór sportu i lig: piłka, Ekstraklasa i ligi średniego szczebla | Accepted |
| [0005](0005-pre-match-vs-live.md) | Pre-match vs live: pre-match, live tylko jako alerty | Accepted |
| [0006](0006-strategia-znajdowania-przewagi.md) | Strategia znajdowania przewagi (hybryda) | Accepted |
| [0007](0007-stack-technologiczny.md) | Stack technologiczny: Python, uv | Accepted |
| [0008](0008-przechowywanie-danych.md) | Przechowywanie danych: DuckDB i warstwa raw | Accepted |
| [0009](0009-zrodla-danych-ingestion.md) | Źródła danych i ingestion: najpierw darmowe | Accepted |
| [0010](0010-rozpoznawanie-encji.md) | Rozpoznawanie encji | Accepted |
| [0011](0011-modelowanie-prawdopodobienstw.md) | Modelowanie prawdopodobieństw | Accepted / Proposed |
| [0012](0012-rola-llm.md) | Rola LLM: ekstrakcja i weto, bez prawdopodobieństw | Accepted |
| [0013](0013-sygnaly-jakosciowe-newsy.md) | Sygnały jakościowe (newsy) | Accepted / Proposed |
| [0014](0014-silnik-decyzyjny-staking.md) | Silnik decyzyjny i staking | Accepted |
| [0015](0015-ewaluacja-backtest.md) | Ewaluacja i backtest, bramki go/no-go | Accepted |
| [0016](0016-interfejsy-runtime.md) | Interfejsy i runtime | Accepted |
| [0017](0017-sygnaly-spolecznosciowe-typerzy.md) | Sygnały społecznościowe i typerzy | Proposed |
| [0018](0018-ruch-kursow-steam.md) | Ruch kursów (steam) | Proposed |
| [0019](0019-wykorzystanie-open-source.md) | Wykorzystanie open source | Accepted |
| [0020](0020-narzedzia-claude-code.md) | Narzędzia Claude Code | Accepted |
| [0021](0021-wyniki-f2-przewaga-tylko-bez-podatku.md) | Wyniki F2: przewaga tylko bez podatku i przy kursach z górnej granicy rynku | Accepted |

## Szablon

```markdown
# ADR NNNN: Tytuł

- **Status:** Proposed | Accepted | Superseded by NNNN | Deprecated
- **Data:** RRRR-MM-DD
- **Research:** (opcjonalnie link do docs/research)

## Kontekst
Jaki problem rozwiązujemy, jakie są ograniczenia i fakty.

## Decyzja
Co postanowiliśmy, konkretnie.

## Konsekwencje
Co z tego wynika (plusy, minusy, ryzyka, dalsze kroki).

## Rozważane opcje
Co odrzuciliśmy i dlaczego.
```
