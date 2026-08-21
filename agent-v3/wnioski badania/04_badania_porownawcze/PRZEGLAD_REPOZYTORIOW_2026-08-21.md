# Porównawcze badanie publicznych agentów i narzędzi Substack

**Data dostępu:** 2026-08-21  
**Metoda:** analiza README i wybranych plików implementacji z płytkich kopii repozytoriów  
**Tryb:** tylko odczyt; bez instalacji, uruchomienia kodu, kluczy, sesji i mutacji kont  
**Cel:** znaleźć wzorce możliwe do adaptacji w w pełni autonomicznym Agent V3

## 1. Ograniczenie porównania

To nie jest benchmark jakości tekstu ani autonomii. Projekty rozwiązują różne zadania: narzędzia API, generowanie Notes, analizę konta, scaffolding przeglądarki lub liniowe tworzenie draftów. Porównanie identyfikuje konkretne mechanizmy i ich dowody w kodzie. Nie przyznaje ocen liczbowych.

## 2. Migawka replikacyjna

| Repozytorium | HEAD zbadanej wersji | Data commitu | Pliki śledzone | Pliki testowe według konwencji |
|---|---|---:|---:|---:|
| [santhosh-patel/substack-agent](https://github.com/santhosh-patel/substack-agent) | `a38457d168bb3fea4037a4d279edd693273c3932` | 2026-08-15 | 164 | 0* |
| [tomsiclucia-blip/substack-growth-engine-template](https://github.com/tomsiclucia-blip/substack-growth-engine-template) | `c353fc6397202742f54cb29bbc4da3ee2e8de885` | 2026-06-22 | 82 | 0 |
| [aboyalejandro/substack-author-agent](https://github.com/aboyalejandro/substack-author-agent) | `43f97d82847001c79716b25a1533adde42b7ef69` | 2026-06-12 | 20 | 0 |
| [kyarminrox/substack-agent](https://github.com/kyarminrox/substack-agent) | `fdd9620a9c354992864ceb859062dcf7d92c6064` | 2026-06-05 | 74 | 0 |
| [conorbronsdon/substack-mcp](https://github.com/conorbronsdon/substack-mcp) | `6470687c77747c6ec9d1c6c4caeb7ccd8e835a43` | 2026-08-06 | 41 | 8 |
| [drona23/substack-ai-bot](https://github.com/drona23/substack-ai-bot) | `9c9d542743746172c5a5b6d675ae2c53c33ace3a` | 2026-06-15 | 9 | 0 |
| [AnthonyDavidAdams/substack-api-reference](https://github.com/AnthonyDavidAdams/substack-api-reference) | `b9ebaf5cd58e527a3dba00689a2933e49a811310` | 2026-06-23 | 11 | 0 |

\* Repozytorium santhosh zawiera skrypty smoke/auth/API, lecz nie leżą one w typowym katalogu `test/tests/__tests__` i nie mają typowych nazw. Kolumna opisuje mechaniczny pomiar nazw plików, nie deklarację autora.

## 3. Wyniki według projektu

### 3.1. Substack Growth Engine

**Fakty z kodu:**

- pięć analiz jest uruchamianych równolegle, a potok zapisuje stan końcowy generowania jako `awaiting_approval`;
- `notes_jsonb_original` przechowuje oryginalny batch obok edytowalnego `notes_jsonb`;
- moduł `learn.js` porównuje treść wersji według indeksu i przekazuje różnice do kolejnego przebiegu jako `voice_corrections_md`;
- planowane notki są łączone z danymi wyniku funkcją porównującą pierwsze 80 znormalizowanych znaków;
- likes, restacks i replies są liczone osobno oraz osobno dla subtype'ów;
- adaptacyjna zmiana miksu źródeł jest domyślnie wyłączona;
- są dwa bezpłatne tryby: pełny stub i realna integracja z fałszywymi odpowiedziami modelu;
- hook blokuje uruchomienie realnego, płatnego pipeline'u przez agenta kodującego.

**Wzorce do adaptacji:**

1. niezmienny oryginał i wersjonowane różnice;
2. oddzielne osie wyniku zamiast jednego score;
3. rozdzielenie testu plumbing od testu integracyjnego z atrapą modelu;
4. blokada płatnego/realnego przebiegu na granicy wykonania;
5. zachowanie częściowych wyników przy awarii.

**Ograniczenia i odrzucenia:**

- zewnętrzna bramka akceptacyjna jest niezgodna z celem pełnej autonomii V3;
- dopasowanie pierwszych 80 znaków nie jest stabilną tożsamością treści;
- dopasowanie po indeksie działa tylko przy niezmiennej kolejności i liczebności;
- brak nazwanych plików testowych oznacza, że deklarowane własności trzeba w V3 udowodnić od nowa;
- zależność od likes jako głównego sygnału jest zbyt wąska dla redakcji.

**Powiązanie z audytem:** A-008–A-011, A-020, A-023, A-041, A-072.

### 3.2. conorbronsdon/substack-mcp

**Fakty z kodu:**

- każde narzędzie jest przypisane do klasy `read`, `draft`, `publicUpload` albo `publish`;
- adnotacje jawnie ustawiają `readOnlyHint`, `destructiveHint` i `openWorldHint`;
- opisy Notes jednoznacznie deklarują natychmiastową publikację;
- operacje długich postów są ograniczone do draftów, a delete i schedule są wyłączone;
- klient ma 30-sekundowy timeout i typowane błędy uwierzytelnienia, limitu, walidacji, braku zasobu, serwera i timeoutu;
- osiem plików testowych sprawdza m.in. adnotacje, timeouty, typy błędów, sesję i kontrakt serwera;
- `get_post_analytics` skanuje do 500 ostatnich postów, aby znaleźć statystyki dla ID.

**Wzorce do adaptacji:**

1. centralny rejestr możliwości i ich właściwości;
2. opis ryzyka jako część kontraktu narzędzia, ale egzekwowany również w kodzie;
3. typowana hierarchia awarii;
4. timeout każdego żądania;
5. testy mapowania narzędzie–możliwość i negatywne testy zakazanych operacji.

**Ograniczenia i odrzucenia:**

- polityka ograniczająca publikację długich tekstów nie jest polityką docelową V3;
- oznaczenie zapisu jako `destructiveHint:false` nie znaczy, że operacja jest odwracalna lub niegroźna;
- skan 500 postów jest ograniczeniem kompletności i wydajności;
- repo korzysta z nieoficjalnego API, więc typy lokalne nie tworzą stabilnego kontraktu platformy.

**Powiązanie z audytem:** A-003–A-007, A-022, A-047, A-049, A-054, A-059–A-060, A-069.

### 3.3. santhosh-patel/substack-agent

**Fakty z kodu:**

- wspólne handlery zasilają MCP i HTTP;
- produkcyjne ścieżki narzędziowe wymagają Bearer `API_SECRET`;
- zestaw dziewięciu narzędzi obejmuje publikację newslettera, Note, komentarz, automatyczne komentarze, listy i scheduler;
- `publish_newsletter` najpierw tworzy draft, a przy `isDraft=false` publikuje i wysyła go do subskrybentów;
- `publish_note` publikuje natychmiast;
- schemat narzędzia jest walidowany częściowo, lecz handler nadal rzutuje argumenty na `any` i wykonuje własne kontrole;
- scheduler przechowuje informację, czy późniejsza operacja ma utworzyć draft czy publikować.

**Wzorce do adaptacji:**

1. jedna implementacja handlera dla wielu interfejsów;
2. centralna autoryzacja transportu;
3. oddzielenie kolejki harmonogramu od wykonania;
4. jawny kontrakt pól narzędzia.

**Ograniczenia i odrzucenia:**

- szeroki zestaw mutacji nie ma widocznej warstwy autonomicznej polityki redakcyjnej;
- `isDraft=false` ma bardzo duży skutek, a jest zwykłym polem boolean;
- natychmiastowe Notes i komentarze wymagają w V3 osobnych capability gates, idempotency keys i potwierdzeń;
- `any` i lokalne kontrole osłabiają korzyść formalnego schematu;
- smoke skrypty nie zastępują testów własności bezpieczeństwa.

**Powiązanie z audytem:** A-003, A-006, A-018, A-023, A-030, A-060, A-069.

### 3.4. Substack Author Agent

**Fakty z kodu:**

- ten sam cel jest zaimplementowany w Agno, Anthropic SDK i OpenAI Agents SDK;
- wspólny prompt i zestaw skills są źródłem zachowania wszystkich wariantów;
- ślady Opik obejmują wywołania modeli, narzędzia, tokeny i koszty;
- sześć skills dotyczy artykułów, Notes, komentarzy, pomysłów, głosu i grafiki;
- sesje wariantu OpenAI są przechowywane w pamięci procesu;
- skills są pobierane przez sieć podczas importu modułu `shared.skills`;
- brak nazwanych plików testowych.

**Wzorce do adaptacji:**

1. wspólny kontrakt pozwalający porównywać dostawców na tym samym zadaniu;
2. pełne ślady tool calli, tokenów, kosztów i czasu;
3. wyspecjalizowane, wersjonowane instrukcje ładowane tylko dla pasującego zadania.

**Ograniczenia i odrzucenia:**

- jest to doradca strategii, nie pełny autonomiczny potok;
- sieć podczas importu jest niezgodna z hermetycznymi testami V3;
- pamięć procesu nie wystarcza dla restartów i spójności;
- obserwowalność przez usługę zewnętrzną nie może być jedynym dziennikiem audytowym.

**Powiązanie z audytem:** A-008–A-011, A-018, A-022, A-041, A-047.

### 3.5. kyarminrox/substack-agent

**Fakty z kodu:**

- README oznacza projekt jako `v0.1 — scaffolding and drivers`;
- architektura rozdziela sterowniki platform, workflow, gateway modelowy, selektory i logi;
- `SAFE_MODE=true` pomija wypełnienie tytułu i treści w ścieżce tworzenia draftu;
- domyślna wartość `SAFE_MODE` w schemacie środowiska to `false`;
- przebiegi są zapisywane w JSONL, a ścieżki publikacji tworzą screenshoty diagnostyczne;
- selektory Substack są zebrane w jednym module;
- brak nazwanych plików testowych.

**Wzorce do adaptacji:**

1. centralne selektory i adapter platformy;
2. dowody wizualne i append-only JSONL dla kroków UI;
3. tryb offline lokalnego modelu;
4. jawny ślad `safeSkip` przy pominięciu operacji.

**Ograniczenia i odrzucenia:**

- bezpieczny tryb nie jest wartością domyślną;
- otwarcie stron przy `SAFE_MODE` nadal wymaga analizy wszystkich efektów ubocznych;
- scaffolding bez testów nie jest dowodem niezawodności;
- screenshot nie zastępuje identyfikatora i potwierdzenia z API.

**Powiązanie z audytem:** A-002–A-004, A-023, A-047, A-058–A-060, A-069.

### 3.6. drona23/substack-ai-bot

**Fakty z kodu:**

- jeden skrypt realizuje Google News RSS -> Claude -> Pexels -> Playwright -> draft;
- harmonogram korzysta z macOS launchd;
- wynik jest draftem gotowym do publikacji;
- repozytorium ma dziewięć plików i brak nazwanych testów;
- dokumentacja deklaruje źródła RSS, ale nie ma porównywalnego modelu pochodzenia twierdzeń, pamięci ani bramek.

**Wniosek:** projekt jest przykładem prostego, liniowego pipeline'u, nie wzorcem docelowej redakcji. Wartość porównawcza polega głównie na pokazaniu, że automatyczne wypełnienie edytora nie jest równoznaczne z systemem redakcyjnym.

### 3.7. AnthonyDavidAdams/substack-api-reference

**Fakty ze źródła:**

- repozytorium określa API jako nieoficjalne, nieobsługiwane i zmienne;
- dokumentuje 129 obserwowanych endpointów oraz specyfikację OpenAPI z 125 operacjami;
- opisuje metodę opartą na curl, Playwright i przechwytywaniu żądań UI;
- wskazuje `GET /api/v1/post_management/detail/{post_id}?offset=0&limit=1` jako endpoint zawierający 31 pól statystyk posta;
- nie zawiera nazwanych testów automatycznych.

**Wzorce do adaptacji:**

1. osobny adapter dla nieoficjalnego API;
2. specyfikacja OpenAPI jako wejście do typowanego klienta;
3. fixture'y odpowiedzi z wersją obserwacji;
4. testy kontraktowe i szybka degradacja przy zmianie schematu;
5. oddzielenie hosta konta od hosta publikacji.

**Ograniczenia:**

Nie zweryfikowano endpointów na żywym koncie. Twierdzenia repozytorium są użytecznymi hipotezami integracyjnymi. Rozbieżność z `substack-mcp`, który skanuje listę 500 postów i deklaruje brak per-post endpointu, jest dowodem, że V3 nie może opierać architektury na jednym nieformalnym źródle.

**Powiązanie z audytem:** A-016, A-033–A-034, A-041, A-054, A-069, A-072.

## 4. Synteza mechanizmów dla V3

| Mechanizm | Źródło inspiracji | Decyzja dla V3 |
|---|---|---|
| niezmienny oryginał + diff wersji | Growth Engine | przyjąć i powiązać z identyfikatorami uwag |
| osobne osie wyniku | Growth Engine | przyjąć; dodać kohorty i horyzonty |
| darmowy plumbing + fake-model integration | Growth Engine | przyjąć i rozszerzyć na cały pipeline |
| rejestr możliwości | substack-mcp | przyjąć jako fundament izolacji |
| typowane błędy i timeouty | substack-mcp | przyjąć |
| testy adnotacji narzędzi | substack-mcp | przyjąć i dodać testy negatywne |
| jeden handler dla API/MCP | santhosh | rozważyć po stabilizacji kontraktów |
| wspólny harness wielu modeli | Author Agent | przyjąć do ewaluacji offline |
| pełne ślady kosztów/tool calli | Author Agent | przyjąć lokalnie jako źródło prawdy |
| centralne selektory i screenshoty | kyarminrox | przyjąć jako dowód pomocniczy |
| OpenAPI dla adaptera | API Reference | przyjąć jako generowany kontrakt roboczy |
| zewnętrzna bramka akceptacyjna | Growth Engine / substack-mcp | odrzucić; niezgodna z pełną autonomią |
| prosty boolean otwierający publikację | santhosh / obecne V3 | odrzucić; zastąpić capability gate |
| sieć podczas importu | Author Agent | odrzucić |
| `SAFE_MODE=false` domyślnie | kyarminrox | odrzucić |
| podobieństwo tekstu jako ID | Growth Engine / obecne V3 | odrzucić |

## 5. Wniosek główny

Żaden zbadany projekt nie dostarcza kompletnego wzorca pełnej autonomicznej redakcji. Najlepsze elementy są rozproszone: różnice wersji i bezpłatne tryby testu, jawne możliwości i typowane błędy, wspólne kontrakty wielu modeli, lokalne ślady wykonania oraz robocza specyfikacja API.

V3 ma szerszy istniejący potok redakcyjny niż badane narzędzia, ale jego przewaga funkcjonalna nie jest przewagą niezawodności. Racjonalna droga nie polega na kopiowaniu repozytorium ani dodawaniu kolejnych agentów. Polega na wbudowaniu powyższych mechanizmów w obecny rdzeń, w kolejności narzuconej przez P0.

## 6. Źródła pierwotne

- [santhosh-patel/substack-agent](https://github.com/santhosh-patel/substack-agent)
- [tomsiclucia-blip/substack-growth-engine-template](https://github.com/tomsiclucia-blip/substack-growth-engine-template)
- [aboyalejandro/substack-author-agent](https://github.com/aboyalejandro/substack-author-agent)
- [kyarminrox/substack-agent](https://github.com/kyarminrox/substack-agent)
- [conorbronsdon/substack-mcp](https://github.com/conorbronsdon/substack-mcp)
- [drona23/substack-ai-bot](https://github.com/drona23/substack-ai-bot)
- [AnthonyDavidAdams/substack-api-reference — ENDPOINTS.md](https://github.com/AnthonyDavidAdams/substack-api-reference/blob/main/ENDPOINTS.md)
