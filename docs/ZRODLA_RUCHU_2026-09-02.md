# Tabela źródeł ruchu — odczyt z panelu, 2 września 2026

Wykonanie zapytania **8.E** z `docs/ROZSTRZYGNIECIE_2026-09-02.md`. Odczyt na
żywej produkcji, własną sesją, przez Chrome'a chodzącego na serwerze
(`browser.podlacz_sie` → CDP). Kłódka `agent-v2/data/agent.lock` sprawdzona
przed każdym uruchomieniem i za każdym razem wolna. Nic nie kliknięte, nic nie
opublikowane, nic nie zapisane do `agent-v2/data/`. Zero wywołań modelu.

---

## 1. Adres — podejrzany, nie zgadnięty

Reguła z `agent-v2/kopia_subskrybentow.py:27-36` („Nie zgadujemy adresów API")
została dotrzymana. Adres wzięty z podsłuchu ruchu, jaki panel wykonuje sam:
Playwright podpięty do sesji, `page.on("request", …)` filtrujący `/api/`, a
potem zwykłe wejście na `/publish/stats/traffic`. Żaden adres nie był
konstruowany z domysłu; oba niżej pojawiły się w logu żądań strony.

**Panel Stats → Ruch („Top sources"):**

```
GET https://nothingisaccidental.substack.com/api/v1/publication/stats/visitor_sources
    ?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&offset=0&limit=20
    &order_by=views&order_direction=desc
```

**Panel Growth → Visitors (drzewo źródeł z subskrypcjami):**

```
GET https://nothingisaccidental.substack.com/api/v1/publication/stats/growth/sources
    ?order_by=users&order_direction=desc&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
```

Przy okazji w logu były jeszcze (nieużyte tutaj, ale to ten sam panel):
`/api/v1/publication/stats/publication_traffic/30d_views`,
`/api/v1/publication/stats/publication_traffic/timeseries?from=…&to=…&category`,
`/api/v1/publication/stats/growth/events?from_date=…&to_date=…`,
`POST /api/v1/publication/stats/growth/partial-timeseries`.

Adres bazowy to **publikacja** (`nothingisaccidental.substack.com`), nie
`substack.com` — zgodnie z podziałem opisanym w `browser.api_json`
(`browser.py:494-524`). Odczyt idzie wejściem na adres, nie `fetch`-em ze
strony, bo z centrum danych `fetch` wraca 403 (tamże).

---

## 2. Zrzut odpowiedzi — `visitor_sources`, ostatnie 30 dni

Adres wykonany dosłownie:

```
https://nothingisaccidental.substack.com/api/v1/publication/stats/visitor_sources?from_date=2026-08-03&to_date=2026-09-02&offset=0&limit=50&order_by=views&order_direction=desc
```

Odpowiedź w całości, bez skrótów:

```json
{
  "rows": [
    { "source": "direct to app", "source_category": "Direct",   "views": 640, "users": 39, "free_signup": null, "subscribed": null },
    { "source": "substack app",  "source_category": "Substack", "views": 184, "users": 46, "free_signup": null, "subscribed": null },
    { "source": "direct",        "source_category": "Direct",   "views": 14,  "users": 5,  "free_signup": null, "subscribed": null },
    { "source": "email opens",   "source_category": "Email",    "views": 12,  "users": 6,  "free_signup": null, "subscribed": null },
    { "source": "substack.com",   "source_category": "Substack", "views": null, "users": null, "free_signup": 1, "subscribed": 0 },
    { "source": "substack notes", "source_category": "Substack", "views": null, "users": null, "free_signup": 5, "subscribed": 0 }
  ],
  "total": 9
}
```

**To nie jest jedna tabela, tylko dwie sklejone.** Wiersz albo ma ruch i
`free_signup: null`, albo ma zapisy i `views: null`. Żaden wiersz nie ma obu
naraz, a słowniki nazw są różne: ruch mówi „substack app", zapisy mówią
„substack notes". Konwersji „zapisy ÷ odwiedziny na źródło" nie da się z tego
policzyć i nie wolno jej udawać.

---

## 3. Tabela źródeł za 30 dni (2026-08-03 → 2026-09-02)

| źródło | kategoria | odwiedziny (views) | osoby (users) | zapisy (free_signup) |
|---|---|---:|---:|---:|
| direct to app | Direct | 640 | 39 | — (brak danych w tym wierszu) |
| substack app | Substack | 184 | 46 | — |
| direct | Direct | 14 | 5 | — |
| email opens | Email | 12 | 6 | — |
| substack.com | Substack | — | — | **1** |
| substack notes | Substack | — | — | **5** |
| **razem** | | **850** | **96** | **6** |

Nie ma wierszy `Substack onboarding`, `Substack trackbacks` ani
`Recommendations` — nie dlatego, że zostały pominięte, tylko dlatego, że w tym
oknie mają zero (potwierdzone drugim adresem, niżej: `trackbacks` 0/0,
`recommendations` 0/0).

Kontrolnie to samo zapytanie na oknie domyślnym panelu
(2026-07-11 → 2026-09-02, 53 dni): direct to app 665/47 przy `free_signup: 1`,
substack app 190/51, direct 19/9, email opens 12/6, substack.com
`free_signup: 3`, substack notes `free_signup: 8`; `total: 12`.

---

## 4. To samo z drugiego adresu — `growth/sources`, i to on mówi więcej

```
https://nothingisaccidental.substack.com/api/v1/publication/stats/growth/sources?order_by=users&order_direction=desc&from_date=2026-08-03&to_date=2026-09-02
```

Drzewo (Traffic / Subscribers; Revenue wszędzie 0):

| źródło | Traffic | Subscribers |
|---|---:|---:|
| **Substack** | 28 | **6** |
| └ Other (`substack other`) | 28 | 1 |
| └ Trackbacks | 0 | 0 |
| └ Recommendations | 0 | 0 |
| └ **Notes** | 0 | **5** |
| **Direct** | 2 | 0 |
| **Direct to App** | 34 | 0 |
| `totals` | **64** | **6** |

**Zapisy zgadzają się co do sztuki z pierwszym adresem: 6, w tym 5 z notek
i 1 z `substack.com` / „Substack Other".** To niezależne potwierdzenie tej
samej liczby dwoma różnymi zapytaniami — najmocniejsza rzecz w tym odczycie.

**Liczba `Traffic` NIE zgadza się** (64 wobec 850 wyświetleń i 96 osób
z `visitor_sources`). Nie wiem, co dokładnie liczy `Traffic` w Growth, i tego
nie zgaduję. Do rozmowy o ruchu należy brać `visitor_sources`; do rozmowy
o zapisach — oba, bo mówią to samo.

### 4a. Panel przypisuje zapisy do KONKRETNYCH notek, po numerze

Gałąź `notes` ma dzieci z polem `noteId` i `originalSourceName` postaci
`substack notes: c-<ID>`:

| notka | zapisy |
|---|---:|
| `c-323761132` — „GPU racks hit this wall hardest — liquid cooling…" | **2** |
| `c-320809275` — „Airline reservation systems hit this in the paper-ticket…" | 1 |
| `c-322556153` — „That ChatGPT subscription sitting on your card statement…" | 1 |
| `c-322757850` — „AI clusters are built for the largest batch you might run…" | 1 |

Wszystkie cztery mają prefiks `Nothing Is Accidental:` — to nasze notki.

---

## 5. Co z tego wynika, a czego ta tabela NIE mówi

**Wynika:** w oknie 30 dni **wszystkie 6 zapisów przyszło z powierzchni
Substacka, a 5 z 6 z notek** — z czterech imiennie wskazanych. Zero z Direct,
zero z Direct to App, zero z Email, zero z trackbacków, zero z rekomendacji.
Jest to wprost przeciwne do tabeli `DOKTRYNA.md:191-195` („artykuł 7 / notki 0")
i zgodne z diagnozą sekcji 1a rozstrzygnięcia: `signups_within_1_day` mierzy
okno czasowe, nie ścieżkę.

**Czego ta tabela nie mówi:**

1. **Nie mówi nic o artykułach.** W drzewie źródeł nie ma gałęzi „post" ani
   pozycji per artykuł — tylko notki dostają rozbicie na sztuki. Brak wiersza
   „artykuł" nie znaczy, że artykuły nie przyniosły zapisu; znaczy, że ten
   przyrząd nie ma na to rubryki. Porównania „notki kontra artykuły" z tego
   NIE da się zrobić.
2. **Nie mówi, co robił czytelnik przed kliknięciem.** „Substack Other" to
   według pomocy Substacka profil, skrzynka albo wiadomość prywatna — czyli
   właśnie to, co robią nasze komentarze i polubienia, wrzucone do jednego
   worka bez rozróżnienia. Komentarzy jako źródła nie widać wcale.
3. **Nie da się z niej policzyć konwersji.** Wiersze z ruchem i wiersze
   z zapisami to dwa rozłączne zbiory (sekcja 2), a `Traffic` z Growth nie
   zgadza się z `views` z `visitor_sources` (sekcja 4).
4. **Jedna liczba pozostaje niewyjaśniona:** `visitor_sources` zwraca
   `"total": 9` przy sześciu wierszach i sześciu zapisach (i `"total": 12` na
   oknie 53-dniowym przy ośmiu wierszach). Nie wiem, czy to licznik
   stronicowania, czy inna wielkość. `limit=50` wyklucza obcięcie listy.
   Zapisuję to jako nierozstrzygnięte, a nie interpretuję.
5. **Próba jest mikroskopijna.** Sześć zapisów. Różnica „5 kontra 1" przy
   sześciu zdarzeniach nie jest wynikiem, na którym wolno oprzeć przydział
   pracy — jest pierwszym pomiarem przyrządem, który wcześniej w ogóle nie
   był czytany. Wartość tego odczytu polega na tym, że przyrząd istnieje,
   działa i da się go czytać codziennie, a nie na tych sześciu.

---

## 6. Jak to powtórzyć

```python
import browser, config
BAZA = "https://%s.substack.com" % config.SUBSTACK_HANDLE
p, br, ctx = browser.podlacz_sie()
page = ctx.new_page()
try:
    d = browser.api_json(page,
        "/api/v1/publication/stats/growth/sources"
        "?order_by=users&order_direction=desc&from_date=2026-08-03&to_date=2026-09-02",
        baza=BAZA)
finally:
    page.close(); br.close(); p.stop()
```

Warunek: kłódka `agent-v2/data/agent.lock` wolna (planowy przebieg używa tej
samej przeglądarki), sesja żywa i wyłącznie z adresu serwera.
