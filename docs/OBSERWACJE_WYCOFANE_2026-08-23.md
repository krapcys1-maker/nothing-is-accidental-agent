# Obserwacje wycofane — Substack zdjął „Follow" ze stron profilowych

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

## Prawdziwa przyczyna

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

## Jak to odkręcić

Jedna stała w `config.py`:

```python
FOLLOW_MIESIECZNIE = (0, 0)   # -> (20, 30), gdy przycisk wróci
```

Blok `obserwuj()` jest nietknięty i nadal umie kliknąć. Test
`test_obserwacje.py` sekcja 6 pilnuje, że jest na miejscu — żeby „wycofane"
nie zamieniło się po cichu w „usunięte".
