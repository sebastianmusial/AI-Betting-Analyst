# ADR 0021: STS jako główny bukmacher, tryb „Typy dnia”, rynki dodatkowe

- **Status:** Accepted
- **Data:** 2026-10-17
- **Częściowo zastępuje:** [ADR 0006](0006-strategia-znajdowania-przewagi.md): porównywanie kursów i AKO bez podatku są nieaktywne.
- **Powiązany:** [ADR 0022](0022-wyniki-f2-przewaga-tylko-bez-podatku.md): wyniki F2, czyli brak przewagi singli z podatkiem 12% na rynkach głównych; dla STS to argument za ostrożnością i trybem papierowym.
- **Research:** [09-sts-offer-feed.md](../research/09-sts-offer-feed.md), [eksperyment kalibracji rogów i kartek](../experiments/2026-10-counts-calibration.md)

## Kontekst
- Właściciel gra praktycznie tylko w STS i chce rano dostać listę „na co postawić i za ile” na dziś i najbliższe dni, także na rogi, kartki i gole.
- Value Scanner v0 używał przybliżeń kursów (betclic_fr z The Odds API). Przy rygorystycznym filtrze EV po podatku często nie dawał żadnego typu.
- Oferta STS jest publicznie dostępna przez feed WebSocket (pełna oferta meczu: ponad 500 rynków).

## Decyzja
1. **STS = domyślny i jedyny aktywny bukmacher** (`bookmakers.yaml: active`). Pozostali bukmacherzy zostają w konfiguracji jako nieaktywni.
2. **Źródło kursów do gry: feed STS** (`sources/sts.py`, mapowanie w `config/sts_markets.yaml`). Przybliżenia z The Odds API służą tylko do porównań.
3. **Tryb „Typy dnia”** (`python -m betting_analyst.morning`, skill `/morning-scout`):
   - ranking po `edge = kurs_STS × p_fair − 1` (przed podatkiem), maks. 1 typ na mecz (korelacja), top N (domyślnie 5);
   - **podatek jest informacją, nie filtrem**: kurs i EV po podatku 12% oraz znak ✅, gdy typ jest na plus także po podatku (próg ADR 0014);
   - stawki: ¼ Kelly dla ✅, mała stała stawka (0,5% bankrolla) dla „typu dnia” bez ✅; limity ADR 0002 bez zmian;
   - minimalny próg: edge > 0. Typów z ujemną przewagą nad rynkiem nie pokazujemy, nawet gdy jest ich mniej niż N.
4. **Cena fair:**
   - 1X2 i O/U 2.5: zdewigowany Pinnacle (The Odds API);
   - inne linie goli i BTTS: Dixon-Coles;
   - rogi i kartki (łącznie i per drużyna): model NB (`models/counts.py`). W Ekstraklasie wyłączone (brak statystyk w football-data).
5. **Polityka rynków „model-only”** (wycena tylko z naszego modelu):
   - zakotwiczenie w rynku: `p_fair = 0,5·p_model + 0,5·p_STS(devig)`;
   - odrzucamy typ, gdy |p_model − p_STS| > 15 pp (zwykle błąd modelu, np. beniaminek z małą historią w lidze) albo kurs > 3,5 (kalibracja: model przeszacowuje ogony kartek);
   - próg edge ≥ 8%;
   - flaga `MODEL_ONLY`;
   - rogi i kartki **tylko linie per drużyna**. Na sumach model wypada praktycznie jak średnia ligi, a feed STS nie podaje sędziego (`count_totals_enabled: false`).
6. **Pomiar:**
   - rejestr zapisuje `fair_source` i `pick_type` (`value` / `daily`);
   - CLV: rynki z ceną Pinnacle względem zamknięcia Pinnacle (`ref_event_id`), rynki model-only względem zdewigowanego zamknięcia STS (słabsza miara);
   - raport rozdziela wyniki według `pick_type` i `fair_source`.
7. **Boosty STS:** do rozpoznania (struktura w feedzie nieznana). Gdy będą, oceniamy je tak samo i oznaczamy flagą `BOOST`.

## Konsekwencje
- Brak porównywania kursów oznacza, że przewaga musi pochodzić z błędnej wyceny STS, z modeli lub z promocji. Pierwszy pomiar (2026-10-17): na 1X2 STS daje najwyżej około +1,5% nad Pinnacle; większe przewagi wychodzą głównie w rynkach model-only.
- „Typy dnia” bez ✅ są **po podatku na minusie w oczekiwaniu**. Mierzymy je osobno; jeśli po kilku tygodniach CLV i wynik się nie bronią, wyłączamy tę grupę.
- Ryzyko limitów skupia się na jednym koncie, więc monitor ryzyka limitów (F7) zyskuje na znaczeniu.
- Feed STS jest nieoficjalny i może się zmienić. Testy kontraktowe na próbkach + Chrome DevTools MCP (`.mcp.json`) do szybkiej diagnozy.
- Kalibracja rogów i kartek pokazuje tylko niewielką przewagę modelu nad średnią ligi. Do realnych stawek te rynki wejdą dopiero po dodatnim wyniku w rejestrze papierowym.
