# Zmiany z analizy przyrostu (16.11.2026)

Źródło: niezależna analiza przyrostu subskrybentów (raport w `robocze/ANALIZA_PRZYROSTU_NIE_FABLE.md`, poza repozytorium).
Decyzja właściciela 16.11: „zobacz co warto i wdroż”, potem „nic nie odkładaj, wdrażaj”. Stała granica: konto pisze o AI.

## Najważniejsze ustalenia (cała historia, od 7.09)

- Zapisy przychodzą z cudzej publiczności: restacki i komentarze pod cudzymi notkami. Własne notki dały 3 przypisane zapisy na 181 notek.
- Restacki drugiego konta: 18 zapisów na 257 (7,0 na 100; 95%: 4,2–11,1). Nasze: 1 na 136 (0,74; 0,01–4,1). To jedyna różnica poza szumem.
- Komentarze pod artykułami: 0 zapisów na 247 i 0 odwiedzin profilu od 19.10. Pod notkami: 13 na 482 (2,7 na 100).
- Z cech stylu z zasięgiem notki idzie tylko długość (rho −0,24; −0,36 do −0,12). Trudność słów, liczby, nazwy i temat są bez związku.

## Co wdrożono

| zmiana | gdzie | jak oceniamy |
|---|---|---|
| E24 wzór restacka: połowa restacków jako własna mini-notka (3 zdania, do 75 słów) | `config.EKSPERYMENTY["wzor_restacka"]`, `prompts/restack_glos.md`, `stages.ocen_restack` | reguła w `docs/WZOR_RESTACKA_E24_2026-11-16.md` |
| Restacki bez konta siostrzanego (16 ze 170 szło do drugiego bota) | `browser.notka_konta_siostrzanego` | bez testu: to nie jest wzrost |
| Komentarze: pod notkami N miejsc, pod artykułami max(1, N//2) (było odwrotnie) | `run.przydzial_komentarzy` | odwiedziny profilu i zapisy z komentarzy na tydzień, 4 tygodnie wobec 4 poprzednich |
| E25 forma notki „trzy wiersze” (fakt, porównanie, stanowisko), 50/50 | `config.NOTE_FORMS["TRZY_WIERSZE"]`, `config.EKSPERYMENTY["forma_trzy_wiersze"]` | przyjąć, gdy iloraz wyświetleń po 72 h wobec tła tygodnia ≥ 1,3 z przedziałem 95% ponad 1, po ≥ 30 notkach na ramię; wykryje ok. +30% |
| Subskrypcje innych kont 1 → 3 dziennie | `config.RAMPA_AKTYWNOSCI` (stopień od 17.11), `SUBSKRYPCJE_DZIENNIE` | zapisy od kont zasubskrybowanych w poprzednich 14 dniach |
| Naprawa faktów w MYŚL: obalone twierdzenie wychodzi, nic nie dochodzi; ponowne sprawdzenie bez szukania | `stages.napraw_mysl` | odsetek MYŚL wychodzących z obalonym twierdzeniem (od 27.10 wyszła 1 taka MYŚL, 3.11) |
| Sprawdzanie faktów ocenia dopowiedzenia („quietly”, „placebo”) i przypisanie źródła („independent report”) | `prompts/weryfikacja.md` | odsetek naprawionych notek (było 19%) |
| Źródło pierwotne przed streszczeniem prasowym | `prompts/seria_lekka.md`, `prompts/przeslania.md` | czytanie ręczne |
| Rozkmina co 4 dni zamiast co 3 (koszt idzie na treści, które nie dają zapisów) | `config.ROZKMINA_CO_DNI` | koszt dobowy |

## Zbiorcza reguła z góry (cały pakiet)

Pakiet działa, jeśli w 8 tygodniach od 17.11 (do 11.01.2027) NIE ma co najmniej 40 zapisów brutto (wcześniej ok. 26 na 8 tygodni).
Przy 3,2 zapisu tygodniowo pojedynczej zmiany nie da się potwierdzić samymi zapisami, dlatego testy E24 i E25 stoją na
wyświetleniach, odpowiedziach i odwiedzinach profilu.

## Uwaga dla ocen trwających

Ocena krótszych notek i restacków 3–4 dziennie (27.11, `docs/ZMIANY_2026-11-13_KROTSZE_NOTKI_RESTACKI.md`) jest od 17.11
zamazana przez E24 (połowa restacków ma nowy wzór) i E25 (połowa notek ma nową formę). Porównywać tylko ramiona „off”.
