# Audyt pieciu agentow — 1 wrzesnia 2026

Pelny audyt systemu prowadzony rownolegle, maksymalnie piecioma agentami naraz:
najpierw naprawy, potem **niezalezna kontrola kazdej naprawy przez innego
agenta**, potem naprawa szkod, ktore kontrola wykryla.

Bilans: **19 znalezisk zweryfikowanych i potwierdzonych, 0 falszywych**. Kontrola
wykryla ponadto **7 szkod wprowadzonych przez same naprawy** — to jest glowny
wynik tego audytu i powod, dla ktorego warto bylo go prowadzic dwuetapowo.

## Reguly, ktore sie z tego wykluly

**Poprawka moze byc martwa mimo zielonego testu.** Trzy razy w tej sesji test
przechodzil, bo odwzorowywal WYOBRAZENIE wywolania, nie produkcje:

- filtr `isinstance(u, str)` przy produkcji podajacej `frozenset` — test podawal
  napisy;
- `zwroc_kandydatow([fakt])` wewnatrz petli powtorek — test podmienial
  `wybierz_fakt` na atrape wydajaca kolejne elementy listy, wiec nie widzial, ze
  prawdziwa para `wez_kandydatow`/`zwroc_kandydatow` cztery razy oddaje TEN SAM
  fakt (`ranga` sie nie zmienia, sortowanie jest deterministyczne);
- `zakwestionuj_promocje` — test sprawdzal obecnosc napisu w zrodle.

**Asercja po tresci zrodla (`"..." in ZRODLO`) przechodzi takze na kodzie
martwym.** Usuniete wszedzie, gdzie znaleziona.

**Kontrdowod jest obowiazkowy i musi byc ODTWORZONY, nie opisany.** Kazdy nowy
test uruchamiany na pliku z `git show HEAD:...`, z prawdziwymi liczbami w
docstringu.

**Dwie poprawki, kazda z osobna sensowna, moga zlozyc sie w szkode.** Podloga w
`note()` + zdjecie warunku przy promocji dawaly razem: jedno „I noticed" w notce
kasowalo artykul z kolejki NA STALE, z pustym powodem, przy zerze platnych
wywolan, a dziennik pisal „(sprawdzenie faktow)".

## Naprawione i zweryfikowane

### `browser.py`
- Komentarz, odpowiedz i odpowiedz pod artykulem zapisuja wynik w `finally` —
  wczesniej brak pola, brak przycisku i wyjatek nie zostawialy sladu, wiec
  `hosty_gdzie_komentarz_nie_wchodzi` o takich hostach nigdy nie slyszalo. Zapis
  osloniety `try/except`, zeby nie mogl powstrzymac zamkniecia przegladarki
  (bez oslony `page.close()`, `browser.close()` i `p.stop()` NIE wykonywaly sie).
- **Polubienie potwierdzane**, nie zakladane. Stan czytany z uchwytu wezla, nie
  z lokatora po nazwie. Progi niesymetryczne: „nie wiem" liczy sie na korzysc,
  bo falszywe „nie udalo sie" zaniza jedyny licznik lajkow dnia.
- `_STAN_PRZYCISKU` pyta `el.isConnected` — wezel poza dokumentem to „nie wiem",
  nie „bez zmiany". Bez tego podmiana wezla przez Reacta dawalaby twarde `False`.
- **Wpis porazki niesie `o_hoscie`** (zrodlem `wynik["klikniete"]`). Timeout i
  padnieta sesja nie skreslaja juz hosta. Okno pamieci **14 dni** — dluzsze niz
  `ODSTEP_DNI_NA_PUBLIKACJE = 4`, rowne `OSTRZEGAJ_PONIZEJ_DNI`, przy tempie
  ~13 prob dziennie miesci ~180 prob. Wpisy sprzed poprawki nie licza sie wcale.

### `run.py`
- Wynik `wystaw_komentarz` / `wystaw_odpowiedz` **nie jest juz ignorowany**.
  Wczesniej licznik przebiegu liczyl PROBY, a alarm liczy z dziennika UDANE —
  dwie polowy jednego pomiaru mierzyly co innego.
- Pominiecie (`juz_sie_odezwalismy`) nie liczy sie do normy i nie pali hosta:
  ta funkcja oddaje `True` takze przy awarii `/public_profile`, wiec liczenie
  pominiec wypalaloby caly dzienny budzet bez ani jednego komentarza.
- **Hamulec per blok.** `_POD_RZAD_ZLE` byl globalny, wiec trzy porazki
  komentarzy konczyly blok komentarzy I NASTEPUJACY PO NIM blok dyskusji — a to
  dyskusje daja 23 z 29 wypowiedzi agenta. Prog bez zmian, zmieniony zasieg.
- Sito martwych hostow przeniesione **przed** platne `wybierz_cele`.

### `stages.py`
- Podlogi z pamieci (`FABRICATED_EXPERIENCE`, `VAGUE_STUDY`) dolozone do
  komentarza — mial je restack i odpowiedz, komentarz nie.
- `wybierz_do_odpowiedzi` sortowalo po `reakcje`/`odpowiedzi`, ktore dwa z
  trzech zrodel w ogole nie wypelniaja. Zastapione mieszaniem zrodel na zmiane;
  `(reakcji: N)` idzie do promptu tylko tam, gdzie ktos to naprawde liczy.
- Kuplet korygujacy dostal zamiennik: `zdania_z_tikiem` dokleja do promptu
  WLASNE zdania z ostatnich 12 notek zawierajace ten tik. Sortowanie po tiku
  bylo martwe, bo `NOTE_CANDIDATES = 1`.

### `artykul_z_puli.py`
- `warto_pisac` / `write` / `review` w `try/except`, powtorka pisarza na Opusie.
- **Fakt odrzucony wraca do puli PO petli, nie w jej srodku** — inaczej cztery
  „kolejne proby" braly ten sam fakt, placac za `temat_z_faktu` za kazdym razem.
- Wstrzykniety fakt oznaczony `not_fetched: True`. `szerokosc_podstawy` go
  pomija, wiec `WASKA_PODSTAWA` znowu sie odzywa; liczba z puli dostaje WLASNA
  uwage `LICZBA_TYLKO_Z_PULI` zamiast `LICZBA_SPOZA_KORPUSU`, ktora by klamala.

### `norma.py`
- **Odwrocony bodziec usuniety.** Bylo: o 23:00 przy zerze dzialan `% PLANU`
  pokazywalo 100%, a po pieciu zrobionych rzeczach 80%. Dzien biezacy
  rozliczany proporcjonalnie do harmonogramu z `systemd/nia-agent.timer`
  (NIE z `przebiegow_dzis()`, ktora liczy przebiegi ODBYTE, nie nalezne).
- `MIN_PLAN_DO_ALARMU` rozdzielone na `MIN_PLAN_DZIENNY_DO_ZNAKU = 3` i
  `MIN_PLAN_W_OKNIE_DO_ALARMU = 10` — jedna stala rzadzila dwiema skalami.
- Poczatek okna z kalendarza, nie z danych. Dzien bez zadnego sladu dostaje plan
  OSZACOWANY, oznaczony `~`. `?` nie jest juz drukowany jako `0.0`.

### `alarm.py`
- Statystyka dlugosci liczy tylko wypowiedzi UDANE. Wczesniej 3 udane po 40 slow
  i 3 nieudane po 400 dawaly srednia 220 i **gasily** alarm „ZA ROWNO".

### Prompty
- Przyklady z ery „ukrytych systemow w przedmiotach" przepisane na ere AI
  (`ciekawostki.md`, `skaut.md`, `forma.md`, `fedreg.md`, `warto_pisac.md`,
  `config.NOTE_FORMS`). Zawieszenie `fedreg.md` w tescie zdjete.
- **`odpowiedz.md`: bariera przeciw wstrzyknieciu pilnowala pustego miejsca** —
  mowila „wszystko PO tym znaczniku to tekst obcych", a `{comment}` i
  `{evidence}` staly PRZED nia. Dane przeniesione za bariere.
- Usuniete zdanie „read it as the record of what you actually argued": przy
  komentarzu pod artykulem `{evidence}` to **sam naglowek, 200 znakow**, bez
  artykulu i bez materialu dowodowego. Naglowek mowi teraz prawde o zawartosci.

### Testy
`test_bariera_wstrzykniecia.py` nie zgaduje z ukladu pliku, tylko przechodzi
`stages.py` przez `ast` i cofa sie po przypisaniach: pole karmione **parametrem
funkcji** jest obce (tedy wchodzi siec), pole konczace sie na `config.*`/`style.*`
jest nasze, **pole nierozpoznane OBLEWA test**. Poprzednie kryterium (oparte na
ukladzie) przepuszczalo wade po dopisaniu jednej linii pod polem albo po
owinieciu go w plot kodu — czyli po zastosowaniu ZALECANEJ higieny.

## Dlugi swiadome (NIEZAMKNIETE)

1. **Notki nie maja podlogi na zmyslone przezycie.** Podloga byla nalozona i
   zostala COFNIETA, bo obejmowala wszystkie piec typow zamiast samego MYSL.
   Zmierzone: `VAGUE_STUDY` blokuje „According to a paper published in Nature in
   December 2024" (zrodlo, pismo, data); `config.py` w ksztalcie OBSERWACJA
   wprost zamawia pierwsza osobe, ktora `FABRICATED_EXPERIENCE` odrzuca, a
   `losowy_ksztalt_mysli` losuje go co czwarty raz; przy `NOTE_CANDIDATES = 1`
   odrzucenie jedynego kandydata znaczy, ze notka dnia przepada bez sladu.
   Zamkniecie: podloga tylko tam, gdzie nie ma karty dowodowej, plus zawezenie
   `VAGUE_STUDY`, zeby nie lapal zdan nazywajacych zrodlo.

2. **`zakwestionuj_promocje` jest kodem nieosiagalnym.** Warunek
   `any(k.get("safe_to_post") ...)` przywrocony swiadomie. Cena jest znana:
   25/26 sierpnia notka promujaca „The Watermark Was Never a Verdict" odpadla na
   sprawdzeniu faktow, artykul ZOSTAL w kolejce, nastepny przebieg napisal o nim
   inna notke i falsz wyszedl w swiat. Zdjecie warunku bylo probowane i cofniete,
   bo bez niego KAZDY powod odrzucenia notki kasowal artykul z kolejki na stale,
   takze w przebiegu BEZ `--wyslij`. Zamkniecie: `zakwestionuj_promocje` ma
   odmawiac, gdy powod nie jest werdyktem faktograficznym, a `run.py` ma wolac
   ja wewnatrz `if wyslij:`.

3. **`co_dodamy` ginie w drodze do promptu.** `stages.comment_on` czyta to pole,
   ale `run.py` go nie przekazuje w ZADNYM z dwoch miejsc (`read_pages` oddaje
   `{url, text, title, error}`; drugie wywolanie buduje slownik recznie).
   `cele.md` czyni z niego trzeci warunek dopuszczenia celu.

4. **`restackuj_w_kanale` zapisuje `udane=True` bez potwierdzenia.** Sygnal
   istnieje (`numer_naszej_notki` jedzie jako pole `id`), ale nie rzadzi polem
   `udane`. Nie bramkowane, bo poprzedni mechanizm trafial numer 6 razy na 29 —
   bramka dawalaby masowo falszywe „nie udalo sie". Zamkniecie: policzyc na
   produkcji odsetek wpisow `restack` z niepustym `id`.

5. **Lokator polubien bez `exact=True`.** Nie wiadomo, jak Substack nazywa
   przycisk PO polubieniu. Zawezenie moglo by wylaczyc lajki calkowicie i
   CICHO — zero prob wyglada w dzienniku jak spokojny dzien.

6. **`browser.py`: brak sprawdzenia wlasciciela komentarza docelowego.** `nasz =
   wpisy.get(target_comment_id)` bierze ze sklejki trzech workow, z ktorej dwie
   linie wyzej wyjmowany jest CUDZY komentarz. Ze target jest nasz, gwarantuje
   tylko docstring — brak warunku `nasz.get("user_id") == moje_id`, choc
   `moje_id` jest tuz obok, a w dwoch pozostalych zrodlach ta kontrola jest norma.

7. **`alarm.py:381` nie ma bramki na wielkosc planu**, ktora dostala `norma.py`.
   Mail nadal potrafi zaalarmowac o subskrypcjach (plan ~2/tydzien), o ktorych
   `norma.py` swiadomie milczy.

8. **`norma.py` nie mierzy artykulow** — `browser.py` pisze `rodzaj: "artykul"`,
   `RODZAJE` go nie zawiera. Zastane, nie skutek tej sesji. Odbior artykulow
   mierzony osobno.

9. **`gates.numbers_outside_corpus` bierze do korpusu `ocena_ciekawosci` i
   `parallel_mechanisms`** — wypowiedzi modelu z cytatami. Zamkniete tylko to,
   co otworzylo wstrzykniecie faktu.

10. **`test_forma_artykulu_bramka.py`** uzywa slownictwa z ery przedmiotow
    (`"object": "carton"`, cytat o polce w lodowce). Straznik `test_prompty_o_ai`
    skanuje tylko prompty i `NOTE_FORMS`, wiec tego nie widzi.
