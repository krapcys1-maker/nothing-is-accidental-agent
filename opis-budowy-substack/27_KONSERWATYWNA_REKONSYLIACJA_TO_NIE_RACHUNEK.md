# Konserwatywna rekonsyliacja to nie rachunek

Najtrudniejszym wynikiem timeoutu nie jest błąd. Jest nim brak wiedzy, czy efekt zdążył wydarzyć się po drugiej stronie granicy.

W trzech historycznych próbach lokalny system zachował identity, moment przekroczenia external effect i maksymalną rezerwę, ale nie dostał usage ani jednoznacznego request ID. Panel providera pokazywał tylko koszt zagregowany. Taki ekran może potwierdzić, że konto ponosiło wydatki; nie mówi jednak, która część należała do konkretnego writera albo reviewera.

Dlatego `CONSERVATIVE_MAX_CHARGED` nie udaje rachunku. Faktyczny koszt nadal pozostaje nieznany. Właściciel mówi jedynie: dla bezpieczeństwa budżetu traktujemy całą zachowaną rezerwę jako wykorzystaną. Osobny ledger zapisuje kto, kiedy, dlaczego i dla jakiej dokładnie identity podjął tę decyzję. Nie dopisuje tokenów, nie tworzy provider request ID i nie zmienia starego timeoutu w sukces.

To rozróżnienie daje cztery zamiast jednej liczby: koszt rzeczywiście znany, koszt konserwatywnie przypisany, ekspozycję nadal nierozstrzygniętą oraz efektywny wydatek budżetowy. Na tymczasowej kopii trzy decyzje dawały odpowiednio `5.172339`, `0.738880`, `0.000000` i `5.911219 USD`.

Najważniejsza własność pozostaje negatywna: żaden stary request nie staje się retryable. Rekonsyliacja usuwa blokadę wynikającą z niepoliczonego ryzyka, ale nie usuwa historii niepewności.

Kod jest kandydatem do niezależnego review. Produkcja nadal stoi na schemacie `0039`, migracja `0040` nie została zastosowana, a system nie jest live-ready. Nie wykonano prawdziwej rekonsyliacji, requestu API ani publikacji.
