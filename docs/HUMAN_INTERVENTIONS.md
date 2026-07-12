# HUMAN_INTERVENTIONS

## Cel

Rejestr każdej ingerencji człowieka: akceptacji, odrzucenia, edycji treści, ręcznego zatrzymania, korekty strategii, ręcznego logowania. Kluczowa metryka eksperymentu brzmi „ile nadzoru agent nadal potrzebuje?" — ten plik na nią odpowiada. Pozwala policzyć: procent treści przyjętych bez zmian, liczbę poprawek na artykuł, czas człowieka dziennie, liczbę ręcznych zatrzymań.

## Zasady

- Jeden wpis = jedna ingerencja.
- Notuj szacowany czas człowieka (minuty) — zasila metrykę „czas człowieka".
- Powiąż z obiektem (content_item / interaction / run) i kontem.

## Typy interwencji (do rozpoznania)

Człowiek: odrzucił decyzję agenta · poprawił tekst · poprawił fakt · zatrzymał publikację · zmienił strategię · zmienił grafikę · naprawił kod · ręcznie zalogował konto · zmienił poziom autonomii · inne.

Skróty typu: REJECT · EDIT_TEXT · FIX_FACT · STOP_PUBLISH · STRATEGY · EDIT_IMAGE · FIX_CODE · LOGIN · AUTONOMY · OTHER.

## Szablon wpisu

```markdown
### [YYYY-MM-DD HH:MM] Typ — krótki opis
- **Typ:** (jeden ze skrótów powyżej)
- **Konto:** account_id
- **Obiekt:** content_item #.. / interaction #.. / run <uuid> (lub —)
- **Co agent chciał zrobić:** proponowana akcja/treść agenta
- **Dlaczego człowiek zareagował:** powód interwencji
- **Co zostało zmienione:** konkretna zmiana (przed → po, jeśli dotyczy)
- **Jaki był efekt:** skutek zmiany (jakość/koszt/harmonogram/strategia)
- **Czas człowieka:** ~N min
- **Wpływ na strategię:** jeśli zmienia zasady → wpis w DECISIONS.md (ADR-XXX)
```

---

## Wpisy

### [2026-07-11] STRATEGY — decyzje właściciela po audycie
- **Typ:** STRATEGY
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** docs/DECISIONS.md
- **Powód:** rozstrzygnięcie pytań otwartych przed kodowaniem.
- **Zmiana:** (1) klucz API — tylko `.gitignore`, bez rotacji [ADR-010]; (2) docelowy sufit autonomii = LEVEL_2 z bramkowaniem [ADR-004]; (3) MVP na jednym koncie `nothing_is_accidental` [ADR-007]; (4) nisza żony = astrologia, konto nieaktywne [ADR-008]; (5) panel = FastAPI [ADR-009].
- **Czas człowieka:** ~5 min
- **Wpływ na strategię:** tak — zamyka ADR-004/007/008/009/010; pozostaje OPEN-4 (budżet dzienny). Plan nadal czeka na ogólną akceptację przed Etapem 0.

### [2026-07-12] STRATEGY — właściciel wyznaczył granice pre-flight pierwszej kompletnej Research Card
- **Typ:** STRATEGY
- **Konto:** nothing_is_accidental
- **Obiekt:** proponowany świeży research topic #2 (jeszcze bez run_id)
- **Co agent chciał zrobić:** przygotować kolejny realny staged research po udanej diagnostyce A2.
- **Dlaczego człowiek zareagował:** realny wydatek i ryzyko kolejnej awarii wymagają najpierw pełnego offline pre-flightu, jawnej estymacji oraz osobnej zgody.
- **Co zostało zmienione:** właściciel narzucił branch `dev/first-successful-research-card`, `max_sources=4`, 1 search per source, A2=1500, retry=0, normalne B; zabronił API, resume, Playwrighta, P1-5, P0-2c, zmian architektury i statusów DB w tej turze.
- **Jaki był efekt:** wykonano wyłącznie testy, read-only kontrolę bazy i estimate-only; koszt 0 USD; powstała propozycja ADR-022 i exact command, ale żadna zgoda na realny call nie została domniemana.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** tak — jeden przyszły run ma być jawnie zatwierdzony, świeży i bez retry; ADR-022 pozostaje PROPOSED.

### [2026-07-12] STRATEGY — review właściciela po audycie/konsolidacji: 4 korekty przed commitem
- **Typ:** STRATEGY
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** MASTER_ARCHITECTURE.md / IMPLEMENTATION_ROADMAP.md / CURRENT_PROJECT_STATE.md / AGENTS.md / dzienniki
- **Co agent chciał zrobić:** zakończyć konsolidację dokumentacji (ADR-023) i zaproponować commit; w blokerach CURRENT_PROJECT_STATE zgoda na run ADR-022 figurowała jako bloker #1.
- **Dlaczego człowiek zareagował:** ocena 8,5/10, zatwierdzenie kierunkowe, ale wykryte 4 niespójności: (1) bloker sugerował, że realny run jest następny w kolejce, podczas gdy roadmapa wymaga najpierw zadań 1–8 Etapu 0; (2) zasady ARCHITECTURE_EVOLUTION nadal wskazywały IMPLEMENTATION_PLAN.md jako miejsce architektury docelowej; (3) AGENTS.md łączył baner korygujący ze starymi, sprzecznymi instrukcjami („baner mówi, żeby nie słuchać reszty pliku"); (4) zasady BUILD_LOG odsyłały do etapów starego planu.
- **Co zostało zmienione:** blokery przepisane (najpierw zadania 1–8, dopiero potem osobna zgoda na zad. 9/ADR-022); zasada ARCHITECTURE_EVOLUTION wskazuje MASTER_ARCHITECTURE + ROADMAP, stare odwołania oznaczone jako archiwalne; AGENTS.md przepisany na krótką wersję 2.0 (stary import → docs/archive/superseded_plans/AGENTS_imported_cowork_instructions_2026-07.md); zasady/szablony BUILD_LOG i DECISIONS wskazują ROADMAP/MASTER; sweep normatywnych odwołań w kronice i SCREENSHOT_INDEX → ścieżki archiwum. Zakaz: zmian architektury, logiki aplikacji, startu Etapu 0 i płatnych runów.
- **Jaki był efekt:** jeden spójny kanon bez konstrukcji „plik odwołuje sam siebie"; kolejność Etapu 0 jednoznaczna; commit dokumentacyjny dopiero po tych korektach.
- **Czas człowieka:** ~15 min (review + decyzja).
- **Wpływ na strategię:** tak — potwierdzone: koniec debaty architektonicznej; następny krok = zadanie 1 Etapu 0 (bez pytania kolejnych modeli o nową architekturę, chyba że problem wymaga zmiany ADR).

### [2026-07-12] APPROVAL — Etap 0 / Task 1 zatwierdzony po drugim code review
- **Typ:** APPROVAL
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** Etap 0 / Task 1 — `research_runs.flow` i bezpieczne resume
- **Co agent chciał zrobić:** zamknąć Task 1 po poprawieniu findingów pierwszego review i opublikować zmiany na branchu developerskim.
- **Dlaczego człowiek zareagował:** commit i push wymagały jawnego zatwierdzenia końcowego zakresu po drugim, niezależnym review.
- **Co zostało zmienione:** właściciel zaakceptował wynik `APPROVE` i polecił commit `Add explicit research run flow and safe resume validation` oraz push wyłącznie na `origin/dev/first-successful-research-card`; Task 2 pozostaje nierozpoczęty.
- **Jaki był efekt:** Task 1 dopuszczony do commita i pushu; bez zgody na API, Playwrighta, realny research ani kolejne zadania roadmapy.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** brak zmiany architektury; formalne zamknięcie Task 1 i utrzymanie kolejności roadmapy.
