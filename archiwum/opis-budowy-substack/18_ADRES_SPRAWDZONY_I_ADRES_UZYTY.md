# 18 — ADRES SPRAWDZONY I ADRES UŻYTY MUSZĄ BYĆ TYM SAMYM ADRESEM

> **Fala E2-C (2026-07-19, ADR-107) — `CLOSED — APPROVED WITH MINOR/P2`.** Kandydat ADR-106 przeszedł niezależny review, merge PR #9 (`ff323746c35f733507a7b0a30837ebf645020b2b`) i zielony post-merge checkpoint `1572/1572`; właściciel formalnie zamknął falę. Etap 2 nadal trwa, controlled-live ma status `NOT READY`, a następna operacja techniczna = `NOT STARTED`. Nie wykonano realnego DNS, połączenia ani pobrania.

## Dziura między dwiema poprawnymi funkcjami

Poprzednia fala potrafiła sprawdzić, czy nazwa serwera prowadzi do publicznego adresu. Potrafiła też wykonać request HTTP. Obie funkcje z osobna wyglądały rozsądnie. Problem ukrywał się między nimi.

Najpierw lokalny resolver sprawdzał adres. Później biblioteka HTTP rozwiązywała tę samą nazwę jeszcze raz. Jeżeli odpowiedzi różniły się, transport mógł połączyć się z adresem, którego polityka nigdy nie widziała. Zielony wynik pierwszego sprawdzenia nie był więc dowodem poprawnego połączenia.

To klasyczny błąd czasu: sprawdziłeś jedną rzecz, ale użyłeś później innej.

## Zamiast „sprawdzone”, „sprawdzone i przypięte”

E2-C tworzy niezmienny `BoundHttpTarget`. Zawiera:

- zatwierdzony URL, schemat, host i port;
- cały kanoniczny zbiór rozstrzygniętych adresów;
- dokładny numeryczny adres wybrany do połączenia;
- ścieżkę requestu;
- wartość HTTP Host;
- nazwę TLS SNI.

Każdy adres zwrócony przez resolver musi przejść politykę. Jeden prywatny, loopback, link-local albo inny niedozwolony wynik odrzuca całość. Pusty wynik też jest odmową.

Transport nie dostaje już samego URL do ponownego rozstrzygnięcia. Dostaje przypięty adres i łączy się dokładnie z nim. Nazwa hosta pozostaje tam, gdzie jest potrzebna do potwierdzenia tożsamości serwera: w Host i SNI.

Redirect nie dziedziczy pozwolenia poprzedniego hosta. Otrzymuje nowe rozstrzygnięcie, nową kontrolę wszystkich adresów i własne przypięcie.

## Przełącznik nie jest zgodą

Drugi problem był prostszy: realny transport był za stałą `False` w kodzie. To bezpiecznie blokowało wszystko, ale każde przyszłe włączenie wymagałoby zmiany programu.

Nowy globalny gate jest jawnym booleanem YAML i domyślnie pozostaje wyłączony. ENV nie może go zastąpić. Nawet wartość `true` nie daje jednak prawa do żadnego requestu. Mówi wyłącznie: system może posiadać tę zdolność.

Prawo do konkretnego pobrania nadal pochodzi z jednorazowej zgody L1. Storage:

1. ponownie czyta zamrożony intent;
2. sprawdza job, konto, URL, fingerprint, limity, termin, lease i run;
3. atomowo konsumuje zgodę;
4. tworzy jedyny attempt w stanie `RESERVED`;
5. dopiero wtedy wydaje krótkotrwałą capability dla composition root.

Bez tej capability realny factory odmawia. Po terminie też odmawia.

## Prywatna klasa nie jest magiczną piaskownicą

Publiczny konstruktor realnego transportu zniknął ze wspieranego API. Prywatny konstruktor wymaga pieczęci factory, a factory wymaga capability ze storage.

To nie jest obietnica, że uprzywilejowany programista nie może zmienić kodu albo importować prywatnych nazw. Python nie jest granicą procesu bezpieczeństwa przeciwko autorowi programu. Uczciwe twierdzenie jest węższe: zwykły wspierany flow aplikacji nie skonstruuje realnego transportu bez przejścia przez trwały approval i kontrolowany root.

## Próba obalenia rozwiązania

Nowy harness zaatakował jedenaście inwariantów:

- publiczny i prywatny konstruktor;
- forged capability;
- próbę włączenia przez ENV;
- zmianę resolvera po preflight;
- pusty i częściowo prywatny wynik DNS;
- redirect z nowym hostem;
- podmieniony wybrany adres;
- próbę ponownej resolucji w realnym transporcie;
- wydanie capability poza oknem `RESERVED`.

Wynik: `13/13` ataków odpartych. Stary harness E2-B nadal przechodzi `13/13`. Cztery jawne okna awarii lifecycle przeszły `4/4`. Pełna suita ma `1572/1572`, a cztery partycje exact-once dały `378+389+394+411`.

Wszystko odbyło się na fake resolverach, fake transportach, fake callerach i tymczasowych bazach. Produkcyjna baza pozostała bajt w bajt taka sama: schema `0014`, 14 migracji, SHA `9906AF…060836`, `364544 B`.

## Co nadal pozostaje zamknięte

Nie było realnego DNS, socketu, HTTP, Fetch, API, providera, browsera, publikacji ani kosztu. Nie migrowano produkcji. Globalny gate pozostaje domyślnie `false`.

`E2B-F-01`, `E2B-F-02` i `E2B-F-03` są technicznie zamknięte w zmergowanym E2-C. Realny transport jest chroniony w granicach wspieranego runtime i composition roots; nie jest to obietnica ochrony przed autorem dowolnego Pythona. Pozostałe P2 i obserwacje nie zostały naprawione.

Przed pierwszym realnym pobraniem nadal potrzebne są osobna decyzja właściciela, snapshot i kontrolowana migracja produkcji `0014→0018`, jawne globalne włączenie zdolności oraz nowa jednorazowa zgoda na dokładny job. Ewentualna operacja ma status `NOT STARTED`; jeśli zostanie osobno autoryzowana, może obejmować dokładnie jeden minimalny realny controlled Fetch bez auto-retry, z pełnym audytem. Formalne zamknięcie E2-C nie udziela żadnej z tych zgód i nie zamyka całego Etapu 2.

**Zdanie do artykułu:** „Nie wystarczy sprawdzić, dokąd prowadzi nazwa. Bezpieczeństwo zaczyna się wtedy, gdy przewód prowadzi dokładnie do adresu, który sprawdziłeś.”
