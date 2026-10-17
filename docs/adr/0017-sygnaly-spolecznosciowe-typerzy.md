# ADR 0017: Sygnały społecznościowe i typerzy

- **Status:** Proposed (wdrożenie w F5)
- **Data:** 2026-10-17
- **Research:** [05-community-tipsters.md](../research/05-community-tipsters.md)

## Kontekst
- Pojedynczy typerzy przegrywają z kursami.
- Konsensus wielu typerów ma małą, udokumentowaną przewagę: +1,3% na 68 tys. zdarzeń (Brown & Reade 2019); podobnie konsensus z Blogabet.
- Polskie grupy (Discord, Telegram, FB, zawodtyper) nie mają audytowanych wyników.
- Płatne grupy VIP i „ustawione mecze” to oszustwa.

## Decyzja
- **Każdy zewnętrzny typ jest daną, nie decyzją.** Zapisujemy go jako `{source, tipster, match, market, selection, odds, posted_at}` z kursem Pinnacle w chwili publikacji i na zamknięciu.
- **Typerów oceniamy przez CLV** (nie przez ROI ani trafność). Źródło lub typera z CLV ≤ 0 po 200 i więcej typach odrzucamy.
- **Źródła:**
  - **Bet2Invest:** główne (typy certyfikowane po kursach Pinnacle, publiczne profile);
  - **konsensus** (OddsPortal, Blogabet): liczba zgodnych typów jako cecha modelu, nie decyzja;
  - **sentyment** (Reddit, zawodtyper „Typy Dnia”): eksperymentalnie, testowany również jako sygnał przeciwny.
- **Ignorujemy:**
  - płatne grupy VIP i Telegram,
  - oferty „fixed matches”,
  - rankingi tylko po zysku (OLBG),
  - screeny influencerów,
  - scraping prywatnych grup.

## Konsekwencje
- Tracker typerów to w praktyce ten sam mechanizm CLV co dla własnych zakładów. Wymaga jedynie dodatkowego `source`.
- Konsensus wejdzie do modelu dopiero, gdy pokaże wartość out-of-sample.
