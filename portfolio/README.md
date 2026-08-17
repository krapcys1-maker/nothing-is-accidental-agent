# Nothing Is Accidental — materiały do portfolio

Wszystko, czego potrzeba, żeby opisać ten projekt na stronie. Materiał jest
gotowy do przekazania agentowi budującemu stronę — nie wymaga dostępu do serwera
ani do kodu.

**Projekt:** autonomiczny agent prowadzący publikację na Substacku. Pisze notki,
komentuje u obcych autorów, odpowiada na reakcje, obserwuje nowych ludzi
i publikuje artykuły. Chodzi z harmonogramu na własnym serwerze, bez ani jednego
pytania do człowieka.

---

## Co gdzie leży

| plik | co to jest |
|---|---|
| **[PROJEKT.md](PROJEKT.md)** | **główny tekst na stronę** — historia, problemy, rozwiązania |
| [FUNKCJE.md](FUNKCJE.md) | wszystkie zdolności agenta, funkcja po funkcji |
| [JAK_DZIALA.md](JAK_DZIALA.md) | warstwa techniczna: przebieg dnia, baza, odporność na awarie |
| [LICZBY.md](LICZBY.md) | wszystkie liczby, gotowe na kafelki |
| [BRIEF_DLA_AGENTA_STRONY.md](BRIEF_DLA_AGENTA_STRONY.md) | **instrukcja dla agenta budującego stronę** |
| [zrzuty/](zrzuty/) | cztery zrzuty z żywego konta + diagram + gotowe podpisy |
| [przyklady/tresci.md](przyklady/tresci.md) | prawdziwe treści napisane przez agenta |
| [przyklady/przebieg-dnia.log](przyklady/przebieg-dnia.log) | pełny zapis jednego przebiegu, 278 linii |

---

## Skrót, jeśli masz minutę

**Poprzednia wersja tego agenta:** 71 598 linii Pythona, 2 817 testów, 42
migracje schematu. Wynik: **dwa artykuły**.

**Ta wersja:** 6 526 linii, 10 plików, 4 tabele, zero migracji. Wynik: **konto
działające codziennie bez człowieka**.

Budżet złożoności ustalono **przed** napisaniem pierwszej linijki i nie był
negocjowalny.

---

## Trzy rzeczy, które warto zrozumieć

**Rzeczywistość jest źródłem prawdy.** Kliknięcie przycisku nie jest dowodem
publikacji. Po każdym działaniu agent pyta Substacka, czy treść naprawdę tam
wisi. Dzięki temu restart w połowie przebiegu nie wysyła tej samej notki drugi
raz.

**Milczenie jest domyślne.** Agent komentuje tylko wtedy, gdy ma coś własnego do
dodania — i regularnie odmawia, uzasadniając dlaczego.

**Nie wyglądać jak automat to był najtrudniejszy wymóg**, bo karą nie jest
komunikat o błędzie, tylko cichy spadek zasięgu, którego agent nigdy nie zauważy.
Stąd widełki zamiast stałych liczb, odstępy dobrane do czynności i zakaz powrotu
pod ten sam tekst.

---

## Liczby na kafelki

| | |
|---|---|
| kod | **6 526 linii** w 10 plikach |
| testy | **139 sprawdzeń**, każde z kontrdowodem |
| koszt | **~0,20 USD** za przebieg, 3 dziennie |
| zasięg | **18 komentarzy u 18 różnych publikacji**, zero powtórek |
| odzew | **18 osób** zareagowało na treści agenta |

---

## Zasada, której trzeba pilnować

Projekt może być opisany jawnie, z nazwą publikacji. **Sekrety nie.** Żadnych
kluczy API, adresu serwera, nazw użytkowników ani zawartości plików
konfiguracyjnych. Materiały w tym folderze zostały pod tym kątem sprawdzone
i są czyste.
