# ADR 0013: Sygnały jakościowe (newsy, kontuzje, składy)

- **Status:** Accepted (F1: ręcznie przez skill), Proposed (F5: pipeline)
- **Data:** 2026-10-17
- **Research:** [06-news-sources.md](../research/06-news-sources.md)

## Decyzja
**Źródła:**
- **RSS per liga** (zweryfikowane):
  - PL: SportoweFakty (filtr `/pilka-nozna`), Weszło, Interia;
  - ENG: Sky 11688, Football League World, BBC;
  - GER: kicker 2. Bundesliga;
  - NED: Voetbal International, VoetbalPrimeur (WebSub push).
- **Google News RSS** per drużyna w lokalnym języku, z wyrazami kluczowymi (kontuzja/injury/Verletzung/blessure…).
- **Kontuzje:** Transfermarkt (z Ekstraklasą), Sportsgambler (bez Ekstraklasy), API-Football `/injuries`.
- **Składy:** FotMob/Sofascore od 75 min przed meczem, API-Football jako backup.
- **Bez płatnego X API** (około $300/mies.) i bez Nitter. Meczyki/Włodarczyk przez Google News.

**Model flagi:**
`{team, player, flag_type, status: confirmed|doubtful|rumour, source_tier: 1|2|3, impact_estimate, evidence_url, published_at, captured_at}`

**Harmonogram (F5):** odpytywanie zagęszczane przed meczem (co 30 → 10 → 5 min, składy co 60–90 s).

**Etap F1:** skill `/daily-scan` sprawdza newsy dla kandydatów przez WebSearch i RSS na żądanie.

## Konsekwencje
- Flagi archiwizujemy wraz z `captured_at`. Pozwala to później sprawdzić, czy dana kategoria newsów faktycznie poprawia prognozy.
- Rumour (poziom 3) nigdy nie daje weta, najwyżej obniża priorytet.
