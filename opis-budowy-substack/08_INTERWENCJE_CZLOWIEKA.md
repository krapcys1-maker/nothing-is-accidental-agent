# 08 — INTERWENCJE CZŁOWIEKA

## Cel pliku
Rejestr każdej sytuacji, w której **człowiek** wkroczył: odrzucił temat, poprawił artykuł/Note/komentarz, zatrzymał publikację, zmienił strategię, poprawił kod, zmienił poziom autonomii albo użył kill switcha. Dla każdej: co agent chciał zrobić, dlaczego człowiek zareagował, co zmieniono, jaki efekt, ile czasu. To bezpośredni pomiar odpowiedzi na pytanie eksperymentu: **ile nadzoru agent naprawdę potrzebuje.**

> **Ważne rozróżnienie (ADR-017):** dwa typy interwencji mają zupełnie inną trajektorię oczekiwaną w czasie. **Zmiana poziomu autonomii** i **decyzje strategiczne** pozostają na stałe rolą człowieka — to nie ma zniknąć, docelowo to JEDYNA trwała bramka „per decyzja" (nie per treść). **Poprawki pojedynczych treści** (artykuł/Note/komentarz) i **odrzucenia tematów** powinny z czasem **maleć** w miarę przechodzenia na wyższe poziomy autonomii — to jest dokładnie to, co ten plik ma pokazać liczbowo. Jeśli po przejściu na LEVEL_2 poprawki treści nie maleją, to sygnał, że progi jakości (scoring) są ustawione za nisko, nie że trzeba wrócić do ręcznej akceptacji na stałe.

## Szablon wpisu
```markdown
### [YYYY-MM-DD] <typ interwencji>
- **Co agent chciał zrobić:**
- **Dlaczego człowiek zareagował:**
- **Co zmieniono:**
- **Efekt:**
- **Czas człowieka:**
```
Typy: DECYZJA STRATEGICZNA · ODRZUCENIE TEMATU · POPRAWKA ARTYKUŁU · POPRAWKA NOTE · POPRAWKA KOMENTARZA · STOP PUBLIKACJI · ZMIANA AUTONOMII · POPRAWKA KODU · KILL SWITCH · LOGIN.

---

## Faza dotychczasowa — charakter interwencji
Na obecnym etapie (przed generacją treści i publikacją) interwencje człowieka miały charakter **strategiczno-decyzyjny i bramkujący**, nie redakcyjny. Właściciel nie poprawiał jeszcze żadnego tekstu (bo żaden nie powstał), za to podjął kluczowe decyzje kierunkowe i wielokrotnie **zatrzymał** agenta przed kosztem/publikacją.

### [2026-07-11] DECYZJE STRATEGICZNE (pakiet startowy)
- **Co agent chciał zrobić / zaproponował:** rekomendacje z audytu (m.in. wybór poziomu autonomii, panelu, polityki budżetu, obsługi klucza, zakresu MVP).
- **Dlaczego człowiek zareagował:** to decyzje właścicielskie, nie techniczne — wymagały wyboru człowieka.
- **Co zmieniono / ustalono:** MVP tylko na koncie `nothing_is_accidental` (ADR-007); nisza żony = astrologia (ADR-008); panel = FastAPI (ADR-009); docelowy sufit autonomii = LEVEL_2 z bramkowaniem (ADR-004); klucz — tylko `.gitignore`, bez rotacji (ADR-010); budżet 2/dzień, 40/mies. z priorytetem miesięcznym (ADR-012); integracja z istniejącym kontem przez Playwright po ręcznym logowaniu (ADR-011).
- **Efekt:** jednoznaczny kierunek MVP; zamknięcie wszystkich decyzji otwartych z audytu.
- **Czas człowieka:** przegląd i decyzje w ramach sesji planistycznej (dzień 2026-07-11).

### [2026-07-11] STOP przed kosztem — trzy zatrzymania
- **Co agent chciał zrobić:** przejść dalej po każdym etapie (po planie → do kodu; po skeletonie → do researchu; po researchu → do pierwszego **płatnego** wywołania Anthropic).
- **Dlaczego człowiek zareagował:** twarda zasada projektu — nie kodować przed akceptacją, nie wydawać budżetu bez zgody, zatrzymać się i czekać.
- **Co zmieniono:** po każdym etapie agent **zatrzymał się** i czekał; realne API pozostało nieuruchomione (dostępne przez `--real`, świadomie nieużyte).
- **Efekt:** 0.00 USD realnego kosztu; pełna kontrola tempa; brak niespodzianek kosztowych.
- **Czas człowieka:** decyzja „idź dalej / czekaj" po każdym etapie.

### [2026-07-11] POPRAWKA KODU (drobna, wychwycona samodzielnie)
- **Co agent chciał zrobić:** dostarczyć działający pipeline researchu.
- **Dlaczego reakcja:** błędny import w teście (`app.workflows.research.validation` zamiast `app.research.validation`).
- **Co zmieniono:** poprawiony import (wychwycony przed runem, nie wymagał interwencji właściciela).
- **Efekt:** 44 testy przechodzą.
- **Czas człowieka:** 0 (samonaprawa) — odnotowane dla pełności.

### [2026-07-11] DECYZJA STRATEGICZNA — doprecyzowanie celu: pełna autonomia (ADR-017)
- **Co agent chciał zrobić / co sugerowała dotychczasowa dokumentacja:** dokumentacja (macierz akceptacji, ADR-004, większość plików `opis-budowy-substack/`) zaczęła sugerować, że ręczna akceptacja każdej pojedynczej akcji jest stanem docelowym systemu.
- **Dlaczego człowiek zareagował:** to nieporozumienie względem pierwotnego celu eksperymentu — właściciel chciał agenta, który SAMODZIELNIE prowadzi konto (LEVEL_3), nie asystenta generującego wyłącznie szkice do klikania.
- **Co zmieniono:** pełna redefinicja dokumentacji (ARCHITECTURE.md, IMPLEMENTATION_PLAN.md CZĘŚĆ D, ADR-017, komplet plików opis-budowy-substack/) — jawna specyfikacja czterech poziomów autonomii, warunków przejścia, Autonomous Interaction Engine, SAFE MODE. **Zero kodu w ramach tej interwencji** — wyłącznie korekta dokumentacji, zgodnie z jawnym poleceniem właściciela „zatrzymaj się i poczekaj na zgodę przed kodowaniem".
- **Efekt:** spójna definicja celu w całej dokumentacji; gotowy, szczegółowy plan wdrożenia LEVEL_2/LEVEL_3, jeszcze niezaimplementowany.
- **Czas człowieka:** jedna, precyzyjna wiadomość z pełną specyfikacją oczekiwań (poziomy, warunki przejścia, scoring, SAFE MODE) — dużo bardziej efektywne niż punktowe poprawki, bo skorygowało założenie u źródła, zanim wpłynęło na kod.

---

## Interwencje jeszcze nieodnotowane (spodziewane w kolejnych etapach)
- **ODRZUCENIE TEMATU / POPRAWKA ARTYKUŁU/NOTE/KOMENTARZA** — pojawią się dopiero, gdy powstaną treści (Etap 2+). To będzie kluczowy materiał: ile % treści agenta przechodzi bez poprawek.
- **LOGIN** — jednorazowe ręczne logowanie do Substacka (Etap 4), zapisywane tu i w `docs/HUMAN_INTERVENTIONS.md`.
- **KILL SWITCH / STOP PUBLIKACJI** — dotąd nieużyte w sensie awaryjnym.

## Metryki nadzoru (do wypełniania)
| Metryka | Wartość na 2026-07-11 |
|---|---|
| Decyzje strategiczne człowieka | 9 (ADR-004/007/008/009/010/011/012/017 + zakres) |
| Zatrzymania przed kosztem/publikacją | 3 |
| Zmiany poziomu autonomii (formalne) | 0 (wciąż LEVEL_0/LEVEL_1 — plan przejść dopiero zdefiniowany, ADR-017) |
| Odrzucone tematy | — (brak generacji) |
| Poprawki treści (art./Note/komentarz) | — (brak generacji) |
| Użycia kill switcha (awaryjne) | 0 |
| Łączny czas człowieka | do uzupełnienia (sesja planistyczna 1 dzień) |

**Do śledzenia od LEVEL_2:** wskaźnik poprawek treści powinien maleć wraz z dojrzewaniem scoringu — to kluczowa metryka odpowiadająca na pytanie eksperymentu wprost.

## Powiązania
- `docs/HUMAN_INTERVENTIONS.md` (źródło), `06_DECYZJE_PROJEKTOWE.md`, `09_KOSZTY.md`

### [2026-07-12] Zgoda na Task 4
- Właściciel dopuścił wyłącznie ustawienie `USED`, jawny force re-research i regresje; zachował zakaz API oraz automatycznych płatnych ponowień.
- Efekt: Task 4 wykonano offline, bez realnego researchu i bez zmian bazy źródłowej.

### [2026-07-12] Zgoda na korektę Task 4 po review
- Właściciel ograniczył poprawkę do czterech P1, fail-closed i dokumentacji; race condition pozostawił jako P2.
- Efekt: pełna finalizacja i regresje wykonane offline, bez API, commita, pushu ani Task 5.
