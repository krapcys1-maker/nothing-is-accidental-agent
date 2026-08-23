# N-020 — atomowa rezerwacja kosztu modelu

- **Status:** `FIXED_OFFLINE; LIVE_REPLAY_OPEN`
- **Ustalenie:** A-095
- **Dowód:** T-079, ekspozycja 0,50 USD przy limicie 0,25 USD

## Hipoteza

Jedna transakcja `BEGIN IMMEDIATE` obejmująca sprawdzenie nierozliczonego
providera, limitu run/day/month, wyliczenie wolnej kwoty i insert `RESERVED`
uniemożliwi nadsubskrypcję także przy wielu procesach.

## Reuse

Zachować `calls.RESERVED/KNOWN/UNKNOWN`, `financial_exposure()` i rekoncyliację
N-017. Zastąpić tylko rozdzielone check-and-reserve jedną operacją DB.

## Testy wymagane

- dwa procesy na jednym limicie: dokładnie jedna rezerwacja;
- osobne runy nadal respektują limit dnia i miesiąca;
- provider z UNKNOWN blokuje nowe rezerwacje atomowo;
- rollback wyjątku nie zostawia martwego `RESERVED`;
- obraz nie przekracza pozostałej dokładnej ceny.

## Kryterium końca

Suma znanego kosztu i aktywnych rezerwacji nigdy nie przekracza żadnego
obowiązującego limitu, niezależnie od kolejności procesów.

## Wynik E-009

`db.reserve_model_budget()` wykonuje sprawdzenie dostawcy, run/day/month,
obliczenie salda i `INSERT RESERVED` pod jednym `BEGIN IMMEDIATE`. Runtime
tekstu i obrazu nie używa już rozdzielonego `reserve_call()`.

- T-092: stary mechanizm ponownie osiągnął 0,50 USD przy limicie 0,25 USD;
- T-093: test celu 7/7 PASS;
- T-095: testy sąsiednie 14/14, 2/2, 11/11 i 4/4 PASS;
- T-096: pełna regresja 46/46 plików, `data/` bez zmiany hashy.

Dowód obejmuje lokalne SQLite i fixture. Rzeczywista rezerwacja, dispatch oraz
rekoncyliacja dostawcy pozostają do kontrolowanego live replayu N-004.
Pełny raport: `../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-009_ATOMOWA_REZERWACJA_KOSZTU_MODELU.md`.
