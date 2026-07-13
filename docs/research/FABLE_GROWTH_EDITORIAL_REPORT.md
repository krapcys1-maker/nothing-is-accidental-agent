# Fable Growth & Editorial Operating System

> **Status: EXTERNAL STRATEGIC RESEARCH — NOT IMPLEMENTED**

- **source:** Fable read-only strategic research
- **date:** 2026-07-13
- **scope:** Growth, editorial system, model routing, writing instruction audit
- **implementation status:** NOT IMPLEMENTED
- **factual verification status:** MIXED — official, creator-reported, anecdotal and inferred claims remain separately labeled.

> **COST ESTIMATES — UNVALIDATED**
>
> Ceny opierają się na konfiguracji projektu. Projekt ma obecnie wspólny cennik dla FAST i QUALITY; wartości wymagają walidacji na realnym `model_usage` i nie są gwarantowanym kosztem produkcyjnym. Nie przeliczano ich w ramach tej integracji.

Uwaga wstępna o zakresie: zlecenie mówi „publikację o AI", ale wg ADR-018 i konfiguracji konta publikacja agenta to anonimowa marka o ukrytych systemach codzienności (EN), z zakazem pisania o AI. Projektuję system dla NIA; benchmark celowo obejmuje publikacje AI/tech, bo to najbliższy ekosystem eseistyki analitycznej i tam jest najwięcej danych o wzroście. Całość przenosi się 1:1 na ewentualny drugi kanał (Chaos Engine), z podmianą niszy.

Oznaczenia dowodów w całym raporcie: **[OF]** dane oficjalne Substacka/pracowników · **[TW]** dane liczbowe od nazwanych twórców · **[AN]** anegdota/niezweryfikowane · **[WN]** mój wniosek.

## 1. Executive summary

Wzrost wczesnego Substacka w 2025/26 dzieje się wewnątrz sieci, nie z zewnątrz: Substack raportował ~32 mln nowych subskrypcji z samej aplikacji w kwartał [OF], a twórcy niszowych publikacji przypisują Notes 60–90% nowych subskrybentów na starcie [TW/AN]. SEO i social zewnętrzny to dodatek, nie silnik.

Algorytm Notes premiuje działania, które dzieją się NA platformie: restack z komentarzem, odpowiedzi, udostępnienia — wprost od szefa ML Substacka [OF]; personalizacja działa po nakładaniu się publiczności, więc komentowanie właściwych publikacji jest targetowaniem, nie grzecznością [OF/WN].

Follows ≠ wzrost. Follower widzi treści tylko w feedzie; przykład 10 000 followers → 200 osiągalnych czytelników [AN]. System musi mierzyć i konwertować follows→subs, nigdy nie raportować follows jako sukcesu.

Najlepsze ROI rekomendacji dają średnie publikacje rosnące w podobnym tempie („growth cohort"), nie wieloryby — Jenny Ouyang: rekomendacja od dużego dała 3 subskrybentów [TW]. To definiuje, kogo agent ma czytać, komentować i rekomendować.

Rytm minimum: 1 artykuł/tydzień („post weekly or become invisible" [TW]) + codzienna obecność w Notes. Nasza konfiguracja (2 art./tydz. max, 2 Notes/dzień, 5 komentarzy/dzień) jest wystarczająca i bezpieczna — problemem nie są limity, tylko jakość wykonania.

Budżet nie jest wąskim gardłem: przy cenach z `.env` pełny tygodniowy cykl (artykuł+research+audyty+Notes+komentarze) kosztuje ~0,35–0,45 USD, czyli <5% budżetu miesięcznego. Stać nas na wariant quality-first zawsze; oszczędzanie na researchu jest nieracjonalne.

Największe ryzyko wzrostowe to nie spam-detekcja, tylko generyczność: rynek „meta-poradników" pokazuje stalle na 500–1000 subach przy przeciętnej treści [AN]; przewaga NIA = research z dowodami (Research Card) + wizualny konkret, których typowy twórca nie robi.

Instrukcja pisania jest mocna w dyscyplinie faktów (9/10) i artykułach (9/10), słaba dla Notes (5/10) i komentarzy (6/10) — wymaga architektury modularnej (sekcja 8), nie kolejnych zakazów.

## 2. Najważniejsze różnice: konta rosnące vs stojące

| Rosnące | Stojące (dobra jakość, brak wzrostu) |
|---|---|
| Obecność w Notes codziennie, w tym treści samodzielne (nie tylko promo) [TW/OF] | Publikują artykuł i znikają na tydzień („park blog posts") [AN] |
| Jedna czytelna obietnica w bio/tagline; czytelnik wie po 5 s, co dostanie [WN z benchmarku] | Positioning „o wszystkim, co mnie ciekawi" |
| Wymiana rekomendacji z kohortą podobnej wielkości [TW] | Zero recommendations albo tylko prośby do wielorybów [TW] |
| Komentują tam, gdzie nakłada się publiczność; komentarz = próbka stylu [OF/WN] | Komentarze grzecznościowe lub żadne |
| Konkret: liczby, testy, artefakty do zabrania (pliki, checklisty) [WN] | Poprawna proza bez „rzeczy do zabrania" |
| CTA rozdzielone: follow w Notes, subscribe w artykule, jeden CTA na tekst [TW/AN] | Brak CTA albo trzy naraz |
| Wcześnie akceptują, że 0→100 to najwolniejsza faza i nie zmieniają strategii co tydzień [TW] | Panika i pivoty co 2 tygodnie |

## 3. Strategia 0 → 100 → 500 → 1000+

Zasada nadrzędna (spójna z `learning_policy`): jedna zmiana strategiczna na ≥7 dni; nigdy nie optymalizujemy pod same views.

| Etap | Cel główny | Artykuły/tydz. | Notes/dzień | Komentarze/dzień | Rekomendacje/współprace | Content/Engagement/Collab | CTA | Metryki sukcesu | Sygnały, że nie działa |
|---|---|---|---|---|---|---|---|---|---|
| 0–100 | dowód obietnicy + pierwsze pętle w sieci | 1 (stały dzień) | 1–2 (≥1 samodzielna, nie-promo) | 3–5 wartościowych | 3–5 rekomendacji dawanych (bez oczekiwań); 0 próśb | 40/55/5 | w Notes: follow/przeczytaj; w artykule: subscribe (1×) | ≥10% odwiedzin profilu→sub; restacki>0 na ≥połowie Notes; open rate>50% | po 4 tyg. <30 subów mimo pełnego rytmu; komentarze bez odpowiedzi autorów; zero restacków |
| 100–500 | powtarzalność + kohorta | 1 (opcjonalnie +1 krótki co 2 tyg.) | 2 | 5 | zbuduj kohortę 5–10 pubów 100–2000 subów; 2–4 wymiany rekomendacji; 1 współpraca/mies. (guest/cross-post) | 40/40/20 | jw. + „recommend us" do czytelników po dobrym tekście (rzadko) | rekomendacje = 15–30% nowych subów [OF-mechanizm/TW-skala]; unsubscribe<2%/mies. | wzrost tylko w dni publikacji Notes o Substacku samym w sobie; suby bez otwarć |
| 500–1000 | konwersja sieci + serie | 1–2 | 2 | 3–5 (bardziej selektywnie, wyżej) | aktywna siatka 10+; 1 kolaboracja/mies.; pierwsze bycie rekomendowanym przez większych | 50/30/20 | seria/tag jako obietnica („co środę: X"); follow→sub kampania w Notes | konwersja follow→sub rośnie; ≥40% nowych z recommendations+Notes łącznie | plateau restacków; wzrost tylko followers |
| 1000+ | retencja + selektywna skala | 2 | 2 | 3 | kuratorowane rekomendacje (jakość>liczba); rozważ płatne dopiero przy stabilnym open rate | 55/25/20 | subscribe domyślne; rozważane paid-CTA po danych | returning readers (waga 0,20 w naszej funkcji celu) rośnie; koszt/sub spada | churn>3%/mies.; open rate<35% |

Nie rekomenduję sub-for-sub na żadnym etapie (patrz sekcja 11) — poza brakiem dowodów na wartość, psuje metrykę nadrzędną projektu (`engaged_subscribers`, waga 0,45).

## 4. Growth flywheel

`topic → research → Research Card → article → 5–10 Notes → discussion → profile visit → follow → subscription → retention → next topic`

W raporcie pętla ma pełniejszy przebieg: `topic → research (karta z dowodami) → artykuł → 5–10 Notes (rozłożone na 7–10 dni) → dyskusja (odpowiedzi <24h) → wizyta na profilu → follow → subscribe → retencja (seria, przewidywalny rytm) → dane → następny topic`.

Jeden artykuł → 5–10 różnych Notes (z jednej Research Card; każda nota = inny atom karty, nigdy parafraza poprzedniej — dokładnie tak, jak istniejący pakiet `SUBSTACK_NOTES_AI_WRITING.md`, który jest dobrym wzorcem):

- Liczba-hak (`citable_number` z kontekstem, bez linku) — dzień publikacji.
- Mechanizm w 4 zdaniach (`main_mechanism` skrócony) + link — dzień 1.
- Najmocniejszy kontrargument z karty, potraktowany serio — dzień 2 (bez linku; link w odpowiedzi, jeśli ktoś dopyta).
- Porażka/zaskoczenie z researchu („źródło, które wyglądało świetnie, odpadło bo…") — dzień 3.
- Pytanie z `uncertain_claims` (prawdziwe, nie retoryczne) — dzień 4–5.
- Wizual (`visual_idea` jako grafika/diagram) + jedno zdanie — dzień 5–7.
- Behind-the-scenes metodyczne (jak sprawdziliśmy X) — tydzień 2.
- Restack własnego artykułu z NOWYM wnioskiem; odpowiedź-notatka na cudzą notę w temacie; „co przegapiliśmy" po dyskusji.

Bez linku promują: liczba-hak, kontrargument, pytanie i restack z wnioskiem — budują profil, a algorytm premiuje treść natywną [OF]; link zawsze najwyżej w co drugiej nocie. **PROPOSED:** ≤40% Notes z linkiem.

Komentarze jako positioning: target = publikacje z nakładającą się publicznością (miasta, logistyka, ekonomia codzienności, design) [OF-mechanizm]; komentarz zawsze dodaje fakt/liczbę/mechanizm w stylu NIA — czytelnik ma z komentarza poznać, czym jest publikacja, zanim kliknie profil. Scoring targetu już istnieje w configu (`min_target_score 70`).

Wybór publikacji do czytania/rekomendowania: (a) overlap tematyczny z niszą, (b) rozmiar 100–5000 (kohorta [TW]), (c) autor odpowiada na komentarze (sygnał żywej społeczności), (d) jakość — rekomendujemy tylko to, co przeszłoby nasz własny scoring ≥70. Rekomendacje dajemy wcześniej, niż prosimy o cokolwiek.

Anty-spam by design: nierówny rytm dobowy (okna z configu, jitter), zero powtarzalnych szablonów (diversity memory, sekcja 8), limity twarde z `growth_policy`, `semantic_duplicate_threshold 0.80` dla komentarzy, cooldown po ukrytym komentarzu (max 1), NIGDY dwa komentarze pod tym samym autorem dziennie.

## 5. Biblioteka formatów

### A1–A9: artykuły

Artykuły (9 konstrukcji; `format_module` wybiera 1, diversity memory zakazuje powtórki 2× z rzędu).

| ID | Konstrukcja | Kiedy | Szkielet |
|---|---|---|---|
| A1 | Mechanizm wyjaśniający | rdzeń NIA | zjawisko znane → mechanizm ukryty → dowody → konsekwencja dla czytelnika |
| A2 | Teza vs popularne przekonanie | gdy karta obala intuicję | przekonanie → test → co mówią dane → gdzie intuicja ma rację → granica |
| A3 | Analiza kosztu/ceny | „skąd się bierze cena X" | dekompozycja liczby → największy zaskakujący składnik → kto na tym zarabia |
| A4 | Dwa przeciwstawne przypadki | dwa miasta/firmy/systemy | case A vs case B → różnica → zasada |
| A5 | Autopsja porażki systemu | awarie, blackouty, recalle | zdarzenie → łańcuch przyczyn → bezpiecznik, którego zabrakło |
| A6 | Benchmark/ranking z metodą | porównywalne obiekty | kryteria jawne → wyniki → outlier → dlaczego |
| A7 | Build log / eksperyment własny | tylko z faktycznie wykonanych działań systemu | plan → przebieg → liczby → wniosek (zero zmyślonych doświadczeń) |
| A8 | Prognoza warunkowa | zmiany regulacji/technologii | jeśli X to Y, bo mechanizm Z; jawne warunki falsyfikacji |
| A9 | Historia jednego obiektu | wózek, kod kreskowy, paleta | obiekt → decyzje projektowe → interesy za nimi |

A7 dla NIA może korzystać wyłącznie z prawdziwych, zatwierdzonych eksperymentów związanych z tematyką publikacji. Nie może ujawniać, że publikację prowadzi agent, ani tworzyć zmyślonych doświadczeń.

### N1–N16: Notes

Notes (16 formatów — cel/długość/ton/kiedy/ryzyko/struktura; bez gotowych tekstów).

| ID | Format | Cel | Dł. (słów) | Ton | Kiedy | Ryzyko powtarzalności | Struktura |
|---|---|---|---|---|---|---|---|
| N1 | Liczba z kontekstem | stop-scroll | 30–80 | suchy | dzień publikacji | wysokie → max 2/tydz. | liczba → co znaczy → 1 zdanie mechanizmu |
| N2 | Mini-mechanizm | próbka wartości | 80–150 | wyjaśniający | D+1 | średnie | „X działa tak: … Dlatego Y" |
| N3 | Kontrargument serio | wiarygodność | 80–150 | wyważony | D+2 | niskie | „Najlepszy zarzut wobec [tezy]: … I ma rację, gdy…" |
| N4 | Kulisa researchu | zaufanie | 60–120 | osobisty-redakcyjny | D+3 | średnie | co odrzuciliśmy i czemu |
| N5 | Prawdziwe pytanie | dyskusja | 30–70 | ciekawy | gdy `uncertain_claim` realny | wysokie (pytania-wydmuszki) | kontekst 1 zd. → pytanie konkretne |
| N6 | Wizual + zdanie | zasięg | 10–30 + grafika | minimalny | gdy `visual_idea` mocny | niskie | grafika niesie treść |
| N7 | Obserwacja z natury niszy | samodzielna wartość | 60–120 | eseistyczny | dni bez promo | średnie | scena → mechanizm → puenta |
| N8 | Restack-z-wnioskiem | sieć | 30–80 | dialogowy | 2–4/tydz. | niskie | cudza nota → NASZ dodatek |
| N9 | „Zmieniłem zdanie" | autentyczność | 60–120 | szczery | rzadko, gdy prawda | niskie | stare przekonanie → dowód → nowe |
| N10 | Mini-lista mechanizmów | zapisywalność | 80–150 | użytkowy | max 1/tydz. | wysokie | 3 pozycje, każda z „bo" |
| N11 | Definicja-odczarowanie | positioning | 40–90 | precyzyjny | terminologia niszy | średnie | „X nie znaczy… znaczy…" |
| N12 | Follow→sub konwersja | konwersja | 40–80 | bezpośredni, bez błagania | 1–2/mies. [AN-skuteczne] | wysokie | co dostaje subskrybent, czego follower nie |
| N13 | Zapowiedź z konkretem | oczekiwanie | 30–60 | rzeczowy | D-1 | średnie | jedna liczba/pytanie z nadchodzącego tekstu |
| N14 | Errata/aktualizacja | zaufanie | 40–100 | protokolarny | gdy fakt się zmienił | niskie | co pisaliśmy → co wiemy dziś |
| N15 | Głos czytelnika + odpowiedź | społeczność | 60–120 | doceniający | po dobrej dyskusji | średnie | cytat komentarza (za zgodą platform. normy) → rozwinięcie |
| N16 | Kontr-nota do newsa | timing | 60–120 | analityczny | news w niszy | średnie | wszyscy mówią A → mechanizm mówi B |

### K1–K8: komentarze

Każdy komentarz musi przejść test „czy dodaje coś, czego nie ma w poście".

| ID | Typ |
|---|---|
| K1 | Fakt uzupełniający ze źródłem przywoływalnym. |
| K2 | Przykład praktyczny z innej branży/kraju. |
| K3 | Uprzejmy kontrargument z mechanizmem, nie opinią. |
| K4 | Pytanie wynikające z tekstu (konkretny paragraf, nie „a co sądzisz o…"). |
| K5 | Analogia systemowa (nasz rdzeń: „to ta sama klasa problemu co X"). |
| K6 | Wynik własnego testu — WYŁĄCZNIE jeśli system faktycznie go wykonał i jest w bazie. |
| K7 | Liczba korygująca skalę („to 3%, nie 30% — źródło"). |
| K8 | Domknięcie wątku z komentarzy (odpowiedź na pytanie, które zostało bez odpowiedzi, jeśli znamy odpowiedź). |

Zakazane: pochwały generyczne (`allow_generic_praise: false` już w configu), streszczenia posta, linki poza `link_ratio`.

## 6. Model routing

Dostępne w projekcie: `claude-haiku-4-5` = FAST, `claude-sonnet-5` = QUALITY; brak trzeciego modelu w konfiguracji.

Ceny z `.env`: input 1,00 / output 5,00 USD/MTok; web search 10 USD/1k. Uwaga (BRAK DANYCH): projekt ma JEDEN cennik dla obu modeli — ledger wycenia haiku i sonneta identycznie; oficjalnych cen per model nie zakładam. Rekomendacja roadmapowa: per-model `PRICE_*` w `.env`. Koszty niżej = cennik projektu + realne obserwacje z `model_usage` (run `c01171bc`).

| Zadanie | Główny | Tańszy | Eskalacja gdy | Max koszt/wywołanie | Context | Drugi model sprawdza? | Deterministycznie zamiast LLM? |
|---|---|---|---|---|---|---|---|
| Topic discovery | FAST | — | 2× z rzędu <2 tematy ≥75 pkt → QUALITY | 0,01 | nisza+historia tytułów | nie | — |
| Dedup + scoring agregacja | kod (jest) | — | — | 0 | — | — | TAK (jest) |
| Source discovery (A1) | QUALITY | FAST w economical | — | 0,05 (obs. 0,029) | plan | nie | nie (search) |
| Extraction (A2) | QUALITY | — | nigdy w dół (to fundament dowodów) | 0,06/źródło (obs. 0,021–0,049) | kandydat | walidacja deterministyczna (UNVERIFIED-wymuszenie jest) | częściowo (parsowanie/progi) |
| Research Card (B) | QUALITY | — | truncation → resume z wyższym `max_tokens` (jest) | 0,03 (obs. 0,014) | karty A2 (~2k tok) | bramka deterministyczna jest; w quality-first: FAST sanity-check mapowań | mapowanie claim↔źródło TAK (po naprawie kontraktu) |
| Outline | FAST | — | temat złożony (≥5 claims) → QUALITY | 0,01 | karta | nie | szkielet z `format_module` TAK |
| Article draft | QUALITY | — | — | 0,04 (≈3k in/2,5k out) | karta+brief+moduły stylu | audyty niżej | nie |
| Fact audit | kod + QUALITY | FAST | rozbieżność wykryta → QUALITY | 0,015 | draft+karta | to JEST drugi model | mapowanie twierdzeń→claims TAK |
| Style audit | kod + FAST | kod sam | — | 0,005 | draft+diversity memory | nie | metryki rytmu/fraz TAK |
| Growth audit | FAST | — | przed publikacją artykułu-eksperymentu → QUALITY | 0,005 | draft+dane eksperymentów | nie | checklisty CTA/tytułu częściowo |
| Rewrite | QUALITY | — | — | 0,03 | draft+findings | ponowny fact audit (kod) | — |
| Notes | FAST | — | nota typu N3/N9/N16 → QUALITY | 0,005 | karta/artykuł+format | style audit (kod) | harmonogram TAK |
| Komentarze | FAST | — | target score >85 albo kontrargument → QUALITY | 0,005 | post+profil targetu | duplicate-check (kod, jest próg 0.80) | scoring targetu TAK (config) |
| Odpowiedzi czytelnikom | FAST | — | krytyka merytoryczna → QUALITY; krytyka agresywna → człowiek | 0,005 | wątek | klasyfikator NO_REPLY (kod) | klasyfikacja identity-question TAK |
| Tygodniowa analiza strategii | QUALITY | — | — | 0,05 | metryki+eksperymenty | człowiek (LEVEL<3) | agregacje metryk TAK |

### Economical / Balanced / Quality-first

Trzy warianty i koszty (artykuł = research 4 źródła + outline + draft + 3 audyty + 1 rewrite + pakiet 6 Notes; ceny projektu).

| | Economical | Balanced | Quality-first |
|---|---|---|---|
| Różnice | A1 na FAST, 3 źródła, audyty tylko kod+FAST, max 1 rewrite | jak w tabeli | 5 źródeł, cross-check B (FAST), 2 rewrity, Notes N3/N9 na QUALITY |
| Artykuł + Notes | ~0,17 USD | ~0,25 USD | ~0,45 USD |
| 1 Note solo | 0,003 | 0,003–0,005 | 0,005–0,01 |
| Tydzień (1 art., 10 Notes, 25 kom., 10 odp., analiza) | ~0,27 | ~0,38 | ~0,60 |
| Miesiąc (4,3 tyg.) | ~1,2 USD | ~1,6 USD | ~2,6 USD (przy 2 art./tydz.: ~4,6) |

Wniosek: nawet quality-first przy maksymalnej dozwolonej kadencji zużywa <12% budżetu 40 USD. Rekomendacja: domyślnie quality-first dla researchu i draftu, economical dla wolumenu (Notes/komentarze) — oszczędzanie na dowodach to jedyna rzecz, na którą nas nie stać.

## 7. Audyt instrukcji pisania

Audyt dotyczy `instrukcja dla pisania artykulow/CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md`; kopia „(9)" jest binarnie identyczna z repo. Ten raport opisuje przyszłe zmiany — nie zmienia instrukcji.

| Wymiar | 0–10 | Komentarz |
|---|---:|---|
| Naturalność | 8 | świetna diagnoza wad AI-stylu, oparta na badaniach z aneksem |
| Wyrazistość głosu | 6 | profil „Chaos Engine" pomaga, ale rdzeń jest defensywny — mówi czego NIE robić częściej niż kim być |
| Różnorodność | 7 | sekcja „Różnorodność w serii" dobra, lecz deklaratywna — bez pamięci ostatnich tekstów nie zadziała |
| Humor | 5 | dozwolony i limitowany, zero wskazówek, JAK brzmi dobry suchy żart tej publikacji |
| Factual discipline | 9 | wzorowa (4 poziomy pewności, zakaz zmyśleń, rejestr pochodzenia) |
| Ochrona przed generycznością | 7 | mocna na poziomie zdania; słabsza na poziomie kompozycji serii |
| Ryzyko nadmiernego ograniczenia | 6 (istotne) | limity liczbowe czytane jako targety; „poprawnie i ostrożnie" to realny tryb awarii |
| Przydatność: artykuły | 9 | to jest jej żywioł |
| Przydatność: Notes | 5 | jeden akapit; brak pierwszej-linii-hooka, formatów, rytmu feedu |
| Przydatność: komentarze | 6 | zasady są, brak typologii i realiów platformy |

Redundancje: sekcje 1–12 i blok 13 to DWIE pełne kopie tych samych reguł (plus profil CE) — przy edycji rozjadą się na pewno; listy zakazanych fraz powtórzone; „Procedura redakcji" ⊃ „Lista kontrolna".

Sprzeczności (drobne): „powtórzenie terminu lepsze niż synonim" vs anty-monotonia (rozstrzygalne per format); polskie ograniczenie jednozdaniowych akapitów stosowane do EN Notes byłoby błędem.

Zbyt sztywne: liczbowe sufity stylistyczne w rdzeniu (należą do formatu); „mało nagłówków" kolidowałoby z formatem benchmark (A6). „Dobrze, ale zawsze podobnie": przewidywalna sekwencja steelman→granica; krótka puenta po długim wywodzie jako tik; brak wymuszonego wyboru typu otwarcia.

Do modułów formatu: długości, nagłówki/listy, CTA, limity metafor, całe zasady Notes/komentarzy. Do mierzalnego style auditu (kod): współczynnik zmienności długości zdań/akapitów, powtórzone otwarcia zdań, frazy zakazane (EN+PL), gęstość liczb, podwójne zakończenia, nakładanie shingle'ów z ostatnimi N tekstami, zgodność z diversity memory. Zgodnie z poleceniem: żadnych nowych zakazów — przenosiny i pomiar zamiast rozbudowy.

## 8. Modularna architektura stylu

- **Core factual constitution** (stała, ~1 strona): 5 zasad nadrzędnych, 4 poziomy pewności, rejestr pochodzenia, zakaz zmyśleń, zasady źródeł, ADR-018 (NO_REPLY, zero osobowych fikcji). Nic o długościach i rytmie.
- **Voice profile NIA** (stały, osobny od CE): anonimowa redakcja EN; ciekawość systemowa, precyzja, suchy humor z sytuacji (nigdy z ludzi), zero „my sądzimy, że świat…" — zamiast tego „the data says / the mechanism is"; stosunek do czytelnika: inteligentny laik, którego nie wolno nudzić ani pouczać.
- **Format module** (wybierany per tekst): A1–A9 / N1–N16 / typ komentarza — z limitami długości, nagłówków, CTA, hooka pierwszej linii (Notes), poziomu humoru.
- **Article-specific brief** (generowany): teza, 3 najmocniejsze dowody z karty, kontrargument, zakazane w TYM tekście (z diversity memory), target otwarcia i zakończenia, CTA.
- **Series diversity memory** (tabela, ostatnie 10 publikacji per typ): `opening_type` · `argument_architecture` · `tone` · `humor_level(0–3)` · `example_domain` · `heading_count` · `ending_type` · `anchor_metaphors[]` · `format_id`.
- **Final style audit:** warstwa kodowa (metryki z sekcji 7) → warstwa FAST-model (czy brzmi jak voice profile; 3 konkretne zarzuty albo pass) → wynik do evaluations.

**PROPOSED — deterministyczne ograniczenia powtarzalności:** nowy tekst nie może powtórzyć `opening_type` ani `argument_architecture` z ostatnich 2, `anchor_metaphor` z ostatnich 10, `format_id` z ostatnich 2 (artykuły) / 3 dni (Notes tego samego typu).

## 9. Inspiracje stylistyczne i repertuar NIA

Próbki analityczne (stan wg mojej wiedzy; do okresowej weryfikacji):

- **One Useful Thing** — humor jako wentyl po twardym dowodzie; otwarcie od eksperymentu; czytelnik = współbadacz.
- **Construction Physics** — reportażowy konkret liczbowy, zero humoru, argument przez dekompozycję; zakończenie = konsekwencja ekonomiczna.
- **Experimental History** — autoironia jako narzędzie epistemiczne; rytm długie→krótkie; czytelnik = wspólnik żartu.
- **AI Snake Oil** — krytyka metodologii jako architektura tekstu; dane cytowane z ograniczeniami.
- **Money-Stuff-owy typ głosu** (funkcja, nie autor) — dygresja w nawiasie jako nagroda za uwagę.
- **Import AI** — telegraficzny rytm sekcji, otwarcie od faktu, zakończenie od implikacji.
- **The Pragmatic Engineer** — struktura jawna, dane od praktyków, zero ozdobników.
- **Garbage Day** — energia i timing kulturowy (funkcja: nota N16), NIE do kopiowania w artykułach NIA.

Zasada: przejmujemy funkcje; nie kopiujemy fraz, osobistych historii ani charakterystycznych metafor; nie tworzymy „pisz jak autor X”.

Repertuar NIA (oryginalny miks): poważna analiza mechanizmów (A1/A3) jako rdzeń · suchy humor sytuacyjny 0–2 razy na tekst, zawsze po konkretach · autoironia TYLKO redakcyjna („nasz research odrzucił połowę źródeł") — nigdy fikcyjno-osobista (ADR-018) · eksperyment/build-log z prawdziwych danych systemu · krytyka zawsze mechanizmu, nie osób · reportażowy konkret: każda sekcja ma liczbę albo scenę · Notes krótkie, pierwsza linia = samodzielny hak.

## 10. Metryki i eksperymenty

Dashboard (per content item + agregaty tygodniowe): `impressions` (Notes) → `profile visits` → `follows` → `free subscribers` → `paid subscribers` (później) · `open rate` · `click rate` · `restacks` · `comments` · `recommendations given/received` · `unsubscribes` · `conversion per item` (subs przypisane w 48h od publikacji itemu, oznaczone `is_estimated` — Substack nie daje twardej atrybucji) · `follows→subs ratio` (tygodniowo). Rozdzielenie followers/subscribers w raportach jest obowiązkowe [OF-definicje].

10 pierwszych eksperymentów (sekwencyjne; jedna zmienna — zgodnie z `one_primary_variable_per_experiment`):

| ID | Hipoteza | Zmienna | Metryka | Czas min. | Kryterium decyzji | Ryzyko małej próby |
|---|---|---|---|---|---|---|
| E1 | Otwarcie liczbą > otwarcie sceną w Notes | typ otwarcia N1 vs N7 | impressions→profile visits | 2 tyg. (≥10 not/wariant) | +30% CTR profilu | wysokie — feed niestacjonarny; powtórzyć raz |
| E2 | Nota bez linku buduje więcej follow niż z linkiem | link on/off | follows/nota | 2 tyg. | różnica ≥2× | mieszany cel (sub vs follow) |
| E3 | Artykuł 1100 słów vs 1600 | długość | open rate + read-through proxy (restacki/komentarze) | 4 art. (4 tyg.) | spójny kierunek 3/4 | bardzo małe n — traktować jako sygnał |
| E4 | N3 (kontrargument) > N2 (mechanizm) dla dyskusji | typ noty | komentarze/nota | 2 tyg. | ≥2× komentarzy | temat może dominować nad formatem |
| E5 | CTA „recommend us" po najlepszym tekście działa | obecność CTA | recommendations received | 1 mies. | ≥2 nowe rekomendacje | atrybucja miękka |
| E6 | Suchy żart w nocie nie obniża konwersji | humor 0 vs 1 | profile visits→subs | 2 tyg. | brak spadku >20% | subiektywność „żartu" |
| E7 | Publikacja artykułu śr. rano vs czw. wieczorem (UTC-okna z configu) | dzień/pora | open rate 48h | 6 tyg. (3v3) | różnica >5 p.p. stabilna | sezonowość |
| E8 | Tematy „infrastruktura fizyczna" > „ekonomia cen" | klaster tematu | conversion per item | 6 art. | spójny kierunek | confound jakości pojedynczego tekstu |
| E9 | Ton bardziej redakcyjno-osobisty (my testowaliśmy) > czysto analityczny | rama narracji | restacki+komentarze | 4 art. | kierunek 3/4 | głos może dryfować — style audit pilnuje |
| E10 | Build-log (A7) > szeroka analiza (A1) dla NOWYCH subów | format | subs 48h/item | 4 art. | ≥1,5× | build-log zależy od atrakcyjności samego projektu |

`n < 30 = SIGNAL, NOT PROOF`. Wszystkie wyniki z n<30 oznaczane w raporcie tygodniowym jako „signal, not proof" (wprost w szablonie analizy).

## 11. Granice autonomii

| Działanie | Auto-safe (od L2) | Approval (L1 zawsze; L2 wg progu) | Zakazane zawsze |
|---|---|---|---|
| Komentarze | draft + scoring targetu; publikacja gdy score≥85 i typ 1/2/4/5/7 | publikacja typu 3 (kontrargument) i 8; każdy target 70–85 | generyczne pochwały; 2. komentarz u autora/dzień; DM (`allow_private_messages: false`) |
| Odpowiedzi | podziękowanie-z-treścią, doprecyzowanie faktu | odpowiedź na krytykę merytoryczną | odpowiedź na atak osobisty (eskalacja do człowieka); JAKAKOLWIEK odpowiedź na pytanie o tożsamość (NO_REPLY, ADR-018) |
| Subskrypcje/follow | follow po 2 wartościowych interakcjach z pubem | subskrypcja e-mailowa pubu | masowe follow; follow-back automatyczny |
| Rekomendacje | shortlist z uzasadnieniem | KAŻDA publikowana rekomendacja (to publiczny endorsement marki) | wzajemność warunkowa („polecę, jeśli polecisz") |
| Linki | w artykułach: źródła zawsze | linki w Notes > limit 40%; jakikolwiek link afiliacyjny (nie przewidujemy) | linki w komentarzach ponad `link_ratio 0.10` |
| Cross-promotion | — | guest posty, cross-posty, wspólne Notes | udział w pods/loops engagementowych |
| Reakcja na krytykę | errata faktograficzna (N14) po weryfikacji | polemika | kasowanie krytycznych komentarzy (poza spamem wg reguł platformy) |
| Tematy kontrowersyjne | — | tematy z polityką regulacyjną w tle (cła, strajki) — tylko mechanizm, nigdy stanowisko partyjne | polityka wyborcza, religia, trwające tragedie, AI-tożsamość konta |
| Sub-for-sub | — | — | całkowicie zakazane — psuje `engaged_subscribers` (nasza metryka nadrzędna), a follows bez czytania są bezwartościowe [AN+WN] |

## 12. Konkretne zmiany do roadmapy

Propozycje — raport źródłowy nie modyfikuje plików:

- Etap 3 (Content): dodać moduły stylu (sekcja 8) jako artefakty config/prompts/ + tabelę `series_diversity_memory`; `format_module` w `content_items`; styl-audit kodowy jako część evaluations.
- Etap 3: biblioteka formatów A1–A9/N1–N16 jako dane (YAML), nie kod — wybór formatu deterministyczny + LLM tylko do treści.
- Etap 6 (Interakcje): doprecyzować limity Notes: split `daily_note_limit` na promo/self-standing (1+1); limit not-z-linkiem ≤40%; follow-policy (2 interakcje → follow).
- Etap 7 (Analytics): metryki z sekcji 10 do `metrics_daily` + conversion per item (`is_estimated`); framework eksperymentów (tabela `experiments`: hipoteza/zmienna/metryka/czas/decyzja) — szablon już istnieje w `docs/experiments/_TEMPLATE.md`.
- `.env`/UsageTracker: per-model `PRICE_*` (dziś jeden cennik dla FAST i QUALITY — ledger nie odróżnia; sekcja 6).
- `growth_policy`: dodać `notes_policy` (dziś brak — są tylko komentarze i tematy) i `recommendation_policy` (kohorta 100–5000, wymagany scoring ≥70).
- Etap 2 (research): priorytet fetch/evidence_excerpt potwierdzony — komentarze typu K1/K7 wymagają cytowalnych faktów.

## 13. Priorytety MUST / SHOULD / MAY

- **MUST (przed pierwszą publikacją):** naprawa kontraktu quality gate (z audytu po Etapie 0 — bez tego nie ma kart PROCEED) · moduły stylu 1–3 + diversity memory · biblioteka Notes N1–N8 · rozdzielenie followers/subscribers w metrykach · granice autonomii z sekcji 11 w Policy (na razie jako approval-checklista człowieka).
- **SHOULD (pierwsze 4–6 tygodni publikowania):** pełny dashboard + E1/E2/E4 · kohorta rekomendacji (ręczny research 10 pubów) · per-model pricing · `notes_policy` w configu · formaty A5/A7 (autopsje/build-log) jako wyróżnik.
- **MAY:** eksperymenty E6–E10 · cross-posty · płatna warstwa (nie przed stabilnym open rate) · trzeci model w routingu (opus-klasa do tygodniowej strategii).

## 14. Plan wdrożenia bez kodowania

Plan na 2 tygodnie, równolegle do prac Etapu 1:

- **T1:** właściciel zatwierdza blueprint → decyzje: kadencja startowa (1 art./tydz.), wariant kosztowy (quality-first research), lista 10 pubów kohorty (ręcznie, 60 min).
- **T2–3:** przepisanie instrukcji na moduły 1–3 (czysta redakcja tekstu, zero kodu) + YAML formatów.
- **T4:** szablon briefu i diversity memory jako plik markdown prowadzony ręcznie do czasu Etapu 3.
- **T5:** szablon tygodniowego raportu metryk (ręczny odczyt z dashboardu Substacka do `METRICS_LOG.md` — szablon już istnieje).
- **T6–7:** sucha próba: 1 karta researchu → draft → 6 Notes w `dry_run` → review właściciela względem voice profile.

Kryterium wyjścia: właściciel akceptuje głos na próbce, zanim cokolwiek zobaczy platforma.

## 15. Pięć błędów, które mogłyby zahamować wzrost

1. Publikowanie artykułów bez codziennej obecności w Notes — na dzisiejszym Substacku to niewidzialność [TW/OF]; nasz system musi traktować Notes jako produkt, nie promocję.
2. Mylenie follows z wzrostem — optymalizacja pod impressions/follows da wykres w górę i zero czytelników [AN/OF-definicje]; metryka nadrzędna pozostaje `engaged_subscribers`.
3. Generyczność wolumenowa — 2 nudne noty dziennie szkodzą bardziej niż 4 dobre tygodniowo; diversity memory + prawo do NIE-publikacji (bramka jakości może odrzucić notę) są ważniejsze niż wypełnienie limitów.
4. Sieciowanie z wielorybami zamiast kohorty — miesiące zabiegów o rekomendację wartą 3 subskrybentów [TW], zamiast 10 wymian w kohorcie 100–5000.
5. Zmiana strategii co tydzień pod szum małych liczb — przy n<30 prawie każdy „wynik" to szum; `minimum_days_before_strategy_change: 7` traktować jako minimum absolutne, a wnioski oznaczać „signal, not proof".

## 16. Lista źródeł researchu

Sources (research zewnętrzny użyty w tym raporcie): Substack metrics guide (support) · What is following on Substack (support) · Substack growth features (official) · The Notes algorithm explained (cytaty Mike'a Cohena, head of ML) · How to grow Substack from zero in 2026 — Jenny Ouyang, 0→4500 · Substack Notes Strategy 2026 (60% of my growth) · Followers vs Subscribers guide · 26,000 followers vs subscribers · Substack changed everything in 2025 · How to grow your Substack audience in 2026 · Substack statistics 2025 · 2026 Notes playbook.

Raport jest blueprintem do niezależnej weryfikacji — nic nie zostało zaimplementowane, żaden plik nie został zmieniony, zero wywołań płatnych API projektu i zero akcji na Substacku.
