# 17 — CONTROLLED FETCH: JAK ZBUDOWAĆ DRZWI DO INTERNETU, KTÓRE JESZCZE SIĘ NIE OTWIERAJĄ

> **Fala E2-B (2026-07-19, ADR-105) — `CLOSED — APPROVED WITH MINOR/P2`; controlled-live = `NOT READY`.** Agent dostał pierwszy prawdziwy adapter sieciowy (`FetchPort`), zdolny pobrać jeden dokument z internetu — i ani razu go nie użył. Cała fala jest offline: fake transport, fake resolver, fake SDK, sieć zablokowana dla całego procesu. Niezależny review wydał `APPROVE WITH MINOR/P2`, właściciel zmergował PR #7 i formalnie zamknął falę (decyzja właściciela, nie implementera). To materiał o tym, że najbezpieczniejszy moment na zbudowanie niebezpiecznej zdolności to moment, w którym jeszcze jej nie włączasz. Dowód: **1551 testów offline**, harness kontrprób **13/13**, produkcyjna baza bajt-w-bajt niezmieniona, koszt `0.000000 USD`.

## O czym jest ten rozdział

Poprzednie fale uczyły agenta pracować z fikcyjnymi danymi (`FakeFetch`). Ta fala buduje prawdziwe drzwi na zewnątrz: adapter, który potrafi połączyć się z serwerem HTTP i pobrać stronę. Różnica między „potrafi” a „zrobił to” jest tu całym tematem.

## Materiał: „Zgoda, która pasuje do dokładnie jednego klucza”

Ludzka zgoda w większości systemów jest jak przepustka: raz wydana, otwiera wiele drzwi. Tu zgoda L1 (`controlled_fetch_approvals`) jest odwrotnością przepustki — jest jak klucz odlany pod jeden konkretny zamek:

- wiąże **jeden** job, **jedno** konto, **dokładny** URL i **odcisk palca** (fingerprint) intentu;
- **wygasa** — zgoda sprzed godziny nie jest zgodą na teraz;
- jest **jednorazowa** — konsumowana atomowo raz, w tej samej transakcji, w której zaczyna się pobranie;
- jest **nieprzenaszalna** — baza danych fizycznie nie pozwala przepiąć jej na inny job ani inny URL (trigger SQL, nie tylko kod Pythona);
- **przeżywa restart** — raz zużytej zgody nie da się „odkonsumować”, więc awaria w połowie nie odnawia prawa do drugiej próby.

**Zdanie do artykułu:** „Dobra zgoda nie mówi »możesz pobierać«. Mówi »możesz pobrać dokładnie to, dokładnie raz, do dokładnie tej godziny« — a potem znika.”

## Materiał: „Payload zatwierdzony to payload wykonany” (domknięcie długu P2-3)

W poprzedniej fali został otwarty dług techniczny: treść zadania (`jobs.payload_json`) mogła teoretycznie zmienić się po zatwierdzeniu, bo broniła jej tylko walidacja w Pythonie. Dla akcji czysto lokalnej to było akceptowalne. Dla akcji sięgającej na zewnątrz — już nie.

Rozwiązanie nie jest kolejnym `if` w kodzie. Jest **barierą w samej bazie**: trigger `jobs_controlled_fetch_payload_frozen` sprawia, że gdy tylko zadanie stanie się kontraktem pobrania, jego treść staje się niezmienna. Człowiek zatwierdza dokładnie te bajty, które maszyna wykona. Bariera jest celowo **wąska** — dotyczy tylko kontraktów pobrania, nie przepisuje historii innych zadań.

**Zdanie do artykułu:** „Walidacja w kodzie mówi »sprawdziłem, że się zgadza«. Bariera w bazie mówi »nie da się zmienić, więc nie ma czego sprawdzać«. Przed akcją nieodwracalną chcesz tego drugiego.”

## Materiał: „Trzy słowa na koniec, i tylko jedno z nich znaczy »nie wiem«”

Pobranie może skończyć się na trzy sposoby, i różnica między nimi to różnica między systemem, który kłamie, a systemem, który przyznaje się do niewiedzy:

- **SUCCEEDED** — request wyszedł, wrócił poprawny dokument, zapisano dowód (retrieval).
- **FAILED** — coś poszło źle **jednoznacznie**: adres odrzucony przez politykę, odpowiedź za duża, zły typ treści, błąd 500. Wiadomo, że się nie udało.
- **NEEDS_VERIFICATION** — request wyszedł, ale wynik jest **niejednoznaczny** (np. proces padł po wysłaniu, przed odebraniem odpowiedzi). System nie zgaduje. Nie ponawia automatycznie. Zostawia to człowiekowi.

Kluczowa decyzja projektowa: **żaden stan niejednoznaczny nie jest automatycznie ponawiany.** Automatyczny retry po „nie wiem, czy wyszło” to najkrótsza droga do podwójnego działania w świecie zewnętrznym.

**Zdanie do artykułu:** „Najuczciwszy stan w całym systemie nazywa się »wymaga weryfikacji«. To maszyna mówiąca: request wyszedł, ale nie każcie mi zgadywać, co się z nim stało.”

## Materiał: „Adapter, którego nie da się zbudować przez pomyłkę”

Prawdziwy transport sieciowy istnieje w kodzie, ale jest za twardą stałą `REAL_CONTROLLED_FETCH_ENABLED = False`. We wspieranym przepływie jedyna droga do zbudowania działającego adaptera prowadzi przez `resolve_controlled_fetch_port` — poprawny kontrakt pobrania i wszystkie trwałe bramki. Żaden zwykły przepływ — offline, dry-run, płatny research, maintenance, reaper — nie skonstruuje go przez pomyłkę. **Uczciwa granica (finding `E2B-F-01` z niezależnego review):** stała chroni tę funkcję, nie sam import klasy — dowolny własny kod poza composition root może ręcznie skonstruować transport. Dlatego poprawne, węższe twierdzenie brzmi: „realny transport pozostaje nieosiągalny przez wspierane composition roots i runtime flow przy `REAL_CONTROLLED_FETCH_ENABLED=False`”, a nie „nie da się go zbudować w żadnym kodzie Pythona”. To różnica między „nie ma ścieżki w produkcyjnym przepływie” a „nie ma ścieżki w ogóle” — i tylko tę pierwszą, węższą prawdę wolno nam napisać.

**Zdanie do artykułu:** „Bezpieczna zdolność to nie ta, której nie używasz. To ta, której nie da się użyć bez przejścia przez wszystkie drzwi, które sam postawiłeś.”

## Materiał: „Próba obalenia własnej pracy”

Przed ogłoszeniem kandydata powstał osobny program (`scripts/harness/e2b_refutation_harness.py`), którego jedynym celem było **złamać** zabezpieczenia: użyć zgody dla innego joba, zużyć ją dwa razy, zmienić treść po zatwierdzeniu, pozwolić staremu procesowi dokończyć po utracie prawa, zbudować adapter w trybie offline, przekroczyć limit, przemycić przekierowanie poza granicę. Wszystkie 13 ataków zostało odparte — nie dlatego, że tak napisano w raporcie, ale dlatego, że każdy atak faktycznie się nie udał.

**Zdanie do artykułu:** „Nie ufaj zieleni własnych testów. Napisz program, którego zadaniem jest udowodnić, że się myliłeś. Dopiero gdy nie da rady — masz prawo mówić o dowodzie.”

## Stan materiału i granice

- **Status:** `E2-B CLOSED — APPROVED WITH MINOR/P2` (ADR-105) — niezależny `APPROVE WITH MINOR/P2`, merge PR #7, formalna decyzja właściciela. Controlled-live = `NOT READY`; kolejna fala techniczna = `NOT STARTED`. Findings review (`E2B-F-01…F-05`, `E2B-OBS-02`) są jawne i nieblokujące dla zamknięcia; `E2B-F-01…F-03` blokują wyłącznie controlled-live.
- **Co NIE zostało zrobione:** żadne realne pobranie, żaden realny request HTTP/DNS, żaden koszt, żaden model, żaden browser, żadna publikacja. Produkcyjna baza pozostaje na migracji `0014`, bajt-w-bajt niezmieniona.
- **Zanim internet zostanie realnie dotknięty:** review i merge tej fali są już za nami; przed pierwszym realnym pobraniem potrzebne będą osobna fala domykająca okno czasowe między sprawdzeniem adresu a połączeniem (realny `urllib` rozwiązuje nazwę sam — finding `E2B-F-02`), runtime'owy mechanizm aktywacji zamiast przełączania stałej w kodzie (finding `E2B-F-03`), migracja produkcji do `0018` i osobna, jednorazowa zgoda właściciela na dokładny dokument. To jest następny rozdział, nie ten — i pozostaje `NOT STARTED`.
