# 16 — MATERIAŁ DO PIERWSZEGO ARTYKUŁU

## Cel pliku
Zebrać w jednym miejscu **gotowy surowiec** do pierwszego artykułu na „Chaos Engine": początek projektu, pomysł, wybór niszy, konto, pierwsza architektura, pierwsze decyzje, walking skeleton, pierwsze koszty i błędy, screeny, fragmenty kodu. To „skrzynka narzędziowa" — z tego pisze się artykuł 1 (i częściowo 2).

**Roboczy tytuł artykułu:** *„Dałem agentowi AI 30 dni, 40 dolarów i własny Substack"*
**Podtytuł:** *„Nie pozwoliłem mu pisać o AI. Miał zbudować newsletter o ukrytych mechanizmach codzienności. Oto koszty, błędy i wyniki."*

---

## 1. Początek projektu
- Data startu: **2026-07-11**. Cały dotychczasowy fundament (audyt → plan → walking skeleton → dedup → research pipeline) powstał w tym jednym dniu, w rytmie „etap → zatrzymanie → zgoda".
- Pytanie eksperymentu: *czy agent AI potrafi od zera zbudować i prowadzić wartościową publikację, mając jasny temat, budżet, zasady i ograniczony nadzór człowieka?*

## 2. Pomysł
- Autonomiczny twórca treści pod nadzorem człowieka; jawnie jako AI, bez podszywania się pod człowieka, bez spamu.
- Docelowo pełne rozliczenie (koszty, błędy, wyniki) opisane jako **seria** na Chaos Engine.

## 3. Wybór niszy — i celowe „nie o AI"
- Nisza: **ukryte systemy, bodźce i decyzje za zwykłymi rzeczami** (supermarkety, bilety lotnicze, kolejki, windy, kody kreskowe, QWERTY…).
- Dlaczego nie o AI: trudniejszy, uczciwszy test (research świata zewnętrznego, weryfikacja źródeł, brak autoreferencji); świeżość względem przesyconego rynku; mocny hak narracyjny („AI, ale pisze o supermarketach").

## 4. Utworzenie / stan konta
- Konto **już istniało**: „Nothing Is Accidental", bio „Explaining the hidden systems, incentives and decisions behind ordinary things.", język EN, `account_id = nothing_is_accidental`.
- Decyzja: **nie tworzymy nowego** — łączymy się później z istniejącym przez dedykowany profil Playwright, po **ręcznym** logowaniu (magic-link), bez hasła w kodzie (ADR-011).

## 5. Pierwsza architektura
- Zasada: **Claude = mózg, lokalne narzędzia = ręce, SQLite = pamięć, Policy Engine = deterministyczna bramka.**
- Model **nie steruje przeglądarką ani bazą bezpośrednio** — proponuje `ProposedAction`, Policy waliduje, orchestrator wykonuje.
- 6 portów (Scheduler/Storage/Browser/SecretStore/FileStore/Notification) = gotowość na chmurę bez zmiany logiki.

## 6. Pierwsze decyzje (właścicielskie)
- MVP tylko na `nothing_is_accidental` (ADR-007); nisza żony = astrologia, konto wyłączone (ADR-008).
- Panel = FastAPI (ADR-009). Sufit autonomii = LEVEL_2 za bramką, efektywnie LEVEL_1 (ADR-004).
- Budżet 2 USD/dzień, 40 USD/mies., **miesięczny nadrzędny** (ADR-012). Grafiki SVG-only (ADR-003). Klucz — tylko `.gitignore`, bez rotacji teraz (ADR-010).

## 7. Pierwszy działający walking skeleton
- Generacja i **ocena tematów** (scoring 25/20/15/15/10/10/5; progi 75/65), zapis do SQLite, liczenie kosztu — w trybie **dry_run** (bez sieci, bez kosztu).
- Rozszerzenia tego samego dnia: **deduplikacja tematów** (lokalna, bez płatnego modelu) i **research pipeline** (Research Card + bramka jakości + ochrona przed prompt injection).
- Jakość: **44 testy przechodzą**.

## 8. Pierwsze koszty
- **Dry_run:** 0.00 USD wszędzie. Szacunki: scoring tematów ~0.0042 USD/run, Research Card ~0.0492 USD (w tym 4 web searche — **web search dominuje koszt**).
- **Pierwszy REALNY koszt (2026-07-11, potwierdzony w konsoli Anthropic): 0,25 USD** za jedno wywołanie, które się NIE powiodło (ucięty JSON, karta researchu nie powstała). Z tego: 0,21 USD tokeny, 0,04 USD wyszukiwanie.
- Ciekawy wniosek do artykułu (podwójny): (1) największą pozycją researchu jest wyszukiwanie w sieci i związany z nim narastający koszt tokenów, nie sam model; (2) **nawet nieudany research kosztuje niemal tyle, ile udany** — porażka nie jest tania.

## 9. Pierwsze błędy (bez ukrywania)
- **Brak `.gitignore`** na starcie → realny klucz w `.env` mógł trafić do commitu. Naprawione (gitignore + `.env.example`), ale **rotacja klucza świadomie odłożona** = ryzyko rezydualne R1.
- **Błędny import** w teście researchu — wychwycony przed runem; nauka: pełny `pytest` jako bramka każdego etapu.

## 10. Cytaty/fakty gotowe do użycia (liczby)
- 3 konta, 1 aktywne. 6 portów. 4 migracje SQLite. 73 testy (po wszystkich naprawach, w tym stabilizacji wznawialności). Budżet 40 USD/mies. **Realny koszt dotąd: 0,25 USD (0,625% budżetu miesięcznego).** Scoring: 7 kryteriów. Progi: artykuł 75, Note 65. Dedup próg: 0.72. Research: min. 3 źródła. **Błąd estymacji kosztu: +163% (szacunek 0,095 USD vs realne 0,25 USD).** **Koszt samego wznowienia drugiego kroku researchu (bez ponownego wyszukiwania): ~0,02 USD wobec ~0,38 USD od zera.**

## 11. Potrzebne screeny (DO ZROBIENIA — patrz `11_SCREENSHOTY_I_DOWODY.md`)
- **SS-01** struktura projektu · **SS-02** 63 passed · **SS-03** pierwszy scoring · **SS-05** pierwszy Research Card (dry_run) · **SS-06** COSTS.csv (z realnym wierszem 0,25 USD) · **SS-08** pierwsza realna próba · **SS-10-koszt** korekta kosztu w bazie. To minimum wizualne do artykułu 1.

## 12. Potrzebne fragmenty kodu (są w `10_FRAGMENTY_KODU.md`)
- Policy Engine (budżet + kill switch), tracking kosztów, ochrona przed injection.

## Czego jeszcze brakuje do „pełnego" pierwszego artykułu
- Screenshoty (żaden nie zrobiony).
- ~~**Realny** koszt (pierwszy `--real`) do porównania z szacunkiem~~ — **zrobione 2026-07-11, patrz niżej, choć z zastrzeżeniem.**
- (Opcjonalnie) pierwszy szkic artykułu agenta jako próbka jakości — wymaga Etapu 2.

## 13. Pierwsze realne wywołanie — najmocniejszy dotychczasowy materiał o porażce (2026-07-11)
To prawdopodobnie najlepszy dotychczasowy fragment do sekcji „gdzie zawiodło" w artykule 1 (lub własny akapit w artykule 8) — teraz z PEŁNYM zamknięciem, nie tylko otwartym pytaniem:

- Właściciel jawnie zatwierdził **jedno**, precyzyjnie ograniczone, płatne wywołanie: cap kosztu 0.30 USD, max 6 wyszukiwań, max 1 ponowienie, zero publikacji, zero artykułu, zero przeglądarki.
- Przed wywołaniem system sam sprawdził: czy jest klucz API (bez ujawniania go), czy nie ma wyłącznika awaryjnego, ile już wydano w tym miesiącu/dniu, i policzył **pesymistyczny sufit kosztu tego jednego wywołania** (~0.095 USD) — dopiero wtedy zadzwonił do prawdziwego API.
- Model naprawdę odpowiedział i naprawdę użył wyszukiwarki internetowej — ale jego odpowiedź urwała się w połowie zdania (za mało miejsca na pełną odpowiedź). System **nie spróbował sam ponownie** — dokładnie zgodnie z poleceniem.
- Przy okazji wyszedł na jaw **drugi, ciekawszy problem**: koszt tej nieudanej, ale prawdziwej próby **nie zapisał się** w naszej księgowości — wyglądało, jakby nic nie kosztowała. Znaleźliśmy to, naprawiliśmy tego samego dnia i dopisaliśmy testy, żeby się nie powtórzyło.
- **Rozwiązanie (ta sama sesja, później):** właściciel sprawdził dokładną kwotę w panelu Anthropic — **0,25 USD**. Nasz „bezpieczny" szacunek sprzed wywołania (0,095 USD) okazał się **2,63× za niski (błąd ~+163%)**. System i tak zmieścił się w zatwierdzonym limicie, ale z dużo mniejszym zapasem, niż zakładaliśmy (0,05 USD zamiast rzekomych 0,20 USD).

**Dlaczego to dobry materiał:** pokazuje pełen łuk „projekt na papierze → pierwszy kontakt z rzeczywistością → dwie osobne pomyłki → poprawka tego samego dnia, bez ukrywania żadnej z nich". System zaprojektowany z ostrożnością (limity, brak auto-ponawiania, jawna zgoda) **ograniczył szkodę do dokładnie tego, na co się umówiliśmy** — nawet gdy zawiodła zarówno księgowość, jak i sama estymacja kosztu.

## 14. Naprawa estymatora i dwuetapowy research — materiał do artykułu 4/7
- Stary sposób liczenia kosztu zakładał **stały zapas** tokenów niezależnie od liczby wyszukiwań. Nowy sposób rośnie **razem** z liczbą wyszukiwań (bo to one, jak się okazało, najbardziej napędzają koszt) i wymaga minimum 50% marginesu bezpieczeństwa.
- Kluczowe zdanie do artykułu: *„limit kosztu, który ustawialiśmy przed wywołaniem, nigdy nie był twardym hamulcem działającym w trakcie zapytania — to tylko kontrola przed startem, oparta na szacunku. Jeśli szacunek jest zły, kontrola nie chroni tak, jak się wydaje."*
- Research podzielony na dwa kroki (zbieranie źródeł osobno od analizy) — nowa projekcja kosztu: ~0,38 USD łącznie (vs ~0,55 USD dla starego podejścia po ponownym przeliczeniu), **~31% taniej**, głównie dzięki mniejszej liczbie wyszukiwań w pierwszym kroku.
- Wszystko to zbudowane i przetestowane (63 testy) **bez wydania ani centa więcej** — druga płatna próba czeka na osobną zgodę.

## Potrzebne screeny (nowe, dopisz do `11_SCREENSHOTY_I_DOWODY.md`)
- Terminal z pre-flight checks + wynikiem nieudanego runu (SS-08).
- `pytest` → 63 passed po wszystkich naprawach (SS-09).
- Wiersz w `COSTS.csv` z realną kwotą 0,25 USD (SS-10-koszt).
- Wynik `--estimate-only` pokazujący projekcję dwuetapowego podejścia (do dodania do indeksu).

## 15. Doprecyzowanie celu: pełna autonomia, nie asystent do klikania — materiał do artykułu 2/9
Dobry, uczciwy materiał o samym procesie budowy, nie tylko o agencie:

- W trakcie budowy dokumentacja zaczęła — bez niczyjej złej woli, po prostu przez nawarstwianie się ostrożnych sformułowań — sugerować, że ręczna akceptacja każdej pojedynczej akcji jest **stanem docelowym** systemu, podczas gdy pierwotnym celem od początku była **pełna autonomia operacyjna**.
- Właściciel to zauważył i skorygował, zanim powstał jakikolwiek kod interakcji z platformą (komentarze, lajki, subskrypcje) — czyli w najtańszym możliwym momencie, na poziomie założeń, nie działającego systemu.
- Powstała pełna specyfikacja czterech poziomów autonomii (od szkiców offline po pełną samodzielność), z jawnymi, mierzalnymi warunkami przejścia między nimi — nie „zaufaj mi", tylko konkretne liczby (minimum X udanych researchów, Y% błędów poniżej progu, przetestowany wyłącznik awaryjny, itd.).
- **Kluczowe zdanie, dobre na cytat:** *„Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta."*
- **Co ustalono w tym momencie (poprawione chwilę później — patrz punkt 16 niżej):** wtedy uznaliśmy, że publikacja będzie jawnie ujawniać AI-autorstwo na każdym poziomie. Ta konkretna część okazała się błędna i została skorygowana tego samego dnia (ADR-018).

**Dlaczego to dobry materiał:** pokazuje, że nawet twórca systemu może nieświadomie zboczyć od pierwotnego celu przez samo nagromadzenie ostrożnych decyzji — i że regularne konfrontowanie dokumentacji z pytaniem „po co my to właściwie budujemy" jest osobną, realną formą nadzoru, różną od poprawiania pojedynczych tekstów.

## 16. Druga korekta tego samego dnia: BRAK publicznego ujawniania AI (ADR-018) — jeszcze mocniejszy materiał
To, co wydarzyło się chwilę po punkcie 15, jest jeszcze lepszym materiałem — bo pokazuje korektę w **przeciwnym kierunku**:

- Zaledwie kilka godzin po ustaleniu „agent ma docelowo działać w pełni autonomicznie", właściciel doprecyzował drugą, niezależną oś: **czy publiczność ma wiedzieć, że to AI?** Odpowiedź: nie, dopóki właściciel osobno o tym nie zdecyduje.
- To pokazuje coś ważnego dla artykułu: **autonomia działania i jawność pochodzenia treści to dwa zupełnie różne wymiary**, łatwe do pomylenia. Można zbudować agenta w pełni samodzielnego, który mimo to nie ogłasza publicznie, że jest agentem — dokładnie tak jak wiele redakcji, newsletterów i marek działa anonimowo, bez ujawniania, kto (albo co) dokładnie pisze.
- **Twarda granica, która ZOSTAJE (nieprzekraczalna, niezależnie od decyzji o jawności):** zero podszywania się pod konkretną, prawdziwą lub fikcyjną osobę. Zero wymyślonej biografii, rodziny, zawodu, miejsca zamieszkania, wspomnień, podróży. Zero zdjęcia fikcyjnego autora. Anonimowość ≠ oszustwo tożsamościowe.
- **Ciekawy szczegół projektowy (dobry do cytowania):** gdy ktoś wprost zapyta komentarz agenta „czy jesteś botem?", agent **nie odpowiada i nie kłamie** — nie ma ani potwierdzenia, ani zaprzeczenia. To trzecia droga między „ujawnij wszystko" a „aktywnie okłamuj pytającego", której na pierwszy rzut oka łatwo nie zauważyć.
- **Inny dobry cytat:** *„Nieregularny harmonogram i umiarkowane limity wynikają z troski o jakość i o odbiorcę, nie z próby oszukania mechanizmów integralności platformy."* — jawny zakaz technicznego maskowania (fingerprint, CAPTCHA, rotacja kont) pokazuje, gdzie leży granica między „dobrymi manierami" a „oszukiwaniem systemu".

**Dlaczego to dobry materiał:** to rzadki przykład dwóch kolejnych, w miarę szybkich korekt tego samego dnia, idących w PRZECIWNYCH kierunkach (najpierw „więcej autonomii działania", potem „mniej publicznej jawności") — dobrze pokazuje, że są to niezależne osie decyzji, a nie jeden spójny „poziom otwartości".

## 17. Naprawa PRZED incydentem, nie po nim — materiał do artykułu 4/7 (2026-07-12, ADR-019)
Dobre uzupełnienie do punktu 13/14 — bo pokazuje inny tryb pracy nad tym samym projektem: nie „coś się zepsuło, naprawiamy", tylko „przeanalizujmy, co jeszcze może się zepsuć, zanim zapłacimy za to drugi raz".

- Po pierwszym incydencie kosztowym (0,25 USD, punkt 13) i naprawie estymatora (punkt 14), właściciel kazał zatrzymać się na jeszcze jeden krok PRZED kolejną realną próbą i zapytać: „czy nasz dwuetapowy podział rzeczywiście chroni wyniki wyszukiwania, czy tylko przesuwa ryzyko gdzie indziej?"
- Odpowiedź: podział na dwa kroki chronił przed uciętą odpowiedzią WEWNĄTRZ jednego wywołania, ale wyniki pierwszego kroku wciąż istniały tylko „w locie" (w pamięci programu) między krokiem 1 a 2 — awaria komputera dokładnie w tym momencie nadal skasowałaby już opłacone wyszukiwanie.
- Naprawa: wyniki kroku 1 są teraz zapisywane na trwałe w jednej, niepodzielnej operacji, zanim program zdąży zrobić cokolwiek innego; dodano możliwość wznowienia WYŁĄCZNIE kroku 2 z zapisanych danych. **Cała naprawa — nowe tabele, nowa funkcja, 10 nowych testów (73 łącznie) — powstała bez wydania choćby centa**, bo nic z tego nie wymagało kontaktu z prawdziwym API.
- **Kluczowe zdanie do artykułu:** *„Naprawienie jednego błędu czasem tylko przesuwa to samo ryzyko o jeden poziom głębiej w architekturze — więc po każdej naprawie warto zapytać: a co, jeśli padnie dokładnie TERAZ, w tym nowym miejscu?"*
- Liczbowy hak: samo wznowienie drugiego kroku (gdy pierwszy już się powiódł) kosztuje teraz ~0,02 USD zamiast ~0,38 USD liczonych od zera — bo nie trzeba płacić za wyszukiwanie drugi raz.

**Dlaczego to dobry materiał:** kontrastuje z punktem 13 (błąd znaleziony PO fakcie, żywy, kosztowy) — tu błąd (a właściwie lukę architektoniczną) znaleziono i zamknięto proaktywnie, offline, zanim doprowadziła do realnej straty. Dobra ilustracja różnicy między „gaszeniem pożarów" a „szukaniem, gdzie jeszcze może wybuchnąć", w tym samym, realnym projekcie.

## 18. Drugi realny test — nowy problem znaleziony tam, gdzie się go nie spodziewaliśmy (2026-07-12)
Świetne domknięcie łuku z punktów 13/14/17 — bo pokazuje, że przygotowanie na jeden scenariusz awarii nie gwarantuje, że TEN scenariusz się wydarzy.

- Zaraz po zbudowaniu i przetestowaniu (offline) pełnej wznawialności — łącznie z gotową ścieżką „wznów tylko krok 2, jeśli on zawiedzie" — właściciel zatwierdził jeden realny test na żywym API, żeby tę ścieżkę zademonstrować.
- Rzeczywistość zaskoczyła inaczej, niż planowaliśmy: **zawiódł krok 1** (zbieranie źródeł), nie krok 2. Skoro krok 1 nie wyprodukował żadnych trwałych źródeł, nie było niczego do wznowienia — to nie była luka w planie, tylko po prostu inny, wcześniej pokryty przez architekturę scenariusz („brak wyników = nieudany, nie częściowy"), który akurat zdarzyło się przetestować pierwszy.
- **Najważniejsza, pozytywna wiadomość:** mechanizm, który zawiódł przy PIERWSZYM realnym teście (11.07) — gubienie prawdziwego kosztu przy błędzie — tym razem zadziałał bez zarzutu, w zupełnie nowym miejscu kodu. Prawdziwy koszt (0,123823 USD, 4 wykorzystane wyszukiwania) trafił do księgowości, mimo że research całkowicie się nie powiódł.
- **Druga dobra wiadomość:** tym razem to SZACUNEK okazał się zbyt ostrożny, a nie zbyt optymistyczny — realny koszt wyniósł ~34% pesymistycznej estymacji. Ładne odwrócenie względem pierwszego incydentu, dobry kontrast do pokazania w artykule (raz szacunek zawiódł w jedną stronę, raz w drugą — obie strony tego samego mechanizmu bezpieczeństwa).
- **Kluczowe zdanie do artykułu:** *„Zbudowaliśmy dokładnie tę siatkę bezpieczeństwa, której zabrakło poprzednio — i została użyta, tylko nie tam, gdzie się jej spodziewaliśmy. To chyba najbardziej realistyczny obraz tego, jak wygląda »przygotowanie na awarię« w praktyce."*
- Po dwóch realnych, płatnych próbach (11.07 i 12.07) wciąż **zero udanych, kompletnych kart researchu** — ale też zero przekroczonych limitów i zero zgubionych pieniędzy w księgowości. Łączny koszt: 0,373823 USD, mniej niż 1% budżetu miesięcznego.

**Dlaczego to dobry materiał:** rzadko się zdarza tak czysty przykład „zabezpieczenie zadziałało, ale nie w scenariuszu, który testowaliśmy" — dobra ilustracja różnicy między testowaniem na danych zastępczych (gdzie sami wybieramy, co się psuje) a konfrontacją z żywym modelem (który psuje się po swojemu, nie po naszemu).

## 19. Objaw kontra przyczyna — druga naprawa tego samego dnia idzie głębiej (2026-07-12, ADR-020)
Naturalne domknięcie punktu 18 — bo pokazuje, co się stało zaraz PO tym, jak zabezpieczenia „zadziałały, ale nie tam, gdzie się spodziewaliśmy".

- Pierwsza, intuicyjna reakcja na „odpowiedź modelu znowu się urywa" brzmiała rozsądnie: podnieś limit długości odpowiedzi, spróbuj ponownie. To by nawet prawdopodobnie zadziałało — na TEN konkretny przypadek.
- Właściciel zatrzymał ten tor myślenia jednym zdaniem: **„samo podniesienie limitu nie jest wystarczającym rozwiązaniem"** — i miał rację. Prawdziwa wada leżała w konstrukcji: JEDNA odpowiedź modelu obejmowała WSZYSTKIE źródła naraz, więc ucięcie w dowolnym miejscu kasowało je wszystkie razem. Wyższy limit tylko przesunąłby moment, w którym to samo znowu by się zdarzyło.
- Naprawa poszła głębiej: krok „zbierania źródeł" rozbity na **szukanie** (agent zwraca tylko krótką listę adresów) i **czytanie pojedynczego źródła** (każde źródło to osobne, w pełni niezależne zapytanie, zapisywane do bazy natychmiast). Efekt: awaria źródła numer 4 nie ma już ŻADNEGO wpływu na źródła 1, 2 i 3.
- Przy okazji zbudowano coś, czego brakowało od pierwszego dnia: prywatny zapis surowej odpowiedzi modelu przy każdym błędzie, razem z dokładnym powodem zatrzymania generacji wprost z API. Do tej pory każdy wniosek o przyczynie ucięcia był w najlepszym razie wykształconym przypuszczeniem.
- **Kluczowe zdanie do artykułu:** *„Najłatwiejsza naprawa to prawie zawsze podniesienie jakiegoś limitu. Najlepsza naprawa to czasem przyznanie, że limit nigdy nie był problemem — problemem była konstrukcja, która w ogóle wymagała zgadywania właściwego limitu."*
- Cała ta naprawa — nowa architektura, nowa tabela, nowa diagnostyka, 12 nowych testów — powstała **bez wydania ani centa** (85 testów zielonych łącznie, zero regresji w starszych, wciąż działających ścieżkach).

**Dlaczego to dobry materiał:** rzadki, uczciwy przykład dwóch KOLEJNYCH podejść do tego samego problemu tego samego dnia — pierwsze płytsze (podnieś limit), drugie głębsze (zmień konstrukcję) — z jasno pokazanym momentem, w którym ktoś (człowiek, nie agent) zatrzymał tę pierwszą, gorszą ścieżkę.

## 20. Najdroższa rzecz, której jeszcze nie uruchomiliśmy — świadomy preflight (2026-07-12)

Po sześciu realnych requestach i koszcie projektu 0,500616 USD nadal nie było kompletnej Research Card. Następnej próby nie uruchomiono odruchowo. Najpierw offline policzono każdy etap świeżego runu: A1 0,033956 USD, cztery A2 łącznie 0,153824 USD, B 0,013500 USD, czyli 0,201280 USD oczekiwanego kosztu. Konserwatywna kalkulacja wyniosła 0,510375 USD, a limit przedstawiony właścicielowi — 0,55 USD.

Cztery źródła są interesującym kompromisem narracyjnym i technicznym: pipeline potrzebuje trzech udanych ekstrakcji, więc czwarte źródło kupuje odporność na dokładnie jedną awarię. Retry pozostaje wyłączony, a dwie awarie zakończą próbę bez syntezy.

**Zdanie do artykułu:** „Pierwszy raz sukces nie oznaczał kliknięcia Enter. Oznaczał, że potrafiliśmy dokładnie powiedzieć, ile możemy stracić, gdzie możemy przegrać i dlaczego jeszcze niczego nie uruchomiliśmy”.

Koszt przygotowania: 0,000000 USD; zero API, zero Playwrighta i zero zmian statusów. Wynik był gotowością do decyzji człowieka, nie zgodą udzieloną przez system.

## 21. Drugi licznik nie może prowadzić własnej księgowości (2026-07-12)

Po ustabilizowaniu typów runów przyszła mniej widowiskowa, ale bardzo praktyczna poprawka: jeden research składa się z A1, wielu A2 i B, więc `runs.cost_usd` łatwo mógł pamiętać tylko ostatni fragment albo policzyć coś drugi raz po wznowieniu. Rozwiązanie nie polegało na nowym estymatorze. Jedyną księgą pozostała tabela `model_usage`, a pole w `runs` stało się odtwarzalnym widokiem jej aktualnej sumy.

Niezależne review odsłoniło jeszcze subtelniejszą wersję tego ryzyka: dwa osobne, poprawne commity mogły po awarii zostawić księgę z nowym wpisem i stary widok. Naprawa związała INSERT usage, ponowne zsumowanie księgi i UPDATE cache'a jedną transakcją SQLite. Test rollbacku wymuszony triggerem sprawdza, że nie zostaje nawet częściowy wpis.

To ma dobry wymiar narracyjny: po pierwszym incydencie nauczyliśmy się, że koszt może zniknąć przy błędzie parsowania. Następna lekcja była subtelniejsza — nawet zapisany koszt może być źle pokazany przez wygodny cache. Testy obejmowały błąd po samym zapisie usage, żeby sprawdzić właśnie tę granicę.

**Zdanie do artykułu:** „Najpierw nauczyliśmy agenta zapisywać rachunki. Potem musieliśmy nauczyć go, że podsumowanie rachunków nie może mieć własnej pamięci."

## 22. Retry jako decyzja, nie odruch (2026-07-12, ADR-024)

Po serii błędów A2 pojawiła się kusząca „prosta” naprawa: gdy run jest częściowy, po prostu spróbuj failed jeszcze raz przy zwykłym resume. Taki mechanizm wyglądałby jak odzyskiwanie, ale w praktyce ukrywałby następny płatny request za komendą, która miała tylko kontynuować nieprzetworzone dane.

Zamiast tego każdy kandydat dostał licznik rozpoczętych prób. Pierwszy call zmienia 0 na 1; dopiero osobna, jasno nazwana komenda może przywrócić failed do kolejki, i tylko poniżej capu 2. Sam reset nie woła modelu ani nie tworzy kosztu. Jeśli nic legalnego już nie zostało, system mówi `PARTIAL_EXHAUSTED` i odmawia zwykłego resume.

**Zdanie do artykułu:** „Najbezpieczniejszy retry to taki, którego nie da się pomylić ze zwykłym wznowieniem.”

To zrobiono całkowicie offline: test migracji na pamięciowej kopii prawdziwej bazy, 14 nowych regresji i **153 testy zielone**, 0 USD. Nie naprawiono jeszcze pobierania faktycznej treści strony ani nie uruchomiono historycznego runu — bezpieczeństwo mechanizmu nie jest dowodem jakości researchu.

## 23. Licznik, który musiał przyznać się do niepewności (2026-07-12)

Review wykazał, że pierwsza wersja retry opowiadała zbyt prostą historię. `attempts=0` dla starego błędu sugerowało brak wcześniejszej próby, choć sam status mówił coś przeciwnego. A licznik zwiększany przed callem zostawiał po awarii rekord wyglądający jak zwykła praca do zrobienia. Następne resume mogło więc kupić kolejną próbę pod niewinną nazwą „wznów”.

Naprawa nie polegała na lepszym zgadywaniu. Rekord dostał stan `EXTRACTION_IN_PROGRESS`: próba jest zarezerwowana, ale jej wynik nie jest jeszcze zapisany. To nie jest porażka ani sukces — to uczciwe „nie wiemy”. Zwykłe resume ma wtedy się zatrzymać. Tylko jawna polityka recovery może kiedyś zdecydować, co dalej.

**Zdanie do artykułu:** „Dobry system po awarii nie udaje pamięci. Zostawia miejsce na zdanie: nie wiemy, czy to już się wydarzyło.”

Ta korekta dodała też atomiczność migracji i możliwość świadomego podniesienia capu, jeśli exhausted run naprawdę odzyskuje legalny ruch. Wszystko sprawdzone offline: **164 testy**, 0 USD, zero API i bez zmian źródłowej bazy.

## Powiązania
- Źródła: `00`–`10`, `docs/BUILD_LOG.md`, `docs/DECISIONS.md` (ADR-017, ADR-019, ADR-020), `docs/COSTS.csv`, `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` CZĘŚĆ D, CZĘŚĆ E, CZĘŚĆ F
- Następny krok redakcyjny: szkic w `article-series/artykul-01-dlaczego-wlasny-substack.md`
