# Wybór tematów: jak jest, jak powinno być, jak to zrobić najtaniej

26 września 2026. Odpowiedź na pytanie właściciela: „skąd brać tematy, sprawdź,
jak to mamy, a jak powinno być, jak to zrobić, jak najtaniej".

Podstawa: kod z `main` (a1242dc), pomiary w `docs/` i research
z `SILNIK_TEMATOW_2026-09-26.md`. Ten raport jest węższy od tamtego: dotyczy
tylko tego, jak **nasz** bot wybiera temat, i kończy się listą zmian w kodzie.

**Ograniczenie.** Kontener, w którym to powstało, nie ma wyjścia do sieci ani
danych produkcji. Koszty są więc z dokumentów pomiarowych (zawsze podaję skąd),
a adresy nowych źródeł z wyszukiwarki. Jedno darmowe polecenie na serwerze
sprawdza jedno i drugie: to krok 0 w rozdziale 4.

---

## Najkrócej

1. **Dziś bot właściwie nie szuka tematów.** Czyta osiem najnowszych tekstów
   z naszych feedów i robi z nich fakty. Tak ustawia to kod: gdy „spiżarnia"
   (te osiem tekstów) nie jest pusta, wyszukiwanie jest wyłączone
   (`web_search = not _tresc` w `stages.znajdz_ciekawostki`). Z 25 feedów 22 to
   branża, a z jednego feedu wchodzą najwyżej 2 teksty. Osiem miejsc zajmują więc
   zwykle cztery blogi. Tak wyszło w pomiarze z 8 września: 32 z 35 faktów
   pochodziło z pytorch.org, latent.space, simonwillison.net i importai.
2. **Wcześniejsza diagnoza była nietrafna, moja też.** Pomiar z 8 września
   i mój raport `SILNIK_TEMATOW` twierdziły, że „model szuka tam, gdzie łatwo
   o dokument". Model niczego nie szukał. Dostał osiem tekstów o PyTorchu
   i Latent Space oraz polecenie „najpierw pracuj na tym". Dlatego trzy zmiany
   promptu nic nie dały: zaczyn co drugi dzień, „najwyżej dwa fakty z jednego
   źródła" i siatka dziedzin. Zmieniały słowa, a materiał wybierał kod.
3. **Skąd brać tematy.** Z miejsc, które publikują datowane dokumenty o tym,
   jak AI dotyka ludzi, i dają je za darmo przez RSS albo API:
   - praca: NBER, Rest of World,
   - zdrowie: KFF Health News, a w etapie 2 lista FDA,
   - szkoła: EdSurge, The 74,
   - pieniądze i oszustwa: FTC, SEC,
   - prawo: Federal Register, CourtListener, a w etapie 2 baza orzeczeń
     o zmyślonych cytatach,
   - codzienność: Pew,
   - badania o ludziach: arXiv cs.CY i cs.HC.

   Adresy i przykładowe tematy są w rozdziale 3.
4. **Jak bot ma poznać, że temat jest ciekawy.** Nie z gustu modelu, tylko z trzech
   rzeczy, które liczy kod:
   - **Etykieta „styku" ze źródła.** Styk to miejsce, w którym AI dotyka
     czytelnika: praca, zdrowie, szkoła, pieniądze, prawo, codzienność albo
     branża. Kod zna go z pochodzenia tekstu, model nie musi zgadywać.
   - **Kwota.** W spiżarni najwyżej 2 teksty branżowe na 8, a co najmniej
     1 z 3 notek dziennie spoza branży.
   - **Miara.** Odwiedziny profilu i zapisy na 100 wyświetleń po 72 godzinach,
     liczone osobno dla każdego styku. Te dane już zbieramy. Ranking ich nie
     czyta, bo dziś uczy się z polubień.
5. **Koszt jest praktycznie taki sam jak dziś: około 1–2 USD miesięcznie za cały
   wybór tematu.** Nie dochodzi ani jedno płatne wywołanie. Zmienia się tylko to,
   co wkładamy do jednego dziennego wywołania skauta, a nowe źródła to darmowe
   zapytania HTTP. Jednorazowo dojdzie pomiar przed zmianą i po niej, za około
   0,2–0,4 USD.
6. **Kolejność:**
   - krok 0: dziś, 0 USD, jedno polecenie na serwerze;
   - kroki 1–6: jeden dzień pracy;
   - dwa tygodnie pomiaru na poligonie (Nothing Is Accidental);
   - przeniesienie do NIA, jeśli nowa miara wyjdzie co najmniej tak samo dobrze.

---

## 1. Jak jest dziś

### 1.1. Droga tematu, etap po etapie

| # | etap | gdzie w kodzie | co robi | koszt | co jest nie tak |
|---|---|---|---|---|---|
| 1 | Korpus | `korpus_kanalow.korpus_kanalow()` | 13 kanałów YouTube + 25 feedów (`ZRODLA`), z każdego do 12 najnowszych wpisów, całość posortowana po dacie | 0 (HTTP) | **22 z 25 feedów to branża**: laboratoria, wydania bibliotek, strony awarii, blogi i podcasty o AI. O ludziach i prawie są trzy: AI Incident Database, Komisja UE, Transformer. YouTube blokuje serwer (12 z 13 kanałów, sprawdzone 5.09), korpus bierze go z zapasu. |
| 2 | Wielkie wydarzenia | `korpus_kanalow.wielkie_wydarzenia` | temat w ≥ 3 kanałach otwiera furtkę dodatkowego szukania | 0 | działa; w praktyce to premiery modeli |
| 3 | Czy szukać | `znajdz_ciekawostki`, `config` | bank trzyma 15–20 wolnych faktów, dobiera raz na dobę (do 5 prób, gdy spadnie poniżej 15), fakt żyje 7 dni | 0 | **ilości jest dość**: 7.09 bank dawał ~17 faktów na dobę przy zużyciu 3 |
| 4 | **Spiżarnia** | `tresc_zrodel.blok_do_promptu(korpus_kanalow(30))` | pobiera pełny tekst ośmiu **najnowszych** wpisów z 30 pierwszych (bez YouTube), najwyżej 2 z jednego źródła, po 2500 znaków; pamięta wynik 30 minut | 0 | **Tu zapada decyzja o temacie.** Na początku listy po dacie są blogi, które piszą najczęściej. Osiem miejsc po najwyżej dwa z bloga to zwykle cztery blogi. |
| 5 | Skaut | `znajdz_ciekawostki` → `llm.call("curiosity", …, web_search = not _tresc)` | V4.1 Flash; prompt `ciekawostki.md`, 5 losowych dziedzin z 46 i „najpierw pracuj na tych tekstach"; gdy wyjdą mniej niż 4 fakty, dokupuje wyszukiwaniem | ok. 0,01–0,03 USD za wywołanie (0,019 zmierzone 5.09) | **Przy pełnej spiżarni szukanie jest wyłączone.** Model ma pokryć np. „AI w szkołach", a dostaje osiem tekstów o infrastrukturze. 8.09 tylko 25% faktów dotyczyło zadanych dziedzin. |
| 6 | Kotwica | `znajdz_ciekawostki`, pole `z_kanalu` | fakt jest „z kanału", jeśli słowami pasuje do nagłówka z korpusu | 0 | Korpus to branża, więc „z kanału" znaczy branża. Fakt ze spiżarni jest zakotwiczony prawie zawsze, fakt o świecie z dokupionego szukania zwykle nie. |
| 7 | Odsiew | `dopisz_kandydatow` | bramka, bliźniaki, „już o tym pisaliśmy", model od powtórek | grosze | działa |
| 8 | Ranking | `posortuj_bank`, `prompts/bank.md` | model układa kolejkę; jako historię dostaje nasze notki mierzone **polubieniami + 3 × odpowiedzi** | ok. 0,5 USD/mies. (0,46 USD za 19 wywołań w 30 dni, pomiar 5.09) | Polubienia nie mówią nic o zapisach: korelacja −0,03 na 17 tys. notek (WriteStack), u nas płasko (audyt 3.09). Odwiedziny profilu i zapisy **mamy w danych**, ranking ich nie widzi. |
| 9 | Kolejka | `wez_kandydatow`: sort `(not z_kanalu, ranga)`, potem `wybierz_material` | bierze 8 z przodu kolejki; notka dostaje pierwszy, który nie zderza się z dzisiejszymi | 0 | Zakotwiczone, czyli branża, idą zawsze przed resztą, bez względu na rangę. Fakty o świecie czekają i po 7 dniach wygasają. |

Pisanie notki (rozbiór, notka, sprawdzenie faktów z wyszukiwaniem, naprawa) to
osobna część i ten raport jej nie zmienia.

### 1.2. Jeden łańcuch zamiast pięciu przyczyn

```
25 feedów, w tym 22 branżowe
   → 30 najnowszych wpisów (po dacie wygrywa ten, kto pisze najczęściej)
      → 8 tekstów, najwyżej 2 z jednego feedu  = zwykle 4 blogi
         → skaut bez wyszukiwania: „najpierw pracuj na tych tekstach"
            → fakty o tym, o czym piszą te 4 blogi
               → „z kanału" = TAK → zawsze na początku kolejki
                  → notka o branży
```

Każde ogniwo z osobna wygląda rozsądnie: oszczędza pieniądze (spiżarnia
zmniejszyła koszt skauta o 74%), pilnuje świeżości albo trzyma regułę
właściciela „trzy czwarte z kanałów". Razem dają jedną rzecz: bot pisze o tym,
o czym piszą cztery blogi techniczne.

### 1.3. Dlaczego pomiar z 8 września tego nie pokazał

Przyrząd `tests/platne/proba_tematow.py` woła `znajdz_ciekawostki` 5–10 razy
w jednym procesie. Spiżarnia pamięta swoją zawartość 30 minut, a przyrząd nie
czyści jej między próbami. Wszystkie próby dostały więc najpewniej te same osiem
tekstów, przy wyłączonym wyszukiwaniu.

Przyrząd nie wypisywał ani składu spiżarni, ani tego, czy szukanie było
włączone. Linia „spizarnia: tresc N zrodel — pisze BEZ platnego szukania" ginęła
w przechwyconym wyjściu. Stąd wniosek „model idzie tam, gdzie łatwo o dokument",
choć model nigdzie nie szedł.

Wniosek „dźwignią są źródła" jest dobry. Dokładniej: źródła **spiżarni**.

### 1.4. Co z tego wychodzi na koncie

| co | liczba | skąd |
|---|---|---|
| skład banku | 70% branża, 6% świat | `POMIAR_TEMATOW_2026-09-08.md` (punkt odniesienia z 7.09) |
| skąd fakty | 32 z 35 z czterech blogów | tamże |
| skąd zapisy | 5 z 6 zapisów w 30 dniach z notek | `ZRODLA_RUCHU_2026-09-02.md` |
| co działa w notkach | odwiedziny profilu na notkę: CIEKAWOSTKA 0,43, DYSKUSJA 0,25, SPROSTOWANIE 0,20, MYŚL 0,00 (małe próby, n = 4–7) | komentarz przy `NOTE_MIX_OTHER_DAY` w `config.py` |
| czym uczy się ranking | polubienia + 3 × odpowiedzi | `stages.co_zadzialalo` |

Ta miara już raz rozstrzygnęła: 7.09, przy przejściu na trzy notki, wypadł typ
MYŚL, bo jako jedyny miał zero odwiedzin profilu. Ranking tematów nadal patrzy
na polubienia.

---

## 2. Jak powinno być

Ta sama droga, zmienione tylko ogniwa, które decydują o temacie:

| # | etap | dziś | po zmianie | koszt |
|---|---|---|---|---|
| 1 | Korpus | 25 feedów, 22 branżowe | dochodzi `ZRODLA_LUDZIE`: 8–12 feedów o ludziach, każdy z etykietą `styk`. Wpisy z feedów ogólnych (KFF, FTC, Pew) wchodzą tylko po darmowym filtrze słów o AI. | 0 |
| 4 | Spiżarnia | 8 najnowszych z 30 pierwszych, najwyżej 2 z feedu | 8 miejsc z kwotą, dobieranych z **całego** korpusu, nie z 30 pierwszych: najwyżej 2 teksty branżowe, co najmniej 4 o ludziach (różne styki, 1 z feedu), reszta dowolna. Pierwszeństwo mają styki, których w banku nie było przez 3 dni. | 0 |
| 5 | Skaut | jedno wywołanie, bez szukania | bez zmian w modelu i w koszcie; każdy blok tekstu ma w nagłówku swój styk | tyle samo |
| 6 | Styk faktu | nie istnieje | kod przepisuje styk z tekstu, na który fakt się powołuje (po adresie, potem po hoście); bez dopasowania fakt dostaje „branża" | 0 |
| 6a | Kotwica | kotwica znaczy branża | nowe feedy są w korpusie, więc fakty o ludziach też są „z kanału" i reguła 3/4 zostaje (decyzja 1) | 0 |
| 8 | Ranking | historia = polubienia | historia = odwiedziny profilu + zapisy na 100 wyświetleń po 72 h, w tabeli po stykach | 0 (mniej tokenów) |
| 9 | Kolejka | branża zawsze pierwsza | co najmniej 1 z 3 notek dziennie spoza branży; gdy w banku nie ma nic spoza branży, log i branża | 0 |
| 10 | Nauka | brak | po 2 tygodniach kolejność styków ustala wynik (próbkowanie Thompsona), a każdy styk ma minimalny udział | 0 |

Limit „2 fakty z jednego hosta" z poprzedniego raportu jest niepotrzebny.
Spiżarnia z kwotą i kwota w kolejce dają to samo i nie wyrzucają opłaconych faktów.

### 2.1. Styki

| styk | o czym | źródła |
|---|---|---|
| `praca` | zatrudnienie, płace, jak ludzie pracują z AI | NBER, Rest of World; etap 2: Census BTOS |
| `zdrowie` | szpitale, pacjenci, ubezpieczenia | KFF Health News; etap 2: lista FDA |
| `szkola` | uczniowie, nauczyciele, dzieci | EdSurge, The 74 |
| `pieniadze` | oszustwa, kary dla firm, ceny | FTC, SEC |
| `prawo` | sądy, przepisy | Federal Register, CourtListener, Komisja UE, Transformer, Tech Policy Press; etap 2: baza orzeczeń |
| `codziennosc` | jak ludzie używają AI i co o nim myślą | Pew |
| `szkody` | wypadki i szkody z udziałem AI | AI Incident Database (już w korpusie) |
| `ludzie` | badania mieszane, gdy tytuł nie wskazuje styku | arXiv cs.CY i cs.HC; styk z darmowej mapy słów w tytule („students" → `szkola`, „patients" → `zdrowie`) |
| `branza` | modele, firmy, sprzęt, wydania | 22 dzisiejsze feedy i YouTube |

---

## 3. Skąd brać tematy

### 3.1. Etap 1: feedy i API, za darmo, bez klucza

Każdy adres sprawdza krok 0 na serwerze (tytuł feedu i data ostatniego wpisu,
nie sam kod odpowiedzi).

| źródło | styk | adres | co przynosi | przykład tematu (sprawdzony) |
|---|---|---|---|---|
| NBER, nowe prace | praca | `https://www.nber.org/papers.rss`; Labor Studies: `https://www.nber.org/programs/ls/papers.rss` | pomiary wpływu AI na pracę i płace, zanim trafią do prasy | „Firm Data on AI" (w34836, 2026): firmy przewidują, że AI zmniejszy zatrudnienie o 0,7% w trzy lata. Szefowie w USA mówią −1,2%, pracownicy +0,5%. 63% firm nie spodziewa się żadnego wpływu. |
| arXiv cs.CY i cs.HC | ludzie | `https://rss.arxiv.org/rss/cs.CY`, `https://rss.arxiv.org/rss/cs.HC` | badania o tym, jak ludzie używają AI; dziennie kilkadziesiąt prac, filtr słów zostawia kilka | przykłady wypisze krok 0 (w weekendy pusto) |
| FTC | pieniądze | `https://www.ftc.gov/feeds/press-release.xml` | kary i ugody z firmami AI, oszustwa | 1.07.2026 FTC zaproponowała zasady wobec „tłumienia dokładności" w systemach AI. Uwagi przyjmowała do 31.07, a ostateczna wersja to ciąg dalszy do pilnowania. |
| SEC | pieniądze | `https://www.sec.gov/news/pressreleases.rss` (User-Agent z adresem kontaktowym) | „AI washing", czyli kary za przechwałki o AI | typ tematu; przykłady wypisze krok 0 |
| Federal Register | prawo | API, już w kodzie (`korpus_fedreg`), dziś bez filtra na AI i tylko typ RULE | przepisy i zawiadomienia o AI | ten sam dokument FTC wyszedł tu 7.07.2026 jako FR 2026-13628 |
| CourtListener | prawo | `https://www.courtlistener.com/feed/search/?q=%22artificial+intelligence%22&type=o` (każde wyszukiwanie ma swój feed; format potwierdzi krok 0) | orzeczenia, w których sąd pisze o AI | przykłady wypisze krok 0 |
| KFF Health News | zdrowie | `https://kffhealthnews.org/feed/` (we wrześniu publiczny rejestr feedów zgłaszał awarie) | AI w szpitalach, u ubezpieczycieli, u pacjentów | 1.06.2026: oprogramowanie Sentri7, używane w setkach szpitali w USA, przez miesiące nie wykryło pielęgniarza kradnącego fentanyl (orzeczenie izby pielęgniarek w Tennessee). Szpitale nie muszą nikomu zgłaszać awarii takich systemów. |
| Pew Research Center | codzienność | `https://www.pewresearch.org/feed/` | co ludzie robią z AI i co o nim myślą | 16.09.2026: pierwszy raz Demokraci bardziej niż Republikanie boją się AI (56% wobec 49% „bardziej zaniepokojonych niż podekscytowanych"). 75% wobec 68% spodziewa się mniej miejsc pracy za 20 lat. Próba: 3 488 osób. |
| EdSurge, The 74 | szkoła | `https://www.edsurge.com/articles_rss`, `https://www.the74million.org/feed/` | AI w klasie, egzaminy, wykrywacze | typ tematu jak w badaniu RAND: 54% uczniów i 53% nauczycieli używa AI w szkole, a uczniowie boją się fałszywych oskarżeń o ściąganie |
| Rest of World | praca | `https://restofworld.org/feed/latest` (rejestr zgłaszał awarie) | ludzie, którzy robią AI i żyją z nim poza Zachodem | 2026: ludzie w Brazylii, Kambodży i na Filipinach ręcznie oznaczają każdy ruch na mundialu. Na tych danych uczą się algorytmy dla drużyn, telewizji i bukmacherów. |
| Tech Policy Press | prawo, praca | feed do ustalenia (`/feed/` albo `/rss/`, sprawdza krok 0) | polityka i ludzie wokół AI | 30.09.2026 Amazon zamyka Mechanical Turk po 21 latach. Na tej platformie ludzie ręcznie opisali zdjęcia do ImageNetu, zbioru, na którym w 2012 roku ruszyło głębokie uczenie. |

Już w korpusie, do oznaczenia stykiem: AI Incident Database (`szkody`),
Komisja UE (`prawo`), Transformer (`prawo`).

### 3.2. Etap 2: zbiory danych, raz w tygodniu, za darmo

Nowe wiersze w porównaniu z poprzednim tygodniem to gotowe fakty z liczbą:

- **Baza orzeczeń o zmyślonych przez AI cytatach (Damien Charlotin).** Plik CSV
  na licencji CC BY 4.0, 9 pól, w tym sąd, sankcja i kara. 18.06.2026 miała
  1 624 sprawy, ostatnio 2 079, czyli od czerwca przybyło około 450 orzeczeń.
  Styk: prawo.
- **FDA, lista urządzeń medycznych z AI.** CSV albo Excel, aktualizowana
  (ostatnio 16.06.2026), ponad 1 500 pozycji. Lista jest niepełna, bo FDA
  tworzy ją wyszukiwaniem słów. Nowy wiersz to temat „dopuszczono AI do X".
  Styk: zdrowie.
- **Census BTOS.** Co dwa tygodnie podaje odsetek firm używających AI:
  17–20% od grudnia 2025 do maja 2026, 37% w firmach od 250 osób,
  w informacji 39,7% i w finansach 33,9% przy średniej 19,8% (3.05.2026).
  Styk: praca.

### 3.3. Etap 3: sygnał popytu, za darmo

- **Wikipedia, wyświetlenia artykułów** (bez klucza). Skok wyświetleń hasła
  z faktu, np. „Amazon Mechanical Turk" po 25.08, znaczy, że ludzie o tym teraz
  czytają. Kod dopisuje to do rankingu jako flagę „popyt"; to nie jest bramka.
- **GDELT**: czy media o tym piszą, przydatne do tematów z ciągiem dalszym.
- **Czego nie brać jako sygnału:** Hacker News (gust inżynierów, czyli nasz
  dzisiejszy błąd). Reddita tylko ostrożnie, bo jego komercyjne API wymaga umowy.

### 3.4. Dlaczego te tematy są ciekawsze od dzisiejszych

Każdy przykład z 3.1 ma to, co według badań budzi ciekawość (szczegóły
w `SILNIK_TEMATOW`, rozdział 2):

- **dotyka życia czytelnika**: praca, szpital, szkoła dziecka, pieniądze;
- **coś już o tym wie, ale nie wszystko**: słyszał o AI w szpitalach, ale nie
  wie, że nikt nie zgłasza jego awarii;
- **ma liczbę i dokument**: 2 079 orzeczeń, 0,7% zatrudnienia, orzeczenie izby
  pielęgniarek;
- **ma odwrócenie albo lukę**: szefowie −1,2% wobec pracowników +0,5%; podział
  polityczny odwrócony w dwa lata.

Dzisiejsza notka o nowej wersji biblioteki ma liczbę i dokument, ale nie
dotyka życia czytelnika, który „nic nie wie o tej technologii". Tak
zresztą opisuje go nasz własny `notka.md`.

---

## 4. Jak to zrobić, krok po kroku

### Krok 0. Dziś, 0 USD, na serwerze

```
.venv/bin/python agent-v2/pomiary/zrodla_ludzie.py --kontakt <adres e-mail>
.venv/bin/python agent-v2/audyt_tematow.py
.venv/bin/python agent-v2/karta_wynikow.py
```

Pierwsze polecenie (nowy plik w tym commicie) robi trzy rzeczy bez żadnego
wywołania modelu i bez zapisu na dysk:

1. podaje koszt etapów wyboru tematu z ostatnich 30 dni, tylko z przebiegów
   produkcyjnych;
2. pokazuje, które osiem tekstów spiżarnia wzięłaby **teraz**, z jakich źródeł
   i z jakim stykiem. To bezpośredni sprawdzian diagnozy z rozdziału 1;
3. sprawdza każde nowe źródło: czy odpowiada, czy to feed, czy przeczyta go nasz
   parser, datę ostatniego wpisu, liczbę wpisów o AI z 30 dni i trzy przykładowe
   tytuły. Na końcu drukuje gotowe wpisy do `ZRODLA_LUDZIE`.

Dwa pozostałe polecenia zapisują punkt odniesienia: stan banku, zasięg po 72 h,
zapisy przypisane notkom i koszt.

### Krok 1. Źródła ze stykiem (`korpus_kanalow.py`)

```python
# ZRODLA O LUDZIACH. Wpisujemy tylko adresy, ktore `pomiary/zrodla_ludzie.py`
# oznaczyl na serwerze jako DZIALA: tytul feedu i data ostatniego wpisu, nie
# sam kod odpowiedzi.
ZRODLA_LUDZIE = {
    "NBER":       ("https://www.nber.org/papers.rss", "praca"),
    "KFF Health": ("https://kffhealthnews.org/feed/", "zdrowie"),
    "FTC":        ("https://www.ftc.gov/feeds/press-release.xml", "pieniadze"),
    "Pew":        ("https://www.pewresearch.org/feed/", "codziennosc"),
    "EdSurge":    ("https://www.edsurge.com/articles_rss", "szkola"),
    # ... tylko to, co krok 0 oznaczyl jako DZIALA
}
STYK_ZRODLA = {"Wpadki AI": "szkody", "Komisja UE": "prawo",
               "Transformer": "prawo"}
STYK = {**{n: s for n, (_, s) in ZRODLA_LUDZIE.items()}, **STYK_ZRODLA}

# korpus_kanalow(): druga petla jak ta dla ZRODLA, z jedna roznica: wpis
# z ZRODLA_LUDZIE wchodzi tylko, gdy FILTR_AI (ten z pomiaru) trafia w tytul
# albo opis. KFF, FTC i Pew pisza tez o innych rzeczach.
# przetworz(): kazdy wpis dostaje "styk": STYK.get(kanal, "branza").
```

Jeśli krok 0 zgłosi „parser `korpus_kanalow` zobaczy tu ZERO wpisów" (feed
RSS 1.0, np. starszy format arXiv), parser trzeba rozszerzyć o `item`
w przestrzeni nazw RSS 1.0. Pomiar ma już taki parser (`wpisy_feedu`).

### Krok 2. Spiżarnia z kwotą (`tresc_zrodel.py`, wywołanie w `stages.py`)

```python
# stages.znajdz_ciekawostki — spizarnia wybiera z CALEGO korpusu, nie z 30
# pierwszych: feed o ludziach pisze rzadziej niz Simon Willison i w pierwszej
# trzydziestce po dacie zwykle go nie ma.
_tresc = _tz.blok_do_promptu(korpus_kanalow.korpus_kanalow(200))

# tresc_zrodel.tresci_zrodel — kolejnosc zamiast "osiem najnowszych":
MAKS_BRANZA = 2      # najwyzej tyle tekstow branzowych na osiem
MIN_LUDZIE = 4       # co najmniej tyle spoza branzy, jesli sa w korpusie
# 1. ludzie: po jednym z kazdego zrodla; styki, ktorych nie bylo w banku
#    przez 3 dni, na poczatek; w obrebie styku najnowsze;
# 2. branza: najwyzej MAKS_BRANZA, najwyzej 2 z jednego zrodla, jak dzis;
# 3. dopelnienie tym, co zostalo.
# Petla pobierania bez zmian (HTTP, `_warto`, 0,4 s przerwy).
# blok_do_promptu: kazdy blok dostaje wiersz "Touchpoint: <styk>".
# Nowa funkcja `ostatnie_tresci()` oddaje liste z _ZAPAS, zeby krok 3
# widzial, z ktorego tekstu jest ktory adres.
```

### Krok 3. Styk w banku (`stages.znajdz_ciekawostki`, `dopisz_kandydatow`)

```python
# Po odpowiedzi modelu. NIE PYTAMY MODELU O STYK: kod przepisuje go ze zrodla,
# tak jak `z_kanalu` (ta sama zasada: "kod liczy, model nie ma jak sciemnic").
_po_adresie = {z["url"]: z["styk"] for z in _tz.ostatnie_tresci()}
_po_hoscie = {host(u): s for u, s in ADRESY_STYKOW.items()}  # z ZRODLA_LUDZIE
for f in fakty:
    f["styk"] = (_po_adresie.get(f.get("url"))
                 or _po_hoscie.get(host(f.get("url")))
                 or "branza")

# dopisz_kandydatow: DOPISAC RECZNIE "styk": str(k.get("styk") or "branza")
# obok "z_kanalu". Pola indeksu ida z KSZTALT_CIEKAWOSTEK, a styk liczy kod PO
# odpowiedzi modelu. Bez recznego wpisu zginie przy zapisie, dokladnie tak jak
# `z_kanalu` (komentarz „KOTWICA MUSI PRZEZYC ZAPIS").
```

### Krok 4. Kwota w kolejce (`stages.wez_kandydatow`, `run.py`)

```python
swiezi.sort(key=lambda p: (not p[0].get("z_kanalu"), p[0].get("ranga", 10 ** 6)))
# KWOTA DNIA: co najmniej jedna notka dziennie spoza branzy.
if not _dzis_byla_spoza_branzy():        # styk dzisiejszych notek z dziennika
    i = next((i for i, (k, _) in enumerate(swiezi)
              if (k.get("styk") or "branza") != "branza"), None)
    if i is None:
        print("  [kwota] w banku nie ma nic spoza branzy — ide z branza")
    else:
        swiezi.insert(0, swiezi.pop(i))
```

`run.py` przy zapisie wystawionej notki do dziennika dopisuje `styk` faktu.
Bez tego kwota nie ma czego liczyć.

Przy okazji ożyje `seria.py`. Seria startuje tylko na temacie, który bank
wyżywi na cztery części, i 6.09 taki temat był jeden („Prąd i data centre").
„AI w pracy", „AI w medycynie" i „AI w szkole" miały po 0–1 faktów. To są
dokładnie nowe styki.

### Krok 5. Miara, która mówi o zapisach (`stages.co_zadzialalo`)

```python
# Bylo: punkty = polubienia + 3 * odpowiedzi.
# Jest: na 100 wyswietlen, pomiar najblizszy 72 h (jak karta_wynikow.zasieg_72h):
#   wynik = 100 * (odwiedziny_profilu + 5 * zapisy_przypisane) / wyswietlenia
# odwiedziny_profilu: pole w `statystyki` (zbierane przy kazdej notce),
# zapisy_przypisane:  `zrodla.jsonl` -> podsumowanie.zapisy_per_notka
#                     (to samo, co czyta karta_wynikow.zapisy).
# Do bank.md idzie TABELA PO STYKACH zamiast listy notek:
#   styk      notek  wysw. 72 h (med.)  odwiedziny+zapisy /100
#   zdrowie     5          38                  3,1
#   branza     24          31                  1,0
```

Waga 5 dla zapisu to punkt startowy. Zapis jest celem, a odwiedziny profilu
tylko krokiem przed nim.

### Krok 6. Przyrząd, który widzi spiżarnię (`tests/platne/proba_tematow.py`)

- Przed każdą próbą `tresc_zrodel.wyczysc_zapas()`, żeby próby nie jechały na
  tych samych ośmiu tekstach.
- Wypisywać skład spiżarni (źródła i styki) i to, czy szukanie było włączone.
- Liczyć udział faktów spoza branży i liczbę różnych hostów.
- `--live --ile 5` przed zmianą i po niej kosztuje około 0,1–0,2 USD każde.

### Krok 7. Po dwóch tygodniach, 0 USD

- **Kolejność styków z wyników.** Próbkowanie Thompsona na mierze z kroku 5,
  z minimalnym udziałem każdego styku, żeby żaden nie zniknął przez pechowy
  tydzień.
- **Etap 2 źródeł.** Tygodniowe różnice w bazie orzeczeń, na liście FDA
  i w BTOS.
- **Etap 3.** Wikipedia jako flaga „popyt" w rankingu.

---

## 5. Ile to kosztuje

| pozycja | dziś | po zmianie | skąd liczba |
|---|---|---|---|
| pobieranie korpusu i spiżarni | 0 | 0 (plus ok. 15–30 zapytań HTTP na przebieg) | HTTP |
| skaut, 1 wywołanie na dobę, bez wyszukiwania | ok. 0,3–0,9 USD/mies. | tyle samo | 0,019 USD za wywołanie (`KOSZT_2026-09-05.md`); V4.1 Flash kosztuje 0,15/0,60 USD za mln tokenów poza szczytem, w szczycie dwa razy więcej |
| dokupienie wyszukiwaniem, gdy spiżarnia da < 4 fakty | rzadko, ok. 0,01–0,04 USD | rzadziej, bo spiżarnia z kilku styków daje więcej materiału | `MODELE_I_WYSZUKIWANIE_2026-09-13.md` §9 |
| ranking banku | ok. 0,5 USD/mies. | tyle samo albo mniej (tabela zamiast próbek notek) | `KOSZT_2026-09-05.md` |
| parowanie bliźniaków | ok. 0,3 USD/mies. (tylko gdy bank się zmienił) | tyle samo | komentarz w `sparuj_bank` |
| styk, kwota, nowa miara | nie ma | 0 (kod) | |
| **razem wybór tematu** | **ok. 1–2 USD/mies.** | **ok. 1–2 USD/mies.** | do 5% budżetu 40 USD |
| jednorazowo: pomiar przed i po | | ok. 0,2–0,4 USD | krok 6 |

Dokładną liczbę z produkcji podaje krok 0 (sekcja „KOSZT WYBORU TEMATU").

**Dlaczego to najtańsza droga.** Porównanie z innymi pomysłami:

| wariant | dodatkowy koszt | co daje |
|---|---|---|
| **A. Ta sama jedna rozmowa, inne teksty (proponowany)** | **0 USD** | kontrola składu w kodzie, fakty z dokumentów |
| B. Codzienne płatne wyszukiwanie w skaucie | ok. 0,3–1,2 USD/mies. | mniej kontroli; zmierzone, że szukanie ciągnie do prasy technicznej |
| C. Osobny skaut na każdy styk (5 wywołań na dobę) | ok. 1,5–4 USD/mies. | to samo co A, pięć razy drożej |
| D. Płatne API newsów albo trendów | abonament | niepotrzebne: dokumenty są za darmo |

---

## 6. Jak sprawdzimy, że działa

| kiedy | co | próg |
|---|---|---|
| przed wdrożeniem (krok 6, ok. 0,2 USD) | skład faktów z 5 prób | co najmniej 50% faktów ze stykiem innym niż branża (ten sam przyrząd 8.09 liczył „świat" na 2–5%); co najmniej 6 różnych źródeł na 8 tekstów spiżarni (dziś 4) |
| po 14 dniach na poligonie (0 USD) | udział wystawionych notek spoza branży | co najmniej 1 z 3 |
| po 14 dniach, `karta_wynikow.py` co tydzień | odwiedziny profilu + zapisy na 100 wyświetleń: notki spoza branży wobec branżowych | spoza branży nie gorsze; całe konto nie gorsze niż przed zmianą |

**Uczciwie o próbie.** 14 dni po 3 notki to 42 notki, z czego około 14 spoza
branży. To wystarczy, żeby zobaczyć dużą różnicę, np. dwukrotną. Na niewielką
nie wystarczy. Dlatego po dwóch tygodniach decydujemy tylko „zostaje albo
cofamy", a proporcje ustawi dopiero krok 7.

Przeniesienie do NIA: po dwóch tygodniach, jeśli progi przeszły. Zgodnie
z decyzją z 26.09 zmiana idzie najpierw na poligon, a do produkcji tylko sprawdzona.
Wdrożenie NIA wyłącznie przez `robocze/wdroz_nia_recznie.sh` z komputera
właściciela, nigdy przez `wdroz.sh` z repozytorium NIA.

---

## 7. Decyzje właściciela

1. **Czy nowe źródła o ludziach liczą się jako „kanały" w regule 3/4?**
   Rekomendacja: tak. To też datowane źródła, które konto obserwuje. Bez tego
   reguła trzyma bota w branży, bo `wez_kandydatow` stawia zakotwiczone przed
   resztą.
2. **Kwota: co najmniej 1 z 3 notek dziennie spoza branży.** Rekomendacja: tak,
   na dwa tygodnie próby.
3. **Miara tematu: odwiedziny profilu + zapisy zamiast polubień.** Rekomendacja:
   tak. Ta miara już raz rozstrzygnęła, który typ notki wypada (MYŚL, 7.09).
4. **Kolejność: najpierw poligon, potem NIA.** Rekomendacja: tak, zgodnie
   z decyzją z 26.09.

---

## 8. Czego nie robić

- **Nie włączać codziennego płatnego wyszukiwania „dla różnorodności".**
  Zmierzone, że szukanie ciągnie do prasy technicznej, a spiżarnię da się
  ułożyć w kodzie.
- **Nie pozwalać modelowi nadawać styku.** Kod bierze go ze źródła, tak jak
  `z_kanalu`.
- **Nie dokładać kanałów YouTube.** Serwer jest blokowany, a spiżarnia i tak
  ich nie czyta.
- **Nie wycinać branży.** Ma być najwyżej 2 z 8, nie zero: premiery modeli to
  też nasz temat.
- **Nie traktować liczby polubień jako sukcesu tematu.**

---

## 9. Źródła

**Nasz kod i pomiary:**

- `agent-v2/stages.py`: `znajdz_ciekawostki` (spiżarnia i `web_search = not
  _tresc`), `dopisz_kandydatow`, `posortuj_bank`, `co_zadzialalo`,
  `wez_kandydatow`, `wybierz_material`, `sparuj_bank`
- `agent-v2/tresc_zrodel.py`, `agent-v2/korpus_kanalow.py`, `agent-v2/config.py`
  (`BANK_*`, `SZUKANIE_BANKU_*`, `NOTE_MIX_OTHER_DAY`, `MODEL_FOR`, cennik),
  `agent-v2/karta_wynikow.py`, `agent-v2/statystyki.py`,
  `agent-v2/tests/platne/proba_tematow.py`
- `docs/POMIAR_TEMATOW_2026-09-08.md`, `docs/KOSZT_2026-09-05.md`,
  `docs/ZRODLA_RUCHU_2026-09-02.md`, `docs/SERIE_TEMATYCZNE_2026-09-06.md`,
  `agent-v2/docs/MODELE_I_WYSZUKIWANIE_2026-09-13.md`,
  `agent-v2/docs/SILNIK_TEMATOW_2026-09-26.md`

**Przykłady tematów i źródła:**

- NBER w34836 „Firm Data on AI": https://www.nber.org/papers/w34836
- FTC, 1.07.2026: https://www.ftc.gov/news-events/news/press-releases/2026/07/ftc-seeks-public-comment-policy-statement-addressing-ai-accuracy
  (Federal Register 2026-13628: https://www.federalregister.gov/documents/2026/07/07/2026-13628/policy-statement-concerning-the-suppression-of-accuracy-in-artificial-intelligence-systems)
- KFF Health News, Sentri7: https://kffhealthnews.org/health-industry/ai-drug-diversion-theft-artificial-intelligence-hospitals-sentri7-software-tennessee/
- Pew, 16.09.2026: https://www.pewresearch.org/short-reads/2026/09/16/democrats-are-now-more-worried-than-republicans-about-ai-and-its-impact-on-jobs/
- Rest of World, mundial: https://restofworld.org/2026/fifa-world-cup-ai-data-workers/
- Mechanical Turk: https://www.cnbc.com/2026/08/25/amazon-service-that-jeff-bezos-called-artificial-ai-is-shutting-down.html,
  https://www.techpolicy.press/mechanical-turk-is-closing-the-workers-who-built-ai-are-still-here/
- Baza orzeczeń: https://www.damiencharlotin.com/hallucinations/
- FDA: https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-enabled-medical-devices
- Census BTOS: https://www.census.gov/library/stories/2026/05/ai-use-businesses.html
- Feedy: https://www.courtlistener.com/feeds/ (feed z każdego wyszukiwania),
  https://www.sec.gov/about/rss-feeds, https://kffhealthnews.org/rss-feeds/,
  https://www.edsurge.com/articles_rss
