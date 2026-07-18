# WRITING_CONTRACT — wersja 2.1

Kontrakt wejścia/wyjścia writera dla przyszłego autonomicznego content pipeline’u (Etap 3). **Specyfikacja, nie kod** — typy opisane poniżej nie muszą jeszcze istnieć w repozytorium. Publikacja nie jest częścią kontraktu writera.

Reguły stylu i faktów są w `WRITER_RUNTIME_CORE_v2.1.md` oraz pełnym podręczniku. Ten dokument definiuje dane, bramki, lineage, rewizje i wyniki audytów.

---

## 1. Zasady systemowe

1. Writer korzysta wyłącznie z `WritingBrief` i ogólnej wiedzy językowej. Nie dociąga nowych faktów o świecie.
2. Polityka `SYSTEM_PROHIBITED_CONTEXT_NIA` jest nieusuwalna. Brief może dodawać zakazy, lecz nie może usuwać zakazów systemowych.
3. Każda zmiana tekstu tworzy nowy `draft_revision` i unieważnia wyniki audytów wcześniejszej rewizji.
4. Do `READY_FOR_APPROVAL` potrzebne są trzy wyniki `PASS` dla tej samej rewizji: Fact, Style i Editorial.
5. Lineage jest oparty na stabilnych identyfikatorach; tekstowy excerpt jest tylko pomocą diagnostyczną.

---

## 2. Typy wspierające

### 2.1 Source

| Pole | Typ | Znaczenie |
|---|---|---|
| `source_id` | id | Stabilny identyfikator źródła. |
| `url` | url | Adres kanoniczny. |
| `title` | tekst | Tytuł dokumentu/strony. |
| `publisher` | tekst | Wydawca lub instytucja. |
| `author` | tekst lub `null` | Autor, jeśli znany. |
| `published_at` | datetime lub `null` | Data publikacji. |
| `event_date` | datetime/range lub `null` | Data opisywanego zjawiska, jeśli inna. |
| `accessed_at` | datetime | Data dostępu. |
| `source_type` | enum | Np. `PRIMARY_DOCUMENT`, `PEER_REVIEWED`, `OFFICIAL_DATA`, `NEWS`, `COMMENTARY`, `PROJECT_LOG`. |
| `quality_tier` | enum | `A`, `B`, `C`, `REJECTED`; nadawane przez research, nie przez writera na podstawie samego URL. |

### 2.2 EvidenceItem

| Pole | Typ | Znaczenie |
|---|---|---|
| `evidence_id` | id | Stabilny identyfikator dowodu. |
| `source_id` | id | Referencja do `Source`. |
| `locator` | tekst | Strona, sekcja, timestamp, tabela, akapit albo inna lokalizacja. |
| `excerpt` | tekst | Zweryfikowany fragment. |
| `excerpt_hash` | tekst | Hash treści fragmentu dla odtwarzalności. |
| `supports_claim_ids` | lista id | Claimy wspierane przez dowód. |
| `contradicts_claim_ids` | lista id | Claimy podważane przez dowód. |

### 2.3 VerifiedClaim

| Pole | Typ | Znaczenie |
|---|---|---|
| `claim_id` | id | Stabilny identyfikator twierdzenia. |
| `text` | tekst | Treść claimu. |
| `verification_status` | enum | `VERIFIED`, `PARTIAL`, `DISPUTED`, `REJECTED`. |
| `certainty_level` | enum | `FACT`, `INTERPRETATION`, `SUPPOSITION`, `OPINION`. |
| `evidence_ids` | lista id | Dowody użyte do oceny. |
| `boundary` | tekst lub `null` | Zakres, poza którym claim przestaje być prawdziwy. |

### 2.4 FirstPersonFact

| Pole | Typ | Znaczenie |
|---|---|---|
| `fact_id` | id | Stabilny identyfikator. |
| `text` | tekst | Dozwolony fakt pierwszoosobowy. |
| `source_type` | enum | Np. `PROJECT_LOG`, `USER_STATEMENT`, `EXPERIMENT_RESULT`. |
| `source_reference` | id/ścieżka | Konkretny materiał potwierdzający. Brak referencji = fakt niedozwolony. |
| `verified_at` | datetime | Moment zatwierdzenia. |

### 2.5 TargetContext

Dane wymagane dla `comment` i `reply`.

| Pole | Typ | Znaczenie |
|---|---|---|
| `target_content_id` | id lub `null` | Id posta/komentarza. |
| `target_content` | tekst | Treść, na którą writer odpowiada. Wymagana dla `comment` i `reply`. |
| `target_content_type` | enum | `POST`, `NOTE`, `COMMENT`, `REPLY`, `ARTICLE`. |
| `target_source_url` | url lub `null` | Link do źródła. |
| `target_author` | tekst lub `null` | Autor, jeśli dostarczony. |
| `quoted_fragment` | tekst lub `null` | Konkretny fragment będący osią odpowiedzi. |
| `thread_context` | lista wiadomości | Tylko dostarczony kontekst wątku; writer nie dopowiada brakujących wypowiedzi. |

---

## 3. WritingBrief — wejście writera

| Pole | Typ | Znaczenie / reguła |
|---|---|---|
| `brief_id` | id | Id konkretnego zadania. |
| `schema_version` | semver | Wersja tego kontraktu. |
| `writer_instruction_version` | semver/hash | Wersja runtime core użyta do generowania. |
| `research_card_id` | id lub `null` | Wymagane dla `article`, `essay`, `note`; opcjonalne dla komentarza/odpowiedzi. |
| `research_card_version` | semver/int lub `null` | Wersja karty. |
| `research_cutoff_at` | datetime lub `null` | Granica czasowa researchu. |
| `created_at` | datetime | Utworzenie briefu. |
| `publication` | enum | `chaos_engine` albo `nothing_is_accidental`. |
| `format` | enum | `article`, `essay`, `note`, `comment`, `reply`, `analysis`. |
| `language` | enum | `pl` albo `en`; musi być zgodne z polityką publikacji. |
| `target_length` | int/range | Długość docelowa; dla Note sufit jest twardy. |
| `publication_recommendation` | enum lub `null` | `PROCEED`, `REVISE`, `REJECT`; wymagane dla formatów korzystających z Research Card. |
| `thesis_candidate` | tekst lub `null` | Writer może zawęzić, nie rozszerzyć ponad claimy. |
| `verified_claims` | lista `VerifiedClaim` | Jedyny zbiór twierdzeń faktograficznych dostępnych writerowi. |
| `sources` | lista `Source` | Metadane źródeł. |
| `evidence_items` | lista `EvidenceItem` | Dowody powiązane z claimami. |
| `allowed_first_person_facts` | lista `FirstPersonFact` | Jedyne dozwolone fakty pierwszoosobowe. Pusta lista oznacza zero. |
| `additional_prohibited_context` | lista tagów | Dodatkowe zakazy briefu; nie mogą osłabić polityki systemowej. |
| `series_memory` | lista wpisów | Ostatnie formaty, otwarcia, architektury, zakończenia, metafory i funkcje stylu. |
| `cta` | enum/tekst lub `null` | Maksymalnie jedno CTA albo brak. |
| `target_context` | `TargetContext` lub `null` | Wymagane dla `comment` i `reply`. |

### 3.1 Nieusuwalna polityka NIA

`SYSTEM_PROHIBITED_CONTEXT_NIA` zawsze obejmuje: AI, bot, agent, modele, API, pipeline, prompty, testy, koszty budowy, architekturę, Research Card jako mechanizm, build log oraz Chaos Engine. Brak lub pusta lista `additional_prohibited_context` nie wyłącza tej polityki.

### 3.2 Walidacja wejścia — fail-closed

Writer nie tworzy draftu, gdy zachodzi choć jeden warunek:

- brak wymaganej karty lub wersji karty;
- `publication_recommendation = REJECT`;
- `publication_recommendation = REVISE` bez rozstrzygnięcia researchu;
- claim potrzebny do tezy nie ma zweryfikowanego `EvidenceItem`;
- `comment`/`reply` nie ma `target_context.target_content`;
- język i publikacja są sprzeczne;
- brief próbuje usunąć politykę systemową NIA;
- first-person fact nie ma `source_reference`.

---

## 4. WritingResult — wyjście writera

| Pole | Typ | Znaczenie |
|---|---|---|
| `status` | enum | `DRAFT`, `SKIP`, `NEEDS_RESEARCH`, `NEEDS_CONTEXT`. |
| `draft_revision` | int | Zaczyna się od 1; każda zmiana treści zwiększa numer. |
| `draft` | tekst lub `null` | Tylko przy `DRAFT`. |
| `claim_map` | lista `AssertionLineage` | Lineage twierdzeń i interpretacji w tej rewizji. |
| `used_source_ids` | lista id | Faktycznie użyte źródła. |
| `style_metadata` | obiekt | Otwarcie, architektura, ton, humor, domena przykładów, nagłówki, zakończenie, metafory, funkcje, format. |
| `warnings` | lista kodów/tekstów | Np. `DIVERSITY_OVERRIDE:<powód>`, `NO_SERIES_MEMORY`. |
| `reason_code` | kod lub `null` | Wymagany przy statusie innym niż `DRAFT`. |
| `reason_detail` | tekst lub `null` | Konkretny brak lub konflikt. |

### 4.1 AssertionLineage

| Pole | Typ | Znaczenie |
|---|---|---|
| `assertion_id` | id | Stabilny identyfikator twierdzenia w drafcie. |
| `draft_revision` | int | Rewizja, której dotyczy wpis. |
| `assertion_type` | enum | `FACT`, `INTERPRETATION`, `SUPPOSITION`, `OPINION`. |
| `sentence_id` | id lub `null` | Stabilny identyfikator zdania/segmentu. |
| `span_start` / `span_end` | int lub `null` | Opcjonalna lokalizacja w tekście. |
| `text_excerpt` | tekst | Pomoc diagnostyczna, nie klucz relacji. |
| `claim_ids` | lista id | Claimy wspierające twierdzenie. |
| `evidence_ids` | lista id | Dowody. Opinia może mieć pustą listę, ale musi być oznaczona `OPINION`. |

Relacja jest wiele-do-wielu: jedno assertion może korzystać z kilku claimów, a jeden claim może wspierać kilka assertions.

---

## 5. Reason codes

### 5.1 SKIP

- `SKIP_CARD_REJECTED`
- `SKIP_THESIS_UNSUPPORTED`
- `SKIP_INSUFFICIENT_EVIDENCE`
- `SKIP_CONTEXT_CONFLICT`
- `SKIP_DUPLICATE`
- `SKIP_FORMAT_MISMATCH` — materiał nie zawiera jednej samowystarczalnej, zweryfikowanej obserwacji, którą można uczciwie przedstawić w limicie wybranego formatu.

### 5.2 NEEDS_RESEARCH

- `NEEDS_RESEARCH_CARD_REVISE`
- `NEEDS_RESEARCH_MISSING_LINEAGE`
- `NEEDS_RESEARCH_THESIS_WIDER_THAN_CLAIMS`
- `NEEDS_RESEARCH_WEAK_SOURCES`
- `NEEDS_RESEARCH_CONTRADICTION_UNRESOLVED`

### 5.3 NEEDS_CONTEXT

- `NEEDS_CONTEXT_MISSING_TARGET_CONTENT`
- `NEEDS_CONTEXT_MISSING_THREAD_MESSAGE`
- `NEEDS_CONTEXT_AMBIGUOUS_TARGET`

Każdy kod ma `reason_detail` opisujący dokładnie, czego brakuje i jaki następny krok jest potrzebny.

---

## 6. Wyniki audytów

### 6.1 AuditFinding

| Pole | Typ |
|---|---|
| `finding_code` | kod |
| `severity` | `P0`, `P1`, `P2`, `INFO` |
| `location` | `assertion_id`, `sentence_id`, span albo sekcja |
| `explanation` | tekst |
| `required_action` | tekst |

### 6.2 FactAuditResult / StyleAuditResult / EditorialAuditResult

Każdy wynik zawiera:

- `audit_type`: `FACT`, `STYLE` albo `EDITORIAL`;
- `draft_revision`;
- `status`: `PASS` albo `FAIL`;
- `findings[]`;
- `audited_at`;
- `auditor_version`.

**Fact Audit** sprawdza lineage, zakres tezy, poziomy pewności, first-person facts, politykę NIA i przypisywanie intencji.

**Style Audit** skanuje prozę writera. HARD_BANNED w dosłownym cytacie, tytule źródła, metadanych, bloku kodu lub analizowanym przykładzie językowym nie jest naruszeniem; użycie tej frazy przez writera w narracji jest naruszeniem. Audyt sprawdza również WATCHLIST, format i rotację.

**Editorial Audit** sprawdza otwarcie, tezę z kosztem, alokację uwagi, kontrargument, zakończenie i zgodność głosu.

---

## 7. Pętla rewizji

```text
WRITER revision N
→ FACT AUDIT
→ STYLE AUDIT
→ EDITORIAL AUDIT
→ zmiana treści przez writera, audytora lub człowieka
→ WRITER revision N+1
→ FACT AUDIT od początku
```

Każda zmiana treści — nawet „tylko stylistyczna” — unieważnia trzy wyniki audytów wcześniejszej rewizji. Nie wolno wracać bezpośrednio do Style albo Editorial Audit.

---

## 8. FinalDraftPackage

Pakiet gotowy do zatwierdzenia zawiera:

- `status = READY_FOR_APPROVAL`;
- końcowy `WritingResult`;
- `FactAuditResult = PASS`;
- `StyleAuditResult = PASS`;
- `EditorialAuditResult = PASS`;
- wszystkie trzy wyniki dla tego samego `draft_revision`;
- końcowy `claim_map`;
- `style_metadata` i `warnings`;
- `assembled_at`;
- `schema_version` i `writer_instruction_version`.

Pakiet nie publikuje tekstu. Approval i publikacja należą do osobnej warstwy polityki/autonomii.
