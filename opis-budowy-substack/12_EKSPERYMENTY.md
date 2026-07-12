# 12 — EKSPERYMENTY

## Cel pliku
Rejestr testów wzrostowych. Każdy: hipoteza, zmienna, okres, metryka sukcesu, wynik, ograniczenia, decyzja po teście. Zasady: jedna główna zmienna naraz, minimum 7 dni, nie zmieniać strategii po jednym poście, zapisać hipotezę **przed** testem.

## Szablon wpisu
```markdown
### EXP-XX — <tytuł>
- **Hipoteza:**
- **Zmienna (jedna):**
- **Grupa/warianty:**
- **Okres:** od–do (≥7 dni)
- **Metryka sukcesu:**
- **Wynik:**
- **Ograniczenia:**
- **Decyzja po teście:**
- **Status:** PLANNED | RUNNING | DONE
```

---

## Stan: brak uruchomionych eksperymentów
Eksperymenty wzrostowe wymagają **realnej publikacji i ruchu** (Etap 4+). Na 2026-07-11 nie ma jeszcze żadnego — poniżej **backlog hipotez** gotowych do uruchomienia, gdy publikacja ruszy.

## Backlog hipotez (PLANNED)

### EXP-01 — Tytuł pytający vs twierdzący
- **Hipoteza:** tytuł w formie pytania („Dlaczego…?") daje wyższy open rate niż twierdzący.
- **Zmienna:** forma tytułu. **Metryka:** open rate / CTR. **Okres:** ≥7 dni, kilka artykułów.
- **Status:** PLANNED.

### EXP-02 — Note z grafiką vs bez grafiki
- **Hipoteza:** Note z prostym diagramem SVG zbiera więcej reakcji/restacków niż sam tekst.
- **Zmienna:** obecność grafiki. **Metryka:** reakcje + restacki na Note. **Status:** PLANNED.

### EXP-03 — Krótki vs średni komentarz
- **Hipoteza:** komentarz 2–3 zdania z jednym mechanizmem daje więcej odpowiedzi/wejść na profil niż dłuższy.
- **Zmienna:** długość komentarza. **Metryka:** replies + profile_visits. **Status:** PLANNED.

### EXP-04 — Publikacja rano vs wieczorem
- **Hipoteza:** pora publikacji wpływa na open rate i pierwsze reakcje.
- **Zmienna:** godzina. **Metryka:** open rate w pierwszych 24h. **Status:** PLANNED.

### EXP-05 — Temat „usługi" vs „przedmioty"
- **Hipoteza:** tematy o usługach (ceny biletów, kolejki) angażują bardziej niż o przedmiotach (QWERTY, kod kreskowy).
- **Zmienna:** kategoria tematu. **Metryka:** komentarze + subskrypcje przypisane. **Status:** PLANNED.

### EXP-06 — Opening „liczba" vs „sprzeczność"
- **Hipoteza:** otwarcie zaskakującą liczbą trzyma czytelnika lepiej niż otwarcie sprzecznością.
- **Zmienna:** typ otwarcia. **Metryka:** czas czytania / dotarcie do końca. **Status:** PLANNED.

## Eksperymenty dot. autonomii (nowe, po ADR-017)
Te „eksperymenty" nie testują treści, tylko samą zdolność systemu do bezpiecznego działania bez człowieka w pętli — to inny rodzaj testu, ale równie ważny dla pytania badawczego projektu.

### EXP-07 — Test wyłącznika SAFE MODE
- **Hipoteza:** SAFE MODE poprawnie wykrywa każdy zdefiniowany trigger (§D.7 planu) i blokuje publikację/komentarze/lajki/subskrypcje, nie blokując researchu.
- **Zmienna:** typ triggera (błędy Playwrighta, wygasła sesja, próg kosztu, wysoki wskaźnik odrzuceń, nietypowa odpowiedź platformy).
- **Metryka sukcesu:** 100% triggerów wykrytych; zero fałszywych negatywów; zero auto-wznowienia bez jawnego resetu.
- **Status:** PLANNED (wymaga zbudowania SAFE MODE — nie zbudowane).

### EXP-08 — Test przejścia LEVEL_1 → LEVEL_2
- **Hipoteza:** po spełnieniu warunków (`docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.3`) system może bezpiecznie działać bez ręcznej akceptacji pojedynczych Notes/komentarzy, utrzymując jakość porównywalną z LEVEL_1.
- **Zmienna:** poziom autonomii (LEVEL_1 z ręczną akceptacją vs LEVEL_2 bez niej, przy tych samych progach scoringu).
- **Metryka sukcesu:** wskaźnik odrzuceń/ukryć po publikacji na LEVEL_2 nie wyższy niż na LEVEL_1; zero naruszeń limitów.
- **Okres:** minimum kilka dni po przejściu, zanim wyciągniemy wnioski.
- **Status:** PLANNED (wymaga osiągnięcia warunków przejścia).

## Ograniczenia metodologiczne (ważne dla uczciwości wyników)
- Substack **nie daje** pełnej atrybucji subskrypcji — część metryk (np. „subskrypcje z komentarzy") będzie **estymacją** oznaczoną `is_estimated`.
- Mały wolumen na starcie = duża wariancja; unikać wniosków po jednym poście.
- Nie zmieniać wielu zmiennych naraz.

## Powiązania
- `docs/experiments/_TEMPLATE.md` (szablon techniczny), `13_WYNIKI_SUBSTACKA.md`, `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` §A.9 (atrybucja)
