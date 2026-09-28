# Pomiar i eksperymenty — jak wiedzieć, co zadziałało (27.09.2026)

Polecenie właściciela z 27.09:

> „pomyśl jeszcze, jak to wszystko wdrożymy, jak robić z tego statystyki, jak
> mierzyć skuteczność i jak coś będziemy zmieniać, żeby wiedzieć, co przyniosło
> skutek, a co nie, i co warto później przenieść do NIA"

## Punkt wyjścia — zmierzone 27.09 (`robocze/moc_pomiaru.py`)

- **Ok. 3 notki na dobę** (średnio 2,7 z ostatnich 14 dni).
- **Po 72 h** notka ma medianę 19 wyświetleń (średnio 24, maksimum 250), 2,9
  polubienia, 0,4 odpowiedzi, 0,1 restacka i 0,4 odwiedziny profilu. 72 ze 105
  notek nie ma ani jednej odwiedziny.
- **Zasięg spada w tle.** Średnia geometryczna wyświetleń w tygodniach 35–39:
  26,5 → 24,6 → 19,0 → 11,1 → 12,2, czyli −55% w miesiąc. Każde „przed i po"
  pokaże więc pogorszenie, niezależnie od tego, co zmieniliśmy.
- **Zmienność:** odchylenie standardowe logarytmu wyświetleń wynosi 0,55.
- **Konto:** 27 subskrybentów i 40 obserwujących.
- **26–27.09 weszło naraz kilka zmian** (E6 tematy, E7 świeżość i źródła, E8
  radar i śledztwo, E9 wniosek). „Przed i po" ich nie rozdzieli.
- **Nowe narzędzie na historii** (`eksperymenty.py`, zasięg względem tła
  tygodnia): żadna cecha — model, forma, typ notki — nie ma wykrywalnego
  wpływu. Przy tej liczbie notek wykrylibyśmy dopiero efekty rzędu +35–60%.
  Surowe średnie wskazywały „lepsze" stare notki (×1,95), ale to był sierpień,
  kiedy zasięg był dwa razy wyższy, a nie efekt zmian.

## Trzy warstwy dowodu

| warstwa | co mówi | tempo | czym |
|---|---|---|---|
| 1. **Jakość** | czy tekst jest lepszy według rubryki właściciela (mocny temat, niesztandarowy wniosek, prosto, uczciwie) | godziny | ślepi sędziowie z dwóch rodzin z materiałem źródłowym + miary z kodu |
| 2. **Odbiór** | czy czytelnicy reagują inaczej | tygodnie | eksperyment przeplatany na notkach; miara decyzji: wyświetlenia po 72 h **względem tła tygodnia** |
| 3. **Wzrost** | czy konto rośnie | miesiące | subskrybenci, obserwujący, zapisy przypisane przez Substack konkretnym treściom |

Warstwa 1 **nie przewiduje zasięgu**: na 105 notkach z historii zgodność
sędziów z zasięgiem wyniosła Spearman ≤ 0,09 (`docs/WNIOSEK_2026-09-27.md`).
Dlatego rozstrzyga, jak pisać, ale nie obiecuje wzrostu. Warstwa 3 jest tą,
która się naprawdę liczy, ale jest za rzadka, żeby przypisać ją drobnej zmianie
w notkach. Służy do oceny dużych zakładów: śledztw, artykułów, restacków.

## Ile notek trzeba (moc 80%, błąd 5%)

| efekt do wykrycia | notek na ramię | przy 3 notkach/dobę, podział 50/50 |
|---|---|---|
| +100% | 10 | ok. 1 tydzień |
| +50% | 29 | ok. 3 tygodnie |
| +25% | 95 | ok. 2 miesiące |
| +15% | 241 | ok. 5 miesięcy |

**Wniosek:** na zasięgu testujemy tylko duże dźwignie i jedną naraz. Drobne
poprawki (sformułowanie w prompcie, forma) rozstrzyga warstwa 1 plus strażnicy
— udawanie, że zasięg je rozstrzygnie, byłoby czytaniem szumu.

## Co jest już wdrożone (27.09)

- **Dziennik notki** ma `wersja` (commit, który ją napisał) i `eksperymenty`
  (ramię eksperymentu przeplatanego) obok tego, co już było: `typ`, `forma`,
  `styk`, `model`, `radar`, `glebia`, `koncowka_ocena`, `wniosek`,
  `przeslanie_id`, `zrodlo_data`.
- **`config.EKSPERYMENTY`** — przełącznik przeplatany, np. `{"wniosek": 0.7}`.
  Pusto oznacza, że nic się nie zmienia (tak jest teraz). Przydział jest
  deterministyczny z dnia i numeru miejsca notki w dobie (`stages.ramie`), więc
  obie grupy dzielą te same dni, godziny i ten sam trend. Obsługiwane: `wniosek`.
- **`agent-v2/eksperymenty.py --pole <pole>`** — grupy notek, każda porównana
  z grupą odniesienia:
  - zasięg względem tła (mediana innych notek z ±7 dni),
  - 95% przedział (bootstrap), werdykt: lepiej / gorzej / brak dowodu (razem
    z efektem, który przy tej liczbie notek dałoby się wykryć) / za mało danych,
  - ostrzeżenie, gdy grupy pochodzą z różnych okresów.

  Przykłady: `--pole eksperyment:wniosek`, `--pole wniosek`, `--pole przeslanie`,
  `--pole wersja`, `--pole forma`.
- **`karta_wynikow.py`** (co poniedziałek) — odbiór grup: radar, karta głębi,
  końcówka, wniosek/przesłanie, spoza branży/branża, koszt, zdrowie źródeł.

## Zasady zmian — żeby wiedzieć, co zadziałało

1. **Każda zmiana dostaje numer w rejestrze** (E…): co i po co, hipoteza,
   miara, projekt (przeplatany / jakość / przed-po), ile notek, data i reguła
   decyzji. Rejestr: `docs/POLIGON_I_PRODUKCJA.md` (lokalnie).
2. **Jedna dźwignia naraz** w eksperymencie zasięgu. Niezależne dźwignie mogą
   iść równolegle tylko wtedy, gdy każda ma własne przeplatanie (osobny klucz
   w `EKSPERYMENTY` = osobne losowanie).
3. **Po dużym wdrożeniu dwa tygodnie zamrożenia** tej samej dźwigni — poza
   naprawami błędów.
4. **Reguła decyzji ustalona z góry**, na zasięgu względem tła, po zaplanowanej
   liczbie notek:
   - **wygrana:** dolna granica przedziału > 1,0, a zaangażowanie nie gorsze;
   - **bez szkody:** dolna granica > 0,9 — zostawiamy, jeśli za zmianą
     przemawia jakość (warstwa 1) albo koszt;
   - **szkoda:** górna granica < 1,0 — cofamy;
   - **za mało danych:** mierzymy dalej, do zaplanowanej liczby notek.

   Nie kończymy wcześniej, bo „wygląda dobrze". Codzienne podglądanie mnoży
   fałszywe alarmy — przy 95% i tak co dwudzieste porównanie bez żadnego
   efektu wychodzi „lepiej" albo „gorzej" (test tego narzędzia to pokazał).
5. **Strażnicy przy każdej zmianie:**
   - obalone fakty i naprawy weryfikatora, odmowy dostawcy,
   - końcówka oceniająca materiał, długość,
   - koszt na notkę i na dobę, zdrowie źródeł.
6. **Wyniki neutralne i ujemne zapisujemy tak samo jak dodatnie** (`docs/`).
   Lista „nie pomogło" jest równie cenna jak „pomogło".
7. **Wdrożenie zmiany** idzie tą samą drogą co 27.09:
   1. gałąź;
   2. A/B lub żywy test na kopii danych (tryb test);
   3. pełne testy na czystej kopii serwera (`robocze/testy_serwer.sh`, porównanie z bazą);
   4. `main` i GitHub;
   5. `bash agent-v2/wdroz.sh` (cofnięcie jednym poleceniem);
   6. ślad z pierwszego przebiegu produkcji;
   7. wpis w rejestrze.

## Kalendarz

- **28.09–11.10 — zamrożenie potoku notek** (tylko naprawy). Zbieramy tło pod
  nowy system. Pierwsze przesłania ze śledztwa wychodzą 28–30.09.
- **ok. 13.10** — decyzja E6 (tematy spoza branży), zaplanowana wcześniej.
- **E10 — pierwszy eksperyment przeplatany, ZATWIERDZONY przez właściciela
  27.09:** wniosek u 70% notek z banku, **28.09–25.10**. W `config.py` wpisane
  z oknem dat, więc eksperyment sam startuje i sam się kończy.
  - Dlaczego wniosek: to największa zmiana w pisaniu, jest tania, sędziowie są
    za nim, a jego wpływ na zasięg jest nieznany.
  - Próba: ok. 84 notki (59 z wnioskiem, 25 bez), wykrywa różnicę rzędu ±45%.
    Notki z przesłania wniosku nie dostają i w eksperymencie nie biorą udziału.
  - Miara decyzji: wyświetlenia po 72 h względem tła, ramię „on" do „off",
    95% przedział.
  - Miary poboczne: zaangażowanie i odbiór na 100 wyświetleń.
  - Strażnicy: końcówka oceniająca, długość, obalone fakty, koszt.
  - Reguła, zapisana przed startem:
    - dolna granica > 1,0 — wygrana, wniosek zostaje dla wszystkich;
    - dolna granica > 0,9 — bez szkody, wniosek zostaje (przemawia za nim jakość);
    - górna granica < 1,0 — szkoda, wniosek wyłączamy i szukamy przyczyny
      w strażnikach;
    - poniżej planowanej próby — nie rozstrzygamy.
  - Ocena ok. **29.10** (ostatnie notki muszą dojrzeć 72 h):
    `python agent-v2/eksperymenty.py --pole eksperyment:wniosek --od 2026-09-28`.
  - Cena tej wiedzy: 30% notek z banku przez 4 tygodnie idzie bez wniosku.
- **E11 — pisarz notek Xiaomi MiMo V2.6 Flash, na polecenie właściciela
  28.09** („możesz mu dać notki na próbę, ale tylko na NIE"). Połowa notek
  z banku, **28.09–25.10**, własne losowanie (`ramie("pisarz")`), niezależne
  od E10, więc oba eksperymenty idą naraz, a każdy ma drugi rozłożony po
  swoich ramionach.
  - Dlaczego: w ślepym teście na 8 produkcyjnych promptach MiMo wygrał 11:5
    u dwóch sędziów (Claude Opus 5.5, Fable 5.1) i miał wyższe oceny we
    wszystkich kryteriach rubryki. Koszt notki jest podobny (0,00066 wobec
    0,00057 USD), ale MiMo pisze 5× wolniej. Sędziowie nie przewidują zasięgu,
    stąd eksperyment na żywo.
  - Zasady: notka z przesłania (Opus) nie bierze udziału. Bez klucza zostaje
    DeepSeek. Gdy MiMo nie napisze, w tym samym przebiegu pisze DeepSeek
    (`pisarz_zastepczy`). Faktyczny pisarz zapisuje się w polu `model` dziennika.
  - Miara i reguła jak w E10 (wyświetlenia po 72 h względem tła, 95% przedział):
    `python agent-v2/eksperymenty.py --pole eksperyment:pisarz --od 2026-09-28`,
    ocena ok. **29.10**. Próba to ok. 42 notki na ramię, co wykrywa różnicę
    rzędu ±40%.
  - Miary poboczne: ocena jakości, obalone fakty, koszt i czas.
- **E12–E18 i E20 — pakiet zatwierdzony przez właściciela 28.09** („przygotuj
  cały test, żeby to działało i żeby zbierało dane"). Każdy eksperyment ma
  okno dat w `config.EKSPERYMENTY` i własne losowanie. Reguły poniżej są
  zapisane przed startem.
  - **E12 — ile restacków (29.09–9.11).** Tygodnie według planu ABBAAB: „on"
    to 3–5 restacków dziennie (średnio 4), „off" 1–3 (średnio 2). Plan zamiast
    losowania, bo sześć tygodni to za mało, żeby los wyrównał trend konta.
    - Miary (tygodniowo): zapisy przypisane restackom, przyrost subskrybentów,
      odwiedziny profilu. Ocena:
      `python agent-v2/eksperymenty.py --tygodnie restacki_norma`, ok. **11.11**.
    - Strażnicy: wykonanie planu restacków (alarm „wolumeny"), odmowy modelu,
      ci sami autorzy, wyświetlenia na restack. Jeśli spadną o ponad połowę,
      to znaczy, że więcej restacków się rozmywa.
    - Reguła: w tygodniach „on" przyrost subskrybentów na dobę i zapisy
      z restacków wyższe, a strażnicy w normie — norma zostaje 3–5. Jeśli
      jedno z nich nie jest wyższe, wracamy do 1–2. Przy trzech tygodniach na
      ramię widać tylko duże różnice, więc „brak różnicy" nie dowodzi, że jej
      nie ma.
  - **E13 — kto pisze zdanie restacka (29.09–26.10).** Opus (etap
    `restack_opus`, wysiłek low) albo Flash, 50/50. Los po treści ocenianej
    notki. Restack z notką jest notką na naszym profilu: 35 z 35 restacków od
    1.09 ma numer i pomiar.
    - Miara jak w E10: wyświetlenia po 72 h względem tła i odbiór na 100
      wyświetleń. Ocena ok. **29.10**:
      `python agent-v2/eksperymenty.py --rodzaj restack --pole eksperyment:pisarz_restackow --od 2026-09-29`.
    - Próba: ok. 80 restacków (40 na ramię), co wykrywa różnicę rzędu ±40%.
    - Koszt zmierzony na żywo 28.09 (kopia danych): ocena Opusem 0,018 USD,
      Flashem 0,00023. Połowa ocen na Opusie to ok. 0,05–0,15 USD na dobę,
      w tygodniach E12 „on" do ok. 0,3 USD. Sufit dzienny NIE to 5 USD.
    - Reguła: dolna granica > 1,0 — restacki pisze Opus; górna < 1,0 albo brak
      dowodu — zostaje Flash (tańszy).
  - **E14 — gdzie komentarz (29.09–19.10).** W każdym przebiegu ta sama liczba
    miejsc co dotąd (N pod artykułami + max(1, N//2) pod notkami), ale każde
    miejsce losuje rodzaj celu. Miejsce, którego blok nie zapełni, przepada
    tak jak dotąd.
    - Miara: odsetek komentarzy z reakcją (polubienie, odpowiedź, restack) po
      48 h oraz odpowiedzi na 100 komentarzy. Zasięgu komentarza Substack
      prawie nie podaje: 78 ze 125 zmierzonych ma 0 wyświetleń.
    - Ocena ok. **22.10**:
      `python agent-v2/eksperymenty.py --rodzaj komentarz --pole eksperyment:cel_komentarza --od 2026-09-29`.
    - Próba: ok. 150 komentarzy, co wykrywa różnicę rzędu 2× (np. 20% wobec 10%).
    - Reguła: dolna granica > 1,0 — więcej miejsc idzie pod ten rodzaj celu
      (np. N pod nim, N//2 pod drugim); w innym razie przydział bez zmian.
    - Każdy komentarz ma od teraz w dzienniku pole `pod` (notka albo artykuł),
      także poza eksperymentem.
  - **E15 — świeży cel (20.10–9.11).** Na miejscach „on" brany jest
    najświeższy wybrany cel młodszy niż 2 h, jeśli taki jest.
    - Próg anty-bota się nie zmienia: artykuł musi mieć 1,5–15 h, notka
      20–90 min. Pod artykułami ramię zwykle nie ma więc czego wziąć i E15
      mierzy głównie notki. Od 20.09 tylko 7 z 62 komentarzy trafiło w cel
      młodszy niż 2 h.
    - Miara i reguła jak w E14, plus faktyczny wiek celu (`wiek_celu_min`).
      Ocena ok. **12.11**.
  - **E16 — pora notki (26.10–22.11).** Dni na przemian, więc w czterech
    tygodniach każdy dzień tygodnia ma po 2 dni w każdym ramieniu.
    - „on": notki dopiero od 3. przebiegu, czyli o 15:20, 17:30 i 19:40 ET.
    - „off": jak dotąd, czyli 7:20, 13:00 i 15:20 ET.
    - Miara i reguła jak w E10: `--pole eksperyment:pora_notki --od 2026-10-26`,
      ocena ok. **26.11**. Zmiana czasu 1.11 dotyczy obu ramion jednakowo.
  - **E17 — krótka notka (26.10–22.11).** „on": okno 33–60 słów zamiast
    33–120. Forma długa i notka z przesłania nie biorą udziału.
    - Miara jak w E10 oraz zaangażowanie. Strażnik: zrozumiałość. 3.09
      właściciel nie zrozumiał notki ściśniętej do 64 słów.
    - Reguła: dolna granica > 1,0 i zaangażowanie nie gorsze — krótkie okno;
      w innym razie bez zmian.
    - Żywy test 28.09 (kopia danych): przy samym oknie 33–60 DeepSeek napisał
      135 słów. Dlatego ramię „on" dostaje polecenie wprost
      (`stages.z_krotka_notka`), z zastrzeżeniem zrozumiałości. Po tej zmianie
      wyszło 57, 75, 65 i 69 słów. Długość nadal jest tylko mierzona, nic nie
      jest cięte.
  - **E18 — pytanie na koniec (26.10–22.11).** „on": notka kończy się jednym
    prawdziwym pytaniem do czytelnika (`stages.POLECENIE_PYTANIA`). Część
    serii i notka z przesłania nie biorą udziału.
    - Sprawdzenie, że zmiana zaszła: pole `konczy_pytaniem` w dzienniku
      (w obu ramionach).
    - Pytanie dopina KOD, nie prośba. Żywy test 28.09: z samym poleceniem 2 z 3
      notek skończyły się stwierdzeniem. Teraz model oddaje pytanie osobnym
      polem, a `stages.dopnij_pytanie` dopina je, gdy notka nie kończy się
      pytaniem, jeszcze przed sprawdzaniem faktów. Po zmianie 2 z 2 notek
      kończyły się pytaniem.
    - Miara decyzji: odpowiedzi pod notką na 100 wyświetleń. Strażnik:
      wyświetlenia względem tła.
    - Reguła: dolna granica odpowiedzi > 1,0, a wyświetlenia bez szkody (dolna
      granica > 0,9) — pytania zostają. W innym razie bez zmian.
  - **E20 — rekomendacje (od 28.09, przed/po).** 28.09 o 18:10 UTC NIE
    zaczęła polecać 4 publikacji o AI, pod którymi naprawdę komentuje, każda
    z „dziesiątkami tysięcy" subskrybentów: AI as Normal Technology, Deep
    (Learning) Focus, Jam with AI, AI Agents Simplified. Wszystkie 4 są
    potwierdzone przez API panelu. Dodała je przeglądarka bota
    (`robocze/e20_polec.py`), a opisy powstały z ich opisów i ostatnich
    tekstów.
    - Stan przed: polecamy 1 (publikacja dodana ręcznie 11.07), polecają nas
      0, zapisy z rekomendacji 0. Stan po: polecamy 5.
    - Skutek uboczny: przy każdej dodanej rekomendacji Substack SAM publikuje
      notkę z kartą polecenia i pustą treścią. 28.09 powstały 4 takie notki,
      od 18:07:57 do 18:09:46 UTC. Nie ma ich w dzienniku bota, więc nie
      wchodzą do porównań notek, ale są publiczne i liczą się do zasięgu
      konta. Przy kolejnych rekomendacjach trzeba sprawdzić, czy okno ma
      przełącznik udostępniania.
    - Przy okazji wyszło, że `browser.kogo_polecamy` był ślepy: API oddawało
      `{rows}` zamiast listy, a `publication/self` nie podawało numeru.
      Naprawione — źródłem jest teraz `recommendations/stats/from`.
    - Miara: `rekomendacje.jsonl` (ilu polecamy, ilu poleca nas, zapisy
      z rekomendacji — liczniki panelu), źródła zapisów w panelu, obserwatorium.
    - Reguła: po 6 tygodniach (ok. **9.11**), gdy ktoś nas poleca albo przyszedł
      choć jeden zapis — dokładamy 2–3 kolejne. Przy zerze zostaje jak jest.
- **Żywy test z publikacją, 28.09 (polecenie właściciela „przetestuj live,
  czy wszystko działa, łącznie z publikacją").** Jeden prawdziwy przebieg dnia
  (nr 324, 18:32–19:49 UTC, DONE, 0 błędów, 0,111 USD), kod i dane produkcji.
  Tylko w tym procesie wymuszono ramiona E12–E18 i wyłączono cichy dzień
  (`robocze/zywy_test_pakietu.py`). E10 i E11 były w nim wyłączone, żeby
  notka testowa nie weszła do ich porównania. Pozycje mają datę 28.09, a
  oceny liczą od dat startu, więc test nie miesza się z pomiarem.
  - Budżet: `[E12 restacki: on]`, 4 restacki. Przydział komentarzy E14: 2 pod
    artykułami, 1 pod notką.
  - Notka z przesłania (Opus, 114 słów): opublikowana. Ma tylko ramię E16 —
    zgodnie z projektem jest poza E17/E18.
  - Notka z banku (Flash): opublikowana. Ma 47 słów, ramiona E16/E17/E18
    i `konczy_pytaniem: true`. Pytanie w osobnym akapicie, czyli dopięte
    kodem.
  - Komentarz pod notką: potwierdzony w wątku. Dziennik: `pod: notka`,
    `cel_komentarza: on`, `swiezosc_celu: off`.
  - Pod artykułami żaden z 2 celów nie przyjmował komentarzy (brak pola,
    tylko dla płacących), więc dziennika dla artykułów w tym przebiegu nie ma.
  - Restack: opublikowany, numer znaleziony na profilu. Dziennik:
    `model: claude-opus-5-5`, ramiona E12/E13 „on"; ocena Opusem 0,0175 USD.
  - Pomiar: `[rekomendacje] polecamy 5, polecaja nas 0`, plik
    `rekomendacje.jsonl` zapisany. Raport obserwatorium ma wiersz
    rekomendacji, a E12–E18 widnieją w nim jako „zaplanowane".
- **Zbieranie danych dołożone 28.09 razem z pakietem:**
  - alarm `pomiar-statystyk`: pomiar treści, licznika i panelu oraz komentarzy
    z dwóch dób;
  - model i ramiona w dzienniku restacka;
  - `pod` w dzienniku komentarza;
  - `konczy_pytaniem` w dzienniku notki;
  - `rekomendacje.jsonl`.
- **ok. 25.10 — ocena E8/E9:**
  - przesłania kontra zwykłe notki (`--pole przeslanie`),
  - artykuły ze śledztw (zapisy przypisane, wyświetlenia),
  - koszt i odsetek odmów dostawcy.
- **Co tydzień:** karta wyników i `eksperymenty.py` dla trwających eksperymentów.

## Śledztwa — co mierzyć

- **Przesłania:** grupa „przeslanie" w karcie i w `eksperymenty.py`. To ok. 6
  notek tygodniowo, więc po 4 tygodniach zobaczymy tylko duże różnice.
- **Artykuły ze śledztw kontra z puli:** zapisy przypisane przez Substack
  (`zrodla.jsonl`, `zapisy_per_notka`) i wyświetlenia. To ok. 1 artykuł
  tygodniowo, więc ocena dopiero po ok. 2 miesiącach.
- **Koszt śledztwa i odmowy dostawcy:** pierwsze śledztwo kosztowało 0,17 USD,
  a artykuł został odrzucony w kategorii „cyber".

## Drugie konto

Co i kiedy przenosić na drugie konto, zapisuje lokalny rejestr
(`docs/POLIGON_I_PRODUKCJA.md`, poza repozytorium). Zasada: najpierw naprawy
błędów i warstwa pomiaru, zmiany treści dopiero po dowodzie z tego konta.
