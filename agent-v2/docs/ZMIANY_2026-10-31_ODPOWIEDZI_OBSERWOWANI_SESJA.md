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

## Wdrożenie
Uzupełnić po wdrożeniu: data, commit, wynik kontroli na żywo.
