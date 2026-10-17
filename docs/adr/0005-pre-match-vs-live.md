# ADR 0005: Pre-match vs live

- **Status:** Accepted
- **Data:** 2026-10-17
- **Research:** [03-modeling-strategy.md](../research/03-modeling-strategy.md)

## Kontekst
Rynki live przesadnie reagują na zaskakujące zdarzenia (np. wczesny gol outsidera). Dowody pochodzą jednak głównie z giełd zakładów. Gdy gra się u bukmachera, dochodzą:
- opóźnienia streamów (5–8 s),
- opóźniona akceptacja zakładów,
- zawieszanie rynków,
- wyższe marże,
- drogie feedy live ($100–300/mies.).

## Decyzja
- **MVP i fazy F1–F6: wyłącznie pre-match.**
- **F7 (opcjonalnie):** kilka prostych, regułowych **alertów live** zestawionych z modelem pre-match (np. „outsider prowadzi po 20 min, kurs na faworyta przestrzelił model o X”). Zakład stawiany ręcznie, bez automatu.

## Konsekwencje
- Prostsza architektura: harmonogram co kilka minut zamiast strumienia.
- Nie wykorzystujemy ewentualnych nieefektywności live. Wracamy do tematu, gdy pre-match pokaże dodatnie CLV.

## Rozważane opcje
- **Live od początku:** odrzucone (koszty, opóźnienia, ryzyko limitów).
