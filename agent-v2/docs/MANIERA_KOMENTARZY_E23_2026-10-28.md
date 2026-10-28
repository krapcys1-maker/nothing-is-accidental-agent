# E23 — maniera komentarza, historia konta, dobór celu wg odpowiadalności autora (28.10.2026)

Podstawa: analiza 24 tys. komentarzy i jej weryfikacja (`KOMENTARZE_STYL_I_ROZMOWA_2026-10-28.md`, sekcja „Wnioski po weryfikacji”).
Decyzja właściciela z 28.10.2026: konto jest do testów, ma mieć „duszę”, ma nie być płaskie i „za każdym razem inne”, a wdrożyć
trzy etapy zaproponowane po analizie. **Wymyślonych osobistych przeżyć nie ma i nie będzie** (decyzja wykonawcy, nie reguła
projektu): prawdziwi ludzie czytają je jako fakty o prawdziwym życiu autora i na tej podstawie komuś ufają (zdrowie, pieniądze, praca).
Zamiast nich konto dostało **prawdziwą ciągłość**: to, co naprawdę opublikowało i z kim naprawdę rozmawiało.

Niezależny przegląd kodu (6 kierunków, 2 sceptyków na znalezisko, 86 agentów) i własne mutacje testów (79 z 80 zabitych, jeden równoważny)
są zrobione przed wdrożeniem; poprawki z przeglądu są w tym dokumencie i w kodzie.

## Co wdrożone

### Etap 1 — dobór celu (obie ścieżki: artykuły i notki, oba ramiona E23)
| zmiana | gdzie | uzasadnienie |
|---|---|---|
| artykuły: najwyżej 3 dni (było 7) | `config.MAKS_WIEK_POSTA_DO_KOMENTARZA_DNI` | pod artykułami starszymi niż 72 h nie mieliśmy **ani jednego** komentarza z ≥ 2 polubieniami lub odpowiedzią postronnego (0 na 163; przy ≤ 72 h: 12%); „jakakolwiek reakcja” bywa i tam (19%) |
| notki: najwyżej 24 h (było 36) | `config.MAKS_WIEK_NOTKI_DO_KOMENTARZA_H` | notki starsze niż 2 doby: −24 pkt proc. (N = 42). Dotyczy też puli notek do obserwacji i subskrypcji (`kanal.nowi_kandydaci` używa tego samego sita) |
| autor, który odpowiada komentującym, jako kryterium kolejki | `odpowiadalnosc.py`, `kanal.wedlug_odpowiadalnosci`, `run._wedlug_odpowiadalnosci` | autor, który nikomu nie odpisuje, odpowiada nam w ok. 3%; odpisujący większości — w ok. 50%; ok. połowa naszych komentarzy trafiała do pierwszych |

Autor o niskiej odpowiadalności (≤ 5% komentarzy z odpowiedzią autora; artykuły: ostatnie 3 wpisy z ≥ 4 komentarzami, a gdy ich brak —
wątek rozważanego wpisu; notki: sam wątek z ≥ 2 komentarzami) **schodzi na koniec kolejki, nie jest wykluczany**; 25% takich celów (po
adresie, stale) idzie bez kary, żeby nie zamknąć się w kilku responsywnych kontach (pętla wzajemnych polubień: 4 stałe konta = 35 z 81
nazwanych polubień po 26.09). **Liczą się tylko komentarze starsze niż 6 h** (`ODPOWIADALNOSC_MIN_WIEK_KOMENTARZA_H`) — autor, który jeszcze
nie zajrzał, nie jest autorem, który nie odpisuje (bez tego 44% „niskich” z pierwszej godziny wątku było w pełnym wątku „ok”). Niewiedza jest
neutralna (błąd sieci → wpis z flagą błędu i TTL 24 h, za mało dojrzałych komentarzy → „nieznana”). Nasze konto (`KONTO_WLASNE_UID`) i konto
siostrzane nie liczą się jako „cudze”. Odczyt: publiczne API Substacka, cache `data/odpowiadalnosc.json`, limit 20 nowych sprawdzeń i 90 s na
wywołanie, bez modelu. Wyłącznik: `config.ODPOWIADALNOSC_WLACZONA`.

**Znane ograniczenia etapu 1:** kara zmienia KOLEJNOŚĆ, więc działa tylko przy nadwyżce celów ponad miejsca (`cele[:ile]`); pętla „szukaj, aż
znajdziesz” nie zna klasy odpowiadalności i nie dosuka lepszych celów, gdy pula równa się liczbie miejsc. E15 (świeży cel) może wziąć cel
„niska” z ogona. Artykuły małych publikacji często zostają „nieznane”. Pozostaje to do zmierzenia w danych (`autor_odp_klasa` w dzienniku).

**Czego świadomie NIE zrobiono (sceptycy):** okna „notka ≤ 6 h” (u nas takie notki mają 33–38% polubień wobec ok. 51% przy 6–24 h, p = 0,02),
globalnej mediany opóźnienia ≤ 3 h, twardego wykluczania autorów.

### Etap 2 — zasady niskiego ryzyka (obowiązują w OBU ramionach)
Bez pochwały / werdyktu / rytualnego „Agreed,” na starcie, bez ram zapowiadających myśl („The part worth…”, „Worth pausing on…”), bez linków,
wykrzykników i emoji; długość 40–70 słów (`config.KOMENTARZ_CEL_SLOW`); w odpowiedziach (`odpowiedz.md`) bez pustego wstępu — zgoda jest
dozwolona jako pół zdania, które niesie coś nowego. **Prośba w prompcie nie jest bramką** (lekcja projektu), ale tu LOG, nie bramka (decyzja
właściciela „sprawdzenia są logiem”): `stages.zasady_stylu` zapisuje naruszenia w wyniku kandydata, w logu przebiegu i — razem z ramieniem —
w dzienniku (`zasady_stylu`). Detektor jest wąski: „Right now…”, „Exactly 3 of…”, „Good luck…” NIE są pochwałą.

### Etap 3 — E23 `maniera_komentarza` (50/50 po adresie celu, 29.10.2026–10.02.2027)
„off” = `prompts/komentarz.md` z zasadami etapu 2. „on” = `prompts/komentarz_b.md` **plus**:
* sedno w pierwszym zdaniu, stanowisko wobec konkretnego twierdzenia z powodem; jawny sprzeciw tylko gdy materiał daje twardą,
  sprawdzalną podstawę (poprawka sceptyków: bez wymuszania sporu), inaczej zgoda z nowym elementem;
* zwykła mowa (skróty, urwane zdania dozwolone, najwyżej jedna pauza lub średnik, bez „nie X, lecz Y” i trójek, bez zamykającego aforyzmu),
  humor tylko z sytuacji, charakter („my”, własne zdanie); przyznanie się do błędu tylko gdy zapis poniżej to pokazuje;
* **pytanie na końcu w ok. 25% komentarzy, a CZĘSTOŚĆ USTALA KOD** (`config.MANIERA_PYTANIE_UDZIAL`, los stały po adresie), nie prośba
  w prompcie; pytanie pada PO tezie, nigdy zamiast niej; jedynym źródłem decyzji o pytaniu jest znacznik reguły (prompt nie zachęca do pytań gdzie indziej);
* **blok „What this account has already said”** (`historia_konta.py`): do 2 własnych opublikowanych wpisów (notki **bez typu MYSL i bez „I/my/me”**,
  tytuły artykułów) z 60 dni, o podobieństwie cosinusowym ≥ 0,13 (wektory słów ważone rzadkością; liczby rzadkie tak samo jak słowa) i ≥ 2
  wspólnych rzadkich terminach; w próbie na 234 celach trafia w ok. 5% (tylko tam, gdzie konto naprawdę coś już mówiło). Prompt: tylko to się
  wydarzyło, daty podane z „Today is”, nic o przeszłości ponad zapis, historię zignorować, gdy niczego nie wnosi; bez bloku nie ma żadnej przeszłości;
* **pamięć rozmówcy** (`stages.pamiec_rozmowcy`) zawsze w ramieniu „on” (E21 skończył się 27.10);
* nazwy naszych bloków danych w cudzym tekście (tytuł, autor, treść) są zastępowane — cudzy post nie podszyje się pod „zapis konta”;
* **pamięć głosu nie miesza ramion** (`stages.pamiec_glosu`): B widzi tylko własne ostatnie komentarze, A — wszystkie spoza ramienia „on”; B nie dostaje
  „Delivery feedback” (pytanie ustala kod). Ramię jest stałe dla adresu celu (`stages.ramie_stale`, bez daty w losowaniu).

**To jest PACZKA** (zmienia naraz wejście, ton, pytanie i historię). Jeśli B wygra, rozkładamy ją na składniki; jeśli przegra — wiemy tylko, że
paczka nie działa. To świadomy wybór pod polecenie właściciela („dajmy mu duszę”), nie zalecenie czystego eksperymentu.

## Co jest zapisywane
**Dziennik (komentarz):** `eksperymenty.maniera_komentarza` = `on`/`off`; `maniera_pytanie`, `historia_n` (0 = sprawdzono, brak powiązań),
`historia_blad` (awaria budowy historii — to NIE to samo co 0), `pamiec_b_wymian`, `zasady_stylu` (lista naruszeń, oba ramiona; `my_w_przeszlosci` =
twierdzenie „we wrote/tried/tested…” — prawdziwe tylko przy `historia_n` > 0; `ja_nawyk` = osobisty nawyk/metoda w 1. osobie, „my test is…”), `podloga` (wymyślone przeżycie w pierwszej osobie); ocena autora: `autor_odp_klasa`, `autor_odp`, `autor_odp_n`.
**`data/cele_bez_komentarza.jsonl` (ITT):** cel przydzielony do ramienia, pod którym nie powstał komentarz — adres, ramię, liczba ciszy/zapory, powody.
Bez niego ocena z dziennika obejmowałaby tylko cele, z których komentarz wyszedł, a ramiona mogą różnić się częstością ciszy.

## Reguła decyzji — ZAPISANA Z GÓRY (28.10.2026, przed pierwszym komentarzem w E23; poprawiona po przeglądzie tego samego dnia)
**Metryka główna:** odsetek komentarzy pierwszego poziomu z odpowiedzią ≥ 15 słów od osoby innej niż my i NIA w ciągu 72 h („rozmowa
merytoryczna”). Baza od 4.10: 22,8% (autor wpisu 28,5%, postronni 2,5%). **Uczciwie: to w ok. 90% odpowiedź autora wpisu, w dużej części grzeczna.**
Dlatego raportujemy ją zawsze rozbitą: autor / postronni.
**Strażnik:** polubienia (≥ 1 polubienie w 72 h, baza 50,2%) — B nie gorsze niż −8 pkt proc. (dolna granica **jednostronnego 90%** przedziału różnicy;
poprzednia wersja, 95% dwustronny, odrzucała równe ramiona w ok. 40% przypadków).
**Tempo i próba:** zmierzone tempo to **ok. 13 komentarzy dziennie** (320 w 24 dni od 4.10), nie 18. 380 na ramię = 760 komentarzy ≈ 57 dni (8 tygodni);
630 na ramię ≈ 95 dni. Okno E23 kończy się 10.02.2027 (zapas na jedno przedłużenie); jeśli przy `do` brakuje do progu, **przesuwamy `do`** w
`config.EKSPERYMENTY`, a nie zmniejszamy progu. Przy 380 na ramię wykrywalna różnica to ok. 9 pkt proc. (rozmowa) i ok. 10 (polubienia).
**Moc łącznej reguły** (rozmowa ≥ +6 pkt i LB90 > 0 oraz strażnik), gdy prawdziwy efekt to +9 pkt przy równych polubieniach: ok. 70% przy 380 na ramię,
ok. 85% przy 630. To konserwatywna reguła — dobre B przejdzie ją przy pierwszym werdykcie w 7 przypadkach na 10, w pozostałych przedłużamy.
**Test manipulacji (po pierwszych 40 komentarzach na ramię):** B ma realnie różnić się od A: start od ram zapowiadających ≈ 0, pauz < 30%,
pytanie ≈ 20–30% (A: ok. 5–8% komentarzy kończy się pytaniem), 40–70 słów, `my_w_przeszlosci` przy `historia_n` = 0 w ≤ 5% komentarzy B. Jeśli nie —
poprawić prompt i liczyć od nowa (lekcja z E17/E18).
**Reguła:**
1. Bez zaglądania w wynik przed 190 na ramię, poza stopem bezpieczeństwa: spadek polubień > 15 pkt proc., zarzuty „to bot/AI” pod naszymi
   komentarzami albo więcej niż 5% komentarzy B z `my_w_przeszlosci` przy `historia_n` = 0, z `ja_nawyk` lub z niepustym `podloga` (wymyślona przeszłość).
2. Werdykt przy 380 na ramię. **Wdrażamy B**, jeśli rozmowa merytoryczna w B jest wyższa o ≥ +6 pkt proc. (jednostronnie, dolna granica 90%
   przedziału > 0, test permutacyjny z klastrowaniem po autorze wpisu) ORAZ spełniony jest strażnik polubień.
3. Kierunek zgodny i efekt ≥ połowy wykrywalnego, ale warunek niespełniony: jedno przedłużenie do 630 na ramię, potem koniec.
4. Rozmowa ≥ +6 pkt proc. przy spadku polubień ≥ 8 pkt proc.: nie wdrażamy całości, rozkładamy paczkę na składniki.
5. Różnica rozmowy < +3 pkt proc. przy 630 na ramię: wracamy do A i uznajemy, że styl nie jest dźwignią (dźwignią jest dobór celu).
6. Zero nieplanowanych podziałów; podziały po miejscu (artykuły/notki) tylko opisowo. Analiza ITT: do mianownika wchodzą też cele z
   `cele_bez_komentarza.jsonl`; różnicę częstości ciszy między ramionami raportujemy osobno.

## Jak ocenić
* Polubienia, odpowiedzi, reakcje (z przedziałem): `python agent-v2/eksperymenty.py --rodzaj komentarz --pole eksperyment:maniera_komentarza --od 2026-10-29`
  (prefiks `eksperyment:` jest obowiązkowy — bez niego wszystkie komentarze trafiają do jednej grupy „brak”).
* Rozmowa merytoryczna (treść odpowiedzi, rozbicie autor/postronni): potok z analizy 28.10 — `robocze/koment_28_10/crawl_watki.py` → `splaszcz.py` →
  `cechy.py` (poza repozytorium; czyta publiczne API, nie dotyka bota). Wątki naszych komentarzy z okresu E23, grupowanie wg `eksperymenty.maniera_komentarza`.
* Zarzuty „to AI”: wyszukanie w odpowiedziach pod naszymi komentarzami (frazy: AI generated, bot, ChatGPT, slop, LLM).
* Analiza wrażliwości bez stałych polubiających (≥ 3 poprzednich polubień naszych komentarzy) i osobno według `autor_odp_klasa`.

## Ograniczenia i ryzyka
* Wszystkie dane są obserwacyjne poza samym E23; efekt wczesności i widoczności u rówieśników nie musi przenosić się na nasze konto.
* Własna publiczność rośnie od 4.10 i cztery stałe konta dają dużą część polubień (wzajemność).
* Filtr po odpowiadalności autora może zmniejszać rozmowę z postronnymi i wzmacniać pętle wzajemności — dlatego 25% bez kary i neutralna niewiedza.
* Odpowiedź autora jest w dużej mierze grzecznościowa (65% to zgoda); nie mierzy jakości komentarza.
* Notki z kanału mają uchwyt autora, a notki z wyszukiwarki dostały go dopiero 28.10 (wcześniej pamięć rozmówcy była dla nich pusta).

## Wycofanie
`config.EKSPERYMENTY["maniera_komentarza"]["do"]` ustawić na datę z przeszłości (ramię „off” = dotychczasowy komentarz z zasadami etapu 2);
`config.ODPOWIADALNOSC_WLACZONA = False`; progi wieku z powrotem na 7 dni i 36 h. Rollback kodu: `git reset --hard <poprzedni commit>` na serwerze.
