# agent-v2 — księga prac

Jedna strona, aktualizowana po każdym skończonym etapie. Czytaj od góry.

**Zasada nadrzędna: każdy etap dostaje test live natychmiast po napisaniu.**
Stary agent zbudował 2800 testów na atrapach i wszystkie były zielone, kiedy
produkcja się wywracała — bo atrapa reviewera zawsze zwraca poprawny JSON,
atrapa dostawcy nigdy nie ma timeoutu, a atrapa internetu nigdy nie zwraca
strony blokady. Tu odwrotnie: mało testów, ale każdy dotyka rzeczywistości.

---

## Co ma robić

Substack „Nothing Is Accidental" — wyjaśnia ukryte systemy, bodźce i decyzje
za zwyczajnymi rzeczami.

| limit | wartość |
|---|---|
| koszt dzienny (agent w pracy) | 5 USD |
| koszt miesięczny | 40 USD |
| artykuły | 4 / miesiąc |
| notki | 5 / dzień |
| komentarze | 15–20 / dzień |
| **testy budowy** | **bez limitu** — nie ograniczamy się przy stawianiu |

Agent ma być **w pełni autonomiczny**. Bez zgód wewnętrznych. Jedyna granica:
nic nie wychodzi na zewnątrz (publikacja, komentarz, polubienie), dopóki
właściciel nie powie inaczej — bo etapu publikacji jeszcze nie ma.

---

## Podział pracy między modele

| etap | model | dlaczego |
|---|---|---|
| skaut tematów | Claude Opus | jakość tematu decyduje o koszcie całej reszty |
| ocena wykonalności tematu | **DeepSeek** | mechaniczne, przed drogim krokiem |
| dyskoveria źródeł | Claude Opus | wymaga wyszukiwania po stronie dostawcy |
| klasyfikacja źródeł | **DeepSeek** | mechaniczne, wysokowolumenowe |
| synteza dowodów | Claude Opus | wymaga oceny |
| pisanie | Claude Opus | to jest produkt |
| recenzja | Claude Opus | to jest bramka jakości |

DeepSeek tam, gdzie praca jest masowa i bez oceny wartościującej. Nie tam,
gdzie od jakości zależy, czy artykuł ma sens.

---

## Stan

| etap | stan | test live |
|---|---|---|
| 0. środowisko, budżet, log kosztów | **w toku** | — |
| 1. skaut tematów | — | — |
| 2. ocena wykonalności (DeepSeek) | — | — |
| 3. dyskoveria + pobranie | — | — |
| 4. klasyfikacja źródeł (DeepSeek) | — | — |
| 5. synteza | — | — |
| 6. pisanie | — | — |
| 7. recenzja + bramki | — | — |
| 8. zapis artykułu | — | — |

---

## Budżet złożoności — pilnuj tego sam

| | limit | ile masz teraz |
|---|---|---|
| pliki .py w agent-v2/ | **10** | 0 |
| tabele w bazie | **4** | 0 |

Poprzedni agent: ~40 000 linii, 2 817 testów, 236 triggerów, 42 migracje,
dwa artykuły. Jeśli przekraczasz budżet — zatrzymaj się i zapytaj właściciela,
jakiej konkretnej straty ta rzecz zapobiega.

## Co przenosimy ze starego (to jest wartość, nie kod)

- [ ] **STYL PISANIA — NAJWAŻNIEJSZE, ZACZNIJ OD TEGO**
      - katalog `instrukcja dla pisania artykulow/` — 5 plików, 55 KB,
        w tym `CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md` (45 KB)
      - korpus próbek `data/style-references/articles/article_style_samples_v1.txt` (57 KB)
      - mechanika doboru fragmentów: `archiwum/app/content/style_examples.py`
        (3–5 fragmentów po 150–900 znaków, dobierane wg funkcji retorycznej,
        korpus przypięty hashem SHA-256)

      **To jest produkt.** Bez tego teksty będą poprawne merytorycznie
      i całkowicie nijakie, a wtedy konto nie różni się od tysiąca innych.
      Test odbioru: porównaj pierwszy wygenerowany artykuł z `ARTYKUL_DRAFT.md`
      i `ARTYKUL_DRAFT_2.md` w korzeniu repo.

- [ ] prompt skauta — po pięciu iteracjach i trzech płatnych pomiarach
- [ ] prompt dyskoverii — instytucje, nie sprzedawcy; katalog to nie dokument
- [ ] prompt syntezy + kontrakt rozmiaru
- [ ] prompt pisarza z warstwą rzemiosła
- [ ] prompt reviewera v3 + rozliczanie twierdzeń per zdanie
- [ ] dziewięć reguł ewaluacji
- [ ] 19 testów kontradowodowych (artykuły, które MUSZĄ zostać odrzucone)
- [ ] polityka dopuszczania źródeł (podłoga pierwotności, dedup, świeżość)
- [ ] wykrywanie blokad hostów po frazach odmowy
- [ ] podłogi porównujące tekst z korpusem, nie z alfabetem

## Czego NIE przenosimy

Trwałych intencji z odciskami, zgód jednorazowych, deklaracji zdolności,
kwalifikacji, lease, kolejki zadań z indeksami unikalnymi, bramki spokoju,
`UNIQUE` na zamrożonym wejściu, limitów w `CHECK`-ach schematu, 236 triggerów.

To jest lista rzeczy, które wywalały produkcję 15 sierpnia.

---

## Dziennik

### 2026-08-15 — start
Decyzja właściciela: przepisujemy warstwę orkiestracji, zachowujemy prompty,
bramki i log kosztów. Powód: sześć kolejnych poprawek w starym systemie
stworzyło sześć nowych problemów, bo każdy limit jest tam przypięty w kilku
miejscach naraz.

### Test zapisu na main
Sprawdzenie, czy ochrona gałęzi nie blokuje zwykłych commitów agenta.
