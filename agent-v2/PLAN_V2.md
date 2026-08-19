# Plan v2 — co mamy, czego brakuje, co działa, co nie

Stan na 2026-08-19. Gałąź `v2-test`, produkcja nietknięta na `main` (tag `v1`).

---

## Co konto potrafi dziś

| zdolność | stan | uwaga |
|---|---|---|
| notki na profilu | **działa** | 5 dziennie, odstępy 45–90 min |
| komentarze u obcych | **działa** | 15–20 dziennie, milczenie dozwolone |
| odpowiedzi w trzech miejscach | **działa** | pod notkami, artykułami i naszymi komentarzami |
| polubienia w kanale | **działa** | 12–20 dziennie |
| obserwowanie profili | **działa** | 30–44 miesięcznie |
| subskrypcje | **działa** | 6–12 miesięcznie, wąsko |
| artykuł od tematu do publikacji | **działa** | pięć opublikowanych |
| grafika do artykułu | **działa** | jeden styl domowy |
| **restack cudzej notki** | **ZBUDOWANY** | 2–4 dziennie, sprawdzony na żywym kanale bez wysyłania |

## Co zbudowane na v2 i przetestowane

- **Bibliotekarz** — grupuje 134 zapłacone, nigdy nieczytane fragmenty po
  mechanizmie. Kod weryfikuje: grupa musi łączyć ≥2 różne dziedziny.
- **Bramka ciekawości** przed pisarzem — wymaga złamanego przekonania. Na pięciu
  prawdziwych kartach odtworzyła sądy właściciela (słoiczek → ODLOZ, autobus → PISZ).
- **Skaut poluje na naruszenia** — każdy temat musi nieść zdanie „Everyone assumes…".
- **Bank notek** — pisanie oddzielone od publikowania, 10 gotowych notek.
- **Notki na Fable 5** — wyraźnie lepsze, +$12/miesiąc przy pięciu dziennie.
- **Rotacja formy artykułu** — 6 zakończeń, 1–3 paralele, koniec z jednym szkieletem.
- **Styl okładek** — ciemniejsze tło, ślady zużycia, przeżywa miniaturę.
- **Historia porażek wraca do dyskoverii** — `fda.gov` i `easa.europa.eu` pomijane.
- **Druga runda przy chudym korpusie** — poniżej 4 źródeł szukamy dalej.
- **Odpowiedzi oddzielone od polubień** w przeglądzie.

## Co NIE działa albo jest otwarte

**Restack — zbudowany, czeka na pierwsze wysłanie.** Ścieżka ustalona na żywym
Substacku: przycisk `Restack` rozwija menu z pozycją `Restack with a note`.
Próba bez wysyłania: 5 rozważonych, 3 przyjęte, 2 odmowy. Pozostaje wpiąć go
w rutynę dnia w `run.py` i wykonać pierwszy prawdziwy.

Pierwszy test znalazł przy okazji **błąd zapory, który blokował poprawne
teksty**: `bez_wstrzykniecia` porównywała podciągi, więc wzorzec `"as an ai"`
łapał `"as an aid"`, `"as an aim"` i `"as an air"`. Ile razy odrzucił coś
dobrego wcześniej — nie wiadomo.

**Pobranie źródeł: 65% (55 z 84).** Dwie dominujące przyczyny wśród 29 porażek:
puste wydobycie treści (10, prawdopodobnie PDF-y — `trafilatura` ich nie czyta)
i blokady automatów (12). Blokad nie obchodzimy; PDF-y to realna luka.

**Zero cichych dni.** Ostatni wyraźny podpis automatu. Publikacja nadająca
identycznie codziennie czyta się jak kanał, nie jak ktoś, kto myśli.

**Pytania czytelników nie zasilają puli tematów.** Odpowiedzi już do nas płyną,
nic ich nie kieruje do skauta. Darmowe i wysokosygnałowe.

**Brak danych o skuteczności form.** Osiem form notek, zero pomiarów — bo nic
z banku jeszcze nie wyszło. To zablokowane na wolumenie, nie na wysiłku.

**`test_integracja` pomijany** — odpala płatny pełny przebieg z przerwami
45–90 min. Pełny dzień nie jest pokryty testem.

## Kolejność prac

1. **Restack z komentarzem** ← teraz
2. Pytania czytelników → pula tematów
3. Ciche dni
4. PDF-y w pobieraniu
5. Pomiar form, gdy bank zacznie wychodzić

## Zasady, które zostają nienaruszone

- Kopia testowa **nie może publikować** — plik `TO_JEST_KOPIA_TESTOWA` odbiera `--wyslij`.
- Artykuł **zawsze powstaje** po opłaconym researchu; bramki tylko zgłaszają uwagi.
- Hosty odmawiające automatom są **respektowane**, nigdy obchodzone.
- Konto nie ujawnia, że jest AI, i **nigdy nie kłamie zapytane wprost** (ADR-018).
- Uczymy się na **odpowiedziach**, nie na polubieniach.
