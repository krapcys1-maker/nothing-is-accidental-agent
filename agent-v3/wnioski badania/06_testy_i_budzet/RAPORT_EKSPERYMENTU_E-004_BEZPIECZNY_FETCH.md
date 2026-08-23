# E-004 — bezpieczny fetch, dokładny dokument i ograniczenie zasobów

## Abstrakt

Eksperyment badał, czy niezaufany URL pochodzący z modelu albo publicznego API
może skierować Agent V3 do sieci prywatnej, zmienić cel po kontroli DNS, ominąć
walidację przez redirect, podstawić zmyśloną ścieżkę w prawdziwej domenie albo
wymusić nieograniczone pobranie i parsowanie dokumentu. Stan bazowy nie
zapewniał tych własności: sprawdzał głównie host, używał automatycznych
redirectów, nie przypinał wyniku DNS, materializował całą odpowiedź i posiadał
przeglądarkowy fallback omijający transport HTTP.

Dodano jeden adapter `safe_fetch`, walidację publicznego unicastu, przypięcie
każdego połączenia do zatwierdzonego literalnego IP, ręczną kontrolę każdego
redirectu, rozdzielne limity typów treści, odmowę kompresji transportowej,
limity parsera PDF i trwały zapis pochodzenia. Discovery wymaga teraz dokładnego
URL wyniku wyszukiwania. Fallback Chromium został wyłączony fail-closed, gdyż
nie zapewnia równoważnego pinningu DNS dla nawigacji i subresource'ów.

Finalny test celu uzyskał 19/19, test granicy transportów 16/16, a pełna
bezpieczna regresja 39/39 plików PASS. Wynik ma status `FIXED_OFFLINE;
LIVE_CONTRACT_OPEN`. Nie wykonano sieci, modeli, przeglądarki, publikacji ani
wdrożenia. Koszt online wyniósł 0.00 USD.

## 1. Pytania badawcze

**RQ1.** Czy jakikolwiek literalny albo rozwiązany adres niepubliczny może
doprowadzić do próby połączenia?

**RQ2.** Czy adres użyty przez gniazdo jest dokładnie adresem zatwierdzonym
przez walidator, także gdy DNS zmieni odpowiedź między kontrolą i transportem?

**RQ3.** Czy każdy redirect przechodzi od początku kontrolę składni, DNS, IP i
polityki schematu?

**RQ4.** Czy kandydat discovery odpowiada dokładnemu dokumentowi zwróconemu
przez wyszukiwarkę, a nie tylko tej samej domenie?

**RQ5.** Czy rozmiar dokumentu jest ograniczony przed materializacją i podczas
strumieniowania, a PDF również podczas dekompresji i ekstrakcji tekstu?

## 2. Ustalenia bazowe

- **A-033:** URL od modelu mógł wskazać prywatny, lokalny lub metadata endpoint;
  automatyczny redirect nie był ponownie walidowany.
- **A-034:** discovery potwierdzało zgodność hosta, nie dokładnej ścieżki.
- **A-054:** odpowiedź była materializowana bez twardego limitu bajtów, a PDF
  nie miał pełnego limitu zasobów parsera.
- browserowy fallback wykonywał własny DNS i pobierał drzewo strony poza
  kontrolą zwykłego klienta HTTP.
- baza przechowywała pierwotny URL, ale nie finalny dokument, redirecty i IP.

W trakcie kontroli po pierwszym zielonym przebiegu wykryto **A-085**: projekcja
IP do zapisu używała słownika `host -> IP` i nadpisywała wcześniejsze piny, gdy
ten sam host pojawił się ponownie w łańcuchu. Nie osłabiało to blokady SSRF, ale
czyniło ślad pochodzenia niepełnym. Zmieniono projekcję na uporządkowaną sumę
unikalnych IP hosta i dodano kontrdowód ponownego rozwiązania tego samego hosta.

## 3. Model zagrożeń

Za niezaufane uznano URL-e zwrócone przez model, metadane publicznego API,
nagłówki `Location` oraz odpowiedzi serwera. Badany przeciwnik może:

- podać IPv4/IPv6 loopback, private, link-local, unspecified, reserved,
  multicast albo adres usługi metadata;
- podać nazwę o mieszanym publicznym i prywatnym zestawie A/AAAA;
- zmienić DNS po walidacji;
- skierować publiczny dokument redirectem do zasobu prywatnego;
- użyć userinfo, innego schematu, niestandardowego portu, backslasha lub znaku
  kontrolnego do zmiany interpretacji URL;
- zwrócić fałszywy albo brakujący `Content-Length`;
- mimo `Accept-Encoding: identity` zwrócić kompresję;
- podać PDF mały na wejściu, ale kosztowny po rozpakowaniu;
- wykorzystać Chromium jako słabiej kontrolowany transport zastępczy.

Poza zakresem pozostają: złośliwy publiczny serwer zdolny atakować bibliotekę
TLS/HTTP, exploit parsera PDF niewynikający tylko z rozmiaru, kontrola pasma na
poziomie systemu operacyjnego oraz prawdziwa zmiana zachowania DNS/TLS w sieci.

## 4. Hipotezy i kryteria falsyfikacji

**H1 — publiczny unicast.** Każdy element rozwiązania DNS musi być dozwolonym
publicznym unicastem. Hipotezę obala utworzenie transportu po zobaczeniu choć
jednego niedozwolonego IP.

**H2 — pinning.** Backend gniazda otrzymuje wyłącznie zatwierdzone literalne IP,
podczas gdy hostname pozostaje nazwą pochodzenia dla HTTP i TLS/SNI. Hipotezę
obala przekazanie nazwy domenowej do `socket.create_connection`.

**H3 — redirect jako nowe wejście.** Każdy kolejny cel jest normalizowany,
rozwiązywany i przypinany ponownie. Hipotezę obala drugie żądanie do celu
prywatnego albo downgrade HTTPS→HTTP.

**H4 — dokładny dokument.** Znormalizowany URL kandydata musi być równy
znormalizowanemu URL-owi rzeczywistego wyniku wyszukiwania. Hipotezę obala
przyjęcie innej ścieżki na tym samym hoście.

**H5 — ograniczone zasoby.** Odpowiedź nieskompresowana nie może przekroczyć
limitu danego typu ani według nagłówka, ani według policzonego strumienia. PDF
ma dodatkowy limit rozpakowanego strumienia, stron i znaków. Hipotezę obala
odczyt kolejnego fragmentu po przekroczeniu limitu albo brak przywrócenia
globalnego limitu parsera.

**H6 — jedna granica.** Żadna modelozależna ścieżka researchu nie może ominąć
adaptera. Hipotezę obala surowy klient HTTP lub `page.goto` w fallbacku.

## 5. Projekt implementacji

### 5.1. Normalizacja i DNS

`normalize_url()` dopuszcza tylko HTTP(S), standardowy port i host bez userinfo.
Usuwa fragment, normalizuje IDNA i odrzuca znaki kontrolne, backslash oraz
nadmierną długość. Literalne IP jest sprawdzane natychmiast.

`validate_url()` pobiera wszystkie A/AAAA. Cały zestaw jest odrzucany, jeżeli
choć jeden adres nie jest publicznym unicastem. Sama własność
`ipaddress.is_global` okazała się niewystarczająca, ponieważ w Pythonie może
być prawdziwa dla multicastu; implementacja wyklucza dodatkowo multicast,
private, loopback, link-local, reserved i unspecified.

### 5.2. Połączenie przypięte do IP

`PinnedDNSBackend` zastępuje rozwiązywanie nazwy na granicy `httpcore`.
Warstwa HTTP nadal widzi oryginalny origin, ale `connect_tcp()` wybiera tylko IP
z zatwierdzonej listy. Brak przypięcia i socket Unix kończą się odmową.

Adapter wyłącza proxy środowiskowe, HTTP/2, retry i współdzielenie keep-alive
między celami. Integracja opiera się na prywatnym polu `_pool` HTTPX, dlatego
wersje `httpx==0.28.1` i `httpcore==1.0.9` są jawnie przypięte.

### 5.3. Maszyna redirectu

Redirecty nie są wykonywane automatycznie. Dla każdego hopu adapter:

1. normalizuje aktualny URL;
2. rozwiązuje komplet adresów;
3. tworzy nowy transport z pinami tylko tego hosta;
4. wykonuje jedno żądanie bez `follow_redirects`;
5. zapisuje URL, host, IP i status;
6. dla `Location` wylicza następny URL i wraca do kroku 1.

Liczba redirectów ma twardy sufit. Początkowe HTTPS nie może przejść do HTTP.

### 5.4. Limity odpowiedzi i PDF

Klient wysyła `Accept-Encoding: identity`. Odpowiedź z innym
`Content-Encoding` jest odrzucana, ponieważ automatyczna dekompresja mogłaby
utworzyć wielki fragment przed policzeniem bajtów przez adapter. Limit jest
sprawdzany niezależnie wobec `Content-Length` i sumy fragmentów `iter_raw()`.

Konfiguracja rozdziela limity JSON, HTML/tekstu i PDF. Po pobraniu HTML
ekstrakcja tekstu ma drugi limit znaków. PDF zachowuje limit 40 stron, limit
tekstu oraz czasowo obniża `pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH`; wartość
globalna jest przywracana w `finally`.

### 5.5. Pochodzenie i exact binding

Tabela `sources` otrzymała `requested_url`, `final_url`,
`redirect_chain_json` i `resolved_ips_json`. Do dalszych etapów trafia finalny
URL dokumentu, natomiast pierwotny kandydat pozostaje zachowany. Kolejne piny
tego samego hosta są agregowane bez utraty wcześniejszych wartości.

Discovery buduje zbiór dokładnych, bezpiecznie znormalizowanych wyników
zebranych przez narzędzie wyszukiwania dostawcy. Inna ścieżka na zgodnym hoście
jest odrzucana.

### 5.6. Zamknięcie fallbacku

`stages._dobierz_przegladarka()` zwraca pusty wynik, a `browser.read_pages()`
jawnie odmawia. Zmniejsza to recall stron wymagających JavaScript, ale zachowuje
jedną granicę bezpieczeństwa. Przywrócenie fallbacku wymaga kontrolowanego DNS,
redirectów i subresource'ów całej nawigacji, nie samego pre-checku głównego URL.

## 6. Metoda eksperymentu

Testy używały `httpx.MockTransport`, własnego strumienia bajtów, atrap resolvera
i backendu gniazda, tymczasowych baz SQLite oraz podmienionego lokalnie parsera
PDF. Nie wykonywały DNS, TCP, TLS ani połączeń HTTP. Każdy niedozwolony cel miał
być zatrzymany przed utworzeniem kolejnego transportu.

Bezpieczna regresja została uruchomiona projektowym
`.venv/Scripts/python.exe` z `PYTHONIOENCODING=utf-8`. Obejmuje 39 plików
`tests/test_*.py` z wyłączeniem `test_czas.py`, który bada sygnały Linux/systemd
przy celowo unieruchomionych usługach. Osobny katalog `tests/platne` nie został
uruchomiony.

## 7. Chronologia prób

### Próba 1 — pierwszy kontrdowód URL i fallbacku

Pierwszy zestaw uzyskał 13/15. Dwie porażki były informacyjne:

- założenie, że `is_global` wystarcza, przepuściło `224.0.0.1`;
- statyczny test znalazł napis `page.goto` w docstringu funkcji odmowy, nie w
  jej ciele wykonywalnym.

Dodano jawne wyłączenie multicastu i zawężono test do ciała wykonywalnego.
Powtórzenie: 15/15 PASS.

### Próba 2 — integracja i pierwsza szeroka regresja

Po rozszerzeniu kontraktu test celu miał 16 przypadków. Razem z izolacją,
ledgerem i OperationalDay zestaw sąsiedni uzyskał 60/60; ówczesny test granicy
pobierania 15/15. Pierwsza pełna regresja po integracji: 39/39 plików PASS.

### Próba 3 — kompresja odpowiedzi

Pierwsza próba testu kompresji uzyskała 15/17 i dwa błędy fixture'u.
`httpx.Response(content=...)` próbował zdekodować fałszywy gzip jeszcze przed
adapterem, a ponownie użyta odpowiedź była już zużytym strumieniem. Zastąpiono
fixture własnym `httpx.SyncByteStream`. Powtórzenie: 17/17; granica pobierania
15/15 i kompilacja PASS.

### Próba 4 — błędna komenda pełnego korpusu

Omyłkowo uruchomiono wszystkie 40 zwykłych testów systemowym Pythonem bez UTF-8
i bez projektowych zależności. Wynik 25/40 plików PASS nie był testem N-007:
porażki obejmowały CP1252, brak `trafilatura` i platformowy `test_czas.py`.
Przebieg zachowano jako wynik negatywny. Poprawna komenda w `.venv`, z UTF-8 i
jawnym wyłączeniem testu platformowego, dała 39/39 PASS.

### Próba 5 — kontrola po zielonej regresji

Przegląd historii pinów ujawnił nadpisanie wcześniejszego IP tego samego hosta
(A-085). Dodano agregację, test ponownego DNS tego samego hosta oraz bezpośredni
test limitu dekompresji/tekstu PDF i przywrócenia globalnej konfiguracji.
Finalnie: test celu 19/19, granica pobierania 16/16, kompilacja PASS i ponowna
regresja 39/39 plików PASS.

## 8. Wyniki

| Własność | Kontrdowód | Wynik offline |
|---|---|---|
| składnia URL | schemat, userinfo, port, control, backslash, długość | odrzucone |
| adresy | IPv4/IPv6 local/private/link-local/multicast/metadata | odrzucone |
| mieszany DNS | publiczne + loopback | cały cel odrzucony |
| pinning | fake backend zapisuje argument `connect_tcp` | literalne IP |
| redirect prywatny | publiczny → metadata | brak drugiego transportu |
| redirect publiczny | dwa hosty | ponowny DNS i pełna historia |
| ponowny host | dwa rozwiązania jednego hosta | oba piny zachowane |
| polityka TLS | HTTPS → HTTP | odrzucone |
| rozmiar | fałszywy nagłówek i rosnący stream | oba zatrzymane |
| kompresja | gzip mimo żądania identity | odrzucone przed odczytem |
| PDF | limit streamu, stron/tekstu i restore | zgodne |
| exact URL | prawdziwa i zmyślona ścieżka jednego hosta | tylko prawdziwa |
| fallback | brak bezpiecznego browser DNS | fail-closed |
| regresja | 39 bezpiecznych plików | 39/39 PASS |

## 9. Zagrożenia trafności i ograniczenia

- Atrapowy backend dowodzi przekazania literalnego IP, lecz nie dowodzi
  prawdziwego handshake TLS, SNI ani zgodności na systemie docelowym.
- Implementacja zależy od prywatnego `_pool` HTTPX. Pin wersji ogranicza dryf,
  ale każda aktualizacja biblioteki wymaga testu kontraktowego.
- Odrzucenie kompresji i browser fallbacku może obniżyć recall i zwiększyć
  transfer. Jest to świadomy koszt fail-closed.
- Limit ZLIB w pypdf nie jest dowodem odporności na wszystkie filtry, błędy i
  podatności parsera PDF. Parser nadal powinien docelowo działać w procesie z
  limitem pamięci i czasu.
- Tymczasowa zmiana globalnego limitu pypdf jest przywracana, ale przy przyszłym
  wielowątkowym parsowaniu wymaga osobnej izolacji procesu lub blokady.
- Exact URL może odrzucić legalne odpowiedniki różniące się parametrami
  śledzącymi albo kanonikalizacją ścieżki. Błąd jest w stronę odmowy.
- Nie istnieje jeszcze wersjonowany łańcuch fragment–twierdzenie–zdanie;
  N-007 domyka transport i dokument, nie A-015/A-016/A-035/A-039.
- Nie wykonano testu live read-only. Status nie dowodzi dostępności publicznych
  serwisów ani poprawności na prawdziwym DNS.

## 10. Odciski artefaktów po zmianie

- `safe_fetch.py`: `db3565a4e2d4082df4c344e39a5ead5f7409435ea589b34a6716a5822dd6f6eb`;
- `stages.py`: `6d2233cd2f32603768df70d5682127a022dec3abb542a6deeb88db4e977472af`;
- `browser.py`: `aca904294558676f57a76e69d627395b1017201144a5617deca65e2aa2843177`;
- `config.py`: `d1fab9bbfd0216eb7046b7aa0bfd4d1bdb38a741c84a657f6b63b407e8226dcd`;
- `db.py`: `51dfe30016892bd5d90e2ed3c81d5997f4e5682e7fbb321c4e45929c7667b8fd`;
- `pomiary/korpus_fedreg.py`: `9ffb07d9e7a530bd808ffd061fa2007a1a736550af29691b3a955528ed8af0bd`;
- `requirements.txt`: `d02b31985b89abf54d679e70e68c163b0609d5205ae52ae99d1686e1896369b8`;
- `tests/test_safe_fetch.py`: `df475065a6804fe4cb41b3e7eda262f07acb21ff89a62fd27d9161467a79278f`;
- `tests/test_pobieranie.py`: `47ce472649484fb242abbea38f3d4aba75bfd6e2d76382d0e95b1881e07b6537`.

## 11. Koszt i efekty zewnętrzne

- Anthropic: 0.00 USD;
- DeepSeek: 0.00 USD;
- GPT/OpenAI: 0.00 USD;
- DNS/HTTP/TLS: brak;
- przeglądarka: brak;
- konta i mutacje zewnętrzne: brak;
- publikacja, wdrożenie i produkcja: brak;
- `agent-v2`: wyłącznie odczyt stanu Git, bez zapisu.

## 12. Wniosek

Dla badanego korpusu offline A-033, A-034, A-054 i A-085 mają kontrdowody.
Model nie wybiera już bezpośrednio celu gniazda, redirect nie omija polityki,
zgodna domena nie zastępuje dokładnego dokumentu, a odpowiedź nie jest
materializowana bez limitu. Najważniejsze niezbadane ryzyko znajduje się teraz
nie w samej decyzji adaptera, lecz w prawdziwym kontrakcie TLS/httpcore i
izolacji parsera PDF. Dlatego uzasadniony status to `FIXED_OFFLINE;
LIVE_CONTRACT_OPEN`, nie gotowość produkcyjna.
