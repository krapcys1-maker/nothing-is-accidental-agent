# 15 — PLAN SERII ARTYKUŁÓW

## Cel pliku
Plan serii artykułów na „Chaos Engine" o budowie i prowadzeniu agenta. Dla każdego artykułu: tytuł roboczy, teza, potrzebne dowody, screenshoty, fragmenty kodu, liczby, błędy, decyzje, status materiału.

Statusy materiału: `GOTOWY` (dość danych, można pisać) · `CZĘŚCIOWY` (część materiału jest) · `CZEKA NA DANE` (wymaga etapów, których jeszcze nie ma).

## Szablon wpisu
```markdown
### Artykuł N: <tytuł roboczy>
- **Teza:**
- **Potrzebne dowody:**
- **Screenshoty:** SS-...
- **Fragmenty kodu:**
- **Liczby:**
- **Błędy:**
- **Decyzje:**
- **Status materiału:**
```

---

### Artykuł 1: Dlaczego dałem agentowi AI własny Substack (i nie pozwoliłem mu pisać o AI)
- **Teza:** autonomiczny twórca treści to realny eksperyment, jeśli dostanie jasny temat, budżet, zasady i człowieka w pętli — a najuczciwszy test to nisza **niezwiązana** z AI.
- **Potrzebne dowody:** struktura projektu, plan, pierwsze decyzje.
- **Screenshoty:** SS-01 (struktura), SS-06 (koszty 0.00 USD).
- **Fragmenty kodu:** —
- **Liczby:** budżet 40 USD/mies., koszt dotąd 0.00 USD, 3 konta, 1 aktywne.
- **Błędy:** brak `.gitignore` (R1).
- **Decyzje:** osobne konto, nie o AI, nisza „ukryte mechanizmy", jedno konto w MVP.
- **Status materiału:** **GOTOWY** (patrz `16_MATERIAL_DO_PIERWSZEGO_ARTYKULU.md`).

### Artykuł 2: Jak zaprojektowaliśmy jego architekturę
- **Teza:** „mózg/ręce/pamięć/strażnik" + porty = system, który jest bezpieczny lokalnie i gotowy na chmurę — zaprojektowany od razu z myślą o pełnej autonomii jako celu, z jawnymi, mierzalnymi bramkami przejścia, nie o człowieku klikającym „zatwierdź" w nieskończoność.
- **Dowody:** diagramy, opis 6 portów, ewolucja V0→V3 (w tym przebudowa na dwuetapowy research po incydencie kosztowym), pełna specyfikacja LEVEL_0→LEVEL_3 i warunków przejścia (ADR-017).
- **Screenshoty:** SS-01, SS-02 (63 testy), SS-12-estymator.
- **Fragmenty kodu:** Policy Engine, kalibrowany estymator kosztu.
- **Liczby:** 6 portów, 3 migracje, 63 testy (było 44 przed incydentem), 4 poziomy autonomii, 17 ADR.
- **Decyzje:** ADR-006 (jedna baza), ADR-009 (FastAPI), ADR-011 (integracja), ADR-016 (dwuetapowy research), ADR-017 (pełna autonomia jako cel).
- **Status materiału:** **GOTOWY**.

### Artykuł 3: Jak nauczyliśmy go szukać tematów
- **Teza:** dobry temat to nie „pomysł", lecz wynik jawnego scoringu i deduplikacji.
- **Dowody:** tabela scoringu, wynik run-topics, dedup.
- **Screenshoty:** SS-03 (scoring), SS-04 (dedup).
- **Fragmenty kodu:** scoring (do skrócenia), dedup (do skrócenia).
- **Liczby:** wagi 25/20/15/15/10/10/5, progi 75/65, DUPLICATE=6.
- **Decyzje:** ADR-001 (źródło prawdy wag), ADR-014 (dedup bez płatnego modelu).
- **Status materiału:** **CZĘŚCIOWY** (brakuje screenshotów).

### Artykuł 4: Jak agent robi research i pilnuje źródeł
- **Teza:** research bez twardej bramki jakości to fabryka halucynacji; reguły muszą stać poza modelem — i nawet dobrze zaprojektowana bramka nie ochroni przed bananowo prostym problemem (za krótki limit odpowiedzi), ani dobry limit kosztu nie pomoże, jeśli szacunek pod nim jest błędny.
- **Dowody:** Research Card (dry_run), bramka jakości, guard iniekcji, **pierwsza realna próba (nieudana, 2026-07-11)**, **naprawa estymatora + dwuetapowy research**.
- **Screenshoty:** SS-05 (Research Card dry_run), SS-08 (realna próba, pre-flight + wynik), SS-12-estymator (nowa projekcja kosztu).
- **Fragmenty kodu:** injection guard, zachowanie usage przy błędzie parsowania, kalibrowany estymator kosztu.
- **Liczby:** min. 3 źródła, koszt ~0.05–0.12 USD/karta (szacunek dry_run); pierwsza realna próba: cap 0.30 USD, **rzeczywisty koszt 0,25 USD** (błąd szacunku +163%); nowa projekcja dwuetapowa ~0,38 USD; injection flags 0.
- **Decyzje:** ADR-015 (bramka + injection), ADR-013 (dry_run), ADR-016 (dwuetapowy research).
- **Status materiału:** **GOTOWY** (dry_run + realna próba + korekta estymatora dają pełny łuk „teoria → pierwszy kontakt z rzeczywistością → poprawka").

### Artykuł 5: Jak pisze artykuły i Notes
- **Teza:** trzy niezależne audyty (fakty/styl/wzrost) robią różnicę między „tekstem AI" a tekstem, który się czyta.
- **Dowody:** pierwszy szkic + wynik audytów.
- **Screenshoty:** SS-11 (szkic).
- **Status materiału:** **CZEKA NA DANE** (generator artykułów niezbudowany).

### Artykuł 6: Jak komentuje bez spamowania
- **Teza:** antyspam to nie „ton", lecz twarde limity (3–5/dzień, 1/autor, link ≤10%, cooldown).
- **Status materiału:** **CZEKA NA DANE** (pipeline komentarzy niezbudowany).

### Artykuł 7: Ile kosztuje prowadzenie autonomicznego Substacka
- **Teza:** koszt da się zmierzyć co do centa — ale samo OSZACOWANIE go z wyprzedzeniem jest zaskakująco trudne (nasz pierwszy szacunek mylił się o 163%), a największą pozycją bywa web search, nie sam model.
- **Dowody:** `COSTS.csv` (z realną kwotą), koszt/Research Card (zmierzony), błąd estymacji, koszt/artykuł, koszt/subskrybent.
- **Screenshoty:** SS-06, SS-12-estymator.
- **Liczby:** **realny koszt dotąd: 0,25 USD** (0,625% budżetu miesięcznego); pierwszy szacunek błędny o +163%; szacunki dry_run; prognoza 20–55 USD/30 dni.
- **Status materiału:** **GOTOWY** na pierwszą część (pierwszy realny wydatek + historia błędu estymacji); brakuje kosztu/artykuł i kosztu/subskrybenta (wymaga kolejnych etapów).

### Artykuł 8: Gdzie agent zawiódł
- **Teza:** porażki są danymi; ukrywanie ich psuje eksperyment — a czasem jedna porażka odsłania drugą, głębszą.
- **Dowody:** rejestr błędów, złe decyzje, słabe teksty, **pierwsza realna, płatna próba researchu — ucięty JSON + bug gubiący koszt + błędny estymator (2026-07-11, wszystko tego samego dnia)**.
- **Liczby:** 5 błędów technicznych/kosztowych dotąd, 1 realne wywołanie (REJECT, koszt 0,25 USD), błąd estymacji +163%, 63/63 testy po wszystkich naprawach (było 44).
- **Status materiału:** **GOTOWY na start** (mamy teraz pełny, potrójny przypadek porażki „na żywym organizmie" — techniczna, księgowa i estymacyjna — z pełnym zamknięciem każdej z nich tego samego dnia; błędy jakościowe treści nadal czekają na generator artykułów).

### Artykuł 9: Ile potrzebował człowieka
- **Teza:** autonomia to widmo — agent świetnie wykonuje, słabiej **decyduje** i **osądza granice**. I nawet twórca systemu potrafi nieświadomie „zdryfować" od pierwotnego celu, jeśli nikt regularnie nie konfrontuje dokumentacji z tym, co naprawdę miało powstać.
- **Dowody:** rejestr interwencji, metryki nadzoru, minuty/artykuł, **korekta celu z 2026-07-11 (ADR-017)** — moment, w którym właściciel zauważył, że dokumentacja zaczęła sugerować „asystent do klikania" zamiast „agent prowadzący konto samodzielnie", i to naprawił, zanim powstał jakikolwiek kod interakcji.
- **Cytowalny fragment:** „Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta."
- **Status materiału:** **GOTOWY na start** (mamy teraz konkretny, dobrze udokumentowany przykład interwencji „na poziomie założeń", nie tylko poprawek pojedynczych treści — redakcyjne poprawki treści nadal dojdą po zbudowaniu generatorów).

### Artykuł 10: Wyniki po 30 dniach
- **Teza:** końcowe rozliczenie — liczby, koszt/subskrybent, co agent robił lepiej, gdzie zawodził.
- **Dowody:** pełne metryki, eksperymenty, wnioski.
- **Screenshoty:** SS-14/15/16.
- **Status materiału:** **CZEKA NA DANE** (wymaga 30 dni publikacji).

---

## Podsumowanie statusów
- **GOTOWE do pisania:** Artykuły 1, 2, 4, 7 (częściowo), 8, 9 (część o korekcie celu).
- **CZĘŚCIOWE:** Artykuł 3 (brakuje głównie screenshotów).
- **CZEKAJĄ NA DANE:** Artykuły 5, 6, 10 (wymagają kolejnych etapów budowy i publikacji).

## Nowa oś narracyjna (propozycja, po ADR-017)
Przejścia między poziomami autonomii (LEVEL_0→1→2→3) to naturalny kręgosłup serii, dopełniający listę tematyczną wyżej — np. „Tydzień 1: LEVEL_1, kontrolowane testy" → „Dzień X: warunki spełnione, przejście na LEVEL_2" → „Dzień Y: pierwszy autonomiczny artykuł" → „LEVEL_3: agent sam zarządza kalendarzem". Nie zastępuje to listy 10 artykułów wyżej — to dodatkowa, chronologiczna rama, którą można nałożyć na tematy 3–9 w miarę jak system faktycznie przechodzi kolejne poziomy.

## Powiązania
- `16_MATERIAL_DO_PIERWSZEGO_ARTYKULU.md`, `article-series/` (szkice), wszystkie pliki 00–14 jako źródła, `docs/DECISIONS.md` ADR-017

## Powiązania
- `16_MATERIAL_DO_PIERWSZEGO_ARTYKULU.md`, `article-series/` (szkice), wszystkie pliki 00–14 jako źródła
