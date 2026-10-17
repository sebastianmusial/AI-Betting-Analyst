# ADR 0006: Strategia znajdowania przewagi

- **Status:** Accepted, częściowo zastąpiony przez [ADR 0021](0021-sts-typy-dnia-rynki-dodatkowe.md) (właściciel gra tylko w STS: porównywanie kursów i AKO bez podatku nieaktywne)
- **Data:** 2026-10-17

## Kontekst
Najlepiej udokumentowana strategia dla indywidualnego gracza to value betting u miękkich bukmacherów względem ostrej linii (Pinnacle). W Polsce przewagę zjada podatek 12% (ADR 0003), więc trzeba przewag większych albo omijania podatku.

## Decyzja
Hybryda złożona z czterech źródeł przewagi, w kolejności priorytetu:
1. **Rynek ostry jako baza.** Zdewigowane kursy Pinnacle (lub konsensus wielu bukmacherów, jeśli Pinnacle brak) dają prawdopodobieństwo fair. Kandydat to kurs polskiego bukmachera, który **po podatku** ma EV ≥ próg (ADR 0014).
2. **Własny model jako druga opinia.** Dixon-Coles i Elo, później stacking (ADR 0011). Służy do potwierdzania lub odrzucania kandydatów i do wychwytywania sytuacji, w których rynek się myli (np. po newsie).
3. **Sygnały jakościowe i ruch kursów.** Newsy (ADR 0013), steam (ADR 0018), typerzy oceniani przez CLV (ADR 0017). Mogą zawetować typ albo podbić jego priorytet. **Nie zmieniają prawdopodobieństw bezpośrednio** (ADR 0012).
4. **Optymalizacja podatkowa:**
   - preferowanie ofert bez podatku,
   - **AKO złożone z 2–3 niezależnych value-nóg** (różne mecze), gdy AKO jest bez podatku,
   - skaner boostów i promocji (F7).

Porównywanie kursów u wszystkich legalnych bukmacherów, na których właściciel ma konta.

## Konsekwencje
- AKO zwiększa wariancję. Wymaga osobnego śledzenia wyników i ostrożniejszego stakingu.
- Bez kursów polskich bukmacherów (scraping lub ręczne wpisanie) system nie wskaże zakładu. Same kursy Pinnacle wystarczą jednak do pomiaru CLV.
