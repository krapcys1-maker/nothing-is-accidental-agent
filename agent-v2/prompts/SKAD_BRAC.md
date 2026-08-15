# Skąd brać to, co działa

Lista rzeczy do przeniesienia ze starego agenta, z dokładnymi miejscami.

**Kopiuj stamtąd, nie odtwarzaj z pamięci.** Każdy z tych promptów powstawał
przez wiele iteracji i płatnych pomiarów. Prompt skauta przeszedł pięć wersji
i trzy przebiegi live, zanim przestał produkować tematy, których nikt nigdy
nie udokumentował. Napisany od nowa „z grubsza tak samo" zacznie ten cykl
od początku, na Twój koszt.

Stary kod jest **tylko do czytania**. Nie poprawiaj go.

---

## Prompty

| co | plik | linia | uwagi |
|---|---|---|---|
| **skaut tematów** | `app/llm/anthropic_client.py` | `_build_prompt`, 66 | Najcenniejszy. Zawiera trzy kryteria źródła (instytucja / darmowe HTML / wpuszcza boty) i definicję `source_quality` przypiętą do realnego pytania. Komentarze w kodzie podają, ile kosztowało każde zdanie. |
| **dyskoveria źródeł** | `app/research/anthropic_source_discovery.py` | ~106 | Zakaz sprzedawców i forów, wymóg źródeł instytucjonalnych „dlaczego", obsługa PDF-a, i reguła „katalog to nie dokument" z wymogiem domeny wydawcy. |
| **synteza (E3, ta używana)** | `app/research/anthropic_client.py` | ~237 | Liczności w prompcie **muszą** zgadzać się z kontraktem rozmiaru. Patrz niżej. |
| **pisarz** | `app/content/prompt.py` | `assemble_writer_prompt`, 70 | Warstwa rzemiosła: nazwij mechanizm wcześnie, nie otwieraj niepopartą praktyką, nie zamykaj streszczeniem, powiedz granice raz. |
| **reviewer v3** | `app/content/reviewer.py` | ~180–300 | Rozliczanie zdań, granica publicystyki, 8 przykładów, reguła „OUTCOME TO NIE JEST KLASYFIKACJA" (223). |

---

## Bramki i reguły

| co | plik | funkcja |
|---|---|---|
| dziewięć ewaluacji | `app/content/evaluations.py` | `evaluate_draft` (56) |
| ocena szkicu, podłogi deterministyczne | `app/content/quality_gate.py` | `assess_draft` (824) |
| rozliczanie twierdzeń per zdanie | `app/content/quality_gate.py` | `_account_article_claims` (578) |
| podział tekstu na segmenty | `app/content/quality_gate.py` | `build_claim_segments` (435) |
| dopuszczanie źródeł | `app/research/source_admission.py` | `evaluate_source_admission` (304) |
| wykrywanie blokad hostów | `app/ports/controlled_fetch.py` | `_blocked_page_reason` |
| kontrakt rozmiaru karty | `app/research/output_contract.py` | cały plik, ~120 linii |

### Podłogi: porównuj z korpusem, nie z alfabetem
Najważniejsza lekcja z `quality_gate.py`. Kontrola typu „czy jest tu cyfra"
albo „czy jest nazwa instytucji" daje fałszywe alarmy na zdaniach, które
**cytują** materiał. Właściwe pytanie brzmi: *czy ta liczba / ta nazwa
występuje w korpusie*. Pierwsza wersja blokowała dobre teksty dwadzieścia razy.

---

## Testy do przeniesienia w całości

| plik | co robi |
|---|---|
| `tests/test_adversarial_bad_articles.py` | **19 artykułów, które MUSZĄ zostać odrzucone.** Zmyślone liczby, fałszywe powołania na badania, wymyślone przeżycia, reviewer kłamiący o klasie. Jedyny test w starym repo sprawdzający, czy bramki łapią **zły** tekst. |
| `tests/test_prompt_contract_agreement.py` | prompt nie może prosić o więcej, niż przyjmie walidator |
| `tests/test_timeout_token_agreement.py` | termin musi pokryć własny sufit tokenów |
| `tests/test_constant_schema_agreement.py` | stała w kodzie kontra `CHECK` w schemacie |

Te cztery to jedyne testy w starym repo, które **znalazły coś, czego nikt nie
szukał**. Reszta z 2800 to siatka na regresje we własnej logice.

---

## Liczby zmierzone, nie zgadnięte

Warte przeniesienia jako stałe, bo każda kosztowała płatny przebieg:

| co | wartość | skąd |
|---|---|---|
| szybkość generowania | **14–18 ms / token wyjścia** (mediana 16,08) | 19 rozliczonych przebiegów, R² 0,98 |
| koszt artykułu (cały łańcuch) | **~1,41 USD** | content 21, świeży temat, pierwsze podejście |
| koszt dyskoverii | ~0,65–0,75 USD | 16 przebiegów |
| koszt syntezy | ~0,19 USD | |
| koszt pisania + recenzji | ~0,37 USD (bez przepisania) | content 21 |
| liczba segmentów artykułu | 49–65 przy 1000–1250 słowach | 9 szkiców |
| wyjście reviewera | **~118 tokenów na segment** | 64 segmenty = 7540 tokenów |
| skuteczność pobrań | 7–10 z 10 przy dobrych źródłach | tematy 113, 119, 131 |

---

## Czego NIE przenosić

Trwałych intencji z odciskami, zgód jednorazowych, deklaracji zdolności,
kwalifikacji modeli, dzierżaw zadań, kolejki z indeksami unikalnymi na
aktywnych zadaniach, bramki spokoju procesów, `UNIQUE` na zamrożonym wejściu,
limitów w `CHECK`-ach schematu, triggerów append-only, rezerwacji przed
wywołaniem, ścieżki rekoncyliacji.

To jest dokładnie lista rzeczy, które wywalały produkcję 15 sierpnia — nie
model, nie prompty, nie bramki jakości.
