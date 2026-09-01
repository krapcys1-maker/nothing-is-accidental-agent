# Błędny wniosek o obserwacjach — 23 sierpnia 2026

> **TEN DOKUMENT OPISUJE POMYŁKĘ.** Zostaje w całości, bo zapis tego, jak
> powstała, jest wart więcej niż sam fakt. Nazwa pliku zmieniona 1 września
> 2026 (było: `OBSERWACJE_WYCOFANE_2026-08-23.md`) — tytuł powtarzał wniosek,
> który okazał się nieprawdziwy. Nikt się na starą nazwę nie powoływał
> (sprawdzone `grep` po całym repozytorium).
>
> **POMIAR BYŁ PRAWDZIWY. WNIOSEK BYŁ FAŁSZYWY.** Na sześciu profilach słowa
> „Follow" naprawdę nie ma w HTML — ta tabela niżej jest poprawna. Ale
> przycisk **jest**: siedzi w menu pod kółkiem „…" obok „Subscribe"
> i „Message", a Substack rysuje to menu **dopiero po kliknięciu**. W HTML
> zamkniętej strony nie ma go i być nie może, więc czytanie HTML-a nie mogło
> tego pytania rozstrzygnąć — ani w jedną, ani w drugą stronę.
>
> **To jest ta lekcja.** Pomiar odpowiada na pytanie, które mu się zadało.
> Zadane brzmiało „czy słowo «Follow» jest w treści strony", a odczytano je
> jako „czy da się kogoś zaobserwować". To dwa różne pytania i różnicy nie
> widać, dopóki się jej nie nazwie. Sprawdzenie kosztowało jedno kliknięcie
> w kółko — czyli mniej niż napisanie tego dokumentu.
>
> **Koszt pomyłki: dziewięć dni bez ani jednej obserwacji** (23 sierpnia —
> 1 września 2026). Najgorsze nie było zero w liczniku, tylko to, że **zero
> miało wyjaśnienie**: `norma.NIEWYKONALNE` tłumaczyło je tym samym
> nieprawdziwym zdaniem, więc przestało wyglądać na problem i nikt nie zapytał
> drugi raz.
>
> **Zmierzone ponownie 1 września 2026**, na żywej sesji, przez OTWARCIE menu
> (bez klikania czegokolwiek w środku): na trzech profilach nieobserwowanych
> menu ma pozycję „Follow", na trzech obserwowanych — „Unfollow". Stan po
> odwieszeniu: `config.FOLLOW_MIESIECZNIE = (30, 44)`, `norma.NIEWYKONALNE`
> puste, droga przez menu w `browser.obserwuj_profil`, cały pomiar spisany
> w `agent-v2/tests/test_obserwowanie_przez_menu.py`.

## Zapis z 23 sierpnia 2026

Poniżej treść z tamtego dnia. Zmieniony jest wyłącznie rozdział „Jak to
odkręcić" — podawał złe liczby i złą instrukcję, a instrukcja czytana po
awarii musi być prawdziwa. Reszta zostaje tak, jak stała.

**Data pomiaru:** 2026-08-23
**Skutek:** `FOLLOW_MIESIECZNIE = (0, 0)`. Blok `obserwuj()` zostaje w kodzie,
ale nie rezerwuje budżetu i nie chodzi.

## Co było widać

Obserwacje wykonywały się **zero razy**, tygodniami, przy budżecie 30–44
miesięcznie. Długo nie było tego widać w ogóle: blok bez śladu w dzienniku
wygląda na blok, który się nie odbywa. Zobaczyliśmy to dopiero wtedy, gdy
nieudane akcje zaczęły zapisywać powód:

```
{'rodzaj': 'obserwacja', 'udane': False, 'komu': 'writersartistsyearbook',
 'powod': 'nie ma przycisku obserwacja u writersartistsyearbook'}
```

## Pierwsza diagnoza — błędna

Twierdziłem, że bierzemy uchwyt **publikacji** zamiast uchwytu **człowieka**:
`uchwyt_publikacji` dla adresów w domenie Substacka robi skrót
`host.split(".")[0]`, więc dla `writersartistsyearbook.substack.com` oddaje
`writersartistsyearbook`. Strona publikacji ma „Subscribe", a „Follow" mają
profile ludzi — brzmiało spójnie i zgadzało się z komentarzem w samym module
(*„OBSERWOWANIE I SUBSKRYPCJA TO DWIE ROZNE RZECZY"*).

Napisałem `uchwyt_autora`, czytający `publishedBylines`. Sprawdzone na żywym
API dla pięciu hostów z historii komentarzy:

| host | uchwyt publikacji | uchwyt autora |
|---|---|---|
| `www.slowboring.com` | halinabennet | halinabennet |
| `ethanding.substack.com` | ethanding | ethanding |
| `www.thebignewsletter.com` | mattstoller | mattstoller |
| `litmagnews.substack.com` | litmagnews | litmagnews |

**Identyczne w każdym przypadku.** Poprawka była bezczynna i została cofnięta.

## Prawdziwa przyczyna [WNIOSEK FAŁSZYWY — patrz nagłówek pliku]

Substack **usunął przycisk „Follow" ze stron profilowych**. Zmierzone na sześciu
profilach — trzech z naszej historii i trzech zupełnie obcych, z którymi nie
łączy nas nic:

| profil | przyciski | „Follow" w HTML |
|---|---|---|
| `@ethanding` | Subscribed, Message | 0 |
| `@litmagnews` | Subscribe, Message | 0 |
| `@writersartistsyearbook` | Pledge, Message | 0 |
| `@shortlivedage` | Subscribe, Message | 0 |
| `@sandeepraiza` | Subscribe, Message | 0 |
| `@omiderfanmanesh` | Subscribe, Message | 0 |

Słowo „Follow" nie występuje w treści tych stron **ani razu** — nie chodzi
o inną rolę elementu czy inną nazwę. Nie ma go również na `/@kto/notes`.

Gdzie przetrwał:

| miejsce | widocznych „Follow" |
|---|---|
| `substack.com/notes` | 20 |
| `substack.com/browse/staff-picks` | 20 |
| strona pojedynczej notki | 20 (w kolumnie obok, nie przy autorze) |

Wszystkie w widgetach **„kogo obserwować"**, czyli w liście podpowiedzi.

## Dlaczego nie przenosimy obserwacji do podpowiedzi

Bo `obserwuj()` broni się przed tym od pierwszego dnia i słusznie:

> Obserwujemy TYLKO tych, u których naprawdę byliśmy — nie z listy podpowiedzi.
> Obserwowanie kogoś, kogo się nie czytało, to zbieranie nazwisk, a nie
> budowanie kręgu.

Klikanie w listę sugestii jest też najbardziej botowatą rzeczą, jaka jest tu
dostępna, a całe konto stoi na tym, żeby nie wyglądać jak bot.

## Dlaczego zero, a nie mała liczba

Właściciel wchodzi teraz w kilkutygodniową obserwację liczników. Rubryka
wiecznie na zerze czyta się jak awaria i kradnie uwagę przy każdym przeglądzie
— a tutaj nie ma czego naprawiać. Zero mówi wprost: **tej zdolności nie mamy.**

Budżetu nie rezerwujemy, dziennika nie zaśmiecamy, licznik pokazuje `realizacja:
brak` zamiast `0%`.

## Czego świadomie NIE zrobiłem

- **Nie zamieniłem obserwacji na subskrypcje.** Subskrypcja ląduje w skrzynce
  właściciela — dlatego jest ich 6–12 miesięcznie, a nie 25. Zamiana jednego
  na drugie zasypałaby skrzynkę i to nie jest moja decyzja.
- **Nie sięgnąłem po wewnętrzne API obserwacji.** Interfejs tej akcji nie
  oferuje; obchodzenie tego to inna kategoria działania niż klikanie w to,
  co widać.

## Jak to odkręcić [POPRAWIONE 2026-09-01 — pierwotna wersja była błędna]

Stało tu, że wystarczy jedna stała:

```python
FOLLOW_MIESIECZNIE = (0, 0)   # -> (20, 30), gdy przycisk wróci
```

**Liczba była nieaktualna, a instrukcja niepełna.** Sprawdzone w historii
(`git log -S`): przed wycofaniem stała naprawdę wynosiła `(20, 30)`
(commit `227c266`, 20 sierpnia; wcześniej `(10, 20)`), więc ta strzałka nie
była zmyślona. Ale przy odwieszeniu 1 września wróciło `(30, 44)` — liczba,
która do tego dnia żyła **wyłącznie w komentarzach i docstringach**
(`browser.py`, `run.py`), nigdy w samej stałej. Nikt tego nie nazwał: powrót
podniósł wolumen o połowę wobec stanu sprzed wycofania.

A stała i tak była za mało. Blok `obserwuj()` faktycznie przetrwał nietknięty,
ale `browser.obserwuj_profil` klikało wtedy przycisk **na wierzchu strony**,
którego tam nie ma. Odwieszenie wymagało trzech rzeczy naraz:

1. `config.FOLLOW_MIESIECZNIE = (30, 44)`,
2. `norma.NIEWYKONALNE = {}` — inaczej licznik dalej tłumaczyłby zero,
3. **nowej drogi w `browser.obserwuj_profil`**: otwarcie menu
   `button[aria-label="Profile actions"]`, odczyt pozycji przez
   `role=menuitem`, porównanie tekstu przez `==` (nie po fragmencie, bo
   „Unfollow" zawiera w sobie „Follow") i kliknięcie wyłącznie pozycji
   z listy `OBSERWUJ_POZYCJE`.

Zdanie „blok `obserwuj()` jest nietknięty i nadal umie kliknąć" było więc
prawdziwe tylko w połowie: blok istniał, ale droga, którą klikał, prowadziła
donikąd.

Nieprawdziwe było też zdanie o teście. Stało tu, że `test_obserwacje.py`
sekcja 6 pilnuje, że blok jest na miejscu — dziś ta sekcja pilnuje czegoś
**odwrotnego**: że widełki wróciły do `(30, 44)`, że `NIEWYKONALNE` jest puste
i że dzień bez obserwacji liczy się jako **0 procent**, a nie jako „brak".
Sprawdzenie samej drogi klikania mieszka w
`agent-v2/tests/test_obserwowanie_przez_menu.py`, a odsiew puli i zapis stanu
„już go obserwujemy" — w `agent-v2/tests/test_pula_obserwacji.py`.
