# 04. Polska: prawo, podatki, limity kont

> To nie jest porada prawna ani podatkowa. Przed decyzjami finansowymi sprawdź źródła u bukmachera i w Ministerstwie Finansów.

## Legalni bukmacherzy
- Legalnie można grać tylko u operatorów z licencją Ministra Finansów. Lista jest na podatki.gov.pl, w sekcji „Zakłady wzajemne i gry hazardowe przez Internet”.
- Główne marki: STS, Fortuna, Betclic, Superbet, Betfan, LV Bet, Totalbet, forBET, eToto, Lebull.

## Pinnacle, Betfair i inni zagraniczni operatorzy
- Pinnacle wycofał się z Polski w 2017 r. Betfair nigdy nie miał polskiej licencji.
- Rejestr domen zakazanych: dostawcy internetu blokują wpisane domeny w ciągu 48 h, a operatorzy płatności w ciągu 30 dni.
- Kary dla gracza:
  - art. 109 KKS (gra na nielegalnej stronie): grzywna do 120 stawek dziennych;
  - art. 107 §2 KKS: grzywna do 720 stawek dziennych i/lub do 3 lat więzienia, plus przepadek wygranej.
- **W projekcie:** kursy Pinnacle i Betfair wykorzystujemy wyłącznie jako *dane referencyjne* przez dostawców danych. Nigdy tam nie gramy.

## Podatki
- **12% od stawki (podatek od gier).** Formalnie płaci go operator, w praktyce przerzuca na gracza: ze stawki 100 zł w grze jest 88 zł. Efektywny kurs to kurs × 0,88. Do progu rentowności potrzeba około 13,6% dodatkowej przewagi.
- **10% od wygranej powyżej 2280 zł na kupon** (pobiera bukmacher). Według większości źródeł dotyczy całej wypłaty.
- **Promocje bez podatku:**
  - Betclic „Gra bez podatku 2.0” (od 05.2026):
    - single bez podatku do 1000 zł stawek, potem 6%;
    - AKO bez podatku;
    - jeśli co najmniej połowa zakładów w okresie to AKO, wszystkie zakłady są bez podatku.
  - Według meczyki.pl STS i Superbet nie mają porównywalnej oferty.
  - Źródła to strony afiliacyjne. **Regulamin trzeba weryfikować u bukmachera**, a w `config/bookmakers.yaml` trzymać aktualne zasady.

## Limity kont
Polscy bukmacherzy limitują wygrywających graczy.
- **Co wyzwala limit:**
  - stawki rzędu kilku tysięcy złotych,
  - częste wygrane,
  - niszowe ligi,
  - nadużywanie bonusów,
  - nietypowe kwoty stawek.
- **Jak to wygląda:** bez ostrzeżenia; dowiadujesz się, gdy zakład zostaje odrzucony.
- **Konta niezweryfikowane:** łączne stawki do 5000 zł.
- **Limity wygranej na kupon:** STS 1 mln zł, Superbet 2 mln zł, Betclic 800 tys. zł, Fortuna około 601 tys. zł, forBET 200 tys. zł.

## Wnioski dla projektu
1. Najpierw podatek. Mała przewaga względem Pinnacle zwykle znika po podatku, więc szukamy:
   - dużych rozbieżności,
   - ofert bez podatku,
   - kuponów AKO z kilku value betów,
   - boostów i promocji.
2. Konfiguracja podatku per bukmacher i per typ zakładu (single/AKO) trafia do kodu silnika EV.
3. Monitor ryzyka limitów:
   - zaokrąglone stawki,
   - mieszanie z „normalnymi” zakładami,
   - rozkładanie zakładów na wiele kont.
