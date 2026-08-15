# START TUTAJ — instrukcja dla agenta budującego agent-v2

Czytasz to, bo masz zbudować **nowego agenta Substacka od zera**, w katalogu
`agent-v2/`. Ten dokument zawiera wszystko, co ustalono. Przeczytaj go w całości
zanim napiszesz pierwszą linijkę.

Kolejność lektury: ten plik → `ARCHITEKTURA.md` → `PROGRESS.md` →
`prompts/SKAD_BRAC.md`.

---

## 1. Co budujesz

Półautonomicznego agenta prowadzącego Substacka **„Nothing Is Accidental"** —
teksty wyjaśniające ukryte systemy, bodźce i decyzje stojące za zwyczajnymi
rzeczami. Przykłady tego, co już wyszło i jest dobre: dlaczego przycisk na
przejściu dla pieszych nic nie robi; dlaczego na jogurcie jest „use by" albo
„best before" i kto o tym decyduje.

Łańcuch: **temat → źródła → pobranie → synteza → artykuł → recenzja → zapis.**

---

## 2. Dlaczego piszemy to od nowa

W tym samym repozytorium stoi poprzedni agent (`app/`, `tests/`, `scripts/`).
**Nie jest zepsuty w sensie jakości** — dowiózł dwa dobre artykuły, a jego
prompty i bramki są wartościowe i masz je przenieść.

Porzucono go, bo **warstwa orkiestracji okazała się nie do utrzymania**:

- każdy limit przypięty w 3–8 miejscach (stała w kodzie, `CHECK` w schemacie,
  liczba w prompcie, asercja w teście) i nikt nigdy nie porównał ich ze sobą
- 40 fal budowy, każda zamrażała własny kontrakt, żadna nie wiedziała o sąsiadach
- 15 sierpnia **sześć kolejnych poprawek stworzyło sześć nowych problemów** —
  nie z niestaranności, tylko dlatego, że zmiana jednej stałej ma tam kilka
  ukrytych zależnych

Konkretne przykłady, żebyś wiedział, czego unikać:

| co zrobiono | co się stało |
|---|---|
| podniesiono limit prób z 2 na 4 w pętli | `attempt_no IN (1,2)` jest `CHECK`-iem w **ośmiu tabelach**; trzecia próba padła, przebieg utknął, 1,84 USD do kosza |
| prompt prosił o „4-8 confirmed_claims" | kontrakt rozmiaru zabijał przy 7 — model posłuszny instrukcji niszczył opłaconą kartę |
| termin 60 s przy suficie 4096 tokenów | przy 16 ms/token pełna odpowiedź potrzebuje 65,9 s — **arytmetycznie niemożliwe**, dostawca policzył, klient wyrzucił |
| walidator odrzucał całość za jeden zły element | **dziesięć** niezależnych egzemplarzy tego samego pomysłu, każdy odkryty przez zapłacenie |

**Wniosek dla Ciebie: jeden limit, jedno miejsce.** Jeśli musisz zapisać liczbę
w drugim miejscu, napisz test, który porówna oba.

---

## 3. Twarde ograniczenia

### Pieniądze
| | |
|---|---|
| dzienny limit działającego agenta | **5 USD** |
| miesięczny | **40 USD** |
| **budowa i testy** | **bez limitu** — nie ograniczaj się przy stawianiu |

Tryb bez limitu: zmienna `AGENT_V2_NO_LIMIT=1`.
Każde wywołanie modelu loguj: dostawca, model, tokeny, koszt, cel.

### Wolumen redakcyjny
4 artykuły/miesiąc · 5 notek/dzień · 15–20 komentarzy/dzień.

### Autonomia
Agent ma być **w pełni autonomiczny**. Żadnych zgód wewnętrznych, żadnych
jednorazowych zatwierdzeń, żadnego zamrażania intencji. Sam wybiera temat,
źródła, treść i ocenia wynik.

### Granice, których nie wolno przekroczyć
1. **Nic nie wychodzi na zewnątrz.** Publikacja, komentarz, polubienie —
   nie istnieją w kodzie i nie powstaną bez osobnej decyzji właściciela.
   „Autonomiczny" znaczy dziś: sam robi artykuł do szuflady.
2. **Nie omijaj blokad botów.** Część stron (eCFR, FederalRegister) serwuje
   CAPTCHA automatom i oferuje w zamian oficjalne API. Wykrywaj odmowę,
   zapisuj jako nieudane pobranie, **nigdy nie próbuj jej obejść** — bez
   zmiany tożsamości, bez rozwiązywania CAPTCHA.
3. **Nie zmyślaj zapisów finansowych.** Jeśli nie wiadomo, czy zapłacono,
   zapisz „nie wiadomo" i powiedz właścicielowi. Nigdy nie wpisuj zgadniętej
   kwoty.
4. **Konto nie ujawnia publicznie, że jest AI** (decyzja właściciela), ale
   **nigdy nie podszywa się pod konkretną osobę i nie kłamie zapytane wprost**.
5. **Właściciel sam wpisuje hasła do Substacka.** Nie dotykasz haseł.

---

## 4. Podział pracy między modele

W `.env` są klucze do **Anthropic** i **DeepSeek**. DeepSeek jest znacznie
tańszy i ma być używany tam, gdzie praca jest masowa i mechaniczna.

| etap | model | dlaczego |
|---|---|---|
| skaut tematów | Claude Opus | jakość tematu decyduje o koszcie całej reszty |
| **ocena wykonalności tematu** | **DeepSeek** | tani odsiew **przed** drogą dyskoverią |
| dyskoveria źródeł | Claude Opus | potrzebuje wyszukiwania po stronie dostawcy |
| **klasyfikacja źródeł** | **DeepSeek** | mechaniczne, wysokowolumenowe |
| synteza dowodów | Claude Opus | wymaga oceny |
| pisanie | Claude Opus | to jest produkt |
| recenzja | Claude Opus | to jest bramka jakości |

Zasada: DeepSeek tam, gdzie błąd kosztuje jedno tanie wywołanie. Claude tam,
gdzie błąd kosztuje cały łańcuch albo jakość tekstu.

---

## 5. Jak pracować

### Etapami, z testem live po każdym
**To jest najważniejsza instrukcja procesowa w tym dokumencie.**

Poprzedni agent zostawił testy live na koniec i przez to zbudował 2800 testów
na atrapach, które były zielone, gdy produkcja się wywracała. Atrapa reviewera
zawsze zwraca poprawny JSON. Atrapa dostawcy nigdy nie ma timeoutu. Atrapa
internetu nigdy nie zwraca strony blokady.

Buduj tak: **napisz etap → puść go na żywo → zobacz, co naprawdę wraca →
popraw → dopiero potem następny etap.**

### Przed każdym płatnym wywołaniem
Sprawdź w kodzie i w danych **wszystkie warunki, które decydują, czy może się
udać**. Jedno zaniedbanie tej zasady kosztowało 0,85 USD na eksperymencie,
który był niemożliwy od początku — licznik pobrań w skrypcie liczył sukcesy
per temat, więc temat z dziesięcioma pobraniami nie mógł już dostać żadnego
nowego, cokolwiek by się poprawiło.

### Testy
Mało, ale każdy dotyka rzeczywistości albo porównuje dwa niezależne miejsca:
- **kontradowodowe** — artykuły, które MUSZĄ zostać odrzucone (przenieś 19 gotowych)
- **zgodności** — prompt kontra walidator, termin kontra sufit tokenów, stała
  kontra `CHECK` w schemacie
- **live po każdym etapie**

Nie pisz testów na atrapach. Jeśli piszesz atrapę, zadaj sobie pytanie, czy
opisuje świat, czy Twoje wyobrażenie o nim.

---

## 6. Co przenieść ze starego (dokładne miejsca)

Patrz `prompts/SKAD_BRAC.md` — jest tam lista plików i linii. Kopiuj stamtąd,
**nie odtwarzaj z pamięci**: prompt skauta powstawał przez pięć iteracji
i trzy płatne pomiary, prompt reviewera przez kilkanaście.

Najkrócej, co jest cenne:
- prompty: skaut, dyskoveria, synteza, pisarz, reviewer
- dziewięć reguł ewaluacji + rozliczanie twierdzeń per zdanie
- polityka dopuszczania źródeł (podłoga pierwotności, dedup, świeżość)
- wykrywanie blokad hostów po frazach odmowy
- podłogi porównujące tekst z **korpusem**, nie z alfabetem
- 19 testów kontradowodowych

---

## 7. Trzy znane pułapki, których stary agent nie rozwiązał

Odziedziczysz je razem z promptami. Nie są naprawione.

### 1. MONOKULTURA ŹRÓDEŁ — napraw to zanim puścisz pierwszy temat

To jest **najpoważniejsza wada odziedziczonego promptu** i właściciel zgłosił
ją wprost: *„co my o Wielkiej Brytanii mamy pisać czy co"*.

Jak powstała: skautowi kazano wybierać źródła, które są (a) instytucjonalne,
(b) darmowe i w HTML, (c) wpuszczają automaty. Każde kryterium osobno słuszne.
Razem dają **jeden serwis na świecie** — brytyjski `gov.uk` — bo amerykański
eCFR blokuje boty, normy BSI/ISO są płatne, a większość reszty publikuje PDF-y.

Skutek: dwanaście kolejnych tematów o brytyjskich przepisach. Daty na jogurcie,
piwo z beczki, opłata stała za prąd, przeglądy techniczne, pojemniki na odpady.
Konto o „ukrytych systemach" zamienia się w biuletyn o regulacjach jednego kraju.

**Czego wymagać od skauta:**

- **twardy zakaz powtórzenia domeny** — żaden temat nie może celować w tę samą
  domenę rejestrowalną, co którykolwiek z ostatnich pięciu
- **rotacja typu instytucji** — kolejne tematy z różnych rodzin:

| rodzina | przykłady |
|---|---|
| regulatorzy krajowi | energetyka, telekomunikacja, transport, żywność — **w różnych krajach** |
| ciała normalizacyjne publikujące otwarcie | W3C, IETF, otwarte części IEEE |
| ujawnienia spółek | raporty roczne, zgłoszenia giełdowe, patenty |
| izby i stowarzyszenia branżowe | wytyczne, kodeksy praktyk |
| nauka | arXiv, PubMed Central, ośrodki uczelniane |
| ciała międzynarodowe | EUR-Lex, OECD, WHO, Bank Światowy |
| samorządy i sądy | uchwały miejskie, publikowane wyroki |
| izby kontroli | NIK, NAO, GAO |

- **rotacja geograficzna** — nie więcej niż dwa z pięciu kolejnych tematów
  z tego samego kraju
- ocena wykonalności (etap DeepSeek) sprawdza dostępność **po** tym, jak temat
  jest już zróżnicowany — nie odwrotnie, bo wtedy znów zbiegnie do gov.uk

**Zbuduj to jako regułę w kodzie, nie tylko jako zdanie w prompcie.** Historia
ostatnich tematów jest w bazie; wystarczy przekazać skautowi listę użytych
domen i krajów z zakazem powtórzenia. Prompt sam tego nie utrzyma — pierwszy
raz też mu kazano „różnicować" i i tak zbiegł.
2. **Ocena artykułu zawsze wychodzi 1.0.** Dziewięć ewaluacji zero-jedynkowych
   daje albo komplet, albo odrzucenie — więc próg „auto-akceptacji 0.9" nie
   odrzuca niczego. Jeśli ocena ma cokolwiek znaczyć, musi być ciągła.
3. **Blokady hostów.** Opisane wyżej. Część tematów jest przez to nieosiągalna
   i skaut musi to uwzględniać w ocenie wykonalności.

---

## 8. Gdzie co leży

```
KTORY_JEST_KTORY.md      ← przeczytaj, żeby nie pomylić agentów
agent-v2/
  START_TUTAJ.md         ← ten plik
  ARCHITEKTURA.md        ← kształt systemu, tabele, budżet
  PROGRESS.md            ← księga prac; AKTUALIZUJ PO KAŻDYM ETAPIE
  prompts/SKAD_BRAC.md   ← co przenieść i z którego pliku
  stages/ gates/ tests/  ← puste, tu budujesz
app/ tests/ scripts/     ← STARY AGENT, ZAMROŻONY, tylko do czytania
data/agent.db            ← STARA baza, zapis finansowy, NIE PISZ
data/agent-v2.db             ← Twoja, czysta
docs/                    ← historia: BUILD_LOG, ERRORS_AND_FAILURES, DECISIONS
```

**Aktualizuj `PROGRESS.md` po każdym skończonym etapie.** To jest jedyne
miejsce, z którego następna sesja dowie się, co działa, a co nie.

---

## 9. Czego właściciel oczekuje

Powiedział to wprost i warto to zacytować:

> „wolę żeby to było prostsze ale działało niż tak jak jest teraz"

> „nie chcę już przepalać dziesiątek dolarów na nic"

> „mają być live testy robione oczywiście, bo ostatnio na koniec zostawiliśmy
> i powstało gówno"

Czyli: **prostota ponad kompletność, działanie ponad elegancję, dowód ponad
obietnicę.** Jeśli jakaś warstwa nie zapobiegła realnej stracie — nie buduj jej.
