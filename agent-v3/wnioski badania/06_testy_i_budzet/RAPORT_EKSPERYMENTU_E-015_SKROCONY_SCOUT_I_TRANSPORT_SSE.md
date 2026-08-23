# E-015 — skrócony scout i transport SSE DeepSeek

**Data:** 2026-08-21  
**Status:** `PROMPT_HYPOTHESIS_REJECTED; SSE_FIXED_OFFLINE; LIVE_BLOCKED`  
**Substack:** brak odczytu, zapisu, sesji, draftu i publikacji

## 1. Hipoteza

T-118 i T-132 użyły promptów scouta o długości około 23 tys. znaków i po
około 181 s zakończyły się `incomplete chunked read`. Hipoteza H-015-1:
redundantny prompt powoduje zbyt długie rozumowanie/odpowiedź i jest główną
przyczyną awarii.

## 2. Interwencja

Aktywny `prompts/skaut.md` miał 448 linii, 3 866 słów i 22 542 znaki. Te same
reguły o dwóch typach tematu, precedensach i nasyceniu były wyjaśniane wiele
razy. Skrócono go do 189 linii, 962 słów i 6 859 znaków bez usuwania:

- sześciu tematów i dwóch rodzajów;
- wszystkich wymaganych pól kontraktu;
- warunku co najmniej trzech SYSTEM_UNDER_TEST z precedensami;
- czterech skal;
- pytań czytelników, pamięci i historii;
- czterech rankingów po trzy indeksy;
- zakazu zmyślania liczb, dokumentów, motywów i precedensów.

Test anty-regresyjny wymaga mniej niż 220 linii i 2 000 słów oraz obecności
wszystkich pól. Kontrakty i limity: 15 testów, 94 podtesty oraz 45/45 kontroli
sufitów PASS.

Pełna regresja T-140 wykazała jednak, że pierwsza kompresja zachowała pola, ale
usunęła część wykonawczego znaczenia: pytania czytelników jako dowód istnienia
przekonania, zaporę przed wróżeniem, obowiązkowy miks tematów, wymuszony ranking
i jawny mechanizm anty-kliszy. `test_pytania.py`, `test_stawka.py` i
`test_wybor_tematu.py` oblały, więc twierdzenie o pełnym zachowaniu kontraktu
zostało odrzucone. Przywrócono brakujące instrukcje bez powrotu do starej
redundancji. Aktywny prompt po T-141 ma 214 linii, 1 192 słowa, 8 256 znaków i
SHA-256 `A712F476B3BE354AB32D5602218C5A1DBFD1D6CD5CAC15AFF638D63BE235F092`;
siedem plików celu przeszło, a finalna regresja T-142 dała 52/52 PASS w
52,687 s. Wykonanie live T-136 pozostaje dowodem dokładnie
wersji 189/962 i jej hasha z artefaktu, nie późniejszego promptu.

## 3. Plan live

Jeden odmienny scout `E-015-DEEPSEEK-SCOUT-R3-CONCISE-PROMPT` na normalnym
`deepseek-v4-pro`; zero retry; cap 1,60 USD. Dwie wcześniejsze rezerwy UNKNOWN
pozostały policzone w pełnej wysokości. Maksymalna ekspozycja całego programu
po próbie: 6,21701670 USD.

## 4. Wynik live

Wyrenderowany user prompt miał 7 499 znaków i SHA-256
`33cdb9699f7a784d087c655f496f00e64c96042cfee62a7a6610c373579adf68`.
Po 120,703 s peer ponownie zamknął połączenie bez kompletnego chunked body.
Nie otrzymano response, usage, tokenów ani request ID.

Ledger: `UNKNOWN`, reserved 1,60 USD, known 0 USD, ok=0. Dalsze 22 planowane
wywołania nie zaszły.

Artefakt: `.live-experiments/E-015-deepseek-concise-scout-live/result.json`,
SHA-256 `AE8E8779B8707440BB68F62B31454ABEF4B2439B6B7B637D7CA9B042141DEB0D`.

## 5. Rozstrzygnięcie hipotezy

H-015-1 w mocnej postaci została odrzucona. Redukcja znaków user promptu o
67,5% nie usunęła klasy awarii. Krótszy prompt może nadal zmniejszać koszt i
złożoność utrzymania, ale nie jest udowodnioną naprawą transportu.

Trzy próby miały różne hashe wejścia, czasy 180,844; 180,875; 120,703 s i ten
sam błąd. Wszystkie używały tylko capability `MODEL_CALL`, bez web search.
Fakt wspiera przyczynę w warstwie transport/dostawca, ale nie pozwala wskazać,
czy odcina dostawca, proxy czy sposób buforowania klienta.

## 6. Naprawa transportu offline

Przed zmianą zwykły DeepSeek używał buforowanego `httpx.post()` i próbował
zdekodować jeden pełny JSON dopiero po zakończeniu odpowiedzi. Anthropic już
używał streamingu i w E-014 ukończył nawet 191-sekundowy artykuł.

Oficjalna dokumentacja DeepSeek podaje, że `stream=true` zwraca częściowe delty
SSE, strumień kończy `data: [DONE]`, a `stream_options.include_usage=true`
dodaje końcowy chunk użycia:
[DeepSeek Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/).

`llm._call_deepseek()` używa teraz tego kontraktu. Sukces wymaga kompletnego
DONE, usage, treści i `finish_reason=stop`. Reasoning nie trafia do JSON-u
etapu. Niepełny SSE nadal daje UNKNOWN bez retry i zachowuje częściową
diagnostykę.

T-138: pierwsza atrapa SSE oblała 4/4 przez brak context managera w fixture;
nie zmieniono parsera. T-139: poprawiona atrapa oraz transport, księgowanie,
uprzęże i bramka po trzech UNKNOWN — 25/25 PASS.

## 7. Blokada i budżet

Konserwatywna ekspozycja po E-015:

| Składnik | USD | Status |
|---|---:|---|
| E-007 historia | 0,07558670 | znany/estymowany |
| T-118 scout | 1,60 | UNKNOWN, pełna rezerwa |
| T-131 Anthropic | 1,341430 | KNOWN |
| T-132 scout R2 | 1,60 | UNKNOWN, pełna rezerwa |
| T-136 scout skrócony | 1,60 | UNKNOWN, pełna rezerwa |
| **Razem ekspozycja** | **6,21701670** | konserwatywnie |
| **Pozostało do 10 USD** | **3,78298330** | nie jest zgodą na dispatch |

DeepSeek ma konserwatywną ekspozycję 4,81898270 USD przy sublimitcie 5 USD.
Dalszy live jest twardo blokowany po trzech kolejnych UNKNOWN, mimo wolnego
salda globalnego. Najpierw wymagana jest rekoncyliacja dostawcy, potem jeden
canary SSE z nowym ledgerem.

## 8. Ograniczenie dowodu

SSE ma wyłącznie dowód offline. Nie wolno twierdzić, że naprawił prawdziwą
awarię. Nie wykonano czwartego calla ze względu na trzy nierozliczone rezerwy i
sub-limit DeepSeek. Nie uzyskano tematów, źródeł, syntezy, ocen ani fact-checku.
