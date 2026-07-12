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
