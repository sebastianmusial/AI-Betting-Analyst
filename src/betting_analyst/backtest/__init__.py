"""Walk-forward backtest (F2, ADR 0015): czy po polskim podatku istnieje przewaga.

Zasady:
- kurs zagrania i prawdopodobieństwo fair tylko z danych dostępnych w chwili decyzji
  (Pinnacle przedmeczowy PSH…, Avg/Max z tego samego momentu), zamknięcie PSCH… wyłącznie do CLV;
- modele statystyczne (Dixon-Coles) dopasowywane tylko na meczach rozegranych przed datą decyzji;
- EV, podatek i Kelly z `decision/ev.py` (ADR 0003, 0014).
"""
