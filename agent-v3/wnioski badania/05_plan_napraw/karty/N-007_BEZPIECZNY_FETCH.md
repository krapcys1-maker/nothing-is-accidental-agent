# N-007 — bezpieczny fetch i dokładne pochodzenie URL

## Metryka

- **Ustalenia:** A-033, A-034, A-054, A-085
- **Status:** FIXED_OFFLINE; LIVE_CONTRACT_OPEN
- **Start:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** transport researchu, discovery, korpus Federal Register,
  przeglądarkowy fallback, schemat źródeł, testy i dokumentacja
- **V2:** wyłącznie odczyt; zakaz zapisu

## Model zagrożeń

URL zwracany przez model lub zewnętrzne API jest niezaufany. Atak lub błąd może
wykorzystać:

- literalny adres prywatny, loopback, link-local, multicast albo metadata;
- nazwę DNS rozwiązującą się do niedozwolonego albo mieszanego zestawu IP;
- zmianę wyniku DNS między kontrolą a połączeniem;
- publiczny URL przekierowujący do celu prywatnego;
- poświadczenia w URL, niestandardowy port albo schemat inny niż HTTP(S);
- wielką lub skompresowaną odpowiedź materializowaną przed kontrolą;
- PDF o nadmiernej liczbie stron/tekstu;
- zmyśloną ścieżkę w prawdziwej domenie, potwierdzoną jedynie zgodnością hosta;
- fallback przeglądarkowy, który omija kontrolę klienta HTTP.

## Hipoteza

Jeżeli każdy niezaufany URL przejdzie jedną walidację strukturalną, wszystkie
jego adresy DNS będą publiczne i zostaną przypięte do połączenia, każdy redirect
powtórzy pełną kontrolę, a zdekodowany strumień zostanie przerwany na twardym
limicie, to model nie skieruje fetchu do zasobu prywatnego ani nie wymusi
nieograniczonej materializacji odpowiedzi.

Jeżeli discovery porównuje znormalizowany pełny URL z dokładnymi wynikami
wyszukiwarki, prawdziwy host z fałszywą ścieżką nie przejdzie pierwszej bramki.

Kontrdowodem jest jakiekolwiek wywołanie transportu dla celu niedozwolonego,
połączenie z IP innym niż przypięte, przejście redirectu bez ponownej walidacji,
odczyt ponad limit albo przyjęcie innej ścieżki na zgodnym hoście.

## Projektowany kontrakt

1. Dozwolone są tylko `http` i `https`, standardowe porty, bez userinfo.
2. Wszystkie rozwiązane IP muszą być publicznym unicastem: samo
   `ipaddress.is_global` nie wystarcza, ponieważ dopuszcza multicast.
3. Transport nie wykonuje drugiego DNS; łączy się wyłącznie z wcześniej
   zatwierdzonym literalnym IP, zachowując hostname dla TLS/SNI.
4. Proxy środowiskowe są wyłączone dla niezaufanego fetchu.
5. Redirecty są ręczne, ograniczone liczbowo i walidowane od zera; downgrade
   HTTPS→HTTP jest zabroniony.
6. Klient wymusza `Accept-Encoding: identity` i odrzuca skompresowaną
   odpowiedź. Nieskompresowany strumień ma twardy limit niezależny od
   `Content-Length`.
7. HTML/tekst, JSON i PDF mają osobne limity; PDF zachowuje limit stron i
   otrzymuje limit wydobytego tekstu.
8. Baza zapisuje URL żądany, finalny, łańcuch redirectów i przypięte IP.
9. Browser fallback researchu pozostaje wyłączony, dopóki nie istnieje
   porównywalnie przypięty resolver dla całego drzewa żądań strony.
10. Discovery wymaga dokładnego URL z wyników, nie tylko zgodnego hosta.

## Plan testów kontrdowodu

- odrzucenie loopback IPv4/IPv6, private, link-local, multicast, unspecified,
  adresu metadata i mieszanego DNS;
- odrzucenie userinfo, błędnego schematu, portu i nadmiernego URL;
- publiczny DNS przechodzi;
- backend łączy się z przypiętym IP nawet po zmianie odpowiedzi resolvera;
- redirect publiczny→prywatny nie uruchamia drugiego transportu;
- redirect publiczny→publiczny jest ponownie rozwiązywany i zapisany w historii;
- HTTPS→HTTP, pętla i nadmiar redirectów są odrzucone;
- `Content-Length` ponad limit i strumień przekraczający limit kończą się
  `ResponseTooLarge`;
- limity typów treści są różne;
- discovery odrzuca inną ścieżkę w tym samym hoście;
- browser fallback jest fail-closed;
- finalny URL i IP trafiają do rekordu źródła;
- pełna regresja offline pozostaje zielona.

## Rollback

Można odłączyć nowy adapter od ścieżki fetch, lecz nie należy usuwać kolumn
pochodzenia ze schematu ani historii testów. Powrót do automatycznych redirectów
lub nieprzypiętego DNS wymaga nowego jawnego modelu zagrożeń, nie cichego
cofnięcia.

## Odciski przed zmianą

- `stages.py`: `cb2bce3d96df5f3658a0a1bca263400a8b12e7589612c38832b82cbc52e807e5`;
- `browser.py`: `8ba79d26fa199605e1fe682827d049beea6c160a4ebe409343d36594e47f5986`;
- `config.py`: `c9c5f5c7c6d8f0a25420d914d0d834bb6398738c4f42c7fa07e7f4d567decc4f`;
- `db.py`: `b648d129f156ca20065867cfd381dac4b2be32e7405c2d60177bcf20cf81ccb1`;
- `pomiary/korpus_fedreg.py`: `e19995f7c9f94f504729978cf4b41415564a0f246602cd49d2d059be810a0bdb`;
- `requirements.txt`: `080dd016ba207a97554e44c3b9dd117b781692a7cf15e6bdcc8a456fbed9d47b`.

## Dowody po zmianie

- `test_safe_fetch.py`: 19/19 PASS. Pokrycie obejmuje składnię URL,
  IPv4/IPv6, mieszany DNS, literalne przypięcie połączenia, publiczne i prywatne
  redirecty, downgrade, limit redirectów, nagłówek i rzeczywisty strumień,
  odmowę kompresji, exact URL, zapis pochodzenia, browser fail-closed, ponowny
  DNS tego samego hosta oraz limity PDF.
- `test_pobieranie.py`: 16/16 PASS. Żadna ścieżka fetchu nie tworzy surowego
  klienta ani automatycznych redirectów; research browser nie nawiguje.
- Testy sąsiednie po integracji: safe fetch, izolacja prototypu, ledger i
  OperationalDay uzyskały łącznie 60/60 PASS w ówczesnym zestawie.
- Finalna bezpieczna regresja: 39/39 plików PASS w projektowym `.venv` z UTF-8.
  Wyłączono wyłącznie platformowy `test_czas.py` i osobny katalog płatny.
- Nieudane próby pozostają w rejestrze: 13/15 po błędnym założeniu o
  `is_global`; 15/17 po wadzie fixture'u gzip; 25/40 po omyłkowym systemowym
  Pythonie bez UTF-8/zależności i z testem platformowym.
- Kontrola po zielonej regresji wykryła A-085: historia IP nadpisywała
  wcześniejsze rozwiązanie tego samego hosta. Agregacja i test ponownego DNS
  zachowują teraz wszystkie zatwierdzone piny.
- Kompilacja zmienionych modułów i testu: PASS.
- Kontrola integralności: 38 dokumentów, 0 brakujących linków, 85 ciągłych ID,
  `git diff --check` exit 0, katalog danych V3 czysty i stan V2 zgodny z punktem
  wejścia.
- Koszt online: 0.00 USD. Sieć, modele, przeglądarka, mutacje i deployment:
  nieuruchomione.

## Odciski po zmianie

- `safe_fetch.py`: `db3565a4e2d4082df4c344e39a5ead5f7409435ea589b34a6716a5822dd6f6eb`;
- `stages.py`: `6d2233cd2f32603768df70d5682127a022dec3abb542a6deeb88db4e977472af`;
- `browser.py`: `aca904294558676f57a76e69d627395b1017201144a5617deca65e2aa2843177`;
- `config.py`: `d1fab9bbfd0216eb7046b7aa0bfd4d1bdb38a741c84a657f6b63b407e8226dcd`;
- `db.py`: `51dfe30016892bd5d90e2ed3c81d5997f4e5682e7fbb321c4e45929c7667b8fd`;
- `pomiary/korpus_fedreg.py`: `9ffb07d9e7a530bd808ffd061fa2007a1a736550af29691b3a955528ed8af0bd`;
- `requirements.txt`: `d02b31985b89abf54d679e70e68c163b0609d5205ae52ae99d1686e1896369b8`;
- `tests/test_safe_fetch.py`: `df475065a6804fe4cb41b3e7eda262f07acb21ff89a62fd27d9161467a79278f`;
- `tests/test_pobieranie.py`: `47ce472649484fb242abbea38f3d4aba75bfd6e2d76382d0e95b1881e07b6537`.

## Ograniczenia

- Test offline nie dowodzi prawdziwego handshake TLS/SNI ani działania na
  docelowym resolverze.
- Pinning używa prywatnego pola `_pool` HTTPX; wersje są przypięte i każda
  aktualizacja wymaga testu kontraktu.
- Browser fallback jest wyłączony, więc strony wymagające JavaScript mogą
  zmniejszyć korpus zamiast przejść słabszą drogą.
- Limity pypdf redukują ryzyko zasobowe, ale nie dowodzą odporności na każdy
  filtr i błąd parsera; docelowo PDF wymaga osobnej izolacji procesu.
- Exact URL jest fail-closed i może odrzucać legalne odpowiedniki różniące się
  parametrami lub kanonikalizacją.
- N-007 nie tworzy jeszcze łańcucha fragment–twierdzenie–zdanie.

Pełny opis eksperymentu:
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-004_BEZPIECZNY_FETCH.md`.
