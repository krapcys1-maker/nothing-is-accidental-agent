# WRITING_CONTRACT

Kontrakt wejścia/wyjścia writera dla autonomicznego content pipeline'u (Etap 3). **Specyfikacja, nie kod** — żaden z tych typów nie istnieje jeszcze w repozytorium; to projekt do implementacji, spójny z `MASTER_ARCHITECTURE.md` (content pipeline) i `CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md` v2.1. Nazwy pól są sugerowane; wiążąca jest semantyka.

Reguły stylu i faktów są w podręczniku; tutaj są wyłącznie granice modułu writera: co dostaje na wejściu, co zwraca na wyjściu i w jakiej kolejności jego wynik jest weryfikowany.

---

## 1. WritingBrief (wejście writera)

Kompletny, samowystarczalny kontekst jednego zadania pisarskiego. Writer nie sięga po nic spoza briefu (poza ogólną wiedzą językową); w szczególności nie dociąga nowych faktów o świecie.

| Pole | Typ | Znaczenie / reguła |
|---|---|---|
| `publication` | enum {`chaos_engine`, `nothing_is_accidental`} | Wybiera profil głosu (C1/C2) i granice kontekstu. Dla `nothing_is_accidental` obowiązuje twarda izolacja kontekstu (patrz `prohibited_context`). |
| `format` | enum {`article`, `essay`, `note`, `comment`, `reply`, `analysis`} | Wybiera moduł D i jego limity pojedynczego tekstu. |
| `language` | enum {`pl`, `en`} | `chaos_engine`→`pl`, `nothing_is_accidental`→`en`. Steruje listami HARD_BANNED/WATCHLIST (B7 vs B8). |
| `target_length` | int (słowa) albo zakres | Nadpisuje default formatu. Dla Note = twardy sufit. |
| `research_card_id` | id | Referencja do karty. Wymagane dla `article`/`essay`/`note`; opcjonalne dla `comment` opartego na cudzym poście. |
| `publication_recommendation` | enum {`PROCEED`, `REVISE`, `REJECT`} | Bramka A-GATE. `PROCEED`→pisz; `REVISE`→`NEEDS_RESEARCH`/`SKIP`; `REJECT`→`SKIP`. Writer nie „ratuje" słabej karty. |
| `thesis_candidate` | tekst | Proponowana teza. Writer może ją zawęzić do materiału; nie wolno jej rozszerzyć ponad claimy. |
| `verified_claims` | lista `{claim_id, text, verification_status}` | Twierdzenia z karty dopuszczone do użycia. Tylko `VERIFIED` mogą stać jako fakt; reszta wyłącznie jako jawne przypuszczenie/opinia. |
| `source_urls` | mapa `claim_id → [url]` | Źródła per twierdzenie. Podstawa `claim_map` w wyniku. |
| `evidence_excerpts` | mapa `claim_id → [cytat/fragment]` | Dowód treściowy per twierdzenie. Fakt bez excerptu nie ma lineage i nie wchodzi do tekstu. |
| `allowed_first_person_facts` | lista tekstów albo `[]` | Jedyne dopuszczone fakty pierwszoosobowe (rzeczywiste materiały projektu). Puste = zero pierwszej osoby faktograficznej. Nigdy nie zawiera niczego fikcyjnego. |
| `prohibited_context` | lista tematów/tagów | Treści zakazane w tym tekście. Dla NIA domyślnie: AI, bot, agent, modele językowe, API, pipeline, prompty, testy, koszty budowy, architektura, Research Card jako mechanizm, build log, jakiekolwiek odniesienie do „Chaos Engine". |
| `series_memory` | lista ostatnich wpisów rejestru serii | Konfiguracja rotacji (moduł E): ostatnie otwarcia, architektury, zakończenia, pary funkcji, metafory-kotwice, formaty. |
| `cta` | enum/tekst albo `null` | Jedno wezwanie (subscribe/recommend/read-previous) albo brak. Format narzuca maks. jeden. |

Walidacja wejścia (fail-closed): brak `research_card_id` dla formatu wymagającego karty, `publication_recommendation ≠ PROCEED`, albo `verified_claims` bez odpowiadających `source_urls`/`evidence_excerpts` → writer nie generuje drafta, tylko zwraca `SKIP`/`NEEDS_RESEARCH` z odpowiednim reason code.

---

## 2. WritingResult (wyjście writera)

| Pole | Typ | Znaczenie |
|---|---|---|
| `status` | enum {`DRAFT`, `SKIP`, `NEEDS_RESEARCH`} | `DRAFT` = powstał tekst do audytów; `SKIP` = świadoma rezygnacja; `NEEDS_RESEARCH` = materiał niewystarczający, wróć do researchu. |
| `draft` | tekst albo `null` | Treść (tylko przy `DRAFT`). |
| `claim_map` | lista `{fragment/zdanie, claim_id, source_url, evidence_excerpt}` | Lineage każdego faktu/liczby w drafcie. Wymagane przy `DRAFT`; wejście do Fact Audit. Fakt bez wpisu = brak lineage. |
| `used_sources` | lista url | Źródła faktycznie użyte (podzbiór `source_urls`). |
| `style_metadata` | obiekt | Wpis do rejestru serii: `opening_type`, `argument_architecture`, `tone`, `humor_level`, `example_domain`, `heading_count`, `ending_type`, `anchor_metaphors[]`, `author_functions[]`, `format`. Zasila moduł E po publikacji. |
| `warnings` | lista tekstów/kodów | M.in. `DIVERSITY_OVERRIDE:<powód>` (świadome powtórzenie struktury z uzasadnieniem), `NO_SERIES_MEMORY` (rejestr niedostępny), inne sygnały do audytu. |
| `skip_reason` | reason code albo `null` | Wymagane przy `SKIP`/`NEEDS_RESEARCH` (patrz niżej). |

---

## 3. Reason codes

### SKIP (writer świadomie nie tworzy tekstu)

| Kod | Kiedy |
|---|---|
| `SKIP_CARD_REJECTED` | `publication_recommendation = REJECT`. |
| `SKIP_THESIS_UNSUPPORTED` | Żadna obronialna teza nie mieści się w `verified_claims`. |
| `SKIP_INSUFFICIENT_EVIDENCE` | Za mało twierdzeń z pełnym lineage, by tekst nie był pusty (a re-research nie rokuje). |
| `SKIP_CONTEXT_CONFLICT` | Jedyny sensowny tekst wymagałby treści z `prohibited_context` (np. NIA temat, którego nie da się opisać bez ujawnienia mechanizmu technicznego). |
| `SKIP_DUPLICATE` | Temat pokrywa się z niedawno opublikowanym (sygnał z `series_memory`/dedup). |
| `SKIP_FORMAT_MISMATCH` | Materiał nie pasuje do zamówionego formatu (np. brak liczby-haka na Note). |

### NEEDS_RESEARCH (materiał jest, ale niewystarczający — wróć do researchu, nie porzucaj tematu)

| Kod | Kiedy |
|---|---|
| `NEEDS_RESEARCH_CARD_REVISE` | `publication_recommendation = REVISE`. |
| `NEEDS_RESEARCH_MISSING_LINEAGE` | Kluczowe twierdzenia bez `source_url`/`evidence_excerpt`. |
| `NEEDS_RESEARCH_THESIS_WIDER_THAN_CLAIMS` | Sensowna teza wymaga twierdzeń, których karta nie zawiera. |
| `NEEDS_RESEARCH_WEAK_SOURCES` | Dostępne źródła nie unoszą tezy (jakość/jedno-źródłowość); potrzebne mocniejsze. |
| `NEEDS_RESEARCH_CONTRADICTION_UNRESOLVED` | Źródła sprzeczne w punkcie nośnym tezy; potrzebne rozstrzygnięcie. |

`skip_reason` zawiera kod + krótki, konkretny opis brakującego elementu (dla `NEEDS_RESEARCH` — czego dokładnie ma dostarczyć kolejny research).

---

## 4. Kolejność weryfikacji: writer → fact audit → style audit → editorial audit

Cztery rozdzielne kroki. Samoocena writera nie jest dowodem poprawności faktów — każdy audyt jest osobnym przebiegiem i może zawrócić tekst.

```
1. WRITER
   wejście: WritingBrief
   wyjście: WritingResult (DRAFT | SKIP | NEEDS_RESEARCH)
   SKIP/NEEDS_RESEARCH → koniec (bez tekstu); DRAFT → krok 2

2. FACT AUDIT (F-FACT; blokujący, oparty na claim_map — nie na wrażeniu)
   sprawdza: każdy fakt ma lineage (claim+źródło+evidence); zero treści spoza karty;
             teza nie szersza niż claimy; poziomy pewności rozróżnialne;
             pierwszoosobowe fakty tylko z allowed_first_person_facts;
             (NIA) zero prohibited_context, brak przypisanej intencji bez dowodu.
   wynik: PASS → krok 3 · FAIL → zwrot do writera lub NEEDS_RESEARCH
          (jeden brak lineage albo jeden fakt spoza materiału = FAIL)

3. STYLE AUDIT (F-STYLE)
   sprawdza: HARD_BANNED_PHRASES = 0 wystąpień (jedno = FAIL binarny);
             każde WATCHLIST_PHRASES uzasadnione jako najdokładniejsze;
             rytm (bez trójek/kleju/równych akapitów), asymetria precyzji;
             format i limity modułu D; rotacja serii (E) + ewentualny DIVERSITY_OVERRIDE.
   wynik: PASS → krok 4 · FAIL → lista poprawek do writera

4. EDITORIAL AUDIT (F-EDITORIAL)
   sprawdza: pierwszy akapit daje powód czytania; teza z kosztem;
             najciekawszy szczegół dostał najwięcej miejsca; sekcja bez dowodu usunięta;
             kontrargument ma odpowiedź; zakończenie bez streszczenia; ton zgodny z profilem;
             test „czy komuś zależało".
   wynik: PASS → draft gotowy do approval/publikacji (wg polityki autonomii projektu)
          FAIL → poprawki redakcyjne albo zwrot do writera
```

Zasada kolejności: fakty przed stylem (nie polerujemy zdania, które wypadnie), styl przed redakcją (redaktor ocenia tekst wolny od tików). Żaden audyt nie ufa deklaracji poprzedniego kroku „sprawdziłem" — każdy weryfikuje samodzielnie w swoim zakresie.

Integracja z resztą systemu (poza tym kontraktem, do zaprojektowania w Etapie 3–4): zapis `claim_map`/`style_metadata` do bazy, wpis do rejestru serii po publikacji, oraz umiejscowienie approval człowieka względem poziomu autonomii — patrz `MASTER_ARCHITECTURE.md` i `IMPLEMENTATION_ROADMAP.md`. Publikacja nie jest częścią kontraktu writera.
