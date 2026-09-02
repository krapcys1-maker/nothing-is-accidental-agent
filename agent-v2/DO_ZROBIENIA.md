# Rzeczy do zrobienia

Jedno miejsce, żeby nie były rozsypane po trzech. Uszeregowane wagą, nie
kolejnością znalezienia.

**Skąd to jest:** audyt zestawu testów z 2 września 2026 — agent uruchomił
wszystkie 111 plików i porównał odciski wszystkich 68 plików w `agent-v2/data/`
przed i po. Szesnaście znalezisk, wszystkie zmierzone, wszystkie z numerami
linii. Jedno naprawione tego samego dnia (poz. 0).

**Czego ta lista NIE zawiera** — żeby nie powstała czwarta kopia tych samych
zapisów, bo to w tym repozytorium osobna klasa błędu:

- otwarte długi doktryny → `agent-v2/DOKTRYNA.md`, sekcja „Rozbieżności doktryny z kodem"
- płatne testy bramki faktów (kalibracja szumu, zbiór regresyjny) → `docs/PAMIEC_I_NAPRAWA_2026-09-01.md`
- pamięć / warstwa oszacowań → gałąź `pamiec/oszacowania`, niewdrożona

---

## 0. ZROBIONE 2026-09-02 — testy dopisywały atrapy do produkcji

`test_wybor_tematu.py` wołał `pick_topic` → `zapisz_przegranych` → produkcyjny
`data/tematy_przegrane.json`. Na serwerze **294 z 400 wpisów było atrapami**.
Zamknięte na poziomie klasy: `config.W_TESCIE` + odmowa w `zapisz_przegranych`.
Zweryfikowane odciskiem całego katalogu: przed 1 plik na 68, po **zero**.

---

## 1. MARTWA FUNKCJA NA PRODUKCJI — `co_dodamy` nigdy nie dociera do modelu

**To jedyna pozycja, która nie jest usterką testu, tylko usterką agenta.**

`wybierz_cele` zapisuje przy każdym przyjętym celu `co_dodamy` — notatkę modelu
o tym, co warto dodać do tego wpisu (`stages.py:1089`). `comment_on` to czyta
i wkleja do promptu (`stages.py:3771`, `:3779`). Ale `run.py` przekazuje jako
`post` **inny słownik**:

- `run.py:1422` — `strony[0]`, czyli pobraną stronę z `read_pages`
- `run.py:1527` — świeżo sklecony `{title, text, author, url}`

`grep -c co_dodamy agent-v2/run.py` → **0**. Model wymyśla, po co komentuje ten
wpis, zapisujemy to do dziennika, i nigdy mu tego nie podajemy.

**Zrobione, gdy:** oba wywołania przekazują `co_dodamy` z `cel`, a
`test_cel_i_tik_w_prompcie.py:172` ma zamiast `print`-a asercję
`sprawdz("run.py przekazuje co_dodamy", "co_dodamy" in _run)`.

**Uwaga:** to zmienia treść promptu komentarza, czyli jakość wyjścia. Nie jest
to poprawka „przy okazji" — wymaga świadomej decyzji i żywego przebiegu.

---

## 2. Najdroższa wada ma test po napisie w oknie 1800 znaków

`test_okno_publikacji.py:93-100` tnie `run.py` na sztywne okno i orzeka
negatywnie: `'na_teraz["komentarze"] = 0' not in blok`.

Ta wada **blokowała jeden z pięciu przebiegów CODZIENNIE** (docstring, linie
17-22) — najdroższa z całej listy. Wystarczy zapisać ją `na_teraz['komentarze']=0`,
pętlą po kluczach albo przesunąć kod o 1800 znaków i test milczy.

**Zrobione, gdy:** sekcja 4 mierzy zachowanie tak, jak sekcje 1-3 tego samego
pliku — podstawiony zegar, sprawdzenie, że `na_teraz["komentarze"]` jest dodatnie.

---

## 3. Asercja pilnuje KOMENTARZA, a nie osłony artykułu

`test_obietnice_bez_pokrycia.py:179` — `"NIGDY nie zatrzymuje" in run_src`.
Jedyne wystąpienie tego napisu to **komentarz** w `run.py:2605`; wywołanie
`stages.grafika` stoi linijkę niżej.

Można usunąć osłonę i zostawić komentarz — test zostanie zielony, a padnięta
grafika zabije artykuł.

**Zrobione, gdy:** test podstawia `stages.grafika` rzucającą wyjątek i sprawdza,
że artykuł mimo to powstaje.

---

## 4. Test podłóg na serwerze mierzy coś innego niż lokalnie

`test_podlogi_playbook.py:41-47` szuka prawdziwego artykułu 0025 w
`agent-v2/data/articles/`. Katalog jest w `.gitignore:99`, więc **na świeżym
klonie i na serwerze pliku nie ma** — a wtedy test po cichu podstawia wbudowane
wycinki i dalej drukuje same OK.

Docstring mówi: „każda nowa podłoga MUSI się na nim zapalić. Jeśli któraś
milczy, to znaczy, że mierzy coś innego, niż myślę". Fallback dokładnie tego
zakazu nie egzekwuje.

**Zrobione, gdy:** albo wycinki 0025 wchodzą do repozytorium jako materiał
dowodowy, albo brak pliku **oblewa** test zamiast drukować notatkę.

---

## 5. Cztery pliki omijają prawdziwy `parse_json`

Podmieniają nie tylko `llm.call`, ale też `llm.parse_json` na lambdę ignorującą
`raw` — czyli omijają jedyną funkcję tłumaczącą odpowiedź modelu na kształt
oczekiwany przez kod (`llm.py:706`, 30 linii obsługi prozy wokół JSON-a, której
własny docstring podaje koszt awarii: „dwadzieścia wyszukiwań i 0,13 USD, po
czym oddało zero").

- `test_cel_i_tik_w_prompcie.py:75, :109, :147`
- `test_wybor_odpowiedzi.py:164-166`
- `test_podlogi_z_pamieci.py:85-90`

**Zrobione, gdy:** podmieniają tylko `call` i oddają `json.dumps({...})` — wzorzec
już działa w `test_bramka_banku.py:66` i `test_pas_wydarzen.py:94`.

---

## 6. Siedem asercji po treści źródła, w tym dwie kłamiące etykietą

Każda przeżyje przeniesienie zachowania do martwej gałęzi i każda oblewa przy
kosmetycznym refaktorze:

| plik:linia | co pilnuje |
|---|---|
| `test_martwe_sygnaly.py:265` | `"pora_na_publikacje()" in reszta` — **etykieta mówi „REALNIE WOŁANE", warunek to grep** |
| `test_martwe_sygnaly.py:326` | `"_stale_sygnaly(topics" in st_src` — to samo |
| `test_pole_komentarza.py:217` | `"pole.click(timeout=8_000)"` — `8000` zamiast `8_000` oblewa bez zmiany zachowania |
| `test_stawka.py:308` | cała linia `stages.py:5337` |
| `test_czas.py:73` | `"_KONIEC_CZASU = time.time() + max("` |
| `test_glebokosc.py:88` | `"stages.write(conn, run_id, card, glebokosc)"` |
| `test_indeks_kandydatow.py:159` | `"dopisz_kandydatow(fakty)"` |

**Zrobione, gdy:** używają wzorca, który w repozytorium już jest —
`test_waga_artykulu.py:178-184` pyta o **drzewo składni**, a
`test_generatory.py:229-249` czyta listę pól z AST wywołania `_prompt`
i porównuje z listą pól z pliku promptu.

---

## 7. Dwie asercje trafiają w zupełnie inny tekst

- `test_kotwica_w_kanalach.py:131` — „ale NIE kasujemy tematów" spełnione przez
  **docstring innej funkcji** (`stages.py:1688`, o faktach o zdarzeniach).
  `grep -ic "nie kasujemy" stages.py` = 0.
- `test_kotwica_w_kanalach.py:123` — „skaut liczy udział z kanałów" trafia
  w `print` z **etapu ciekawostek** (`stages.py:1418`), nie ze skauta
  (`stages.py:5014`). Usunięcie pomiaru ze skauta nie oblewa testu.

**Zrobione, gdy:** obie mierzą wywołanie — skaut dostaje listę tematów poniżej
progu i sprawdzamy, że **wszystkie** wracają.

---

## 8. Dwa testy przybite do wcięcia i do sztywnego okna

- `test_komentarz_potwierdzony.py:544-558` — sekcja 9: dwa gołe identyfikatory
  w `ZRODLO` (spełnione też przez komentarz) plus `index()` z 16 spacjami
  wcięcia wpisanymi w asercję. Sekcje 1-8 tego pliku są mocne. **Skasować
  sekcję 9**, tak jak skasowano sekcję 6 w `test_podlogi_z_pamieci.py:186`.
- `test_slad_przebiegu.py:131` — okno 2600 znaków od `def rytm(`, kończące się
  w połowie funkcji. Dziś działa przypadkiem, bo `return False` jest jedno.

---

## 9. Drobne, ale zawyżają licznik

- `test_pobieranie.py:95` i `test_jednostki_systemd.py:57` — `sprawdz(nazwa, True)`
  poza blokiem `except`. **Nie mogą oblać nigdy.** Zamienić na `print` albo dopisać
  realny warunek.
- `test_pisarz_zakazy.py:116` — sprawdza istnienie **komentarza** w `config.py`.
  To test dokumentacji podszyty pod test kodu. Zostawić, ale nazwać wprost.
- Bramka „PRODUKCJA" drukuje „bez zmian" także dla plików, których **w ogóle nie
  ma** (`odcisk` oddaje wtedy „brak", a „brak" == „brak"). Mechanizm jest
  poprawny, ale wiersz czyta się jak potwierdzenie ochrony, której nie ma.
  Drukować „nie istniał i nie istnieje", jak robi `test_ratunek_tekstu.py`.
- `test_bank_notek.py:5` i `test_indeks_kandydatow.py:19` przestawiają
  `config.DATA_DIR` globalnie i nie cofają. Przy uruchamianiu pętlą (proces na
  plik) to martwe; ożywa dla czegokolwiek, co ładuje dwa moduły naraz.
  Przywracać w `finally`, jak `test_budzety_dzienne.py:122`.

---

## Zasada, która z tego wynika

Większość tych pozycji to jedna wada w wielu przebraniach: **asercja po treści
źródła zamiast po zachowaniu**. Pilnuje kształtu kodu, nie tego, co kod robi —
więc przeżywa przeniesienie zachowania do martwej gałęzi i umiera przy zmianie
wcięcia. Nowe testy w tym repozytorium tego nie robią; te są starsze.

Gdy wybór stoi między „grep w źródle" a niczym, lepszy jest **AST** (jak
`test_waga_artykulu.py`) albo **uruchomienie z atrapą i policzenie wywołań**
(jak `test_regula_naprawy.py`).
