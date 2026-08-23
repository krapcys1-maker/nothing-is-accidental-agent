# E-008 — ledger zdalnego szkicu artykułu

## Abstrakt

Eksperyment sprawdził A-093/N-019: czy dodatnia ścieżka artykułu utrwala zamiar
zapisu zdalnego szkicu przed otwarciem edytora, a publikację traktuje jako
drugą, zależną mutację. Stara implementacja otworzyła atrapiony edytor bez
rekordu `draft_write`. Po zmianie fixture przechodzi 4/4 przypadki, testy
sąsiednie 44/44 metod, a pełna regresja 45/45 plików. Katalog `data/` pozostał
niezmieniony. Nie użyto sieci, przeglądarki, sesji, Substacka ani modeli;
koszt wyniósł 0 USD.

## 1. Pytanie i hipotezy

Pytanie: czy awaria na dowolnej granicy zapisu szkicu pozostawia trwały,
rekoncyliowalny stan zamiast osieroconego zdalnego obiektu?

- **H1:** `draft_write.PENDING` oraz `dispatched_at` istnieją przed pierwszym
  `page.goto()` nowego edytora.
- **H2:** intencja zawiera osobne SHA-256 tytułu, podtytułu, HTML i obrazu;
  zmiana dowolnej części zmienia payload.
- **H3:** brak dokładnego ID po możliwym zapisie kończy próbę jako `UNKNOWN` i
  nie tworzy próby publikacji.
- **H4:** potwierdzony szkic tej samej intencji jest wznawiany po dokładnym ID,
  bez otwarcia ścieżki tworzącej nowy szkic.
- **H5:** publikacja ma osobny rodzaj `article_publish`, zależy od ID szkicu i
  jako jedyna zużywa jednostkę dziennego limitu artykułów.

## 2. Środowisko i granice

- Windows, projektowa `.venv`, wymuszone UTF-8;
- prawdziwy SQLite w katalogu tymczasowym;
- całkowicie atrapione `page`, `context`, edytor i potwierdzenia platformy;
- wejście: deterministyczny Markdown, podtytuł i bajty `fixture-png-bytes`;
- brak gniazd sieciowych, sekretów, sesji i trwałych ścieżek danych;
- Substack celowo nie był użyty: użytkownik zakazał jakiegokolwiek szkicu lub
  innej mutacji tej platformy.

## 3. Stan przed i kontrdowód

Odciski zapisane przed zmianą:

| Plik | SHA-256 przed |
|---|---|
| `browser.py` | `ACA904294558676F57A76E69D627395B1017201144A5617DECA65E2AA2843177` |
| `mutation_ledger.py` | `333E17E445EE90CFC497BF913A1403650B7D639D613AA9F6A44260FB73C9AE55` |
| `db.py` | `4F56D9003E71500FB6E6C04D0DE9AF96F78AEFC8F57B88EBCACEF2DC7DE65173` |
| `tests/test_mutation_ledger.py` | `9548A0632DC87F24460B7BB695AB7550D9B8651434A1EFC93B3EF1F444434DA1` |
| `tests/test_artykul.py` | `F743A3F4C676A91354ABFFE36E1DE92E4A87831B34406127E428245F951F3083` |

T-088 uruchomił nowy test przeciw starej implementacji. Atrapa w
`page.goto(.../publish/post?type=newsletter)` odczytała tę samą tymczasową bazę
i rzuciła `AssertionError: edytor otwarto przed ledgerem draft_write`.
Drugi przypadek nie znalazł jeszcze `_draft_write_intent`. Konsola CP1252
dodatkowo utrudniła wydruk polskiego komunikatu po pierwszym błędzie; nie
zmieniło to kontrdowodu kolejności, a dalsze próby wymusiły UTF-8.

## 4. Minimalna zmiana

1. `_draft_write_intent()` buduje kanoniczny manifest `draft-write@1` z hashami
   tytułu, podtytułu, HTML i obrazu; ledger nie przechowuje treści artykułu.
2. `wystaw_artykul()` rezerwuje `draft_write`, utrwala dispatch i dopiero wtedy
   otwiera nowy edytor oraz wypełnia treść.
3. Dokładne ID z URL edytora kończy `draft_write` jako `CONFIRMED`; brak ID daje
   `UNKNOWN` i zatrzymuje publikację.
4. Blokada przez ten sam `CONFIRMED` jest wznawialna wyłącznie wtedy, gdy
   idempotency key, rodzaj i numeryczne `source_ref` odpowiadają tej samej
   intencji. Wznawiana jest dokładna ścieżka szkicu, nie ścieżka tworzenia.
5. Końcowa mutacja ma osobny rodzaj `article_publish` i referencję próby
   szkicu. `draft_write` jest jawnie niekwotowaną mutacją bezpieczeństwa;
   dzienną jednostkę `artykuly` rezerwuje tylko publikacja, więc ledger nie
   podwaja limitu wolumenu.

Nie zmieniono capability gates, trybów, sesji, transportu ani potwierdzenia
opublikowanego ID.

## 5. Wyniki

| Test | Wynik | Dowód |
|---|---|---|
| T-088 | FAIL/ERROR zgodnie z hipotezą starej wady | edytor przed `draft_write`; brak nowego helpera |
| T-089 | 4/4 PASS | kolejność, dwa rodzaje mutacji, hashe, `UNKNOWN`, restart/reuse |
| T-090 | 16/16 + 14/14 + 14/14 PASS | ledger, OperationalDay i bezpieczeństwo prototypu |
| T-091 | 45/45 plików PASS | pełna regresja offline; `data/` bez zmian |

Odciski po implementacji:

| Plik | SHA-256 po |
|---|---|
| `browser.py` | `C866377D2F3A781B825F26332547FDBE4438FF519E8A83D59315C8EB1E7B0E33` |
| `mutation_ledger.py` | `3951FEAF5334F25DCAB775FF01F59450F9ADDB7FE943AC3C8275237E54795531` |
| `operational_day.py` | `D597D5C18C18E72297C5CAE623BDEBAB07427F119F67A94BDE6C123C013C665A` |
| `tests/test_operational_day.py` | `8509009DC86FF74FD72555398EF81CDA17F4DC970FFB03F77039F9942643AC84` |
| `tests/test_remote_draft_ledger.py` | `E9D95CF0D5296F292221140FB9D280DEFD2B057A8A22FA0E9EF15879DCD47FC3` |

Odciski przed dla `operational_day.py` i jego testu nie zostały zapisane przed
rozszerzeniem zakresu o rozdzielenie limitu szkic/publikacja. Jest to jawne
ograniczenie protokołu; dokładny diff i odciski po zostały zachowane.

## 6. Ograniczenia i kryterium obalenia

Fixture dowodzi kolejności wywołań, trwałości SQLite, idempotencji i stanów
awarii. Nie dowodzi aktualnych selektorów, autosave ani formatu URL prawdziwego
Substacka. Live test tej własności musiałby utworzyć lub zmienić szkic, więc
jest niedozwolony przy bieżącej granicy „nic nie trafia na Substacka”.

Wynik obali dowolny kontrprzykład, w którym nowy edytor jest otwarty przed
trwałym dispatch, ten sam manifest tworzy drugi szkic, brak ID dopuszcza
`article_publish`, albo szkic zużywa drugą jednostkę dziennego limitu artykułów.

## 7. Wniosek

A-093/N-019 otrzymuje status `FIXED_OFFLINE; PLATFORM_LIVE_NOT_RUN`.
Własność nie jest zamknięta dla żywej platformy, ale kod nie ma już osiągalnej
ścieżki tworzenia nowego szkicu bez wcześniejszego trwałego ledgeru.

