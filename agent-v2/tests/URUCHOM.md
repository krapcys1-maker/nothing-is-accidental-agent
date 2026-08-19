# Testy agenta

Do 2026-08-19 te pliki leżały w katalogu tymczasowym sesji, poza repozytorium.
Pięćset kilkadziesiąt asercji, których nikt poza mną nie mógł uruchomić i które
zniknęłyby przy pierwszym sprzątaniu `%TEMP%`. To był największy dług tego
projektu i dlatego stoją teraz tutaj.

## Jak uruchomić wszystkie

Z **korzenia repozytorium**, nie z tego katalogu — testy dopisują `agent-v2`
do ścieżki i wczytują moduły po nazwie:

```
for t in agent-v2/tests/test_*.py; do echo "$t"; python "$t"; done
```

Na Windowsie ustaw najpierw `PYTHONIOENCODING=utf-8`, bo konsola domyślnie
nie radzi sobie z polskimi znakami w wyniku.

## Czego wymagają

| test | wymaga |
|---|---|
| `test_artykul`, `test_integracja` | `playwright` i `trafilatura` — padają na komputerze bez nich |
| `test_czas` | prawdziwego `SIGTERM`, więc tylko Linux |
| `test_pobieranie` | sieci |
| reszta | niczego, chodzą wszędzie |

## Czego NIE uruchamiać bezmyślnie

**`test_integracja` odpala PŁATNY pełny przebieg dnia** z prawdziwymi
przerwami 45–90 minut między notkami. Przy starych odstępach był wykonalny,
teraz chodzi godzinami i pali pieniądze na API. Trzeba mu podmienić
`config.ODSTEPY`, tak jak podmienia `OKNO_PUBLIKACJI_ET`. **Do tego czasu
pełny przebieg dnia nie jest pokryty testem.**

## Zasada, która się tu sprawdziła

Test ma wykrywać **także stan sprzed naprawy**. Test, który tylko potwierdza,
że nowy kod robi to, co chciałem, potwierdza mój model problemu, a nie
rzeczywistość — i taki właśnie `test_sufity` przeszedł, podczas gdy przebieg
padał drugi raz z rzędu, bo mierzył miejsce na treść zamiast na rozumowanie.

Dlatego prawie każdy plik tutaj ma sekcję nazwaną wprost „kontrdowód".
