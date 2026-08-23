# Testy agenta

Do 2026-08-19 te pliki leżały w katalogu tymczasowym sesji, poza repozytorium.
Pięćset kilkadziesiąt asercji, których nikt poza mną nie mógł uruchomić i które
zniknęłyby przy pierwszym sprzątaniu `%TEMP%`. To był największy dług tego
projektu i dlatego stoją teraz tutaj.

## Jak uruchomić wszystkie

Z **korzenia repozytorium**, nie z tego katalogu — testy dopisują `agent-v3`
do ścieżki i wczytują moduły po nazwie:

```
for t in agent-v3/tests/test_*.py; do echo "$t"; python "$t"; done
```

Ta pętla jest **darmowa**. Testy, które kosztują pieniądze, leżą osobno
w `platne/` i nie łapie ich `test_*.py` z tego katalogu — patrz
`platne/PRZECZYTAJ.md`.

Na Windowsie ustaw najpierw `PYTHONIOENCODING=utf-8`, bo konsola domyślnie
nie radzi sobie z polskimi znakami w wyniku.

## Czego wymagają

| test | wymaga |
|---|---|
| `test_artykul` | `playwright` i `trafilatura` — pada na komputerze bez nich |
| `test_czas` | prawdziwego `SIGTERM`, więc tylko Linux |
| `test_pobieranie` | atrap transportu; nie wykonuje prawdziwej sieci |
| reszta | niczego, chodzą wszędzie |

## Testy płatne

Jedenaście skryptów leży w `platne/`. Nie wchodzą do zwykłej regresji. Tylko
`test_provenance_live.py` ma aktualny kontrolowany harness; reszta wymaga przed
ponownym użyciem wspólnego preflightu, tymczasowej bazy, planu kosztu i
maszynowego kryterium wyniku. Szczegóły: `platne/PRZECZYTAJ.md`.

## Zasada, która się tu sprawdziła

Test ma wykrywać **także stan sprzed naprawy**. Test, który tylko potwierdza,
że nowy kod robi to, co chciałem, potwierdza mój model problemu, a nie
rzeczywistość — i taki właśnie `test_sufity` przeszedł, podczas gdy przebieg
padał drugi raz z rzędu, bo mierzył miejsce na treść zamiast na rozumowanie.

Dlatego prawie każdy plik tutaj ma sekcję nazwaną wprost „kontrdowód".
