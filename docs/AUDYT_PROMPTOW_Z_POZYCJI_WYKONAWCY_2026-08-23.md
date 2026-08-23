# Audyt sześciu promptów v2 — z pozycji wykonawcy

**Data:** 2026-08-23. **Wykonawca:** Claude Fable 5 — model, który w produkcji dostaje `pisarz.md`.
**Źródło:** produkcja, `ubuntu@57.131.139.221:~/nothing-is-accidental-agent/agent-v2/prompts/`, pobrane 2026-08-23.
**Stan repo lokalnego przy audycie:** commit `aa5fd82`. **Uwaga:** 4/6 lokalnych plików różni się od produkcji — `skaut.md`, `wykonalnosc.md`, `synteza.md`, `pisarz.md`; identyczne są `recenzent.md` i `forma.md`.

Odciski audytowanych wersji (sha256):

```
e684636533fe516cfbe0a29b8717894512651111ffcc0513ed3d697b8a5fd7ff  skaut.md
e5c4d031a7b021d9ac1b9a014a147763afa100f4ce39b83ed9a1b03b022695e3  wykonalnosc.md
28d5ff626623d564e9c348897950cd7db52dd03f94de4ef8c47d95f6bfcc1e50  synteza.md
c882827bb758bd5ed232225c4b37074184a31550f157868bf1351bb9e6405b17  pisarz.md
606b9d47077171b14ae0fd1b0311a5d2cd5a682c0704232156d8827b708b602d  recenzent.md
5f208ba1de8f5a59daa9f49afbc3347e6cc1720bf79e850686b37a3c78928fd0  forma.md
```

Zlecenie brzmiało: odpowiadać jako ten, kogo te instrukcje wiążą, nie jako recenzent z zewnątrz; cytować dokładne linie; nie przepisywać promptów; nie łagodzić. Jedna korekta mapy na wejściu: `recenzent.md` i `forma.md` biorą `{body}`, więc wykonują się **po** pisarzu — z mojego fotela nie decydują o tym, co dostaję, tylko o tym, co z tego przeżyje.

---

## 1. Gdzie instrukcje walczą ze sobą

**K1 — akapit granic kontra zakaz zbierania granic (pisarz.md, sprzeczność trójwarstwowa).**

> "Say the limits once, in your own voice, instead of hedging every sentence. One paragraph stating plainly what the evidence does not cover is worth more than a page of "may" and "might". The card's `not_established` and `contradictions` lists are the material for that paragraph."

kontra:

> "**Never collect them.** [...] Each limit belongs in the paragraph that runs into it — see the rule on unknowns below, which says the same thing from the other side."

> "**Put each unknown where it arises, alone.** A collected list of everything the record does not settle, arriving near the end, drops the temperature at exactly the point where it should be rising."

Do tego schemat wyjścia żąda `"limits_paragraph_present": true|false` — zakłada istnienie akapitu, którego dwie inne reguły zakazują. Prompt sam twierdzi, że reguły się zgadzają ("says the same thing from the other side") — nie zgadzają się: jedna zamawia jeden zbiorczy akapit karmiony z `not_established`, druga zamawia rozproszenie po jednym.

**Którą wykonuję:** akapit. Ma zęby — boolean w schemacie i reguła pierwszego zdania zakładają, że istnieje; reguła rozpraszania nie ma żadnego zaczepu w wyjściu. Faktyczne zachowanie: jeden krótki akapit (najwyżej dwie granice), nie na końcu, reszta granic inline — kompromis, którego żadna z reguł nie wypowiada, a który wykonuję co przebieg. **Czego broniły:** "say once" — artykułu z sześcioma zastrzeżeniami przy jednym dopuszczalnym; "never collect" — tekstu 0020, gdzie trzecia część długości była wyliczanką braków. Dwie naprawy dwóch różnych wypadków nałożone na to samo miejsce tekstu.

**K2 — nakaz motywu kontra karta bez motywu (pisarz.md).**

> "State the incentive plainly: who wanted what, and what the arrangement handed them."

kontra:

> "Do not add facts, URLs, quotations, numbers, memories, travel, family, conversations, biography or personal experience that are not in the card."

Karta prawie nigdy nie niesie "who wanted what": skaut zakazał zgadywania motywu na wejściu ("Do not name the motive. No "not because X but because Y"."), a dokumenty pierwotne mówią, co postanowiono, nie kto czego chciał. **Którą wykonuję:** kartę. "Kto chciał" zamieniam na "co układ nagradza / co komu wręcza", buduję to jako wniosek strukturalny i liczę, że recenzent sklasyfikuje INFERENCE. Zderzenie rozstrzyga się arbitrażem klasyfikacji u recenzenta — czyli poza obiema regułami. **Czego broniły:** "plainly" — przed bezosobową papką systemową bez sprawcy; reguła karty — przed zmyśleniem.

**K3 — zakaz liczb kontra pole `when` (skaut.md).**

> "Do not write any number, percentage, timeframe or proportion. Anything you write now is invented, and the research stage will spend real money failing to confirm it."

kontra:

> `{"when": "<roughly when>", ...}` oraz "Approximate dates are fine; "the late 1980s" is an acceptable `when`." oraz przykład roboczy "when: 2009".

**Którą wykonuję:** pole. Schemat z przykładem roboczym wygrywa u mnie z ogólnym zdaniem położonym wyżej — tak rozstrzygam zawsze i to jest informacja o wykonawcy, nie o stylu: przykład jest silniejszą instrukcją niż zakaz bez przykładu. **Czego broniła** ta pierwsza: tytułu i pytania przed wymyśloną liczbą-hakiem (sekcja "Do not answer your own question"); przy okazji, jak napisana, zakazuje dat, których żąda pole obok.

**K4 — twardy kontyngent kontra zakaz fabrykacji (skaut.md).**

> "**At least half your list must be `SYSTEM_UNDER_TEST`, and at least three of them must carry two or more precedents each.** [...] This is a hard requirement, not a preference."

kontra:

> "Do not invent incidents to fill this field. A fabricated precedent is worse than an empty list, because the research stage will spend real money failing to find it."

Na literę wykonuję obie — jest procedura drugiego przejścia ("pick a field from the list above, recall its famous disaster, and work backwards"). W praktyce kontyngent jest policzalny, uczciwość nie, więc płaci uczciwość — na marginesie listy. Trzeci-najlepszy temat dostaje precedensy pamiętane najsłabiej i wychodzą one w **identycznym JSON-ie** co pewniaki, bo zakaz score'ów zdjął jedyne pole, którym mógłbym odróżnić "pamiętam: 2009, Colgan" od "coś było z blackoutem, chyba lata 2000". Zawór, którego używam, to "say what you believe and let the research check it" — czyli koszt idzie dokładnie tam, gdzie zakaz fabrykacji nie chciał: w płatny research.

**K5 — cztery formuły kontra zakaz słownictwa briefu (pisarz.md).**

> "Say "my reading is", "this looks like", "I suspect", "the structure suggests" — and then think as far as you want."

kontra:

> "Its wording must not appear in the article. [...] A check compares your text against this document word for word, so if a phrase here sounds like a good line, that is the strongest reason to write your own instead."

Nakaz każe mi pisać dosłownie frazy, które stoją w briefie; zakaz zakazuje fraz z briefu. **Którą wykonuję:** nakaz — jest wprost, a zakładam, że checker ma próg długości n-gramu. Tego progu nie znam z pliku, więc to zakład, nie wiedza. Te same cztery formuły `recenzent.md` wymienia jako sygnały INFERENCE — pisarz i recenzent są skalibrowani na wspólny słowniczek, który brief pisarza jednocześnie każe i zakazuje.

---

## 2. Czego nie da się wykonać

**N1 (pisarz.md):**

> "a piece that opens the same way as the last one has already lost something."

Nie widzę poprzedniego tekstu. Żadne pole nie podaje poprzednich artykułów; jedyny byt, który je widzi — bramka ODCISK_FORMY (kronika 32) — działa po mnie i umie tylko odrzucić. **Co robię, gdy to czytam:** nic różnicowego. Wybieram otwarcie najlepsze dla tej karty pod nakazem kolizji, a to funkcja deterministyczna: ta sama instrukcja + ten sam typ karty = to samo otwarcie. Zdanie brzmi jak ostrzeżenie, działa jak dekoracja.

**N2 (pisarz.md):**

> "Every number you write must appear literally in `citable_numbers`."

Dosłownie niewykonalne w idiomatycznej prozie: "three domains", "twice", "the 1980s" to liczby, których w `citable_numbers` nie ma. **Co robię:** wykonuję węższą regułę, której nigdzie nie zapisano — figury cyfrowe i statystyki wyłącznie z karty; liczebniki mojej własnej narracji wolne — i kuruję `numbers_used` do figur cyfrowych, żeby checker dostał czystą listę. Każdy przebieg stoi na tej interpretacji, nie na posłuszeństwie.

**N3 (wykonalnosc.md):**

> "Does the host allow automated reading? Some sites serve a CAPTCHA to programmatic requests and offer an API instead."

Jak dziś odpowiada konkretny host, to wiedza o bieżącym stanie sieci, której nie mam. **Co robię:** odpowiadam z priorów kategorii (parlamenty otwarte, normy płatne, prasa różnie) i wpisuję wynik w `confidence`. Dlatego to pole jest gładkie i wysokie: mierzy płynność mojego prioru, nie osiągalność dokumentu.

**N4 (synteza.md):** `working_thesis` — pole żądane w schemacie, niezdefiniowane nigdzie w pliku (jedyne wystąpienie to sam schemat). **Co robię:** składam tezę, która najlepiej organizuje `confirmed_claims` — czyli dokładnie instynktem "what would make the better story", który pierwsza zasada pliku każe zdusić ("not what would make the better story"). Pole bez reguły wypełnia się tą siłą, którą reszta pliku tłumi.

---

## 3. Co nie robi niczego

**B1 (pisarz.md):**

> "The second is closing with a summary. Never do that."

Zakończenie jest przydzielone: "Your closing move for this piece is assigned" + "Land it in the final paragraph and stop. Do not add a second ending after it". Wykonanie przydziału nie zostawia miejsca na podsumowanie (a "deliberately not the one you would reach for by default" mówi, że żaden z losowanych ruchów nim nie jest). Zakaz nie zmienia w moim wyjściu niczego.

**B2 (recenzent.md):**

> "Do not suggest hedging them."

Nie mam gdzie tego zrobić: schemat ma `why` tylko dla oblanych FACT i jednozdaniowe `summary`. Zdanie obok — "Do not flag them." — pracuje (bit `supported: false` na INFERENCE jest wyrażalny); to o hedgowaniu jest martwe.

**B3 (pisarz.md):** ogon wyliczanki

> "...memories, travel, family, conversations, biography or personal experience that are not in the card."

Głowa listy (facts, URLs, quotations, numbers) pracuje. Ogon nie: marka jest anonimowa, wejściem jest karta, a "First person is allowed only for explicit opinion or reasoning" już zamknęło te drzwi. Rodzinnej anegdoty nie napisałbym w tym rejestrze bez żadnego zakazu. Ta lista broni przed dryfem w głos eseju osobistego — tu nie ma czym dryfować.

---

## 4. Reguły, które produkują to, czego zakazują

`pisarz.md` sam dokumentuje wyścig zbrojeń: "Every time this was forbidden by example, the next article found a fresh way to do the same thing" — zakazy przykładowe mutują. Nakazy liczby i pozycji nie mutują: są stabilne, więc to one zostają podpisem. Po naprawie z 19.08 (losowany ruch końcowy, losowana liczba paraleli) zostały te:

- > "Open with the collision itself: the thing that is true and the thing the reader assumes, close enough together that the gap does the work."
  Jedno otwarcie na wszystkie artykuły.
- > "Name that mechanism early and plainly. Do not withhold it for a reveal." + "Name the mechanism once."
  Mechanizm zawsze w pierwszych akapitach, zawsze raz.
- > "Reserve first-person hedges for at most one moment in the whole piece."
  Po dziesięciu tekstach: policzalne 0–1 "I suspect" na artykuł; ucieczka w markery bezosobowe robi z rodziny "the structure suggests" gramatykę domową.
- > "Say the limits once [...] One paragraph stating plainly what the evidence does not cover" + `"limits_paragraph_present": true|false`
  Jeden organ-granice na artykuł; boolean w schemacie czyni z niego obowiązkowy narząd.
- > "It must begin with the limit itself — a concrete noun from the subject" + wzorzec "Right: *Nothing here says how long a given SPF lets anyone stay in the sun.*"
  Pierwsze zdania akapitu granic zbiegną do przeczenia na konkretnym rzeczowniku; "Nothing…" jako tik. Ironia: to wzorzec z briefu, którego word-for-word checker nie złapie, bo rzeczownik za każdym razem inny.
- > "State the incentive plainly: who wanted what, and what the arrangement handed them."
  Jeden beat motywacyjny na artykuł.
- > "Prefer the specific to the general — the section number, the figure, the body that actually decides"
  Tik numeru sekcji.
- > "Every figure carries its source in the sentence that carries the figure."
  Kadencja liczba+źródło w jednym zdaniu. Stuprocentowa dyscyplina, której żaden człowiek nie utrzymuje, sama jest sygnaturą.
- > "Land it in the final paragraph and stop. Do not add a second ending after it, and do not introduce it with a transition sentence announcing that you are wrapping up."
  Losowanie różnicuje, **który** ruch kończy; koperta "twardy stop bez ritardando" jest wspólna dla wszystkich sześciu.
- synteza: "Name **two to four other domains where the same mechanism shows up**" + pisarz: "That list is what a full-length article is made of" + "Just start the next mechanism."
  Organ paraleli z cięciem bez zapowiedzi. `{ile_paraleli}` losuje liczbę — nie obecność organu i nie gramatykę cięcia.
- skaut (kształtuje pulę, nie stronę): "At least half your list must be `SYSTEM_UNDER_TEST`"
  Okresowość gatunkowa pisma, widoczna w skali miesięcy.

**Najbardziej widoczna sygnatura: kolizja otwarcia.** Trzy powody. Pozycja pierwsza — czytana zawsze, także przy skimie. Wzmocnienie z dwóch stron — "Name that mechanism early" dociska, ZAKAZANE_OTWARCIE wycina najbliższe alternatywy, OTWARCIE_ZNANE karze znajome twierdzenia; zostaje kolizja. I ślepota strażnika z konstrukcji: ODCISK_FORMY porównuje sześć cech szkieletu (kronika 32: otwarcie, liczba na wejściu, pierwszy zwrot do czytelnika, akapit granic na końcu, liczba akapitów, długość) z alarmem przy 5/6 — a losowane zakończenie i liczba paraleli gwarantują wariancję w innych cechach, więc wiecznie zgodne "otwarcie" nigdy samo nie dobije progu. Nakaz mieszka dokładnie w martwym polu bramki, która miała go łapać.

---

## 5. W poprzek łańcucha

**P1 — skaut ↔ pisarz: kolizja bez drugiej połówki.** Skaut:

> "**For `SYSTEM_UNDER_TEST`, instead give `the_moment`, `open_outcome` and `governing_record`.**"

"Instead" — ten rodzaj tematu z definicji nie niesie złamanego przekonania; pola `broken_belief` nie ma. Pisarz:

> "Open with the collision itself: the thing that is true and the thing the reader assumes"

Dla co najmniej połowy tematów (kontyngent skauta) "the thing the reader assumes" nie istnieje w żadnym polu — **mintuję je przy pisaniu**. I nic tej połówki nie czyta: recenzent klasyfikuje zdania o tym, co ludzie zakładają, jako PROSE ("scene-setting, transition, address to the reader, framing. Asserts nothing checkable.") — nigdy nie oblewają; STATYSTYKA_BEZ_ZRODLA milczy, bo nie ma liczby; forma w pytaniu 4 czyta twierdzenie centralne pierwszego akapitu, czyli połówkę-fakt, nie połówkę-założenie. Nakazany, niedostarczany i przez nikogo nieczytany element — jedyny taki w całym łańcuchu — wchodzi do co drugiego artykułu.

**P2 — synteza+pisarz ↔ recenzent: paralele.** Synteza:

> "These are the writer's READING, not claims from the record, so they do not need sources"

Pisarz: "That list is what a full-length article is made of" + "Just start the next mechanism" + budżet hedge ≤1. Efekt: zdania o bezpiecznikach i anodach przychodzą na zimno, w formie faktu. Recenzent:

> "`FACT` — it asserts something as true about the world [...] a rule, a figure, a finding" / "A FACT sentence fails if the card does not carry evidence for it."

A `recenzent.md` ani razu nie mówi, co zrobić z `parallel_mechanisms` — jedyną sekcją karty bez evidence i url. Każdy pełnowymiarowy artykuł niesie więc kilka zdań, które recenzent według litery powinien oblać, a według praktyki przepuszcza pasażem. Przeżycie przebiegu wisi na łaskawości klasyfikatora, której jego własny brief mu nie przyznał.

**P3 — skaut ↔ synteza: sceny sprzedane, niedopuszczone.** Skaut wybiera tematy ZA precedensy ("each occasion the system failed is a scene with people in it, and the clause that followed is the consequence") i żąda ich z pamięci. Wykonalność bramkuje wyłącznie dokumenty pytania ("at least two primary documents bearing on the question"), definiując primary jako "itself a record, not a commentary on somebody else's record" — a sceny mieszkają głównie w narracjach; osiągalności źródeł precedensów nie sprawdza nikt. Potem synteza:

> "If a fact is not in the excerpts below, it does not exist for the purposes of this article"

Więc to, co zrobiło z tematu artykuł, dociera do pisarza tylko wtedy, gdy fetcher przypadkiem to złowił. `{target_words}` przychodzi skalibrowane na artykuł; karta — nierzadko na notkę.

**P4 — skaut ↔ wykonalnosc: lekcja o score'ach cofnięta jeden krok dalej.** Skaut:

> "Do not include scores. [...] self-assigned scores drift to the top of their range regardless of the thing being scored."

Wykonalność, w schemacie: `"confidence": 0.0-1.0`. Chiazm: pewność zakazana tam, gdzie niosłaby informację (przy pojedynczym precedensie z pamięci — K4), nakazana tam, gdzie jest szumem (samoocena wykonalności — N3).

**P5 — pisarz ↔ forma: bramka na cechy, o które nikt nie prosił.** Forma pyta:

> "Is there a place where the article stops talking about people in general and addresses **this reader**, holding **one concrete object**?"

oraz "is that claim already widely circulated". `pisarz.md` nie zawiera ani słowa o zwrocie do czytelnika z przedmiotem ani o nieznajomości twierdzenia otwarcia. Z kroniki 32 wiem, że to celowe — nakaz pozycji stałby się podpisem — ale operacyjnie to droga jednokierunkowa: pisarz jest bezpamięciowy, bramka umie tylko zgłosić brak, a jedyny kanał, którym ta cecha może do pisarza trafić, to `{style_examples}` ("one per rhetorical function"). Czy przypięty korpus niesie fragment funkcji "zwrot do czytelnika" — z tych sześciu plików nie widać; jeśli nie niesie, ta pętla nie konwerguje, tylko zgłasza ten sam brak w kolejnych tekstach.

**Coda, spoza sześciu plików (PROGRESS.md, decyzja właściciela nr 1):** synteza i pisarz grożą — "blocks the article for any factual claim without evidence behind it" — a systemowo "Nic nie blokuje artykułu. [...] tekst zawsze trafia do szuflady". Na mnie ta fikcja działa co przebieg od nowa, bo jestem bezpamięciowy i wierzę promptowi; jako narzędzie ostrożności jest skuteczna. Ale straż, którą prompty obiecują, w systemie raportuje, nie blokuje — warto to wiedzieć, czytając własne bramki.

---

## 6. Jedno skreślenie

Z `pisarz.md` skreśliłbym jedno zdanie:

> "Open with the collision itself: the thing that is true and the thing the reader assumes, close enough together that the gap does the work."

Co zmienia się konkretnie:

1. Dystrybucja otwarć przestaje być 10/10 jednym ruchem. BROKEN_BELIEF naturalnie zostaje przy kolizji — tam założenie jest w karcie (`broken_belief`), to najsilniejsze otwarcie dla tej klasy. SYSTEM_UNDER_TEST otwiera się sceną z precedensu (jeśli dotarł do karty) albo momentem z pytania, albo mechanizmem na zimno.
2. Kanał z P1 zamyka się: znika nakaz, który przy SUT kazał mintować "everyone assumes".
3. Cecha "otwarcie" w ODCISK_FORMY odzyskuje wariancję, więc próg 5/6 odzyskuje czułość na pozostałych pięciu cechach.

Podłogę trzymają bez tego zdania: ZAKAZANE_OTWARCIE (kod) dalej wycina errandy, "Name that mechanism early and plainly" dalej nie pozwala na tease, OTWARCIE_ZNANE dalej zgłasza znajome twierdzenia. Koszt, uczciwie: kolizja jest sprawdzonym, najmocniejszym otwarciem dla tekstów o przekonaniu i część otwarć po skreśleniu będzie słabsza. Ale dla połowy pisma obecny nakaz produkuje dokładnie tę słabość w przebraniu — kolizję z dorobioną połówką.

---

## 7. Co by mnie obaliło

Najmocniejsze twierdzenie audytu: nakaz kolizji jest jednocześnie najtrwalszą sygnaturą (pkt 4), kanałem fabrykacji przy SUT (P1) i stąd jedynym skreśleniem (pkt 6). Trzy znaleziska, które by to złamały:

1. **W korpusie stylu:** jeśli `{style_examples}` ma funkcję "otwarcie" z rotującymi fragmentami różnych ruchów (sprawdzić `agent-v2/style.py` i `agent-v2/prompts/styl/`), to otwarcia są sterowane korpusem, a ja przeczytałem jedną linijkę jako wiążącą, gdy działa jak jedna opcja z wielu.
2. **W tekstach:** pierwsze akapity ostatnich ~8 przebiegów (37–45 w PROGRESS.md). Jeśli mniej niż ~2/3 to dwutakt "fakt vs założenie", nakaz nie wiąże produkcyjnego pisarza tak, jak twierdzę. Osobno dla SUT: jeśli te teksty otwierają się bez dorobionego beatu "everyone assumes / most people think", kanał z P1 jest teoretyczny.
3. **W logach ODCISK_FORMY:** jeśli cecha "otwarcie" realnie zmienia się między ostatnimi tekstami, pada argument o wiecznie zgodnej cesze siedzącej pod progiem 5/6.

---

*Promptów nie zmieniałem. Kronika `opis-budowy-substack/` jest w `archiwum/` (tylko do czytania po porządkach 23.08), więc zapis audytu leży tu, w `docs/`, wzorem datowanych rekordów.*
