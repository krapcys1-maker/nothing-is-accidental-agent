# Rejestr wydatków online Agent V3

**Waluta:** USD  
**Zasada:** każda pozycja jest dopisywana przed i po wywołaniu; brak wpisu oznacza brak zgody procesu testowego na koszt

## Saldo

| Dostawca | Limit | Wydano | Zarezerwowano | Pozostało |
|---|---:|---:|---:|---:|
| Anthropic | 5.00 | 1.398034* | 0.00 | 3.601966* |
| DeepSeek | 5.00 | 0.33877270 | 4.90 UNKNOWN + 0.30 E-023 UNKNOWN | -0.53877270† |
| GPT/OpenAI — tylko obrazy | 2.00 | 0.00 | 0.00 | 2.00 |
| **Razem — limit globalny** | **10.00** | **1.73680670*** | **4.90 UNKNOWN + 0.30 E-023 UNKNOWN** | **3.06319330†** |

\* Historyczne 0,056604 USD Anthropic jest estymacją według oficjalnej taryfy
obowiązującej 2026-08-21 i nie ma kwoty z faktury. Nowe 1,341430 USD E-014 ma
pełne lokalne tokeny i zweryfikowany cennik, lecz także czeka na rachunek
dostawcy. Stara wersja V3 zapisała historyczne 0,084906 USD według
nieaktualnej taryfy 3/15. DeepSeek E-007 został zrekoncyliowany z eksportem
godzinnym: niepełna synteza kosztowała 0,00855294 USD, a całość 0,01898270 USD.

† T-118, T-132 i T-136 zachowują po 1,60 USD `UNKNOWN`. E-017 discovery dodało
0,10 USD `UNKNOWN`, a E-023 dodało 0,30 USD `UNKNOWN`. Nie oznacza to
potwierdzonego wydatku 5,20 USD ani kosztu 0 USD. Wszystkie rozliczone próby
DeepSeek dają 0,33877270 USD kosztu `KNOWN`. Konserwatywna ekspozycja DeepSeek
wynosi 5,53877270 USD, czyli przekracza sublimit o 0,53877270 USD. Dostawca
pozostaje zablokowany do rekoncyliacji E-023; historyczne `UNKNOWN` nie są
traktowane jak zero.

Sublimity dostawców nie są addytywne. Każda nowa rezerwacja musi przejść
zarówno limit w swoim wierszu, jak i nadrzędne saldo globalne 10 USD.

**Jednorazowa decyzja E-019-F:** po ponownym jawnym poleceniu właściciela, aby
kontynuować testy segmentowo w ramach jednego limitu całych badań 10 USD,
zarezerwowano 0,03 USD na dokładnie jeden normalnie routowany feasibility
DeepSeek Flash. Pierwszy call rozliczył się jako KNOWN 0,020601 USD. Ręczna
kontrola wykazała, że głębokość była oceniona dla uniwersum zamiast wybranej
drogi, więc przed jakimkolwiek research/write poprawiono kontrakt i
zarezerwowano drugie, rozstrzygające 0,03 USD. Nie zmieniono modelu ani
routingu; zero retry. Drugi call rozliczył się jako KNOWN 0,019462 USD. Trzy
historyczne rezerwy i E-017-D nadal są liczone konserwatywnie jako `UNKNOWN`.
Ekspozycja globalna po rozliczeniu wynosi 6,44480970 USD. Wyjątek nie zwalnia
z twardego capu globalnego i nie upoważnia automatycznie do następnego calla.

**Rozliczenie E-020-D:** normalne discovery `deepseek-v4-pro`, dokładnie jeden
logiczny call, zero retry. Responses może wykonać jedno dodatkowe żądanie bez
narzędzi wyłącznie wtedy, gdy pierwsze zwróci prawdziwe URL-e bez końcowego
JSON-u. Predispatch liczy dwa pełne wyjścia i powtórzony input: worst case
0,281278 USD; rezerwacja wynosiła 0,30 USD. Jeden call zakończył się za
0,115807 USD KNOWN, a rezerwację zwolniono. Transport i schemat przeszły, lecz
ręczny audyt odrzucił segment: 22 wyszukiwania przy limicie 8, zawyżona klasa
mirrorów, jeden nieosiągalny kandydat i report wymagający loginu. Ekspozycja
globalna po rozliczeniu wynosi 6,56061670/10 USD. Nie uruchomiono fetch ani
żadnej czynności Substack.

**Rozliczenie E-021-D:** po testach celu 68/68 i pełnej regresji 56/56 jeden
powtórny live segment discovery na tym samym `deepseek-v4-pro`, tym razem przez
oficjalny interfejs DeepSeek zgodny z Anthropic i serwerowe `max_uses=8`.
Dokładnie jeden logiczny call, zero retry; jeden beznarzędziowy selektor jest
dopuszczalny tylko wtedy, gdy pierwszy call zwróci prawdziwe URL-e bez JSON-u.
Worst case wynosił 0,28215132 USD, rezerwacja 0,30 USD. Call zakończył się za
0,033609 USD KNOWN, z 6/8 wyszukiwań. H1 twardego limitu przeszła live, lecz
ręczny audyt odrzucił zestaw za fałszywą deklarację dostępu IOGCC, substytut
EDF, dwa proposed/pending records i ponowne pominięcie mocniejszego baseline
BLM/GAO/DOI. Fetch, browser i Substack pozostały poza segmentem.

**Rozliczenie E-022-D:** po naprawie `discovery@3`, testach celu 70/70 i pełnej
regresji 56/56 wykonano dokładnie jeden segment discovery na tym samym
`deepseek-v4-pro`. Koszt to 0,042581 USD KNOWN, 8/8 wyszukiwań, zero retry.
Kontrakt zatrzymał przebieg przed fetchem: z 10 propozycji 6 przeszło exact URL
i deklarację dostępu, ale brakowało kwalifikowanego `SECOND_ACT`. Ręczna
kontrola potwierdziła, że OSMRE jest realnym i mocnym drugim aktem, lecz jego
URL nie wystąpił w wynikach tej sesji modelu. DOI FY2024 jest mocnym current
scale; cały zestaw nadal nie dorównuje jednak baseline BLM/GAO/DOI i zawiera
trzy mylące deklaracje pełnego dostępu. Po zwolnieniu rezerwacji ekspozycja
globalna wynosi 6,63680670/10 USD. Fetch runtime, pisarz, Notes i Substack nie
zostały uruchomione.

**Rozliczenie E-023-D:** po 72/72 testów celu i poprawnej pełnej regresji 56/56
uruchomiono jedno logiczne discovery na tym samym `deepseek-v4-pro`. Pierwszy
request bounded search zakończył się po około 7 s błędem
`incomplete chunked read`, bez finalnego usage. Exact-URL selector nie
wystartował, retry=0. Rezerwacja 0,30 USD pozostaje w całości `UNKNOWN`; nie ma
dowodu kosztu 0 ani podstaw do ponowienia. Capture błędnie podał zero provider
requestów, ponieważ E-023 ujawniło, że trace powstawał dopiero po kompletnym
body; A-129 naprawia to offline. Bezpłatny endpoint salda dostawcy o 21:34
+03:00 pokazał 24,95 USD dostępnego salda, lecz brak snapshotu sprzed E-023 i
brak historii per request nie pozwalają z tej jednej wartości rozliczyć próby.
Globalna ekspozycja pozostaje 6,93680670/10 USD. Fetch, classify, synthesis,
writer, Notes i Substack nie wystartowały.

## Dziennik transakcji

| ID | Data/czas | Karta naprawy | Dostawca/model | Cel | Limit wywołania | Koszt rzeczywisty | Status | Artefakt |
|---|---|---|---|---|---:|---:|---|---|
| — | 2026-08-21 | dokumentacja | — | audyt lokalny i kwerenda publicznego kodu | 0.00 | 0.00 | zakończony | `../07_dziennik_badan/DZIENNIK_BADAN.md` |
| E-001 | 2026-08-21 | N-001–N-004 | — | implementacja i pełna bezpieczna regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-001_FUNDAMENT_IZOLACJI.md` |
| E-002 | 2026-08-21 | N-005 | — | ledger mutacji, kontrprzykłady restartu i regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-002_LEDGER_MUTACJI.md` |
| E-003 | 2026-08-21 | N-006 | — | zamrożona doba, transakcyjny budżet i regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-003_DOBA_I_BUDZET.md` |
| E-004 | 2026-08-21 | N-007 | — | safe fetch, exact URL, limity zasobów i regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-004_BEZPIECZNY_FETCH.md` |
| E-005 | 2026-08-21 | N-008 | — | 22 wersjonowane kontrakty LLM, telemetria, fail-closed i regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-005_WERSJONOWANE_SCHEMATY_LLM.md` |
| E-006 | 2026-08-21 | N-009 | — | pełny ledger pochodzenia twierdzeń, liczb, zdań i cytowań oraz regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE | `RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md` |
| E-007-D | 2026-08-21 | N-009, N-017 | DeepSeek v4 Flash/Pro | live: classify, synthesis i review na zamrożonym korpusie syntetycznym | 0.25 | 0.01898270 | PARTIAL_PASS; BILL_RECONCILED; RESERVATION_RELEASED | `RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md` |
| E-007-A | 2026-08-21 | N-009, N-016 | Anthropic Claude Sonnet 5 | historyczny live: trzy granice i dodatkowa analogia; nieuprawniony runtime override zamiast normalnego routingu V3 | 0.75 | 0.056604 EST. | COMPLETED_LIVE; BILL_OPEN; AUTHORIZATION_ERROR | `RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md` |
| E-008 | 2026-08-21 | N-019 | — | ledger zdalnego szkicu, restart i pełna regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE; PLATFORM_LIVE_NOT_RUN | `RAPORT_EKSPERYMENTU_E-008_LEDGER_ZDALNEGO_SZKICU.md` |
| E-009 | 2026-08-21 | N-020 | — | atomowa rezerwacja kosztu, konkurencja i pełna regresja offline | 0.00 | 0.00 | COMPLETED_OFFLINE; LIVE_REPLAY_OPEN | `RAPORT_EKSPERYMENTU_E-009_ATOMOWA_REZERWACJA_KOSZTU_MODELU.md` |
| E-010-P | 2026-08-21 | N-004 | plan: DeepSeek v4 Flash/Pro + Claude Fable 5 | preflight pełnego replayu rdzenia; 8–11 dispatchy, bez Substacka | 1.50 | 0.00 | PREFLIGHT_BLOCKED_NO_CREDENTIALS; NO_RESERVATION; NO_DISPATCH | `RAPORT_EKSPERYMENTU_E-010_PELNY_REPLAY_POTOKU.md` |
| E-011 | 2026-08-21 | N-010 | — | transakcyjny zapis, fault injection i recovery | 0.00 | 0.00 | COMPLETED_OFFLINE; POWER_LOSS_NOT_PROVEN | `RAPORT_EKSPERYMENTU_E-011_TRANSAKCYJNY_ZAPIS_ARTYKULU.md` |
| E-012-P | 2026-08-21 | N-004/N-013/N-015/N-023 | plan: 14× DeepSeek Pro, 10× Flash, 3× Fable 5, 5× Opus 5 | scout, research, style A/B, rewizja i pięć Notes; maks. 32; bez Substacka | 4.50 | 0.00 | HARNESS_READY; STYLE_BLOCKER_FIXED_OFFLINE; PREFLIGHT_BLOCKED_NO_CREDENTIALS; NO_RESERVATION; NO_DISPATCH | `RAPORT_EKSPERYMENTU_E-012_PELNY_SYSTEM_REDAKCYJNY_LIVE.md` |
| E-012-D1 | 2026-08-21 16:50–16:53 +03:00 | N-004/E-012 | DeepSeek v4 Pro | pierwszy live scout; pozostałe role tylko po sukcesie | 1.60 | UNKNOWN | STOPPED_FAIL_CLOSED; INCOMPLETE_CHUNKED_READ; NO_RETRY; 31 DISPATCHES NOT_RUN | `.live-experiments/E-012-editorial-system-live/result.json` |
| E-013 | 2026-08-21 | N-011 | — | wersjonowana polityka, dwie iteracje, pełne bramki i kwarantanna | 0.00 | 0.00 | COMPLETED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN | `RAPORT_EKSPERYMENTU_E-013_AUTONOMICZNA_REWIZJA_I_KWARANTANNA.md` |
| E-014-A | 2026-08-21 17:18–17:25 +03:00 | N-011/N-013/N-015 | Claude Fable 5 + Opus 5 | live: artykuł styl/ablacja, minimalna rewizja i pięć form Notes | 3.50 | 1.341430 | COMPLETED_LIVE; 8/8 KNOWN; QUALITY_FINDINGS; NO_FACTCHECK | `RAPORT_EKSPERYMENTU_E-014_RAMIONA_DOSTAWCOW_STYL_REWIZJA_NOTES.md` |
| E-014-D2 | 2026-08-21 17:33–17:36 +03:00 | N-004/N-017 | DeepSeek v4 Pro | materialnie zmieniony scout po T-118 | 1.60 | UNKNOWN | STOPPED_FAIL_CLOSED; INCOMPLETE_CHUNKED_READ; NO_RETRY; 22 NOT_RUN | `.live-experiments/E-014-deepseek-scout-research-live/result.json` |
| E-015-D3 | 2026-08-21 | N-004/N-025 | DeepSeek v4 Pro | scout po redukcji promptu o 67,5% | 1.60 | UNKNOWN | STOPPED_FAIL_CLOSED; SAME_ERROR; PROMPT_HYPOTHESIS_REJECTED | `RAPORT_EKSPERYMENTU_E-015_SKROCONY_SCOUT_I_TRANSPORT_SSE.md` |
| E-015-SSE | 2026-08-21 | N-025 | — | oficjalny kontrakt SSE, parser DONE/usage i blokada po trzech UNKNOWN | 0.00 | 0.00 | FIXED_OFFLINE; LIVE_NOT_VALIDATED; BILL_RECONCILIATION_REQUIRED | `RAPORT_EKSPERYMENTU_E-015_SKROCONY_SCOUT_I_TRANSPORT_SSE.md` |
| E-016 | 2026-08-21 18:22–18:26 +03:00 | N-025/N-027 | DeepSeek v4 Pro | pierwszy kompletny live Scout przez SSE | 0.10 | 0.032564 | TRANSPORT_PASS; QUALITY_FAIL; KNOWN | `.live-experiments/E-016-scout-sse-canary/result.json` |
| E-017-F | 2026-08-21 | N-027 | DeepSeek v4 Flash | normalne feasibility na zamrożonym Scoucie E-016 | 0.03 | 0.005868 | COMPLETED_LIVE; KNOWN | `.live-experiments/E-017-normal-v3-segments/segment-feasibility-result.json` |
| E-017-D | 2026-08-21 | N-026 | DeepSeek v4 Pro | normalne discovery `/responses` | 0.10 | UNKNOWN | STOPPED_FAIL_CLOSED; 0.10 RESERVED; NO_RETRY | `.live-experiments/E-017-normal-v3-segments/segment-discovery-result.json` |
| E-018 | 2026-08-21 19:01–19:05 +03:00 | N-027/N-028 | DeepSeek v4 Pro | jeden Scout uniwersów artykułowych | 0.04 | 0.049298 | TRANSPORT_SCHEMA_PASS; RAW_REPLAY_PASS; COST_CAP_BREACH | `RAPORT_EKSPERYMENTU_E-018_SCOUT_UNIWERSA_ARTYKULOW.md` |
| E-019-F1 | 2026-08-21 20:02–20:07 +03:00 | N-027 | DeepSeek v4 Flash | live feasibility@2: 6 uniwersów, 24 drogi, wybór jednej drogi artykułu na exact raw E-018 | 0.03 | 0.020601 | COMPLETED_LIVE; CONTRACT_PASS; MANUAL_QUALITY_FAIL_ROUTE_DEPTH_MISSING | `.live-experiments/E-019-scout-manual-audit/segment-feasibility-result.json` |
| E-019-C0 | 2026-08-21 20:09 +03:00 | N-027 | — | negatywny test izolacji cache po zmianie wyłącznie promptu feasibility | 0.00 | 0.00 | REFUSED_PREDISPATCH; CROSS_STAGE_CACHE_BUG_FOUND; NO_MODEL_CALL | `.live-experiments/E-019-scout-manual-audit/segment-feasibility-result.json` |
| E-019-F2 | 2026-08-21 20:10–20:14 +03:00 | N-027 | DeepSeek v4 Flash | live feasibility@3: osobna głębokość i drugi akt wszystkich 24 dróg | 0.03 | 0.019462 | COMPLETED_LIVE; CONTRACT_PASS; MANUAL_SELECTION_FAIL_THEN_FIXED_OFFLINE; ZERO_RETRY | `.live-experiments/E-019b-scout-route-depth-live/segment-feasibility-result.json` |
| E-020-P0 | 2026-08-21 | N-026/N-027 | — | preflight discovery przy historycznych nazwach sekretów bez prefiksu V3 | 0.00 | 0.00 | REFUSED_PREDISPATCH; NO_RESERVATION; NO_DISPATCH; ENV_UNCHANGED | `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json` |
| E-020-D | 2026-08-21 20:41–20:43 +03:00 | N-026/N-027/A-122 | DeepSeek v4 Pro | live discovery wyłącznie dla Afterlife/orphaned well z pełnym route brief | 0.30 | 0.115807 | TRANSPORT_SCHEMA_PASS; MANUAL_FAIL_22_OF_8_SEARCHES; SOURCE_SET_PARTIAL; ZERO_RETRY; NO_SUBSTACK | `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json` |
| E-021-D | 2026-08-21 21:00–21:01 +03:00 | A-123/A-124/N-026/N-028 | DeepSeek v4 Pro | powtórne live discovery po twardym `max_uses`, z origin/access metadata | 0.30 | 0.033609 | HARD_CAP_PASS_6_OF_8; CONTRACT_PASS; MANUAL_SOURCE_QUALITY_FAIL; ZERO_RETRY; NO_FETCH; NO_SUBSTACK | `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json` |
| E-022-D | 2026-08-21 21:12–21:13 +03:00 | A-125–A-128/N-026/N-028 | DeepSeek v4 Pro | trzecie live discovery po rolach dowodowych, statusie proposed i current-official-scale | 0.30 | 0.042581 | HARD_CAP_PASS_8_OF_8; CONTRACT_FAIL_MISSING_SECOND_ACT; MANUAL_SOURCE_QUALITY_FAIL; ZERO_RETRY; NO_FETCH; NO_SUBSTACK | `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json` |
| E-023-D | 2026-08-21 21:32 +03:00 | A-125/A-128/A-129/N-026/N-028 | DeepSeek v4 Pro | bounded search + planowany beznarzędziowy exact-URL selector | 0.30 | UNKNOWN | STOPPED_FAIL_CLOSED; INCOMPLETE_CHUNKED_READ_FIRST_REQUEST; USAGE_MISSING; SELECTOR_NOT_RUN; ZERO_RETRY; NO_FETCH; NO_SUBSTACK | `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json` |
| E-023-B | 2026-08-21 21:34 +03:00 | N-026 | DeepSeek account | bezpłatny snapshot salda po niepełnym streamie | 0.00 | 0.00 | READ_ONLY; AVAILABLE_USD_24.95; CANNOT_RECONCILE_WITHOUT_PRE_SNAPSHOT | odpowiedź `/user/balance`, bez utrwalania klucza |
| E-023-B2 | 2026-08-21 | N-026 | DeepSeek account | drugi bezpłatny snapshot salda i próba panelu Usage | 0.00 | 0.00 | READ_ONLY; AVAILABLE_USD_24.92; DELTA_0.03_NOT_REQUEST_ATTRIBUTABLE; USAGE_LOGIN_REQUIRED | `/user/balance`; panel bez sesji; Chrome/extension niedostępne |
| E-024 | 2026-08-21 | N-007/A-130 | — | live `safe_fetch` sześciu ręcznie zakwalifikowanych publicznych dokumentów | 0.00 | 0.00 | LIVE_FETCH_PASS_5_OF_6; MANUAL_CONTENT_PASS; ONE_HTTP_403; NO_MODELS; NO_SUBSTACK | `RAPORT_EKSPERYMENTU_E-024_LIVE_SAFE_FETCH_CANARY.md` |

## Reguła aktualizacji

1. Przed wywołaniem dopisz pozycję ze statusem `RESERVED` i najgorszym kosztem.
2. Odejmij rezerwację od dostępnego salda.
3. Po odpowiedzi wpisz koszt rzeczywisty i status `COMPLETED`, `FAILED_BILLED` albo `FAILED_UNBILLED`.
4. Zachowaj identyfikator odpowiedzi dostawcy tylko w lokalnym artefakcie testowym, bez klucza API.
5. Jeżeli koszt nie jest znany, wpisz `UNKNOWN`, zablokuj dalsze wywołania dostawcy i nie traktuj go jako 0.
