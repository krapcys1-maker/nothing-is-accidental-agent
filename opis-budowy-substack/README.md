# opis-budowy-substack/ — kronika projektu i materiał redakcyjny

Ten folder to **uporządkowana kronika budowy agenta „Nothing Is Accidental"** oraz surowy materiał redakcyjny do późniejszej **serii artykułów na Substacku** (na publikacji „Chaos Engine"). Nie mieszamy go z folderem `docs/`.

- **`docs/`** — bieżąca dokumentacja techniczna systemu (build log, decyzje ADR, błędy, koszty, architektura). Źródło prawdy technicznej.
- **`opis-budowy-substack/`** (ten folder) — narracja, chronologia, dowody i materiał do artykułów. Czerpie z `docs/`, ale pisany jest tak, by zrozumiał go też czytelnik nietechniczny.

## Standard redakcyjny (obowiązuje w każdym pliku)

Dokumentacja ma być: konkretna · chronologiczna · technicznie poprawna · zrozumiała dla nietechnicznego czytelnika · bez marketingowych ogólników · oparta na prawdziwych wynikach · **bez ukrywania porażek**.

**Zakaz zapisywania sekretów:** żadnych kluczy API, tokenów, cookies, haseł ani danych logowania.

## Zasada aktualizacji (Definition of Done każdego zadania)

Po każdym większym zadaniu, ZANIM uznasz je za ukończone:

1. zaktualizuj `docs/`,
2. zaktualizuj odpowiednie pliki w `opis-budowy-substack/`,
3. dopisz nowe decyzje (→ `06_DECYZJE_PROJEKTOWE.md`),
4. dopisz błędy (→ `07_BLEDY_I_NIEUDANE_PROBY.md`),
5. dopisz koszty (→ `09_KOSZTY.md`),
6. dopisz fragment kodu, jeśli powstał ważny mechanizm (→ `10_FRAGMENTY_KODU.md`),
7. dodaj screenshot albo wpis `SCREENSHOT REQUIRED` (→ `11_SCREENSHOTY_I_DOWODY.md`),
8. dopiero potem zamknij zadanie.

> **Zadanie bez aktualizacji tego folderu nie jest ukończone.**

## Mapa plików

| Plik | O czym |
|------|--------|
| `00_START_PROJEKTU.md` | Skąd projekt, dlaczego osobny Substack, dlaczego nie o AI, wybór niszy |
| `01_CEL_I_ZALOZENIA.md` | Cel, metryki, budżet, autonomia, zasady bezpieczeństwa, zakazy |
| `02_POMYSL_NA_PUBLIKACJE.md` | Nazwa, bio, obietnica, odbiorca, nisza, tematy, ton, styl |
| `03_ARCHITEKTURA_AGENTA.md` | Diagramy, moduły, warstwy, tryby, autonomia, gotowość do chmury |
| `04_JAK_DZIALA_AGENT.md` | Krok po kroku, językiem zrozumiałym dla nietechnicznych |
| `05_BUDOWA_KROK_PO_KROKU.md` | Pełna chronologia etapów budowy |
| `06_DECYZJE_PROJEKTOWE.md` | Każda ważna decyzja: opcje, wybór, powody, ryzyka |
| `07_BLEDY_I_NIEUDANE_PROBY.md` | Błędy, nieudane próby, co naprawiliśmy |
| `08_INTERWENCJE_CZLOWIEKA.md` | Kiedy i dlaczego wkraczał człowiek |
| `09_KOSZTY.md` | Koszty API, researchu, grafik, artykułu, subskrybenta, czas człowieka |
| `10_FRAGMENTY_KODU.md` | Reprezentatywne wycinki kodu z wyjaśnieniem |
| `11_SCREENSHOTY_I_DOWODY.md` | Indeks screenshotów i dowodów |
| `12_EKSPERYMENTY.md` | Hipotezy, zmienne, wyniki testów wzrostowych |
| `13_WYNIKI_SUBSTACKA.md` | Chronologia metryk publikacji |
| `14_WNIOSKI_CZASTKOWE.md` | Co zaskoczyło, co działało, co nie |
| `15_PLAN_SERII_ARTYKULOW.md` | Plan serii artykułów na Chaos Engine |
| `16_MATERIAL_DO_PIERWSZEGO_ARTYKULU.md` | Zebrany materiał do artykułu #1 |
| `17_CONTROLLED_FETCH_ZGODA_L1.md` | E2-B: jednorazowa zgoda i lifecycle kontrolowanego pobrania |
| `18_ADRES_SPRAWDZONY_I_ADRES_UZYTY.md` | E2-C: capability, aktywacja YAML i przypięcie adresu do transportu |
| `19_BACKUP_NIE_ZAMYKA_WYSCIGU.md` | Orchestrator migracji 0014→0018: snapshot, rewalidacja, sidecary i recovery |

Podfoldery: `timeline/`, `screenshots/`, `diagrams/`, `code-snippets/`, `weekly-summaries/`, `article-series/`.

---
*Utworzono: 2026-07-11. Stan projektu w chwili utworzenia: zbudowany walking skeleton + research pipeline (Etap 0/1A/1B), 44 testy, zero płatnych wywołań API, zero publikacji. Kod czeka na zgodę właściciela przed pierwszym płatnym wywołaniem Anthropic.*
