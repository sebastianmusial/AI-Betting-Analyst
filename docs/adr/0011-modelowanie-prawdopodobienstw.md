# ADR 0011: Modelowanie prawdopodobieństw

- **Status:** Accepted (etapy 1–2), Proposed (etapy 3–4: zależą od wyników F2)
- **Data:** 2026-10-17
- **Research:** [03-modeling-strategy.md](../research/03-modeling-strategy.md)

## Decyzja
Budujemy modele warstwowo. Każda warstwa musi pobić poprzednią na kalibracji out-of-sample, inaczej nie wchodzi do użytku.

1. **Rynek (baza):**
   - devig kursów Pinnacle metodami `power` i `shin` (domyślna metoda wybrana empirycznie w F2), plus `multiplicative` jako punkt odniesienia;
   - gdy Pinnacle brak: konsensus (średnia zdewigowana) wielu bukmacherów.
2. **Modele statystyczne (druga opinia):**
   - Elo (ClubElo jako cecha albo własne);
   - **Dixon-Coles z zanikaniem wagi w czasie** (`penaltyblog`), per liga, na 2–3 ostatnich sezonach. Daje pełny rozkład wyników, więc obejmuje 1X2 i O/U 2.5.
3. **xG** (Proposed): Sofascore/FotMob, jeśli dostępne dla naszych lig. W innym razie wariant bez xG albo płatny Sportmonks.
4. **Stacking** (Proposed): regresja logistyczna lub LightGBM na cechach:
   - rynek, DC, Elo, xG,
   - odpoczynek i natłok meczów,
   - wartość składu,
   - flagi z newsów (ADR 0012, 0013).

   Rozważamy funkcję celu „mniej skorelowaną z rynkiem” (Hubáček i in. 2019).

**Selekcja modeli po kalibracji, nie po trafności:** Brier, log loss, RPS, krzywe kalibracji. Walidacja walk-forward (ADR 0015).

## Konsekwencje
- MVP (F1) używa tylko etapów 1–2. Reszta dopiero po bramce F2.
- Każdy model zapisuje wersję i datę dopasowania, a prognozy w rejestrze odwołują się do wersji.
