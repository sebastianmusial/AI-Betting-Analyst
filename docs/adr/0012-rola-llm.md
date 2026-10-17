# ADR 0012: Rola LLM (Claude)

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
W benchmarku MŚ 2026 (bez wycieku danych treningowych) żaden z 4 frontier-LLM nie pobił rynku w Brier score, a pewność LLM nie korelowała z trafnością. LLM świetnie radzą sobie natomiast z ekstrakcją informacji z tekstu, dopasowaniem nazw, wyjaśnianiem i orkiestracją.

## Decyzja
**LLM robi:**
- ekstrakcję z newsów do ustrukturyzowanych flag (kontuzje, zawieszenia, zmiana trenera, konflikty, finanse, podróż, pogoda, motywacja), zawsze z `evidence_url` i cytatem;
- propozycje dopasowań nazw (ADR 0010; zatwierdza człowiek);
- uzasadnienie typu, raport dzienny, post-mortem;
- orkiestrację: uruchamia skaner, narzędzia MCP, wyszukiwanie;
- **weto:** może odrzucić kandydata na podstawie twardej, cytowanej informacji (np. potwierdzona absencja kluczowego zawodnika, której rynek jeszcze nie uwzględnił). Weto i jego powód trafiają do rejestru.

**LLM nie robi:**
- **nie generuje i nie modyfikuje prawdopodobieństw ani kursów fair**;
- nie liczy stawek; robi to deterministyczny kod.

**Ewaluacja wpływu LLM:** CLV i wynik zakładów zawetowanych vs przepuszczonych śledzimy osobno. Jeśli weta nie pomagają, wyłączamy je.

## Konsekwencje
- Flagi LLM mogą później stać się cechami modelu statystycznego (ADR 0011, etap 4), kalibrowanymi na danych.
- Koszt: na start Claude Code w ramach subskrypcji (headless `claude -p`), później ewentualnie tani model przez API do masowej ekstrakcji.
