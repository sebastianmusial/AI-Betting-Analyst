# ADR 0014: Silnik decyzyjny i staking

- **Status:** Accepted
- **Data:** 2026-10-17

## Decyzja
- **Efektywny kurs:** przy podatku od stawki `t` z postawionej kwoty S w grze jest S × (1 − t), więc wypłata to S × (1 − t) × kurs, a `odds_eff = odds × (1 − t)` (np. 2,00 × 0,88 = 1,76). Podatek od wygranej (10% powyżej 2280 zł) uwzględniany przy dużych wypłatach. Konfiguracja per bukmacher i typ zakładu (ADR 0003).
- **EV:** `EV = p_fair × odds_eff − 1`. `p_fair` pochodzi z rynku (ADR 0011, etap 1), ewentualnie potwierdzone modelem.
- **Progi:**
  - min. EV ≥ 3% po podatku;
  - przy kursie > 3,0 próg ≥ 5% (większa niepewność devig przy outsiderach);
  - model DC nie może istotnie przeczyć rynkowi (różnica > 8 pp) bez wyjaśnienia; inaczej oznaczamy kandydata „do ręcznej weryfikacji”.
- **Staking:** ¼ Kelly na `odds_eff` z limitami:
  - maks. 1,5% bankrolla na zakład,
  - maks. 5% ekspozycji dziennie (ADR 0002);
  
  stawki zaokrąglane do „naturalnych” kwot (mniejsze ryzyko limitów).
- **AKO:** łączy 2–3 nogi z różnych meczów, każda z dodatnim EV na prawdopodobieństwie fair, tylko u bukmacherów, gdzie AKO jest bez podatku. EV kuponu = iloczyn `p` × iloczyn kursów − 1. Stawka: ⅛ Kelly (większa wariancja).
- **Wybór bukmachera:** najwyższy `odds_eff` spośród kont właściciela.
- **Wynik działania silnika:** lista kandydatów z uzasadnieniem (`p_fair`, `p_model`, `odds`, `odds_eff`, `EV`, stawka, bukmacher, flagi).

## Konsekwencje
- Silnik jest deterministyczny i w pełni pokryty testami jednostkowymi.
- Progi to hipotezy. Kalibrujemy je w F2 i F6, a ich zmiany zapisujemy w ADR.
