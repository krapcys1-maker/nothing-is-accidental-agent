# 00 — START PROJEKTU

## Cel pliku
Uchwycić moment i kontekst startu: kiedy projekt powstał, skąd pomysł, dlaczego osobne konto, dlaczego agent nie pisze o AI, dlaczego nisza „Nothing Is Accidental", jaki był stan początkowy i pierwsze założenia. To pierwsza cegła narracji do serii artykułów.

## Szablon wpisu (dla późniejszych uzupełnień)
```markdown
### [YYYY-MM-DD] Tytuł momentu startowego
- **Co się wydarzyło:**
- **Dlaczego to ważne dla historii:**
- **Cytat/decyzja właściciela (jeśli była):**
- **Powiązania:** docs/... , ADR-...
```

---

## Kiedy projekt powstał
Prace nad eksperymentem ruszyły **11 lipca 2026**. Tego dnia wykonano pełny audyt założeń, powstał `docs/IMPLEMENTATION_PLAN.md`, a następnie — w kolejnych sesjach tego samego dnia — walking skeleton, deduplikacja tematów i research pipeline. Cała dotychczasowa budowa zmieściła się w jednym dniu roboczym, w trybie „najpierw plan, potem kod, z zatrzymaniami do akceptacji".

## Skąd wziął się pomysł
Pomysł to **eksperyment z autonomicznym twórcą treści**: sprawdzić, czy agent AI potrafi od zera zbudować i prowadzić wartościową publikację na Substacku, jeśli dostanie jasny temat, budżet, zasady i **ograniczony** nadzór człowieka.

Pytanie badawcze projektu brzmi:
> Czy agent AI potrafi od zera zbudować i prowadzić wartościową publikację na Substacku, jeśli dostanie jasny temat, budżet, zasady i ograniczony nadzór człowieka?

Docelowo cały przebieg (koszty, błędy, wyniki) ma zostać opisany na osobnej publikacji autora — **„Chaos Engine"** — jako seria artykułów. Ten folder gromadzi surowiec do tej serii.

## Dlaczego osobne konto Substack
Trzy powody:
1. **Czystość eksperymentu.** Osobna publikacja pozwala zmierzyć wzrost „od zera" — bez efektu istniejącej publiczności autora.
2. **Bezpieczeństwo konta głównego.** Automatyzacja nie dotyka konta osobistego właściciela ani konta żony (oba pozostają na razie wyłączone, tryb tylko-komentarze).
3. **Anonimowa marka redakcyjna, nie fikcyjny człowiek (ADR-018).** Publikacja NIE informuje publicznie, że treści tworzy agent AI — ale też nie udaje konkretnej osoby: brak fikcyjnego imienia i nazwiska, brak wymyślonej biografii, brak fikcyjnych doświadczeń. Prawda o automatyzacji zostaje w prywatnej dokumentacji projektu, do osobnej decyzji właściciela o ujawnieniu eksperymentu.

## Dlaczego agent NIE pisze o AI
To celowe ograniczenie tematyczne i redaktorskie:
- **Trudniejszy, uczciwszy test.** Pisanie „AI o AI" byłoby łatwe i autoreferencyjne. Prawdziwym testem jest, czy agent poradzi sobie w niszy **niezwiązanej** ze sobą — wymagającej researchu świata zewnętrznego, weryfikacji źródeł i unikania halucynacji.
- **Unikanie przesytu.** Rynek treści o AI jest przesycony; nisza „ukryte mechanizmy codzienności" jest świeższa i pojemniejsza.
- **Materiał na finał.** Kontrast „agent AI, ale pisze o supermarketach i biletach lotniczych" jest mocnym hakiem dla końcowego artykułu na Chaos Engine (roboczy tytuł: *„Dałem agentowi AI 30 dni, 40 dolarów i własny Substack — i nie pozwoliłem mu pisać o AI"*).

## Dlaczego nisza „Nothing Is Accidental"
Nisza: **ukryte systemy, bodźce i decyzje stojące za zwykłymi rzeczami**. Dlaczego akurat ta:
- **Nieskończony zasób tematów** z codzienności (supermarkety, bilety lotnicze, kolejki, windy, kody kreskowe, QWERTY…).
- **Oparta na faktach, nie na osobistych przeżyciach** — idealna dla agenta, który nie ma „życia" i nie może udawać doświadczeń.
- **Naturalnie prowokuje dyskusję** („nie wiedziałem, że to działa tak!") → sprzyja komentarzom, Notes i wzrostowi.
- **Wizualna** — mechanizmy da się pokazać diagramem/SVG, co pasuje do ograniczeń grafiki w MVP (patrz ADR-003).

## Jaki był stan początkowy
- **Konto Substack już istniało** — nie tworzymy nowego (patrz niżej).
- Istniały trzy dokumenty źródłowe: opis projektu (`zalozenia projektu/…`), założenia dla agenta (`zalzoewnia dla agenta/…`), instrukcja stylu pisania (`instrukcja dla pisania artykulow/…`), plus wstępna `ARCHITECTURE.md`, `README.md`, `IMPLEMENTATION_PROMPT.md` i przykładowe configi.
- **Nie istniał żaden kod** (`app/` nie istniał), nie istniał folder `docs/` z logami.
- W repo znajdował się realny klucz API w `.env` bez `.gitignore` — pierwszy realny problem bezpieczeństwa (patrz `07_BLEDY_I_NIEUDANE_PROBY.md`, R1).

## Jakie konto już zostało założone
- **Nazwa profilu:** Nothing Is Accidental
- **Bio:** „Explaining the hidden systems, incentives and decisions behind ordinary things."
- **Język publikacji:** angielski
- **`account_id` w systemie:** `nothing_is_accidental`
- **Tryb:** FULL_PUBLICATION (pełne prowadzenie), jedyne aktywne konto w MVP.

Decyzja: **nie tworzymy nowego konta** — łączymy się później z istniejącym przez dedykowany profil przeglądarki Playwright, po **ręcznym** zalogowaniu właściciela (magic-link), bez auto-logowania i bez zapisu hasła (ADR-011, `docs/architecture/SUBSTACK_INTEGRATION.md`).

Dwa pozostałe konta (`owner_account`, `wife_account`) to tryb **tylko komentarze**, oba `active: false` w MVP. Nisza konta żony została ustalona jako **astrologia** (ADR-008), ale konto pozostaje wyłączone do czasu po MVP jednego konta.

## Jakie były pierwsze założenia
1. **„Claude = mózg, lokalne narzędzia = ręce, SQLite = pamięć, Policy Engine = deterministyczna bramka".** Model językowy nigdy nie steruje bezpośrednio przeglądarką ani bazą.
2. **Najpierw plan, potem kod.** Żaden `.py` nie powstaje przed akceptacją planu; po planie — zatrzymanie i czekanie.
3. **Nic nie publikujemy** na Substacku na obecnym etapie.
4. **Bez prawdziwych haseł i bez ujawniania kluczy API** w żadnym dokumencie.
5. **Wszystko dokumentowane** — build log, decyzje, błędy, interwencje człowieka, koszty, dowody.
6. **Jakość > szybkość.** Bez podszywania się pod konkretną osobę, bez fikcyjnej biografii, bez spamu — i bez publicznego ujawniania automatyzacji (ADR-018: decyzja właściciela, informacja tylko w dokumentacji prywatnej, do czasu osobnego ujawnienia).

## Powiązania
- `docs/IMPLEMENTATION_PLAN.md` (audyt + plan MVP)
- `docs/architecture/SUBSTACK_INTEGRATION.md` (jak podłączymy istniejące konto)
- `docs/DECISIONS.md` — ADR-007 (jedno konto w MVP), ADR-008 (nisza żony), ADR-011 (integracja z istniejącym kontem)
- `01_CEL_I_ZALOZENIA.md`, `02_POMYSL_NA_PUBLIKACJE.md`
