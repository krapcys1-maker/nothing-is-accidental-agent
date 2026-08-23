# Nothing Is Accidental — agent

Autonomiczny agent prowadzący anglojęzycznego Substacka. Sam wymyśla tematy,
szuka źródeł, pisze artykuły, wystawia notki, komentuje u innych i publikuje —
bez pytania człowieka o zgodę na żadnym etapie.

Repozytorium jest publiczne, bo cała wartość tego projektu siedzi w **decyzjach
i w tym, dlaczego zapadły**, a nie w kodzie. Kod jest prosty. Trudne było
ustalenie, czego autonomiczny system nie może robić, żeby nie wyglądał jak
automat i nie zaczął produkować treści, których nikt nie chce czytać.

> **Uwaga:** to nie jest produkt do pobrania i uruchomienia. Nazwa publikacji
> jest wpisana w prompty, korpus stylu jest przypięty hashem i to on jest głosem
> konta, a instalacja wymaga ręcznego zalogowania się do Substacka przez pulpit
> zdalny. Patrz [Czy da się tego użyć u siebie](#czy-da-się-tego-użyć-u-siebie).

---

## Co tu jest

| | |
|---|---|
| kod agenta | `agent-v2/` — 11 plików `.py`, 11 231 wierszy |
| testy | 43 zestawy, 1128 sprawdzeń, żaden nie woła płatnego modelu ani nie otwiera przeglądarki |
| prompty | 25 plików w `agent-v2/prompts/` |
| **dokumentacja odtworzeniowa** | [`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md`](agent-v2/JAK_ZBUDOWANY_JEST_BOT.md) — 10 535 wierszy |
| stary agent, zamrożony | `archiwum/` — patrz [`KTORY_JEST_KTORY.md`](KTORY_JEST_KTORY.md) |

**Zacznij od dokumentacji odtworzeniowej.** Opisuje cały system na tyle
dokładnie, żeby dało się go odbudować od zera: wszystkie etapy, wszystkie
prompty w całości, wszystkie stałe konfiguracji z uzasadnieniami i kluczowy kod
dosłownie. Części mechaniczne są **generowane** przy każdym składaniu przez
`ast` — test pilnuje, żeby przebudowa niczego nie zmieniała, czyli żeby dokument
nie mógł rozjechać się z kodem.

---

## Zasady, z których wynika reszta

Te cztery decyzje tłumaczą większość kodu i prawie każdy dziwny wybór.

**Model obserwuje, kod rozstrzyga.** Oceny liczbowe modelu degenerują się do
stałej. Zmierzone trzy razy niezależnie: samooceny zawsze 1,0, liczba wątków
zawsze sześć, znane teksty zawsze trzy. Model dostaje więc pytania o **cytaty
i fakty**, a progi, liczenie i sortowanie robi kod. Jedyny sygnał odporny na
wyrównanie to **wymuszony ranking** — listy bezwzględne da się wyrównać,
porównania nie.

**Nic nie blokuje artykułu.** Bramki oddają uwagi, nie werdykty. Odsiew, który
nie może odrzucić, nie jest odsiewem — ale odsiew, który zabija opłacony
przebieg, jest gorszy. Skoro research został opłacony, artykuł ma powstać,
a zastrzeżenia idą do pliku obok.

**Zakazy zostawiają przestrzeń, nakazy stają się podpisem.** Reguła nakazująca
pozycję („postaw to w trzecim akapicie") po dziesięciu tekstach sama zamienia
się w rozpoznawalny wzorzec. Dlatego prompty mówią, czego **nie** robić,
a kształt każdego artykułu jest losowany osobno.

**Stała liczba dziennie wygląda jak robot.** Człowiek nie ma normy: raz
przeczyta pół kanału, raz nic. Wolumeny są losowane z widełek, raz na dobę,
z ziarnem wyprowadzonym z daty — więc wszystkie przebiegi doby liczą ten sam
budżet, a kolejne dni różny.

---

## Jak to działa

Dwie ścieżki, jeden proces, jedno polecenie.

**Ścieżka dnia** (`--dzien`) — osiem bloków po kolei: odpowiedzi, notki,
obserwowanie, subskrypcje, komentarze, dyskusje, polubienia, restacki, kopia
listy subskrybentów. Każdy blok osobno: padnięte komentarze nie zabierają ze
sobą notek.

**Ścieżka artykułu** — dziesięć etapów: skaut tematów, odsiew wykonalności,
dyskoveria źródeł, pobieranie, klasyfikacja, synteza, decyzja o pisaniu, pisarz,
bramki, recenzja, obserwacja formy, grafika, publikacja.

Cztery tabele (`runs`, `calls`, `articles`, `sources`), jedna warstwa dostępu do
modeli (`llm.py`), zero migracji, zero kolejek. Zmiana schematu to nowa kolumna
z wartością domyślną, nigdy przepisywanie danych.

---

## Stan na dziś

Uczciwie, bo to jest bardziej użyteczne niż lista funkcji.

**Działa:** publikuje artykuły z okładkami, wystawia notki, komentuje u innych,
odpowiada pod własnymi tekstami, polubia, podaje dalej. 37 przebiegów,
718 wywołań modelu, 12,50 USD łącznie.

**Nie działa albo działa słabo:**

- wolumeny na **55–66% zadeklarowanych**, restacki na 48%
- **obserwacje na zerze** — dla hostów `.substack.com` wyliczamy uchwyt
  publikacji, a szukamy przycisku „Follow", który mają tylko profile osób
- system **nie uczy się z własnych wyników** — w dzienniku leży 71 zapisanych
  reakcji na nasze treści i nie czyta ich ani jedna linia kodu podejmująca
  decyzje

Pomiar tego wszystkiego powstał **23 sierpnia 2026** i to jest data, od której
wiadomo cokolwiek. Wcześniej licznik działań żył w pamięci jednego przebiegu,
drukował się na końcu i ginął razem z nim — więc na pytanie „czy agent w ogóle
komentuje" nie było odpowiedzi.

---

## Uruchomienie

```bash
python agent-v2/run.py --dzien          # dzień pracy konta, BEZ publikowania
python agent-v2/run.py --dzien --wyslij # to samo, na żywo
python agent-v2/run.py                  # jeden artykuł do szuflady
python agent-v2/alarm.py                # kontrola zdrowia i licznik wolumenów
```

Domyślnie **nic nie wychodzi na zewnątrz**. Publikuje wyłącznie `--wyslij`.
Jeśli obok `config.py` leży plik `TO_JEST_KOPIA_TESTOWA`, `--wyslij` kończy się
odmową — kopia testowa nie ma prawa nic opublikować, nigdy.

Testy:

```bash
for f in agent-v2/tests/test_*.py; do python "$f"; done
```

---

## Czy da się tego użyć u siebie

Dziś nie, i nie jest to kwestia spakowania.

**Nazwa publikacji jest wpisana w dziesięć plików**, w tym w siedem promptów.
Skaut zaczyna się od zdania o tym, czym jest to konkretne konto.

**Korpus stylu jest głosem.** Jeden plik, 57 KB, przypięty hashem — loader
odmawia pracy, jeśli ktoś go podmieni. Oddanie go znaczyłoby tysiąc kont
brzmiących identycznie; nieoddanie znaczy, że bot nie ruszy po instalacji.
Sensowna wersja „dla ludzi" musi mieć odpowiedź na pytanie, skąd bierze się
**twój** głos, a to jest projekt, nie plik README.

**Instalacja nie jest „dodaj klucze API".** Agent podłącza się do Chrome'a,
którego właściciel uruchomił i **zalogował ręcznie** przez pulpit zdalny.
Playwright startujący przeglądarkę z flagami automatyzacji wpada w reCAPTCHA,
więc tej drogi nie ma.

---

## Granice, których ten agent nie przekracza

Zapisane, bo w projekcie o automatyzacji cudzej platformy to jest ważniejsze
od funkcji.

**Konto nie ujawnia z siebie, że jest prowadzone przez AI, ale nigdy nie kłamie
zapytane wprost.** Zakazana jest impersonacja i techniczne ukrywanie się przed
wykryciem.

**Hosty odmawiające automatycznego czytania są respektowane.** eCFR blokuje
boty — nie obchodzimy tego. Adresy, które nigdy nie oddały treści, trafiają na
listę pomijanych.

**Nie zgadujemy nieudokumentowanych adresów API.** Czytanie własnego panelu
własną sesją to co innego — właściciel patrzy na własne konto — i tą drogą
robi się kopia listy subskrybentów. Sondowanie cudzych endpointów to scraping
i tego nie ma.

**Sekrety nie wchodzą do repozytorium.** `.env` i katalog `data/` są poza gitem;
kopie listy subskrybentów zapisują się z prawami `0600`, bo zawierają cudze
adresy e-mail.

---

## Historia i archiwum

Tagi w repozytorium są punktami powrotu, nie ozdobą:

| tag | co to |
|---|---|
| `v1`, `v2` | wersje agenta |
| `archive/stary-agent-main` | poprzedni agent przed zamrożeniem |
| `prototyp-gpt-2026-08` | prototyp napisany przez inny model — 31 000 wierszy, nigdy nie napisał artykułu z prawdziwego tematu; wnioski w [`agent-v2/dokumentacja-zrodla/AUDYT_2026-08-23.md`](agent-v2/dokumentacja-zrodla/AUDYT_2026-08-23.md) |
| `archive/*` | gałęzie zachowane przed sprzątaniem — patrz [`docs/GALEZIE_USUNIETE_2026-08-23.md`](docs/GALEZIE_USUNIETE_2026-08-23.md) |
