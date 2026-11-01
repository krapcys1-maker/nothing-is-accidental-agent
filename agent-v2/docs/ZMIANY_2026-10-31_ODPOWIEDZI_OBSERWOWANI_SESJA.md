# Trzy zmiany z 31.10.2026: odpowiedzi pod cudzymi notkami, pamięć obserwowanych, alarm sesji

Zlecenie właściciela („ok zrób to”) po analizie z 29–30.10, która wykazała trzy rzeczy do naprawy w NIE. Każda ma test z mutacjami
(13 + 9 + 14 mutacji, wszystkie wykrywane) i dowód z danych produkcji. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

## 1. Odpowiedzi na nasze komentarze pod CUDZYMI NOTKAMI (`note_reply`)

**Luka.** `browser.odpowiedzi_na_nasze_komentarze` brała tylko `comment_reply` (odpowiedzi pod ARTYKUŁAMI). Odpowiedź na nasz komentarz pod cudzą
notką przychodzi jako `note_reply`, a `nieodpowiedziane` czyta tylko nasze WŁASNE notki, więc nikt jej nie obsługiwał. Zmierzone 29.10 na 162 naszych
komentarzach: pod artykułami odpisaliśmy autorom w 9 z 13 wątków, pod cudzymi notkami w 0 z 33. Kształt zdarzenia potwierdzony na żywym kanale:
`comment_id` = ich odpowiedź, `target_comment_id` = nasz komentarz z niepustym `ancestor_path` (`<korzeń notki>.<nasz komentarz>`).

**Zmiana.** `type in ("comment_reply", "note_reply")`; `note_reply` bierzemy WYŁĄCZNIE, gdy cel to nasz komentarz w cudzym wątku
(`_nasz_komentarz_w_cudzym_watku`: nasz `user_id`, niepusty `ancestor_path`, korzeń nieznany albo nie nasz). Limit rozmowy, „już odpisaliśmy po ich
wypowiedzi" i konto siostrzane działają jak pod artykułami (infrastruktura `korzen_rozmowy`/`_komentarze_galezi` już obsługiwała notki). Kontekst dla modelu
mówi „note thread", nie „post". `run.bez_powtorzonych_odpowiedzi` odsiewa po numerze ich odpowiedzi, bo ta sama odpowiedź (na nasz komentarz pod NASZĄ notką)
może przyjść dwiema drogami.

**Skutek dla E23 (ważne).** Zmienia metrykę główną w obu ramionach jednakowo, ale podnosi poziom bazowy — patrz granica w
`MANIERA_KOMENTARZY_E23_2026-10-28.md`. **Publikacja** odbywa się istniejącą ścieżką `wystaw_odpowiedz(pod_id=ich_id)` (pole pod wątkiem, potwierdzenie
w API); weryfikacja interfejsu na żywo tylko w trybie sprawdzenia (`wyslij=False`).

## 2. Pamięć „kogo obserwujemy" scala się, zamiast przepisywać

**Błąd.** `odswiez_kogo_obserwujemy` przepisywała pamięć z zakładki `/following`, która oddaje ok. 41–47 osób przy 134 zaobserwowanych przez bota (lista
wirtualizowana/obcięta). Wszystko, co `obserwuj_profil` dopisał po drodze, znikało przy najbliższym przebiegu, a konto wracało do losowania: od 1.10 ok. 130
wejść na profil zakończonych „już obserwujemy". **Skala jest mała:** z 1531 pominięć obserwacji od 1.10 aż 1400 to filtr rozmiaru (5000), nie ta pamięć —
wcześniejsze „1482 pominięć wobec 120 obserwacji" mieszało oba powody.

**Zmiana.** Zakładka tylko DOPISUJE; konta, o których dziennik wie, że je obserwujemy (`_obserwowani_z_dziennika`: udana `obserwacja` i `obserwacja_pominieta`
z powodem zaczynającym się od „juz obserwujemy"), wracają do pamięci przy każdym odświeżeniu — także gdy plik pamięci zginie. Pierwszy zapisany czas konta
zostaje; mapa host → uchwyt nie wypada; pusta zakładka nie kasuje pamięci (jak dotąd) i nie przesuwa `zrzut`.

**Cena (świadoma).** Odobserwowanie przez właściciela nie znika z pamięci samo: konto zostaje poza pulą obserwacji. Stary test pilnował „samoleczenia"
(`test_pula_obserwacji`, sekcja 1) i został zmieniony świadomie — samoleczenie zakładało, że `/following` oddaje CAŁĄ listę, a nie oddaje. Fałszywe „już
obserwujemy" kosztuje jedno konto w puli, fałszywe „nie" jedno wejście na profil.

## 3. Alarm sesji mierzy żywą sesję

**Błąd.** Bot pracuje na żywym Chrome serwera (CDP), a `storage-state.json` jest tylko zapasem. Alarm i ostrzeżenie „sesja wygasa za N dni" brały dni Z PLIKU,
którego nikt nie odświeżał od 16.08: 30.10 plik mówił 14 dni (wygaśnięcie 14.11), a żywa sesja miała 89 (28.01.2027; Substack przedłuża przy aktywności).
Tekst alarmu kazał logować się NA KOMPUTERZE właściciela i kopiować plik — a sesja z innego adresu IP jest odrzucana przy publikowaniu.

**Zmiana.** `browser.odswiez_plik_sesji` (czyta tylko ciasteczka żywego Chrome, bez nawigacji; nadpisuje plik wyłącznie gdy zalogowany, atomowo i po
walidacji JSON-a; gdy Chrome nie odpowiada — `None`, żadnej innej przeglądarki w zastępstwie) wołana przez `alarm.sprawdz_sesje_i_ostrzez` PRZED pomiarem dni.
Tekst alarmu: logowanie NA SERWERZE (noVNC, port 6080 przez tunel SSH) i `python agent-v2/browser.py sesja`.

## Dowody i ograniczenia
* Testy: `test_odpowiedz_pod_cudza_notka` (29), `test_pamiec_obserwowanych_scala` (32), `test_alarm_sesja_zywa` (25) + zmieniony `test_pula_obserwacji`.
* Czerwone testy lokalne na Windows (`test_kanal_platnego_wywolania`, `test_pusty_budzet_nie_sprawdza`, `test_rozmowy_i_odpowiedzi`) są takie same na czystym
  `HEAD` — środowiskowe, nie z tej zmiany; porównanie z bazą serwera (`robocze/czerwone.sh`) przed wdrożeniem.
* Wymiana pamięci rozmówcy (E21), `maniera_komentarza` i reszta eksperymentów nie zmieniają się; zmienia się wolumen odpowiedzi pod cudzymi notkami.

## Po przeglądzie niezależnym (1.11.2026; 6 agentów + krytyk)
Pierwsza próba przeglądu (31.10) NIE odbyła się — agenty padły na tygodniowym limicie użycia — i nie została uznana za wykonaną; druga przeszła.
Zero blokerów, jedna realna luka, kilka wzmocnień. Poprawione przed wdrożeniem:
* **Korzeń wątku `note_reply` (jedyna prawdziwa luka).** Na żywym kanale korzeń wątku NIGDY nie leży w paczce zdarzeń, więc sito „korzeń nie jest nasz"
  było martwe: nasza odpowiedź pod NASZĄ notką (jej `ancestor_path` to sama notka) wyglądała jak komentarz w cudzym wątku, a bot odpisałby drugi raz i obszedł
  limit rozmowy. Teraz `_wlasciciel_korzenia` ustala autora korzenia jednym zapytaniem (`rootComment.user_id`, pamięć na przebieg), a brak odpowiedzi,
  wyjątek albo nasz korzeń znaczą POMIŃ. Częstość niska (0 przypadków w danych historycznych), ale skutek publiczny.
* **Autor i uchwyt z `user_id` odpowiedzi**, nie z pierwszego nadawcy zdarzenia zbiorczego (E21 i `komu` w dzienniku).
* **Wyłącznik prób dla `komentarz_obcy`** (`nieudane_odpowiedzi_w_watku`): po 2 porażkach odpowiedź nie wraca, bez modelu i bez przerwy — nowa ścieżka nie była
  używana na produkcji, a poprzednio wyłącznik dotyczył tylko artykułów.
* **Plik sesji:** unikalna nazwa tymczasowa (`mkstemp`, od razu 0600) zamiast stałej `.nowy`; tekst alarmu z komendą, która działa na serwerze
  (`cd ~/nothing-is-accidental-agent && .venv/bin/python agent-v2/browser.py sesja`); zdanie „wg żywego Chrome" tylko po udanym odświeżeniu; poprawione
  `JAK_WROCIC.md`.
* **Pamięć obserwowanych:** zapis atomowy, odporny odczyt dziennika (`errors="replace"`), liczba „40" w komentarzach (zakładka oddaje dokładnie 40 osób
  w 198 z 198 odświeżeń od 12.09, nie „41–47"), poprawiony nieaktualny komentarz o „samoleczeniu" w `obserwuj_profil`.
* Testy: korzeń poza paczką, odczyt korzenia nieudany/z wyjątkiem, pamięć korzeni, limit `ile`, pusta treść, wyłącznik prób, pierwsza data z dziennika,
  ucięty koniec pliku; mutacje 26 + 14 + 12, wszystkie wykrywane.

**Świadomie zostaje (backlog, nie regresja):** alarm sesji nie rozróżnia „Chrome nie odpowiada / wylogowany" od „sesja zdrowa" (dawniej też nie widział);
brak osobnego sufitu wolumenu na odpowiedzi (szczyt kroczącego okna 40 przy suficie 71, dodatkowe 3–7 odpowiedzi/dobę nie zbliżają się do niego); pamięć
obserwowanych nie leczy się po ręcznym odobserwowaniu; obserwacje wynikające z subskrypcji bota (menu „Unfollow") są nieznane odtwarzaniu z dziennika
(ok. 84 zbędnych wejść na profil); `time.sleep`-podobne czekanie bloku odpowiedzi odejmuje ok. 0,4 komentarza na dobę z budżetu czasu przebiegu.

## Wdrożenie
**1.11.2026, ok. 04:07 UTC (06:07 RO): `64712c2` → `b6271bc`** (`wdroz.sh`: moduły wstają, sesja i konto potwierdzone; cofnięcie: `git reset --hard 64712c2`).
Przed wdrożeniem: pełny zestaw 227 testów na serwerze w czystym worktree = **te same 24 czerwone co baza `64712c2`, zero nowych** (porównanie nazwa + kod
wyjścia); moje testy na Linuksie 58 + 36 + 30 + 46 + 41 zielone, w tym część o uprawnieniach 600 pomijana na Windows, i trzy mutacje uprawnień wykryte tylko tam.

**Dowody z produkcji (skrypt `robocze/zywa_weryfikacja_31_10.py`, 1.11 04:03–04:04 UTC, nic nie wysłane):**
* *Sesja:* `odswiez_plik_sesji()` → 89 dni żywej sesji; plik 253 505 B → 239 642 B, tryb 600 zachowany, dni wg pliku 88 → 89, brak plików `.nowy`; alarm
  (wysyłka zatrzymana) nic by nie wysłał.
* *Odpowiedzi pod cudzymi notkami:* `odpowiedzi_na_nasze_komentarze` oddaje 3 oczekujące odpowiedzi z notek (uchwyty `urkishika`, `hoangleitvn`, kontekst
  „our own comment in someone else's note thread"); tryb próbny `wystaw_odpowiedz(wyslij=False)`: pole odpowiedzi otwarte i wypełnione (9 słów), przycisk „Post"
  widoczny, `wyslane=False`, `blad=None`; dziennik bez nowych wpisów. **Publikacja i potwierdzenie w wątku NIE były jeszcze sprawdzone na żywo** — dopiero pierwsze
  prawdziwe odpowiedzi (przebieg ok. 11:27 UTC) to pokażą; obejrzeć ręcznie dwie pierwsze (wpis `odpowiedz`, `gdzie = note/c-<id>`, `udane`).
* *Pamięć obserwowanych:* 40 → 164 uchwyty (dziennik znał 164, w pamięci brakowało 124), żaden nie zginął, mapa hostów (40) nietknięta.

**Do sprawdzenia po pierwszych przebiegach:** czas bloku odpowiedzi względem limitu przebiegu (6900 s) i realizacja norm komentarzy/notek w trzech pierwszych dobach;
skuteczność wyłącznika prób; liczba odpowiedzi pod cudzymi notkami na dobę (szacunek ze skutków: 3,6 zdarzenia `note_reply` na dobę); granica w ocenie E23.
