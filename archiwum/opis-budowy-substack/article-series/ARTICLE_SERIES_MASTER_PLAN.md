# ARTICLE_SERIES_MASTER_PLAN — seria o budowie agenta „Nothing Is Accidental"

> Data: 2026-07-12. Dokument redakcyjny (nie architektoniczny). Zastępuje **redakcyjnie** listę z `../15_PLAN_SERII_ARTYKULOW.md` — tamten plik pozostaje jako materiał historyczny; obowiązująca kolejność i briefy są tutaj.
> Fakty weryfikowane wg hierarchii: `CURRENT_PROJECT_STATE.md` (stan) → `MASTER_ARCHITECTURE.md` (architektura) → `IMPLEMENTATION_ROADMAP.md` (kolejność) → `docs/DECISIONS.md` (powody) → dzienniki (chronologia).
> Wszystko przeznaczone do publikacji — po angielsku. Komentarze organizacyjne — po polsku.

---

## 1. Analiza pierwszego artykułu

*„I'm Handing an AI Agent the Keys to a Substack Account"*

**Główna teza.** Prawdziwym eksperymentem nie jest „czy model umie napisać artykuł" (umie), tylko czy kontrolę przez nadzór da się zastąpić kontrolą przez reguły, progi i logi — mierząc to pieniędzmi, interwencjami i skutkami.

**Najmocniejszy element.** Otwarcie: *„The first real thing my AI agent ever did cost me $0.25 and produced nothing."* Jedno zdanie ustawia całą serię: konkret, pieniądze, porażka, zero pozy. Drugi najmocniejszy: zakaz pisania o AI jako uczciwość testu, nie gimmick.

**Obietnica dla czytelnika.** Dosłowna: *„this series will not be a demo reel. It will be a build log — costs, bugs, bad estimates and all."* Plus obietnice szczegółowe: każdy dolar (łącznie z kosztem jednego subskrybenta), każda interwencja człowieka jako właściwa metryka, każdy błąd (od klucza API bez .gitignore po estymator mylący się o 163%), finał po 30 dniach z ujawnieniem publikacji.

**Ton i narrator.** Pierwsza osoba, właściciel-budowniczy, nie ekspert. Suchy, rzeczowy, z rzadkim, ironicznym humorem (*„it doesn't know anything — it's a pipeline, not a person"*). Zdania krótkie tam, gdzie pada puenta. Liczby zawsze z kontekstem. Zero słownictwa startupowego.

**Elementy wymagające konsekwencji w serii:**
- Nie ujawniamy nazwy publikacji agenta do finału (kontaminacja danych wzrostu) — żaden tekst nie może jej zdradzić ani ułatwić identyfikacji.
- „Budget ledger" jako obietnica: liczby kosztów muszą się zgadzać co do szóstego miejsca po przecinku z `docs/COSTS.csv`/bazą.
- Rozróżnienie poziomów autonomii (Level 0–3) wprowadzone w artykule 1 — używać tej samej nomenklatury.
- Zdanie-kotwica serii (z ADR-017): *„the human approves the level of autonomy and its boundaries, not every individual action"* — można do niego wracać, nie wolno go rozmywać.
- Zapowiedziany tytuł finału: *„I gave an AI agent 30 days, $40, and its own Substack — and banned it from writing about AI."*
- Konwencja „agent to pipeline, nie osoba" — w kolejnych tekstach nie wolno pisać, że agent „chciał", „uwierzył", „postanowił" bez cudzysłowu lub ironii.

**Czego nie powtarzać:**
- Pełnej ekspozycji eksperymentu (budżet, limity, zakaz AI, poziomy) — w kolejnych tekstach maksymalnie jedno zdanie przypomnienia, za każdym razem inne.
- Historii $0.25/+163% jako głównego dania — była daniem głównym artykułu 1; wolno się do niej odwołać jednym zdaniem jako do punktu odniesienia.
- Metafory „keys to the account" i formuły „brain/hands/memory/gate" — zużyte w tekście 1.
- **Korekta faktograficzna:** artykuł 1 mówi „three revisions in a single day" — w rzeczywistości trzy przebudowy researchu (ADR-016/019/020) rozłożyły się na dwa dni (11–12.07). W kolejnych tekstach używać wersji ścisłej („three redesigns in 48 hours" / „two days"), nie powielać skrótu.

**Pytania, które artykuł otwiera (paliwo serii):**
1. Co właściwie kosztowało te $0.25 i dlaczego szacunek zawiódł? → art. 3
2. Jak wygląda „build log" od środka — co się naprawdę zbudowało, skoro nic nie publikuje? → art. 2
3. Czy bramka, która „czyta liczby, nie język", naprawdę działa, gdy model kłamie w liczbach? → art. 5
4. Kiedy agent napisze pierwsze słowo? → art. 9–10
5. Jak wygląda dzień, w którym człowiek musiał interweniować? → art. 6–7
6. Czy $40 wystarczy? → wątek stały, finał

---

## 2. Główna koncepcja serii

To nie jest seria „jak zbudowałem agenta AI" i nie jest to devlog. To zapis próby **przekazania oprogramowaniu odpowiedzialności** — z pełną księgowością tego, co ta próba kosztuje, zanim powstanie jakikolwiek efekt. Siłą serii jest odwrócenie proporcji, którego nie ma nigdzie indziej: po trzech dniach budowy i sześciu płatnych wywołaniach API agent nie napisał ani jednego zdania do publikacji — a mimo to wydarzyło się wystarczająco dużo na osiem artykułów: trzy realne porażki za łącznie $0.50, dwa błędy estymacji w przeciwnych kierunkach, audyt, który znalazł system przyznający sobie samemu oceny, i dokumentacja, która zaczęła kłamać szybciej niż kod. Czytelnik nie śledzi funkcji — śledzi pieniądze, decyzje i rachunek za każdą lekcję.

Drugie odwrócenie: bohaterem napięcia nie jest model (model jest nudny — robi, co umie), tylko **granica między modelem a światem**: księgowość, limity, stany, potwierdzanie skutków. Wszystko, co w demach agentów pomija się jako „szczegóły implementacyjne", tu jest fabułą.

**Redakcyjna zasada serii (jedno zdanie):**

> **Autonomy is measured in dollars spent, interventions logged, and effects confirmed — never in demos.**

Wariant zapasowy (bliższy obietnicy z artykułu 1): *„A build log keeps the receipts: what it cost, what broke, and who had to step in."*

---

## 3. Profile odbiorców i warstwy tekstu

| Odbiorca | Czego szuka | Która warstwa go trzyma |
|---|---|---|
| Ogólnie zainteresowani AI | „czy to już działa? czy mnie zastąpi?" | historia + liczby-hooki (25 centów za nic; $0.50 i zero zdań); zero żargonu w warstwie głównej |
| Twórcy/użytkownicy narzędzi AI | „co mnie czeka, gdy dam AI realne zadanie" | wnioski przenośne: estymaty vs rachunek, samoocena modelu, drift dokumentacji |
| Programiści / budujący agentów | „jak to ugryźć architektonicznie" | sekcja **Under the hood** + precyzyjne rozróżnienia (offline vs live, plan vs kod) |
| Zainteresowani przyszłością pracy | „co zostaje człowiekowi" | licznik interwencji + charakter interwencji (granice i cele, nie poprawki tekstu) |

**Układ warstw w każdym tekście (nie per akapit, per sekcja):** (1) historia z liczbami — dla wszystkich; (2) 1–3 akapity „co to znaczy, jeśli budujesz cokolwiek z AI" — dla środka tabeli; (3) opcjonalne *Under the hood* na końcu — wyłącznie dla technicznych; tekst musi być kompletny bez niego. Nie tłumaczymy pojęć w miejscu — tłumaczy je fabuła (czytelnik rozumie „idempotencję" przez historię o podwójnej publikacji, nie przez definicję).

---

## 4. Filary tematyczne serii

1. **Autopsies (failures with receipts).** Każda porażka z dokładnymi liczbami i zamknięciem: co miało działać, co się stało, ile kosztowało, co zmieniono. Trzyma czytelnika, bo w publicznym internecie prawie nikt nie pokazuje rachunków za własne błędy.
2. **The price of autonomy.** Koszt jako narracja: estymaty vs rzeczywistość, koszt porażki ≈ koszt sukcesu, cap który nie jest hamulcem. Uniwersalne — każdy, kto używa API, przeżył to samo mniejszym lub większym rachunkiem.
3. **The human in the loop — but not where you think.** Interwencje człowieka dzieją się na poziomie celów i granic (drift dokumentacji, „symptom vs przyczyna", zgody na wydatki) — nie przy poprawianiu tekstów, bo tekstów nie ma. Przewrotny wniosek: im mniej człowieka w pętli wykonania, tym więcej w pętli założeń.
4. **Architecture forced by reality.** Żadna przebudowa nie wzięła się z whiteboardu — każda ma numer incydentu i kwotę. Trzy generacje researchu w 48 godzin. Dla czytelnika: architektura jako osad po błędach, nie jako projekt.
5. **What the model can't know (and won't admit).** Epistemika: model przyznający sobie „VERIFIED" bez przeczytania źródła, confidence jako samoocena, dowód vs wiedza modelu. Najgłębszy filar — dotyka tego, czym różni się „brzmi prawdziwie" od „jest sprawdzone".
6. **Building in public without pretending.** Jawne rozróżnianie: zaplanowane / zakodowane / zielone testy / potwierdzone na żywym API / hipoteza. Buduje zaufanie, które jest jedyną walutą tej serii.

---

## 5. Kolejność serii (14 tekstów; #1 opublikowany)

Poziom techniczności: 1 = czysta narracja … 5 = tekst dla inżynierów. Statusy: **READY** (materiał kompletny dziś) / **NEEDS DATA** (czeka na przyszłe etapy).

| # | Tytuł roboczy (EN) | Tytuł alternatywny | Hook (1 zdanie) | Główne pytanie | Konflikt | Źródła | Wniosek | Tech | Under the hood | Prowadzi do | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | I'm Handing an AI Agent the Keys to a Substack Account | — | $0.25 for nothing | czy reguły zastąpią nadzór? | demo vs build log | (opublikowany) | eksperyment = kontrola, nie pisanie | 2 | — | całą serię | DONE |
| 2 | My Publishing Agent Has Written Zero Words. That's the Plan Working. | Three Days, Six API Calls, No Sentences | Half a dollar spent, 102 tests green, zero publishable words — and that's the healthiest possible state. | co się właściwie buduje, zanim agent napisze słowo? | oczekiwanie („agent = pisze") vs rzeczywistość („agent = księgowość, pamięć, granice") | CURRENT_PROJECT_STATE, COSTS.csv, BUILD_LOG, 05/14 | „działający agent" i „model, który umie pisać" to dwie różne inwestycje; pisanie jest ostatnie, bo jest najtańsze do cofnięcia | 2 | co naprawdę jest w SQLite: runs, model_usage, stany researchu; czemu dry_run ma osobną flagę kosztu | 3 (skoro księgowość jest sercem — jak bardzo można się w niej pomylić?) | **READY** |
| 3 | My "Pessimistic" Estimate Was 2.63× Too Low. The Fixed One Overshot 3×. | The Cap That Was Never a Brake | The safety margin I trusted was wrong in both directions within 24 hours. | czy da się z góry wiedzieć, ile zapłacisz za wywołanie agenta? | estymata vs rachunek; „cap" vs realny hamulec | ERRORS (3 wpisy COST), cost_estimator, COSTS.csv, 07/09/16 | jedyne twarde limity to te egzekwowane przez API (max_tokens, max_uses); wszystko przed wywołaniem to prognoza — trzeba pokazywać sufit i środek OSOBNO | 3 | kalibracja n=2 z rozrzutem 2.3×/search; czemu koszt rośnie z liczbą wyszukiwań, nie z rozmiarem promptu | 4 (skąd brały się porażki, za które płaciliśmy?) | **READY** |
| 4 | The Same Crash, Three Sizes Smaller | Symptom, Meet Cause | We hit the identical failure at 3000, 1200 and 500 tokens — because the size was never the problem. | dlaczego „podnieś limit" prawie zawsze kusi i prawie nigdy nie wystarcza? | łatka vs przebudowa; moment, w którym człowiek zatrzymuje płytszą naprawę | ERRORS (ucięcia 11.07/12.07/1L), ADR-016/020, 07 pkt „objaw kontra przyczyna", diagnostics | jeśli jedna odpowiedź niesie N wyników, ucięcie kasuje wszystkie N — konstrukcja, nie parametr; a pierwszą rzeczą do zbudowania po dwóch zgadywankach był magnetofon (raw response + stop_reason) | 3 | JSONL per linia; per-source calls; pierwszy raz przyczyna POTWIERDZONA (stop_reason=max_tokens), nie hipoteza | 5 (co jeszcze znalazł audyt, skoro tu było aż tak krucho?) | **READY** |
| 5 | The Agent Was Grading Its Own Homework | Three Bugs That Would Have Lied to Me | An audit found my agent marking sources "VERIFIED" it had never read — and a success status that had never once been written. | komu system raportuje prawdę, skoro sam wystawia sobie oceny? | samoocena modelu vs deterministyczny dowód; zielone testy vs żywe API | AUDYT (arch.), P0-1/2/3, validation.py, BUILD_LOG 1J/1K | bramka jakości licząca UNVERIFIED jak VERIFIED to bramka teatralna; „SUCCESS" istniał w enumie i dokumentacji, nigdzie w kodzie — dokumentacja opisuje intencje, baza opisuje fakty | 4 | P0-1 (terminal RUNNING), P0-2 (self-VERIFIED + min_verified_sources), P0-3 (jedna komenda bez capu); czemu naprawa to wymuszenie deterministyczne, nie lepszy prompt | 6 (skoro system się myli — kto i kiedy interweniuje?) | **READY** |
| 6 | Every Intervention So Far Happened Before the Agent Did Anything | The Human Edits the Goals, Not the Text | I've logged three human interventions — none of them touched a single sentence of content, because there is no content. | gdzie naprawdę jest człowiek w pętli, zanim jest co zatwierdzać? | oczekiwanie „człowiek poprawia teksty" vs rzeczywistość „człowiek pilnuje celu, granic i portfela" | HUMAN_INTERVENTIONS, ADR-017 (drift), 14 (wnioski o dryfie), 08 | dryf dokumentacji: system opisał się jako ostrożniejszy, niż miał być, i nikt tego nie zdecydował; agent pisał te zdania i sam dryfu nie zauważył | 2 | jak wygląda wpis interwencji (typ, obiekt, czas, skutek); czemu liczba interwencji to metryka nadrzędna eksperymentu | 7 (druga korekta tego samego dnia — w przeciwnym kierunku) | **READY** |
| 7 | More Autonomy, Less Disclosure: Two Corrections in One Day | The Bot That Won't Say It's a Bot (and Won't Deny It) | Hours after deciding the agent should ultimately act alone, we decided the public wouldn't be told it's an agent at all. | czy autonomia działania i jawność pochodzenia to jedna oś, czy dwie? | intuicja „więcej autonomii = więcej ujawnienia" vs decyzja: to niezależne wymiary | ADR-017/018, 16 pkt 15–16, D.5a (NO_REPLY) | anonimowość ≠ impersonacja: zero fikcyjnej osoby, zero kłamstwa przy pytaniu wprost — trzecia droga (brak odpowiedzi + prywatny log); zakaz technicznego maskowania pokazuje granicę między dobrymi manierami a oszukiwaniem platformy | 1 | reguła NO_REPLY jako klasyfikator + log, nie prompt; tabela powierzchni (gdzie prawda jest pełna: całe prywatne repo) | 8 (skoro dokumentacja steruje projektem — co gdy zaczyna kłamać?) | **READY** |
| 8 | The Documentation Started Lying Before the Code Did | Four Competing Architectures, One Repo | By day two the repo held four overlapping "target architectures" — and the agent that wrote them couldn't tell which one was true. | co się dzieje, gdy AI produkuje dokumentację szybciej, niż ktokolwiek ją czyta? | dokumentacja jako pomoc vs dokumentacja jako źródło błędu następnego modelu | ADR-023, BUILD_LOG 1P, HUMAN_INTERVENTIONS (review 4 korekt), archive/ | kanon trzeba wyznaczyć jawnie (source of truth + archiwum z twardym banerem), bo „więcej dokumentów" pogarsza sprawę; ta sama lekcja czeka każdy zespół używający AI do pisania czegokolwiek | 2 | zasada „ARCHIVED — NOT A SOURCE OF TRUTH"; czemu logi (append-only) przeżyły czystkę, a plany nie | 9 (porządek zrobiony — czas na pierwszą kompletną kartę) | **READY** |
| 9 | The First Card | $0.55 for One Honest Answer | After three failed attempts and $0.50, we're approving one more run — four sources, so the plan survives exactly one failure. | czy system w końcu dowiezie pierwszy kompletny, zweryfikowany research? | tolerancja jednej awarii (4 źródła przy progu 3) vs rzeczywistość, która dotąd psuła się inaczej niż planowano | ADR-022, BUILD_LOG 1O, wynik przyszłego runu | (zależny od wyniku — obie wersje uczciwe: sukces = pierwszy potwierdzony SUCCESS na żywo; porażka = czwarta lekcja z rachunkiem) | 3 | anatomia pre-flightu: expected vs conservative vs cap; czemu retry=0 | 10 | **NEEDS DATA** (run za zgodą właściciela, zad. 9 Etapu 0) |
| 10 | Teaching the Agent to Write (Last) | Three Audits Before a Single Reader | The writing engine is the last thing we're building — and it won't publish anything that can't cite its own research card. | czy tekst z kartą dowodową różni się od „tekstu AI"? | generacja vs trzy deterministyczne audyty (fact/style/growth) | Etap 3 roadmapy, instrukcja pisania, przyszłe evaluations | (hipoteza do sprawdzenia: audyty wytną więcej, niż autor by chciał) | 3 | mapowanie twierdzenie→claim→evidence_excerpt; pętla rewrite z limitem | 11 | **NEEDS DATA** (Etap 3) |
| 11 | Pressing Publish With a Robot Hand | The Timeout That Might Have Posted | A browser timeout after "submit" means you might have published — and the worst response is trying again. | jak opublikować coś dokładnie raz, nie wiedząc, czy się udało? | retry-instynkt vs UNCERTAIN-status; weryfikacja skutku odczytem stanu | Etap 5, MASTER §8.2, przyszłe joby | publikacja to problem idempotencji, nie generacji | 4 | idempotency_key, verify-before-publish, screenshot jako dowód | 12 | **NEEDS DATA** (Etap 5) |
| 12 | The Agent Reads the Room | Five Comments a Day, One per Author | Its first social act is bounded by numbers: 3–5 comments, one per author, links under 10%. | czy da się uczestniczyć w społeczności wyłącznie przez limity i scoring? | uprzedzenie „AI spamuje" vs antyspam z liczb | Etap 6, D.5 scoring, przyszłe interactions | (do zmierzenia: odbiór realnych komentarzy) | 2 | scoring progowy komentarza; cooldowny | 13 | **NEEDS DATA** (Etap 6) |
| 13 | What the Numbers Said | Cost per Subscriber, Finally | For the first time we can divide dollars by subscribers — the number this whole series promised. | czy dane zmieniają strategię, czy tylko ją uzasadniają? | strategy loop vs pokusa nadinterpretacji małych liczb | Etap 7, metrics_daily, strategy_decisions | (do zmierzenia) | 2 | attribution bez twardych danych platformy; is_estimated | 14 | **NEEDS DATA** (Etap 7) |
| 14 | I Gave an AI Agent 30 Days, $40, and Its Own Substack | (tytuł obiecany w #1) | pełne rozliczenie + ujawnienie publikacji | czy reguły zastąpiły nadzór? | cała seria | wszystko | (finał) | 2 | pełny ledger | — | **NEEDS DATA** (30 dni) |

**Zasada kolejności:** teksty 2–8 są gotowe dziś i celowo NIE są raportem z etapów — każdy jest problemowy (księgowość, estymaty, konstrukcja vs parametr, epistemika, rola człowieka, jawność, kanon dokumentacji) i łączy zdarzenia z różnych dni. Teksty 9–14 wchodzą w rytm rzeczywistych postępów projektu; jeśli projekt się wywróci, każdy z nich ma uczciwą wersję „porażkową".

---

## 6. Trzy następne artykuły — briefy

### Artykuł 2: „My Publishing Agent Has Written Zero Words. That's the Plan Working."

- **Otwarcie:** *After three days, six paid API calls and $0.50, my publishing agent has produced exactly zero publishable words. If that sounds like failure, you've just discovered the difference between a language model and an agent.* (liczby: 6 requestów, $0.500616, 102 testy — zweryfikowane w bazie).
- **Przebieg narracji:** (1) inwentarz z zaskoczenia — co JEST po trzech dniach: księga kosztów co do 6 miejsc po przecinku, baza stanów, bramka budżetowa, wyłącznik, dziennik każdej próby; czego NIE MA: ani zdania treści; (2) dlaczego ta kolejność nie jest przypadkiem — każdy element powstał jako reakcja na coś, co realnie zabolało (jedno zdanie o $0.25 jako odnośnik do art. 1, bez powtarzania historii); (3) scena: dry_run — agent „pracuje" całymi przebiegami bez wydania centa, koszty księgowane osobną flagą jako estymaty; (4) rozróżnienie planned/coded/tested/live — tabelka słowna, uczciwie: research potwierdzony częściowo na żywo, synteza nigdy; (5) refleksja: pisanie jest ostatnie, bo jest najtańsze do cofnięcia — cofnąć nie da się wydatku i publikacji.
- **Najważniejsze sceny:** inwentarz „co kupiło $0.50"; dry_run jako teatr prób; moment z audytu (jedno zdanie — zapowiedź art. 5).
- **Liczby:** $0.500616 (1,25% budżetu); 6 realnych requestów; 0 kart; 0 słów treści; 102 testy; 3 dni; 5 migracji bazy; 2 USD/dzień, 40 USD/mies.
- **Under the hood:** co siedzi w SQLite (runs, model_usage z flagą dry_run, stany researchu); czemu budżet liczy tylko wiersze realne.
- **Finał:** *The agent will eventually write. But the first thing I needed it to do reliably was spend money without lying about it.*
- **Ryzyko:** tekst-inwentarz może osunąć się w changelog. **Unik:** każda pozycja inwentarza wchodzi tylko z powodem-zdarzeniem („ledger istnieje, bo…"), nie jako feature; maksymalnie 8 pozycji; zero nazw plików w warstwie głównej.

### Artykuł 3: „My ‘Pessimistic' Estimate Was 2.63× Too Low. The Fixed One Overshot 3×."

- **Otwarcie:** *Before the first paid call, the system computed a "pessimistic ceiling" of $0.095. Anthropic charged $0.25. Twenty-four hours later the corrected estimator predicted $0.36 for a call that cost $0.12. Both numbers were wrong. Only one of them was safe.*
- **Przebieg:** (1) rekonstrukcja pierwszego szacunku — płaski bufor tokenów, logika „wyglądało rozsądnie"; (2) rachunek z konsoli: $0.21 tokeny + $0.04 search; przyczyna: koszt rośnie z LICZBĄ wyszukiwań (treść wyników wraca jako kontekst) — mechanizm wyjaśniony na obrazie „każde wyszukiwanie dosypuje modelowi lektury, za którą płacisz"; (3) najniewygodniejsze odkrycie: `--max-cost-usd` nigdy nie był hamulcem — API nie przerywa wywołania po kwocie; hamulcem są tylko max_tokens i max_uses; (4) naprawa i jej pokora: kalibracja z 1 obserwacji → druga obserwacja różni się per-search 2.3× → decyzja: pokazywać ZAWSZE dwie liczby (conservative/expected), nigdy jedną; (5) wniosek uniwersalny: gdy prognozujesz koszt systemu z pętlą narzędzi, błąd w obie strony jest normą — bezpieczeństwo bierze się z twardych limitów w wywołaniu, nie z lepszej prognozy.
- **Sceny:** właściciel sprawdzający konsolę Anthropic (agent nie ma tam dostępu — bez człowieka błąd żyłby dalej); moment „margines 50% obowiązkowy".
- **Liczby:** 0.095 → 0.25 (+163%, 2.63×); 0.3615 → 0.123823 (~34% sufitu); per-search 0.04875 vs 0.020956; margines ≥50%; cap 0.30 (zapas $0.05 zamiast $0.20).
- **Under the hood:** czemu kalibrujemy z realnych obserwacji zamiast cennika; wzór sufitu; dlaczego failed call kosztuje prawie tyle, co udany.
- **Finał:** *An estimate is a story you tell yourself before the bill arrives. The bill is the only part the budget believes.*
- **Ryzyko:** za dużo arytmetyki pod rząd. **Unik:** liczby podawane parami w zdaniach narracyjnych, żadnych tabel w warstwie głównej; jedna tabela dopuszczalna w Under the hood.

### Artykuł 4: „The Same Crash, Three Sizes Smaller"

- **Otwarcie:** *We hit the same failure three times: at 3,000 tokens, at 1,200, and at 500. Each time the response was longer than the box we gave it, and each time the box was not the problem.*
- **Przebieg:** (1) trzy ucięcia jako jedna choroba: jedna odpowiedź niosąca WSZYSTKIE wyniki naraz — ucięcie w dowolnym miejscu kasuje wszystko; (2) instynkt „podnieś limit" i scena, w której człowiek go zatrzymuje („samo podniesienie limitu nie jest wystarczającym rozwiązaniem") — objaw vs przyczyna; (3) przebudowa: szukanie zwraca tylko listę adresów (po jednym na linię — uszkodzona linia gubi jeden wiersz, nie całość), czytanie = jedno źródło na wywołanie, zapis natychmiast; awaria źródła 4 nie dotyka 1–3; (4) wątek detektywistyczny: przez dwa incydenty przyczyna ucięcia była HIPOTEZĄ, bo nikt nie zapisywał surowej odpowiedzi — trzecia porażka jest pierwszą z dowodem (stop_reason=max_tokens wprost z API); najtańszym narzędziem debugowania okazał się magnetofon; (5) wniosek: najlepsza naprawa bywa przyznaniem, że limit nigdy nie był problemem — problemem była konstrukcja wymagająca zgadywania limitu.
- **Sceny:** trzy daty, trzy liczby limitów; decyzja właściciela; pierwszy odczyt pliku diagnostycznego.
- **Liczby:** 3000/1200/500; output 640 i 653 przy limicie 500; diagnostyka: 915 tokenów, end_turn, $0.028969; koszt trzech porażek: 0.25 + 0.123823 + 0.097824.
- **Under the hood:** JSONL vs JSON; per-source persistence; czym jest stop_reason i czemu bez niego debugowaliśmy na ślepo.
- **Finał:** *Every architecture we shipped this week is just the residue of a failure we could finally prove.*
- **Ryzyko:** czytelnik nietechniczny zgubi się w tokenach. **Unik:** metafora pudełka/lektury utrzymana konsekwentnie; ani jednego fragmentu JSON w warstwie głównej.

---

## 7. Powracające elementy serii

| Element | Forma | Częstotliwość |
|---|---|---|
| **The ledger** | 1–2 zdania w tekście (nie ramka): wydatek łączny + % budżetu + koszt zdarzeń z tego odcinka | co tekst, ale wpleciony w prozę — nigdy jako tabelka-rytuał |
| **Interventions count** | licznik + JEDNO zdanie, czego dotyczyła ostatnia | gdy przybyła nowa; nie odhaczać „wciąż 3" w każdym tekście |
| **Autonomy level** | wzmianka tylko przy zmianie lub gdy tekst o tym traktuje | rzadko; poziom zmienia się wolno i częste raportowanie by to obnażało nudą |
| **What the agent believed vs what happened** | dwuzdaniowy kontrast | tylko przy realnym rozjeździe (estymata/rachunek, VERIFIED/nieprzeczytane); max 1 na tekst |
| **Under the hood** | sekcja końcowa 100–250 słów, opcjonalna dla czytelnika | co tekst, jeśli jest treść; wolno pominąć |
| **Open question** | ostatni akapit zostawia jedno sprawdzalne pytanie | sporadycznie — tylko gdy pytanie jest prawdziwe i wróci w serii; nie jako cliffhanger-rytuał |
| **Receipts** (dosłowne kwoty z 6 miejscami) | liczby jak z księgi: $0.500616, nie „~pół dolara" (pierwsze użycie w tekście; potem można zaokrąglać) | stały tik serii — jej podpis |

Regularnie: ledger, Under the hood. Sporadycznie: cała reszta. Nic nie może wyglądać jak rubryka do odhaczenia — jeśli element nie wnosi treści w danym tekście, znika bez śladu.

---

## 8. Zasady stylu serii (uzupełnienie instrukcji naturalnego pisania i profilu Chaos Engine)

1. **Pierwsza osoba budowniczego, nie eksperta.** „I trusted this number and it was wrong" zamiast „common pitfalls include". Autor uczy się na oczach czytelnika; wolno przyznać, że agent napisał większość dokumentacji, w której autor nie zauważył dryfu.
2. **Liczby zawsze z kontekstem i zawsze zgodne z księgą.** Kwota + odniesienie (% budżetu, porównanie z szacunkiem). Pierwsze wystąpienie kwoty — dokładne; dalej można zaokrąglać. Żadnych liczb „z pamięci": każda musi mieć źródło w COSTS.csv/bazie/dziennikach.
3. **Akapity o różnych funkcjach i długościach** (dowód / scena / komentarz / kontrargument); krótkie zdanie tylko jako puenta po dłuższym wywodzie. Śródtytuły 2–4 na tekst, frazowe, bez „Podsumowania".
4. **Terminologia:** w warstwie głównej zero nazw klas, plików, tabel; pojęcia techniczne wchodzą przez skutek („system, który nie umie zapisać własnego sukcesu"), definicja najwyżej w Under the hood. Wyjątek: pojęcia-osie serii (research card, Policy Engine, dry run, kill switch) — używane konsekwentnie, wprowadzone raz.
5. **Kod:** nie cytujemy kodu w warstwie głównej; w Under the hood najwyżej 1 krótki fragment/pseudokod, tylko gdy niesie puentę.
6. **Humor:** suchy, rzadki (1–3 miejsca), zawsze kosztem sytuacji albo autora, nigdy „zabawnego robota". Wzorzec z art. 1: „it's a pipeline, not a person".
7. **Porażki:** protokolarnie, z kwotą i zamknięciem; zero autobiczowania i zero bagatelizowania. Formuła serii: co miało się stać → co się stało → rachunek → co zmieniliśmy. Porażka bez wniosku nie wchodzi do tekstu.
8. **Anty-AI-ton:** zakazy z instrukcji obowiązują w wersji EN (no „delve/pivotal/game-changing/journey"); żadnych symetrycznych trójek, pytań retorycznych jako przejść, podsumowań sekcji; różnicować typ otwarcia i architekturę wywodu między kolejnymi tekstami (nie dwa razy z rzędu ta sama konstrukcja).
9. **Uczciwość statusów:** przy każdym twierdzeniu o działaniu systemu jasne, czy to plan, kod, zielony test offline, czy potwierdzenie na żywym API. Formuły: „tested offline, never proven live", „the code exists; the proof doesn't yet".
10. **Cudze głosy:** cytaty tylko z własnych dokumentów projektu (ADR, logi) — i oznaczane jako takie; żadnych wymyślonych dialogów.

---

## 9. Czego nie robić (zagrożenia redakcyjne)

- **Changelog przebrany za artykuł** — jeśli tekst da się streścić „zrobiliśmy X, potem Y", nie ma tekstu. Test: czy istnieje konflikt/pytanie, które przeżyje usunięcie połowy szczegółów?
- **Nazwy klas/tabel/plików w warstwie głównej** — czytelnik nie zna repo i nie musi; wszystko takie idzie do Under the hood albo znika.
- **Przepisywanie roadmapy** — plany nie są historią; o przyszłości mówimy najwyżej ostatnim akapitem i tylko konkretem najbliższego kroku.
- **Re-ekspozycja eksperymentu w każdym tekście** — jedno zdanie przypomnienia, za każdym razem inaczej sformułowane; kto wszedł w środku serii, dostanie link do #1.
- **Sztuczne cliffhangery i dramatyzowanie** — trzy porażki za $0.50 są ciekawe same z siebie; „ale wtedy stało się coś, co zmieniło WSZYSTKO" jest zakazane.
- **Udawanie autonomii, której nie ma** — agent niczego nie publikuje, nie komentuje, nie decyduje o wydatkach; poziom faktyczny to kontrolowane, pojedyncze akcje za zgodą. Każde „the agent decided" wymaga sprawdzenia, czy to nie był człowiek albo deterministyczna reguła.
- **Chwalenie architektury** — architektura pojawia się wyłącznie jako konsekwencja zdarzeń („po trzecim ucięciu…"), nigdy jako obiekt dumy; żadnych diagramów-pochwał.
- **Publikowanie, bo domknięto etap** — tekst wchodzi, gdy jest historia z napięciem i wnioskiem; ukończenie migracji 0006 nie jest historią. Odwrotnie też: dobra historia może czekać na drugą połowę faktów (art. 9 czeka na run, nie odwrotnie).
- **Mieszanie estymat dry_run z realnymi kosztami** — w tekstach kwoty realne i szacunkowe zawsze rozdzielone słowem („estimated"/„billed").
- **Zdradzanie nazwy publikacji agenta** — również pośrednio (nisza-tematy przykładowe podajemy najwyżej te, które już ujawnił art. 1: supermarkety, bilety, walizki).
- **Dwa zakończenia** (puenta + morał) i podsumowania po sekcjach — obowiązuje instrukcja pisania.

---

## 10. Końcowa rekomendacja

1. **Następny artykuł:** #2 — *„My Publishing Agent Has Written Zero Words. That's the Plan Working."*
2. **Dlaczego ten:** podejmuje dokładnie to pytanie, które art. 1 zostawia otwarte („co właściwie budujesz, skoro nic nie publikuje?"), odwraca oczekiwanie czytelnika (inwersja „zero słów = plan działa" jest tezą, nie unikiem), scala wszystkie dotychczasowe fakty bez powtarzania historii $0.25, i ustawia sceny pod teksty 3–5 (estymaty, ucięcia, audyt). Jest też najbezpieczniejszy faktograficznie: opiera się wyłącznie na stanie zweryfikowanym (baza, testy, COSTS.csv), bez zależności od przyszłych runów.
3. **Materiał, który już istnieje:** komplet — CURRENT_PROJECT_STATE (stan modułów, liczby kontrolne), COSTS.csv (6 realnych wierszy, $0.500616), BUILD_LOG (chronologia 11–12.07), 05/14 (sceny i wnioski), art. 1 (ton i obietnice).
4. **Czego brakuje:** niczego blokującego. Opcjonalnie wzmocniłyby tekst 2–3 screenshoty (COSTS.csv z realnymi wierszami; `pytest` 102 passed; wydruk dry_run z „koszt~0.004200 USD (szacunek dry_run)") — do zrobienia w 10 minut, wpis w SCREENSHOT_INDEX już to przewiduje.
5. **Czy można pisać uczciwie już teraz:** tak — pod dwoma warunkami dyscypliny: (a) każda wzmianka o researchu rozróżnia „zielone offline" od „na żywo: A1 tak, ekstrakcja raz, synteza nigdy"; (b) tekst nie obiecuje daty pierwszej publikacji (roadmapa jej nie gwarantuje).
6. **Pierwszy akapit (propozycja):**

> After three days, six paid API calls and exactly $0.50, my publishing agent has produced zero publishable words. No drafts, no titles, not a sentence. If that sounds like the project is failing, you've just run into the difference between a language model and an agent — a language model writes on request; an agent has to be trusted with money, memory and consequences first. The writing turned out to be the last thing you build, because it's the only part you can take back.

---

*Uwagi organizacyjne: plik zastępuje redakcyjnie listę artykułów z `15_PLAN_SERII_ARTYKULOW.md` (tamten zostaje jako historia; przy najbliższej aktualizacji kroniki warto dopisać mu jednolinijkową notę odsyłającą tutaj — poza zakresem tego zadania). Szkice piszemy w tym folderze wg konwencji `artykul-NN-<slug>.md`. Przed każdym szkicem: skill chaos-engine-writer + ta lista + weryfikacja liczb względem `docs/COSTS.csv` i `CURRENT_PROJECT_STATE.md`.*
