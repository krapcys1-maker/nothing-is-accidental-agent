# E-011 — transakcyjny zapis artykułu N-010

**Data:** 2026-08-21  
**Zakres:** wyłącznie V3, fixture i tymczasowe SQLite/katalogi  
**Sieć/API/Substack:** nie użyto  
**Koszt:** 0 USD  
**Status:** `FIXED_OFFLINE; POWER_LOSS_NOT_PROVEN`

## 1. Pytanie badawcze

Czy zapis pliku artykułu, pliku uwag, rekordu `articles`, `content_items`,
rewizji oraz finalnego grafu pochodzenia może po awarii pozostawić tylko jeden
z dwóch stanów: kompletny artefakt albo jawnie odzyskiwalny intent bez
osieroconych danych?

## 2. Hipoteza i kryterium obalenia

**H-011:** przygotowanie plików pod hashami, trwały intent `PREPARED`, jedna
transakcja SQLite obejmująca wszystkie rekordy i atomowe `os.replace`, a po
restarcie deterministyczna rekoncyliacja, usuwają osiągalne stany częściowe.

Hipotezę obala którekolwiek z poniższych:

- finalny `.md` lub `.uwagi.md` bez `articles` po zwykłym wyjątku;
- `articles` bez finalnego pliku o zapisanym SHA-256;
- `content_items`, rewizja albo graf bez właściwego `article_id`;
- ponowienie tworzące drugi artykuł dla tego samego artefaktu;
- recovery usuwające plik obcy albo zmieniony po zapisie;
- brak wykrycia niezgodnego hasha ukończonego artefaktu.

## 3. Stan przed i kontrdowód T-105

Pierwsza wersja `test_transactional_article_save.py` instalowała trigger
SQLite `BEFORE INSERT ON articles`, który zawsze przerywał insert. Dawne
`stages.save()` zdążyło wcześniej utworzyć:

- `0001-transactional-fixture.md`;
- `0001-transactional-fixture.uwagi.md`.

Tabela `articles` miała równocześnie zero rekordów. To dokładny stan „pliki bez
rekordu”, a nie hipotetyczny skutek inspekcji kodu.

Hashe wejściowe zapisane przed zmianą:

| Plik | SHA-256 |
|---|---|
| `stages.py` | `E9EA18FBBC38AC7A7BFA07B980061EB99AE91AC215B6FF24FE2C3D94C86E7D73` |
| `editorial.py` | `B84CDDC963EAB4456BE5BBD6FC030307220EAADAE307330B5660657B118253DD` |
| `provenance.py` | `473D6D97D425A665BBD9DD1AA5298D729C58DCCA07B6B794FF2A151D65FD36F5` |
| `db.py` | `6994BDEBAB4D91B09F98F9C25ACD2E3D0426604E9AD81A4462454F9813D49D5E` |

Hash wejściowy `run.py` nie został utrwalony przed pierwszą zmianą N-010. Nie
rekonstruowano go z brudnego drzewa, bo dawałoby to pozorną precyzję.

## 4. Zmiana

### 4.1. Tożsamość i intent

`articles` dostało `artifact_key`, ścieżki i SHA-256 obu artefaktów. Nowa tabela
`article_save_intents` przechowuje targety, pliki przygotowane, hashe i stan
`PREPARED / COMPLETE / ROLLED_BACK / BROKEN`. Częściowy unikalny indeks
`articles.artifact_key` daje idempotencję ponowienia.

### 4.2. Prepare, transakcja i commit

`stages.save()`:

1. rekoncyliuje wcześniejsze intenty;
2. renderuje dokładne bajty i SHA-256;
3. zapisuje oraz `fsync`-uje pliki `.save-transactions/*.tmp`;
4. utrwala intent `PREPARED`;
5. otwiera `BEGIN IMMEDIATE`;
6. tworzy `articles`, graf provenance, `content_items` i rewizje z tym samym
   `article_id`, bez commitów pośrednich;
7. wykonuje atomowe podmiany plików;
8. ustawia intent `COMPLETE` i zatwierdza SQLite.

`run.py` nie zapisuje już rewizji przed istnieniem artykułu. Przekazuje rekordy
rewizji do `save()`, gdzie powstają w tej samej transakcji.

### 4.3. Recovery

`recover_article_saves()` rozpoznaje intenty po restarcie. Usuwa wyłącznie
pliki należące do intentu i zgodne z jego hashem. Obcego albo zmienionego pliku
nie usuwa: oznacza intent `BROKEN` i zatrzymuje pracę. Ukończony intent jest
ponownie weryfikowany względem rekordu i finalnych hashy.

## 5. Fault injection i wyniki

T-106 wykonał 7 metod, w tym dziesięć punktów awarii przed commitem:

`after_article_prepare`, `after_notes_prepare`, `after_intent_commit`,
`after_article_insert`, `after_provenance`, `after_content_item`,
`after_revisions`, `after_article_replace`, `after_notes_replace`,
`before_commit`.

Wynik każdego punktu: brak artykułu, `content_items`, rewizji i grafu; brak
finalnych plików i tempów; intent nie istnieje albo jest `ROLLED_BACK`.

Dodatkowo:

- poprawny zapis jest idempotentny i ma dokładnie jeden artykuł oraz rewizję;
- rewizja i `content_items` mają właściwe `article_id`;
- wadliwy graf cofa wszystko;
- symulowana śmierć procesu po pierwszym replace zostawia stan, który restart
  usuwa bez osierocenia;
- symulowana śmierć po commicie jest rozpoznawana jako `COMPLETE`;
- ręczna zmiana finalnego pliku daje `BROKEN`, a recovery nie kasuje zmiany.

T-107: replay 7/7, provenance 19/19, zapis wywołań 16/16, artykuł 9/9 i
kontrakty 11/11 PASS. T-109: 48/48 bezpiecznych plików PASS w 46,683 s;
`data/` byte-identical. T-108 zachowuje nieważną próbę regresji:
`unittest discover` zinterpretował prawidłowe `SystemExit(0)` skryptowego
`test_artykul.py` jako błąd loadera; po przejściu na bezpośrednie uruchamianie
każdego pliku wynik był zielony.

## 6. Hashe po zmianie N-010

| Plik | SHA-256 |
|---|---|
| `db.py` | `F9AC410D4D123A6A118997C149D22B5BC0ED549C8F3894ACB7C03475C45606C3` |
| `stages.py` | `563BB308E99103B3B6479EEE4177C136ED1BBA88A9CBE518B5FBC707B150E931` |
| `editorial.py` | `7D7D73DED8D3DA6738CE0B83F55112F0C0185CB662398BBFCED6AE02F9626323` |
| `run.py` | `0A988E91058E8D67564FA10D6FA3D275A32EC42CA8DC87D769817DA634591460` |
| `tests/test_transactional_article_save.py` | `8C10C74D21294046A7D4CCE6D6C235B85F23485F4D31208A4099D51D8294687C` |

## 7. Wniosek i ograniczenia

H-011 nie została obalona w badanym modelu awarii. A-013 i A-055 są
`FIXED_OFFLINE`. A-041 jest naprawione dla atomu artykułu, ale pozostałe JSON-y,
ledger platformy i pomiar nadal są osobnymi transakcjami. A-042 jest tylko
częściowo naprawione: migracja jest addytywna, nadal brak pełnego numerowanego
systemu migracji i globalnych kluczy obcych.

Dowód nie symuluje zaniku zasilania pomiędzy `os.replace` a utrwaleniem wpisu
katalogowego przez system plików. Pliki są `fsync`-owane, lecz Windows nie daje
tu przenośnej gwarancji `fsync` katalogu. Status nie jest więc `CLOSED`, tylko
`FIXED_OFFLINE; POWER_LOSS_NOT_PROVEN`.
