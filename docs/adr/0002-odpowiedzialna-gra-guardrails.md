# ADR 0002: Odpowiedzialna gra i guardrails

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
Narzędzie, które daje poczucie „przewagi”, może zachęcać do grania ponad stan. Guardrails muszą być wbudowane w silnik, a nie zależeć od dobrej woli w danym dniu.

## Decyzja
- **Bankroll:** jedna, z góry ustalona kwota przeznaczona wyłącznie na grę (w configu). Silnik nie zaproponuje stawki ponad bankroll i nie podpowiada dopłat.
- **Limity** (konfigurowalne, domyślnie):
  - maks. 1,5% bankrolla na zakład,
  - maks. 5% ekspozycji dziennie,
  - maks. 15% tygodniowo.
- **Stop-loss:** spadek bankrolla o 25% od szczytu oznacza automatyczną pauzę rekomendacji na 7 dni i obowiązkowy post-mortem.
- **Zakaz „odgrywania się”:** stawka liczy się tylko z Kelly'ego i bieżącego bankrolla. Silnik nie zwiększa stawek po stratach.
- **Cooling-off:** komenda wstrzymująca rekomendacje na N dni.
- **Przejrzystość:** raport dzienny zawsze pokazuje skumulowany wynik (również ujemny) i CLV, nie tylko „trafione”.
- **Najpierw paper trading** (ADR 0001).

## Konsekwencje
- Część potencjalnie dodatnich zakładów zostanie pominięta przez limity. To świadomy koszt.
- Guardrails są testowane jednostkowo jak każda inna logika.
