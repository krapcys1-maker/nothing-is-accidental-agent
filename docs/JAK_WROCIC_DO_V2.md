# Jak wrócić do działającego bota v2

**Zapisano:** 2026-08-25, przed przeróbką konta na wariant AI.

To jest stan bota, który **prowadził konto i działał**: 43/43 testów, timer
aktywny, publikował notki, komentarze, odpowiedzi i artykuły na Substacku
„Nothing Is Accidental".

## Co zostało zapisane i gdzie

**Kod — znacznik w historii, wypchnięty na GitHuba:**

```
v2-dziala-2026-08-25  ->  df3de64d81967864a2a373d78caabfecf66f1f10
```

Znacznik jest *anotowany* i niesie w opisie listę ostatnich napraw oraz znanych
otwartych spraw. Nie zniknie przy żadnym przestawianiu gałęzi.

**Stan — archiwum na serwerze:**

```
~/kopie-v2/stan-v2-20260825-0849.tar.gz     7,1 MB, 84 pliki
sha256 zaczyna się od: 949fde134974f4bc82c66f37
```

W środku: baza `agent.db` z całą historią przebiegów i kosztów, dziennik działań
(`dziennik.jsonl`), zużyte fakty, stan promocji artykułów, kopia listy
subskrybentów, wszystkie prompty i kod modułów.

**Czego w archiwum celowo NIE MA:** pliku sesji Substacka
(`storage-state-serwer.json`) ani `.env`. To sekrety — sesję odtwarza się
logowaniem, kluczy się nie kopiuje. Pierwsza wersja archiwum objęła sesję przez
zły wzorzec wykluczenia i została skasowana.

## Powrót — kod

Lokalnie:

```bash
git checkout v2-dziala-2026-08-25
```

Na serwerze:

```bash
cd ~/nothing-is-accidental-agent
git fetch --tags
git reset --hard v2-dziala-2026-08-25
bash agent-v2/wdroz.sh
```

`wdroz.sh` sam sprawdzi, czy wersja wstaje, i cofnie się, jeśli nie.

## Powrót — dane

Dane produkcji **zostają na miejscu** przy zwykłym powrocie kodu i zwykle nie
trzeba ich ruszać. Archiwum jest na wypadek, gdyby baza albo dziennik zostały
uszkodzone:

```bash
cd ~/nothing-is-accidental-agent
tar -xzf ~/kopie-v2/stan-v2-20260825-0849.tar.gz
```

**Uwaga:** to nadpisze bieżące `agent-v2/data/`. Przed rozpakowaniem zrób kopię
tego, co jest teraz — inaczej stracisz wszystko, co bot zrobił od 25 sierpnia.

## Co ta wersja miała nienaprawione

Warto o tym pamiętać, gdyby powrót miał być trwały:

- **Licznik wolumenów zaniża komentarze.** Komentowanie cudzych notek loguje się
  jako `odpowiedz` i ta kategoria nie ma normy, więc alarm pokazywał 46% przy
  realnych ~67%. To błąd pomiaru, nie działania.
- Wolumeny poniżej normy: notki 63%, polubienia 70%.
- **Brak pętli zwrotnej**: 71 zapisanych reakcji czytelników, których żaden kod
  nie czyta.
- **Obserwacje wycofane — i to było błędem, nie właściwością tej wersji.**
  Stało tu: „Substack zdjął przycisk «Follow» ze stron profilowych (sprawdzone
  na sześciu profilach, zero wystąpień w HTML)". Pomiar był prawdziwy, wniosek
  fałszywy: przycisk siedzi w menu pod kółkiem „…", które Substack rysuje
  dopiero po kliknięciu, więc w HTML zamkniętej strony go nie ma i być nie
  może. Ta wersja archiwum ma więc `FOLLOW_MIESIECZNIE = (0, 0)` i nie
  obserwuje nikogo; po powrocie do niej trzeba to odkręcić ręcznie —
  widełki `(30, 44)` plus droga przez menu w `browser.obserwuj_profil`.
  Pełny opis pomyłki: `docs/BLEDNY_WNIOSEK_O_OBSERWACJACH_2026-08-23.md`.

## Zasada

Znacznik i archiwum są **niezależne**: nawet gdyby serwer przepadł, kod stoi na
GitHubie; nawet gdyby repozytorium zostało przestawione, archiwum trzyma dane.
Żeby stracić jedno i drugie, musiałyby zawieść obie rzeczy naraz.
