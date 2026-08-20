
| stała | wartość | po co |
|---|---|---|
| `AGENT_DIR` | `Path(__file__).resolve().parent` | — |
| `REPO_ROOT` | `AGENT_DIR.parent` | — |
| `ENV_PATH` | `AGENT_DIR / ".env"` | — |
| `DATA_DIR` | `AGENT_DIR / "data"` | — |
| `DB_PATH` | `DATA_DIR / "agent-v2.db"` | — |
| `PROMPTS_DIR` | `AGENT_DIR / "prompts"` | — |
| `ARTICLES_DIR` | `DATA_DIR / "articles"` | — |
| `STYLE_CORPUS` | `PROMPTS_DIR / "styl" / "article_style_sample` | Korpus stylu. Przypięty hashem, bo to jedyna rzecz odróżniająca to konto od tysiąca innych — loader ma odmówić, jeśli ktoś po cichu podmieni głos, na  |
| `STYLE_CORPUS_SHA256` | `"d4e4e6bf928421d6a0eed6a6cafc796807ea289b275` | — |
| `STYLE_PROFILES_DIR` | `REPO_ROOT / "instrukcja dla pisania artykulo` | — |
| `ANTHROPIC_API_KEY` | `_env("ANTHROPIC_API_KEY")` | — |
| `DEEPSEEK_API_KEY` | `_env("DEEPSEEK_API_KEY")` | — |
| `OPENAI_API_KEY` | `_env("OPENAI_API_KEY")   # wylacznie do graf` | — |
| `IMAGE_MODEL` | `"gpt-image-1.5"` | Grafika do artykulu. Wybor NIE jest podyktowany cena: przy jednym obrazie na artykul nawet najdrozsza opcja to grosze miesiecznie, a taniej znaczy tu  |
| `IMAGE_SIZE` | `"1536x1024"` | — |
| `IMAGE_QUALITY` | `"high"` | — |
| `IMAGE_PRICE_USD` | `0.04   # cennik sierpien 2026, NIEPOTWIERDZO` | — |
| `IMAGE_TIMEOUT_S` | `300` | — |
| `SUBSTACK_HANDLE` | `"nothingisaccidental"` | Konto na Substacku. |
| `WYLACZ_WYKRYWANIE_AI` | `True` | Czy agent ma klikac "Wylacz wykrywanie AI" przy kazdej publikacji. WLACZONE decyzja wlasciciela z 2026-08-15. To wybor publiczny, nie ustawienie techn |
| `DRY_RUN` | `_env("DRY_RUN", "false").lower() in {"1", "t` | — |
| `KILL_SWITCH` | `_env("KILL_SWITCH", "false").lower() in {"1"` | — |
| `NO_LIMIT` | `_env("AGENT_V2_NO_LIMIT", "0").lower() in {"` | — |
| `TRYB_SERWERA` | `_env("AGENT_V2_SERVER", "0").lower() in {"1"` | Serwer bez ekranu: zamiast podlaczac sie do Chrome'a uruchomionego przez czlowieka, agent otwiera wlasna przegladarke bez ekranu i wklada jej zapisana |
| `CLAUDE` | `"claude-opus-5"` | — |
| `SONNET` | `"claude-sonnet-5"` | — |
| `FABLE` | `"claude-fable-5"  # najmocniejszy, dwa razy ` | — |
| `DEEPSEEK` | `"deepseek-v4-flash"` | — |
| `DEEPSEEK_PRO` | `"deepseek-v4-pro"  # ma server-side web_sear` | — |
| `MODEL_FOR` | `{ …` | Decyzja właściciela 2026-08-15: DeepSeek do wszystkiego poza pisaniem. Pisanie zostaje u Opusa 5, bo to jest produkt. |
| `DEEPSEEK_BASE_URL` | `"https://api.deepseek.com"` | — |
| `DEEPSEEK_EFFORT` | `"low"` | Głębokość rozumowania DeepSeeka na /responses. Tokeny rozumowania liczą się do sufitu wyjścia, więc przy `high` model kończy budżet na szukaniu i nie  |
| `CHEAP_MODE` | `_env("AGENT_V2_CHEAP", "0").lower() in {"1",` | Tryb tani: wszystko na DeepSeeku. Do testowania HYDRAULIKI — czy łańcuch przechodzi, czy JSON się parsuje, czy zapis działa. Przebieg kosztuje wtedy g |
| `BEZ_TOKENOW` | `{"obraz"}` | — |
| `PRICING` | `{ …` | — |
| `STAWKI_PRZED_PODWYZKA` | `{ …` | --- taryfa szczytowa DeepSeeka ----------------------------------------------- Od 2026-08-16 16:00 UTC DeepSeek wprowadza ceny szczytowe i pozaszczyto |
| `TARYFA_SZCZYTOWA_OD` | `"2026-08-16T16:00:00+00:00"` | — |
| `GODZINY_SZCZYTU_UTC` | `frozenset(range(1, 4)) \| frozenset(range(6, ` | — |
| `MNOZNIK_SZCZYT` | `2.0` | Mnozniki wzgledem stawek wyzej, po wejsciu nowej taryfy. Szczyt to DOKLADNIE dwukrotnosc bazy, jednakowo dla wejscia, wyjscia i cache. Sprawdzone na f |
| `MNOZNIK_POZA_SZCZYTEM` | `1.0   # baza to juz stawka po podwyzce` | — |
| `WEB_SEARCH_TOOL` | `{ …` | Filtrowanie dynamiczne (`_20260209`) jest na Opusie i Sonnecie 5. |
| `WEB_SEARCH_USD_PER_1K` | `10.00` | Wyszukiwanie po stronie Anthropic: USD za 1000 zapytań. |
| `DAILY_LIMIT_USD` | `5.00` | — |
| `MONTHLY_LIMIT_USD` | `40.00` | — |
| `PONOWIENIA` | `2` | Sufit na JEDEN przebieg. Działa ZAWSZE, także przy AGENT_V2_NO_LIMIT=1. „Bez limitu na budowę" miało znaczyć „nie blokuj eksperymentów", a nie „pozwól |
| `PONOWIENIE_ODSTEP_S` | `8` | — |
| `RUN_LIMIT_USD` | `1.60` | — |
| `TOPIC_COUNT` | `6` | --- skaut i różnorodność ---------------------------------------------------- |
| `DIVERSITY_LOOKBACK` | `5` | — |
| `DISCOVERY_MAX_RESULTS` | `10` | --- dyskoveria -------------------------------------------------------------- 10, nie 6. Odsiew przy pobieraniu jest brutalny: martwe adresy (404), bl |
| `DISCOVERY_MAX_SEARCHES` | `8` | Zmierzone na jednym trudnym temacie (szpara pod drzwiami kabiny): 31 rund -> 7 organizacji, 6 pierwotnych, $1,33 (bez limitu, przeciek) 6 rund -> 1 or |
| `FEDREG_MAX_ZNAKOW` | `60_000` | Ponizej tylu POBRANYCH zrodel uruchamiamy druga runde dyskoverii, zanim tekst pojdzie do pisarza. Prog z danych, nie z przeczucia: artykuly, ktore wys |
| `MIN_ZRODEL_DO_PISANIA` | `4` | — |
| `MIN_PRIMARY_SOURCES` | `2  # wymóg właściciela: w korpusie ≥2 dokume` | — |
| `MIN_WHY_SOURCES` | `2  # ≥2 źródła mówiące DLACZEGO, nie tylko t` | — |
| `BLOCKED_HOSTS` | `( …` | Hosty, które serwują automatom CAPTCHA albo są płatne. Nie omijamy blokad — wykrywamy je i nie marnujemy na nie zapytań. |
| `CLASSIFY_MAX_INPUT_CHARS` | `90_000` | --- klasyfikacja ------------------------------------------------------------ |
| `CLASSIFY_MAX_EXCERPTS` | `12` | — |
| `CLASSIFY_MAX_EXCERPT_CHARS` | `700` | — |
| `CARD_MIN_CONFIRMED` | `5` | --- karta dowodowa ---------------------------------------------------------- |
| `CARD_MAX_CONFIRMED` | `8` | — |
| `CARD_MAX_UNCERTAIN` | `3` | — |
| `CARD_MAX_CONTRADICTIONS` | `3` | — |
| `CARD_MIN_NUMBERS` | `3` | — |
| `CARD_MAX_NUMBERS` | `8` | — |
| `CARD_MAX_CLAIM_CHARS` | `240` | — |
| `DLUGOSC_WG_GLEBOKOSCI` | `{ …` | Zmierzone na dziewięciu artykułach: przy „cel 1075, zakres 950-1250" model kotwiczył się przy górnej granicy (średnia 1212). Sufit obniżony, a prompt  |
| `TARGET_WORDS` | `1075` | — |
| `MIN_WORDS` | `950` | — |
| `MAX_WORDS` | `1200` | — |
| `BUDZET_ZASTRZEZEN` | `1` | Ile razy w jednym tekscie wolno powiedziec „moim zdaniem" i pochodne. Znakowanie wnioskowania jest DOBRE — recenzent wprost go chce, bo dzieki niemu s |
| `NASYCENIE_OD_ILU` | `2` | Od ilu ZNANYCH ISTNIEJACYCH TEKSTOW temat uznajemy za nasycony. Skaut wymienia, co jego zdaniem juz o danym temacie napisano — i uzywamy jego pamieci  |
| `PRECEDENSOW_NA_ARTYKUL` | `2` | ILE UDOKUMENTOWANYCH AWARII ROBI Z TEMATU ARTYKUL. To jest kryterium, ktorego nie mielismy w ogole, i to przez jego brak wychodzily tematy wielkosci n |
| `ZASIEGI_ARTYKULOWE` | `("AN_INDUSTRY", "A_COUNTRY")` | KOGO WIAZE WYNIK. Drugie brakujace kryterium i drugi powod, dla ktorego tematy wychodzily mialkie. Zepsuta maszyna do glosowania to piecset glosow w j |
| `ILE_TEKSTOW_DO_POROWNANIA_FORMY` | `4` | Ile ostatnich artykulow porownuje bramka ODCISK_FORMY. |
| `SLOW_NA_BEAT` | `150` | Ile slow moze przypadac na jedno NOWE twierdzenie. Beat to zdanie, po ktorym czytelnik wierzy w cos innego niz zdanie wczesniej; powtorzenie tej samej |
| `ARTICLE_LANGUAGE` | `"English"` | Artykuł powstaje po angielsku — konto jest anglojęzyczne. |
| `CHARS_PER_TOKEN` | `3.5` | Zachowawczo, żeby sufit był raczej za duży niż za mały. Zmierzone na starym agencie: CJK 2,19x, cyrylica 1,41x; dla angielskiego 3,5 znaku na token z  |
| `JSON_OVERHEAD_TOKENS` | `1200` | Ile tokenów zajmuje rusztowanie JSON-a, klucze i pola opisowe poza samą treścią. |
| `THINKING_HEADROOM_TOKENS` | `28000` | Myślenie na Opusie 5 jest domyślnie włączone, liczy się jak tokeny wyjściowe i NIE jest częścią kontraktu — więc sufit wyliczony z samego kontraktu po |
| `EFFORT` | `{ …` | Głębokość myślenia. Jawnie, bo domyślne `high` na Opusie 5 potrafi podwoić rachunek za wyjście bez pytania. |
| `MAX_TOKENS` | `{ …` | — |
| `NOTE_MIN_WORDS` | `33` | --- notki i komentarze ------------------------------------------------------ Zmierzone na publicznych analizach Substacka: 33-64 słowa dają najwyższe |
| `NOTE_MAX_WORDS` | `64` | — |
| `NOTE_CANDIDATES` | `1` | Ilu kandydatów generujemy, żeby wybrać jednego. Sensowne tylko dlatego, że DeepSeek kosztuje grosze — u Fable'a byłoby to nie do obronienia. Trzech ka |
| `DZIEDZINY_CIEKAWOSTEK` | `( …` | Ile ciekawostek szukamy naraz. Cztery z pięciu notek dziennie stoją na nich, a jedno szukanie kosztuje tyle co jedno — więc bierzemy zapas na kilka dn |
| `ILE_DZIEDZIN_NA_PRZEBIEG` | `5` | — |
| `CURIOSITY_BATCH` | `8` | — |
| `CURIOSITY_MEMORY` | `60` | Ile ostatnio zuzytych faktow pokazujemy szukajacemu jako zakaz powtorki. Bez tego to samo szukanie codziennie oddaje te same slynne osiem. |
| `COMMENT_CANDIDATES` | `3` | — |
| `DLUGOSCI_WYPOWIEDZI` | `( …` | DLUGOSC KOMENTARZA I ODPOWIEDZI losowana osobno za kazdym razem. Sam prompt tego nie zalatwi: proszony o roznorodnosc model i tak osiada w waskim pasi |
| `POSTAWY_KOMENTARZA` | `{ …` | SPOSOB OTWARCIA, losowany tak samo jak dlugosc i z tego samego powodu. Zmierzone na naszych wlasnych komentarzach: SIEDEM Z DZIEWIECIU zaczynalo sie o |
| `OTWARCIA` | `( …` | — |
| `COMMENTS_PER_DAY` | `4` | Sufit dzienny. Research mówi, że trzy przemyślane komentarze tygodniowo biją piętnaście uprzejmych; pierwotne 15-20 dziennie było z planu sprzed danyc |
| `NOTE_FORMS` | `{ …` | Typy notek. W dniu publikacji artykułu lecą notki typu ARTYKUL z linkiem; w pozostałe dni — pozostałe typy, oparte na fragmentach, których artykuły ni |
| `NOTE_FORM_MIX` | `("SCENA", "KONTRAST", "ZACZEP_I_KONKRET", "P` | — |
| `NOTE_TYPES` | `{ …` | — |
| `PUBLISH_TIMEZONE` | `"America/New_York"` | Strefa czasowa publikacji. Liczy się strefa CZYTELNIKÓW, nie właściciela: konto jest anglojęzyczne, więc publiczność jest głównie amerykańska, a dane  |
| `BEST_NOTE_HOURS` | `(6, 7, 8)  # ET — NIEUZYWANE` | UWAGA: CZTERY PONIZSZE STALE NIE SA UZYWANE PRZEZ ZADNA LINIE KODU. Agent wystawia notki rownomiernie w calym oknie OKNO_PUBLIKACJI_ET (6-22 ET), z lo |
| `WORST_NOTE_HOURS` | `(12, 13)  # ET, zwłaszcza w piątek` | — |
| `BEST_NOTE_DAYS` | `("sunday", "saturday")` | — |
| `OKNO_PUBLIKACJI_ET` | `(6, 22)        # wolno od 6:00 do 21:59 czas` | TWARDE OKNO PUBLIKACJI, w czasie CZYTELNIKOW. Agent wystawil notki o 03:57 i 04:00 UTC — czyli 23:57 i polnoc w Nowym Jorku. Tekst wrzucony, gdy publi |
| `WORST_NOTE_DAYS` | `("monday", "friday")` | — |
| `NOTEK_PROMUJACYCH` | `3` | Rozkład na tydzień: pięć notek dziennie, dzień publikacji artykułu ma własny. Ile notek promuje jeden artykul i przez ile dni. Decyzja wlasciciela z 2 |
| `NOTE_MIX_ARTICLE_DAY` | `("ARTYKUL", "ARTYKUL", "CIEKAWOSTKA", "DYSKU` | — |
| `NOTE_MIX_OTHER_DAY` | `("CIEKAWOSTKA", "CIEKAWOSTKA", "DYSKUSJA", "` | — |
| `LAJKI_DZIENNIE` | `(10, 16)` | --- zachowanie spoleczne: widelki, nie stale liczby ------------------------- Stala liczba dziennie wyglada jak robot, bo czlowiek nie ma normy. Losuj |
| `KOMENTARZE_DZIENNIE` | `(8, 12)     # 0 jest dozwolone: milczenie bi` | Osiemnascie komentarzy dziennie pod cudzymi tekstami to nie jest tempo czytelnika, tylko podpis bota — i kosztuje najwiecej po pisaniu, bo kazdy to tr |
| `FOLLOW_MIESIECZNIE` | `(20, 30)     # obserwowanie to czytanie, nie` | Obserwacje wykonywaly sie ZERO razy przez piec dni przy budzecie 30-44 miesiecznie. Przyczyna nie byla w liczbie, tylko w kolejnosci blokow — patrz `r |
| `SUBSKRYPCJE_MIESIECZNIE` | `(6, 12)  # laduje w skrzynce wlasciciela, wi` | — |
| `CICHY_DZIEN_NA_ILE` | `8          # srednio jeden na osiem dni` | ODBLOKOWANE decyzja wlasciciela 2026-08-19. Restack cudzej notki z wlasnym zdaniem trafia do kanalu NASZYCH obserwujacych, powiadamia autora oryginalu |
| `CICHE_DNI_WLACZONE` | `True` | — |
| `RESTACK_DZIENNIE` | `(1, 2)` | Zjechane z 2-4 na 1-2 (2026-08-20). Restack stawia NASZE nazwisko obok cudzego tekstu — to najmocniejszy gest w calym repertuarze i jedyny, ktory firm |
| `RESTACK_MAX_SLOW` | `40` | Dopisek do cudzej notki. Powyzej tego to juz nie dopisek, tylko wlasna notka doczepiona do czyjegos tekstu — a wtedy lepiej napisac wlasna notke. |
| `PRZEBIEGOW_DZIENNIE` | `3` | Pierwszy miesiac na dolnej polowie widelek. Nowe konto z jednym artykulem, ktore nagle obserwuje dwadziescia osob, wyglada dokladnie jak farma. Ile ra |
| `LIMIT_CZASU_PRZEBIEGU_S` | `9000` | ILE CZASU MA PRZEBIEG. Musi zgadzac sie z `TimeoutStartSec` w pliku uslugi — to jedyne miejsce, gdzie ta sama liczba stoi dwa razy, i pilnuje tego tes |
| `ZAPAS_CZASU_S` | `900` | Zapas na domkniecie: ostatnia publikacja, zamkniecie przebiegu, alarm. |
| `ROZBIEG_DNI` | `30` | — |
| `ODSTEPY` | `{ …` | Odstepy miedzy dzialaniami, w sekundach. Pietnascie polubien w dziewiecdziesiat sekund to nie jest czytanie i kazdy system to widzi. Odstepy ROZNE dla |
| `ODSTEP_MIEDZY_DZIALANIAMI` | `(45, 180)   # zapas dla czynnosci bez wlasne` | — |
| `ZWLOKA_PRZED_NOTKAMI` | `(0, 2400)        # 0-40 min` | ZWLOKA PRZED PIERWSZA NOTKA PRZEBIEGU. Bez niej pierwsza notka wychodzila zawsze kilka minut po starcie zegara, wiec trzy razy dziennie o tej samej po |
| `UDZIAL_CZASU_NA_NOTKI` | `0.60` | ILE CZASU PRZEBIEGU WOLNO ZJESC SAMYM NOTKOM. Rozdzielnik dzienny nie wiedzial nic o czasie: dzielil norme tak, jakby dzialania byly natychmiastowe. P |
| `CZAS_DZIALANIA_S` | `240` | Ile trwa samo dzialanie poza przerwa: napisanie, sprawdzenie faktow, wystawienie i potwierdzenie u zrodla. Z realnych przebiegow. |
| `MIN_WIEK_POSTA_MIN` | `(90, 900)      # od poltorej godziny do piet` | NIE KOMENTUJEMY SWIEZYCH POSTOW. Wlasciciel opisal to najlepiej: napisal notke i piec sekund pozniej ktos odpisal ogolnikowa zgoda — i to zdradza bota |
| `MIN_WIEK_NOTKI_MIN` | `(20, 90)       # od dwudziestu minut do polt` | NOTKA TO NIE ARTYKUL i zyje godziny, nie dni. Ten sam prog co dla artykulow oznaczal, ze pod notki wchodzilismy zawsze PO koncu rozmowy: przeglad poka |
| `KOMFORTOWO_KOMENTARZY` | `25` | ILU KOMENTARZY POD CELEM JESZCZE NIE UWAZAMY ZA TLOK. Wyszukiwarka oddawala posty ze srednio 45 komentarzami, jeden ze 126 — a komentarz sto dwudziest |
| `ODSTEP_DNI_NA_PUBLIKACJE` | `4` | Ile dni odstepu przed kolejnym komentarzem pod TA SAMA publikacja. Komentarz pod kazdym kolejnym tekstem tej samej osoby to drugi najczytelniejszy syg |
| `HASLA_SZUKANIA` | `( …` | HASLA, KTORYMI AGENT SZUKA NOWYCH KONT. Kanal czytelnika pokazuje tylko to, co juz znamy, wiec sam z siebie nie przyprowadzi nikogo nowego — a wlasnie |
| `ILE_HASEL_NA_PRZEBIEG` | `3` | — |
| `ODPOWIEDZI_POZA_LIMITEM` | `True` | Odpowiedzi POD WLASNYMI tresciami sa poza limitami dziennymi. Decyzja wlasciciela i jest sluszna: limit chroni przed wygladaniem na spamera u obcych,  |
| `ODPOWIADAJ_WSZYSTKIM_DO` | `5      # male konto: kazdemu, bez wyjatku` | Do ilu komentarzy odpowiadamy BEZ wybierania. Przy dwoch odpowiada sie obu. Przy dwustu odpowiedz pod kazdym wyglada jak maszyna — nawet gdy kazda jes |
| `WYBIERAJ_POWYZEJ` | `20            # powyzej tego liczy sie juz p` | — |
| `MAX_ODPOWIEDZI_MALE` | `6` | — |
| `MAX_ODPOWIEDZI_DUZE` | `8` | — |
| `MAX_TOKENS` | `{ …` | Zapas na myślenie dostają WSZYSTKIE etapy, nie tylko Claude'owe: modele DeepSeek v4 też rozumują, a tokeny rozumowania liczą się do sufitu wyjścia. Od |
| `MS_PER_OUTPUT_TOKEN` | `16.08` | — |
| `TIMEOUT_MARGIN` | `1.5` | — |
| `MAX_TIMEOUT_S` | `300` | Twardy sufit na JEDNO wywolanie. Bez niego wyliczenie z sufitu tokenow dawalo 965 sekund, a przy wyszukiwaniu razy trzy — 48 MINUT. Jedno zawieszone w |
| `REFUSAL_PHRASES` | `( …` | — |
| `FETCH_TIMEOUT_S` | `30.0` | — |
| `FETCH_MIN_CHARS` | `400  # krótszy tekst to zwykle strona-zajawk` | — |
| `FETCH_USER_AGENT` | `"Mozilla/5.0 (compatible; NothingIsAccidenta` | — |
| `RUCHY_KONCOWE` | `{ …` | --- ruch koncowy i szerokosc drugiego aktu -------------------------------- Dwa artykuly napisane PO naprawie szamponu (0017 "The Gas You Didn't Buy", |
| `RUCH_KONCOWY_MIX` | `("DO_SPRAWDZENIA", "KTO_NA_TYM_STOI", "POWRO` | — |
| `ILE_PARALELI_WAGI` | `{1: 4, 2: 4, 3: 3}` | Ile paraleli w drugim akcie. Trzy wyliczone po kolei czytaja sie jak lista; jedna rozwinieta na dwa akapity czyta sie jak mysl. Chcemy obu, na zmiane. |
| `OPIS_LICZBY_PARALELI` | `{ …` | — |
| `GENERATORY` | `{ …` | --- generatory tematow ------------------------------------------------------ Mielismy 52 DZIEDZINY, czyli odpowiedz na pytanie GDZIE szukac, i zero w |
| `ILE_GENERATOROW_NA_PRZEBIEG` | `4` | — |
| `KANDYDATOW_NA_PRZEBIEG` | `25` | Ile kandydatow-jednolinijkowcow zamawiamy, zanim cokolwiek napiszemy. Nadprodukcja jest obowiazkowa: piec notek z piatki pomyslow to mediana, piec z d |
| `W_TYM_MIESIACU` | `{ …` | --- co czytelnik trzyma w reku W TYM MIESIACU ------------------------------- Najtansza dzwignia, jaka mamy, i nie mielismy jej wcale. Zwykla rzecz, k |
