# ADR 0010: Rozpoznawanie encji (drużyny, ligi, mecze)

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
Każde źródło nazywa drużyny inaczej, np. „Legia Warszawa” / „Legia Warsaw” / „Legia”, „Sparta Rotterdam” / „Sparta R.”, „1. FC Kaiserslautern” / „Kaiserslautern”. Bez wiarygodnego dopasowania kursy trafią do złego meczu.

## Decyzja
- Kanoniczny identyfikator drużyny (`team_id`) i tabela `team_aliases(source, alias, team_id)`.
- Mecz identyfikujemy jako (`league`, `home_team_id`, `away_team_id`, data ± 36 h).
- Nowe aliasy:
  1. dopasowanie dokładne,
  2. dopasowanie fuzzy (`rapidfuzz`),
  3. propozycja LLM.
  
  **Każde dopasowanie spoza kroku 1 wymaga zatwierdzenia przez człowieka** (skill/CLI) przed zapisem.
- Mecz bez dopasowania jest pomijany i raportowany. Nigdy nie zgadujemy po cichu.

## Konsekwencje
- Krótki koszt ręczny na starcie (około 80 drużyn w 4 ligach), potem prawie zero.
