# Persona „Marit” (etap 1: wdrożenie ciemne), 2.11.2026

Zlecenie właściciela (1-2.11): konto NIE ma mieć osobowość z upodobaniami, własnymi (także błędnymi) zdaniami i zmyśloną biografią, bo to nośnik badania pamięci LLM (kanon z datami, dopowiedzenia, zmiana zdania pod wpływem zdarzeń). Ustalenia z sesją badawczą „Pamięć LLM” (tablica: N-020 do N-033, P-036): publiczne bio ujawnia, że konto to eksperyment prowadzony przez bota, a biografia jest zmyślona (wstawione 2.11, N-024); persona sama o tym nie wie (założenie badawcze), więc ochrona czytelników siedzi w kodzie POZA nią. **Data włączenia na żywo: patrz „Wdrożenie” na końcu.**

## Co jest w tej zmianie

- `persona.py` (nowy moduł) i kanon `persona/marit_v0.md` (po angielsku, gotowy do promptu: biografia, twarde fakty z datami, charakter i głos, upodobania, osiem opinii), zasiewy notek z życia `persona/zasiewy.json` (10, część z oknem dat), prompt `prompts/Notka_zycie.md`.
- **Bramka na bio** `bio_ok()`: persona działa tylko, gdy publiczne API profilu (`substack.com/api/v1/user/<handle>/public_profile`) zawiera zdanie „written by an AI bot”. Błąd sieci albo brak zdania = wyłączona (fail-closed). Wynik pamiętany 1 h (pozytywny) lub 5 min (negatywny).
- **Filtr wejścia** `pomin_cel()`: odpowiedź na nasz komentarz, która pyta wprost o bycie botem/AI/człowiekiem/maszyną/eksperyment albo prosi o spotkanie, telefon, zdjęcie, jest pomijana bez odpowiedzi (decyzja właściciela 2.11: „niech olewa takie pytania i nie odpowiada wcale”). W logu persony tylko kategoria i długość, bez treści. Wpięty w `run.py` przy sicie odpowiedzi.
- **Filtr wyjścia** `wyjscie_ok()` (tani, wzorcowy, bez klasyfikatora LLM): tekst z jawnym „I am human” albo „I am not a bot” nie wychodzi; wpięty w jednym miejscu przy publikacji tekstu w `browser.py` (notka, komentarz, odpowiedź, odpowiedź pod artykułem). To siatka; główna ochrona to filtr wejścia.
- **Blok persony w promptach**: `stages._prompt` dokłada go PO wspólnym głosie (lub przed zadaniem, gdy prompt nie ma wspólnego głosu), tylko dla plików z `config.PERSONA_PROMPTY`, tylko gdy flaga i bramka na bio. Zawiera datę „dziś” i regułę zapisu (brzmienie z testu drugiej sesji).
- **Pas notek z życia** (`persona.notka_zycia` + blok w `run.notki`): jedna notka na dobę, typ i forma `ZYCIE`, zasiew najdawniej niewykorzystany, poza dzienną normą notek; stan i dopowiedzenia (`data/persona_dopowiedzenia.jsonl`, źródło „improwizacja”) zapisywane dopiero po POTWIERDZONEJ publikacji.
- Flagi w `config.py`: `PERSONA`, `PERSONA_ZYCIE`, `PERSONA_PROMPTY`, `PERSONA_HANDLE`. **Wszystkie wyłączone**: przy `PERSONA = False` nic w żadnym prompcie ani publikacji się nie zmienia (test).

## Czego NIE ma (celowo)

- Żadnych zakazów co do opinii, plotek ze źródłem ani życia codziennego persony. Granice to wyłącznie trzy ustalone (ujawnienie w bio, brak twierdzeń o byciu człowiekiem i zaprzeczania botowi, brak zmyślonych FAKTÓW o prawdziwych nazwanych firmach, osobach i projektach; ten ostatni punkt siedzi w karcie, nie w kodzie). `DOKTRYNA.md` §2 opisuje to jako wąską czwartą siatkę.
- Persony w komentarzach i artykułach (etap 2, po testach stabilności i uległości wobec nacisku drugiej sesji), modułu pamięci drugiej sesji (wersja 0.2.0 czeka na osobne ZAMIERZAM), embeddera (nie jest potrzebny, P-035), wymiany promptów z zakazami wymyślonej biografii (dotyczy etapu 2; etap 1 używa osobnego promptu `Notka_zycie.md`, a istniejące zostają nietknięte).
- Zmiany ustawienia wykrywania AI (zostaje wyłączone, decyzja właściciela).

## Włączanie etapami (po wdrożeniu ciemnym)

1. **Etap 1a (suchy przebieg):** `PERSONA = True`, `PERSONA_ZYCIE = True`, `PERSONA_PROMPTY = ("Notka_zycie.md",)` na serwerze, przebieg `--poza-oknem` bez `--wyslij`: tekst notki z życia na ekranie, nic nie wychodzi. Ocena tekstu przeze mnie (czytam, nie liczę testów).
2. **Etap 1b (żywy, wąski):** ta sama konfiguracja z publikacją: jedna notka z życia na dobę. Kontrola po każdym przebiegu: filtry (log persony), zgodność tekstu publicznego z dziennikiem, wygląd notki.
3. **Etap 2 (po P4-P6 drugiej sesji):** komentarze i odpowiedzi (wymaga zmiany zakazów wymyślonej biografii w `glos_krotkich.md` i `komentarz_b.md`, osobnych wariantów promptów albo edycji), potem artykuły (notka redaktorki na końcu).

## Dowody i ograniczenia

- `tests/test_persona.py` (54 sprawdzenia, bez pytesta, bez sieci i modelu); mutacje `robocze/mutacje_persona.py`: 29 mutantów, wszystkie zabite przy zielonej bazie.
- Filtr wejścia zmierzony na 60 pozycjach P7 drugiej sesji: 36 z 36 pytań o naturę (direct/accusation/pressure) pominiętych, 0 z 12 niewinnych; filtr wyjścia: 20 z 20 jawnych twierdzeń zablokowanych, 0 z 20 fałszywych alarmów. **Liczby zawyżone**, bo wzorce były strojone na tych samych pozycjach; czysty pomiar to ślepy zbiór drugiej sesji (plik `nature_filter_v0.py`, sha256 d722096351d4daf6a4c53ed8d33fa56d282072a853ab61691e6f7a8e2690d92a). Wzorce filtra wejścia nie są zmieniane do czasu tego pomiaru.
- Wyniki testów persony drugiej sesji (jedna persona, jeden model, jedno uruchomienie): fakty z rdzenia 0,95; przeciek życia do zadań nieosobistych 1 z 45 bez reguły i 0 z 45 z regułą; zgodność dopowiedzeń z zapisem 0,73 (stąd reguła zapisu); na pytania wprost o naturę konta persona bez instrukcji twierdziła lub zaprzeczała w 39% (stąd filtr wejścia).
- Filtr wejścia nie zna kontekstu: może pominąć niewinne pytanie, które brzmi jak pytanie o naturę konta; koszt to pominięta odpowiedź, nie błąd. Dowody tego na żywych danych dopiero po wdrożeniu (log persony).

## Wycofanie

`config.PERSONA = False` (jedna linia, bez restartu bazy), albo `git reset --hard <poprzednia wersja>`. Dane persony (`data/persona_log.jsonl`, `data/persona_dopowiedzenia.jsonl`) są osobnymi plikami i niczego innego nie dotyczą.

## Poprawki 13.11.2026 (przed wdrożeniem ciemnym)

Decyzja właściciela 13.11: „ok to wprowadź to”.

- **Błędy z przeglądu:** `PERSONA_HANDLE = SUBSTACK_HANDLE` (druga kopia bota czyta własny profil); pas z życia jest osobnym blokiem przebiegu `zycie()` po `notki()`, więc pętla notek znów kończy się zwrotem faktów do puli, a wyjątek w pasie nie gubi zwrotu.
- **Pamięć z zapisu:** każda nowa notka z życia dostaje w prompcie ostatnie 8 opublikowanych dopowiedzeń z datami (`persona.zapis`, `blok_zapisu`). Powód: test P2 drugiej sesji, sama reguła „trzymaj się zapisu” dawała 0,73–0,76 przy progu 0,90, bo persona nie widziała, co już powiedziała.
- **Pomiar spójności (nie bramka):** `persona.sprawdz_spojnosc` (Flash z myśleniem, etap `persona_spojnosc`) porównuje notkę z kanonem i zapisem; sprzeczność liczy się tylko z dosłownym cytatem z notki (sprawdza kod). Wynik trafia do `persona_log.jsonl` (`zycie_spojnosc`, same liczby) i do dopowiedzenia. Notka wychodzi niezależnie od wyniku.
- **Filtr wejścia v1:** gdy wzorce v0 milczą, rozstrzyga tani klasyfikator (`persona.natura_klasyfikator`, etap `persona_natura`, bez myślenia), fail-closed, decyzje pamiętane po skrócie tekstu (`persona_natura_cache.json`). Wzorców v0 nie stroiłem pod ślepy zbiór drugiej sesji; v1 mierzy ona na NOWYM zbiorze.
- **Kanały kosztu:** blok `zycie` na kanale `notka`, klasyfikator na kanale `odpowiedz`.
- **Dowody:** `tests/test_persona.py` 75/0; mutacje `robocze/mutacje_persona.py` 39/39 zabitych; testy kanałów, zwrotu faktów i drugiego konta bez nowych czerwonych względem bazy.
