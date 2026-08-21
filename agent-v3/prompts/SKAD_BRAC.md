# Skąd brać to, co działa

Lista rzeczy do przeniesienia ze starego agenta, z dokładnymi miejscami.

---

## ZANIM COKOLWIEK — STYL PISANIA

**To jest najcenniejsza rzecz w całym repozytorium i najłatwiejsza do
przeoczenia, bo nie leży w kodzie.** Bez niej dostaniesz teksty poprawne
merytorycznie i całkowicie nijakie — a wtedy cały projekt nie ma sensu, bo
jedyne, co odróżnia to konto od tysiąca innych, to sposób pisania.

| plik | rozmiar | co to |
|---|---|---|
| `instrukcja dla pisania artykulow/CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md` | **45 KB** | Główna instrukcja naturalnego pisania. Najważniejszy pojedynczy plik. |
| `instrukcja dla pisania artykulow/ARTICLE_STYLE_PROFILE_V1.md` | 3,8 KB | Profil pozytywny: jak ma brzmieć |
| `instrukcja dla pisania artykulow/ARTICLE_NEGATIVE_STYLE_PROFILE_V1.md` | 2,5 KB | Profil negatywny: czego nie robić |
| `instrukcja dla pisania artykulow/NOTES_STYLE_PROFILE_V1.md` | 2,2 KB | Styl notek |
| `instrukcja dla pisania artykulow/STYLE_SOURCES_MANIFEST.md` | 1,5 KB | Skąd wzięto próbki |
| `data/style-references/articles/article_style_samples_v1.txt` | **57 KB** | Korpus próbek stylu, zatwierdzony przez właściciela |

**Mechanika, którą też przenieś** — `archiwum/app/content/style_examples.py`:

- korpus jest przypięty **hashem SHA-256** i loader **odmawia**, jeśli się nie
  zgadza. To nie jest formalność: chodzi o to, żeby nikt po cichu nie podmienił
  głosu, na który właściciel się zgodził
- do promptu trafia **3–5 fragmentów**, każdy 150–900 znaków, dobranych według
  **funkcji retorycznej** (otwarcie, mechanizm, kontrargument, granice,
  zamknięcie) — a nie losowo
- fragment ilustruje **ruch, nie frazę do przepisania**; wszystko dłuższe niż
  900 znaków jest odrzucane, żeby model nie przepisywał całych akapitów

Zweryfikowano na produkcji, że styl **dociera do modelu i jest widoczny
w tekście**: pięć fragmentów korpusu plus oba profile trafiają do promptu
pisarza przy każdym artykule.

**Sprawdź to jako pierwszy test live nowego pisarza:** wygeneruj artykuł
i porównaj z `ARTYKUL_DRAFT.md` oraz `ARTYKUL_DRAFT_2.md` w korzeniu repo.
To są dwa teksty, które przeszły wszystkie bramki i właściciel uznał je za
dobre. Jeśli nowy brzmi płasko obok nich — styl nie dotarł.

---

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
| **skaut tematów** | `archiwum/app/llm/anthropic_client.py` | `_build_prompt`, 66 | Najcenniejszy. Zawiera trzy kryteria źródła (instytucja / darmowe HTML / wpuszcza boty) i definicję `source_quality` przypiętą do realnego pytania. Komentarze w kodzie podają, ile kosztowało każde zdanie. |
| **dyskoveria źródeł** | `archiwum/app/research/anthropic_source_discovery.py` | ~106 | Zakaz sprzedawców i forów, wymóg źródeł instytucjonalnych „dlaczego", obsługa PDF-a, i reguła „katalog to nie dokument" z wymogiem domeny wydawcy. |
| **synteza (E3, ta używana)** | `archiwum/app/research/anthropic_client.py` | ~237 | Liczności w prompcie **muszą** zgadzać się z kontraktem rozmiaru. Patrz niżej. |
| **pisarz** | `archiwum/app/content/prompt.py` | `assemble_writer_prompt`, 70 | Warstwa rzemiosła: nazwij mechanizm wcześnie, nie otwieraj niepopartą praktyką, nie zamykaj streszczeniem, powiedz granice raz. |
| **reviewer v3** | `archiwum/app/content/reviewer.py` | ~180–300 | Rozliczanie zdań, granica publicystyki, 8 przykładów, reguła „OUTCOME TO NIE JEST KLASYFIKACJA" (223). |

---

## Bramki i reguły

| co | plik | funkcja |
|---|---|---|
| dziewięć ewaluacji | `archiwum/app/content/evaluations.py` | `evaluate_draft` (56) |
| ocena szkicu, podłogi deterministyczne | `archiwum/app/content/quality_gate.py` | `assess_draft` (824) |
| rozliczanie twierdzeń per zdanie | `archiwum/app/content/quality_gate.py` | `_account_article_claims` (578) |
| podział tekstu na segmenty | `archiwum/app/content/quality_gate.py` | `build_claim_segments` (435) |
| dopuszczanie źródeł | `archiwum/app/research/source_admission.py` | `evaluate_source_admission` (304) |
| wykrywanie blokad hostów | `archiwum/app/ports/controlled_fetch.py` | `_blocked_page_reason` |
| kontrakt rozmiaru karty | `archiwum/app/research/output_contract.py` | cały plik, ~120 linii |

### Podłogi: porównuj z korpusem, nie z alfabetem
Najważniejsza lekcja z `quality_gate.py`. Kontrola typu „czy jest tu cyfra"
albo „czy jest nazwa instytucji" daje fałszywe alarmy na zdaniach, które
**cytują** materiał. Właściwe pytanie brzmi: *czy ta liczba / ta nazwa
występuje w korpusie*. Pierwsza wersja blokowała dobre teksty dwadzieścia razy.

---

## Testy do przeniesienia w całości

| plik | co robi |
|---|---|
| `archiwum/tests/test_adversarial_bad_articles.py` | **19 artykułów, które MUSZĄ zostać odrzucone.** Zmyślone liczby, fałszywe powołania na badania, wymyślone przeżycia, reviewer kłamiący o klasie. Jedyny test w starym repo sprawdzający, czy bramki łapią **zły** tekst. |
| `archiwum/tests/test_prompt_contract_agreement.py` | prompt nie może prosić o więcej, niż przyjmie walidator |
| `archiwum/tests/test_timeout_token_agreement.py` | termin musi pokryć własny sufit tokenów |
| `archiwum/tests/test_constant_schema_agreement.py` | stała w kodzie kontra `CHECK` w schemacie |

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
