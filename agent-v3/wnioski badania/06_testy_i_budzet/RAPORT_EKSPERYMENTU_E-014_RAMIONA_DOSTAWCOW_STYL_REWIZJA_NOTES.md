# E-014 — izolowane ramiona dostawców: styl, rewizja, Notes i DeepSeek

**Data:** 2026-08-21  
**Status:** `ANTHROPIC_COMPLETE; DEEPSEEK_STOPPED_FAIL_CLOSED`  
**Substack:** `FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION`

## 1. Pytania badawcze

1. Czy normalny pisarz Fable potrafi stworzyć artykuł z zamrożonej karty?
2. Co zmienia obecność zatwierdzonego korpusu i profili stylu przy tym samym
   modelu, materiale, celu długości, zakończeniu i liczbie paraleli?
3. Czy Fable usuwa kontrolowany fakt bez pokrycia minimalną rewizją?
4. Czy Opus realizuje pięć form Notes na identycznym fakcie i zachowuje
   kontrakt 33–64 słów?
5. Czy oddzielny, materialnie zmieniony scout DeepSeek przejdzie po T-118?

## 2. Plan przed dispatch

Ramię Anthropic: Fable 5 ×3 (`write` styl, `write` ablacja, `revise`) oraz Opus
5 ×5 (PROSTA, LICZBA, SCENA, ODWROCENIE, ZACZEP_I_KONKRET), cap 3,50 USD.

Ramię DeepSeek: maksymalnie Pro ×13 i Flash ×10 dla skauta, researchu, ocen
artykułów, rewizji oraz fact-checku pięciu Notes, cap 3,25 USD. T-118 pozostał
policzony w pełnej wysokości 1,60 USD. Transport miał zero automatycznych retry.

Uprząż `editorial_live_continuation.py` używa osobnych workspace i SQLite per
dostawca, zapisuje pełne system/user/response, hashe, czasy i koszty, blokuje
cross-provider call oraz wszystkie domeny Substacka.

## 3. Wynik ramię Anthropic

Wykonano 8/8 wywołań. Wszystkie koszty są KNOWN; łączny koszt wyniósł
**1,341430 USD**.

| # | Rola | Model | Wejście | Wyjście | Czas | Koszt |
|---:|---|---|---:|---:|---:|---:|
| 1 | write ze stylem | claude-fable-5 | 12 330 | 8 665 | 191,39 s | 0,556550 |
| 2 | write bez stylu | claude-fable-5 | 8 670 | 6 763 | 105,75 s | 0,424850 |
| 3 | revise | claude-fable-5 | 6 860 | 1 751 | 21,88 s | 0,156150 |
| 4 | Note PROSTA | claude-opus-5 | 2 695 | 1 150 | 13,67 s | 0,042225 |
| 5 | Note LICZBA | claude-opus-5 | 2 959 | 1 154 | 12,95 s | 0,043645 |
| 6 | Note SCENA | claude-opus-5 | 2 720 | 1 117 | 14,11 s | 0,041525 |
| 7 | Note ODWROCENIE | claude-opus-5 | 2 739 | 1 063 | 13,27 s | 0,040270 |
| 8 | Note ZACZEP_I_KONKRET | claude-opus-5 | 2 928 | 863 | 10,58 s | 0,036215 |

Routing pozostał niezmieniony, browser nie został zaimportowany, a żaden
fact-check ani platforma nie były ukrytym wywołaniem Anthropic.

Artefakt lokalny: `.live-experiments/E-014-anthropic-controlled-live/result.json`,
SHA-256 `A3B95579ABE736959B09810FEF736E75FCECA8ADBDE62A12809312B36C4C2801`.

## 4. Styl A/B

Materiał był syntetycznym, jawnie fikcyjnym rozporządzeniem o oświetleniu.
Zmienne stałe: karta, Fable 5, `RICH`, zakończenie, dwie paralele i pusta pamięć
redakcyjna. Jedyną interwencją była obecność pięciu próbek stylu oraz profilu
pozytywnego/negatywnego.

| Cecha | Ze stylem | Bez stylu | Obserwacja |
|---|---:|---:|---|
| słowa | 817 | 945 | stylowany nie spełnił minimum RICH=900 |
| akapity | 8 | 8 | makrostruktura pozostała taka sama |
| zdania | 37 | 53 | stylowany ma dłuższe jednostki |
| mediana słów/zdanie | 24 | 18 | wyraźnie inny rytm |
| em dash | 5 | 9 | profil zmniejszył, lecz nie usunął tiku |
| budżet zastrzeżeń | PASS | FAIL | ablacja użyła `my reading` i `I suspect` |
| pięciowyrazowe kopie z assetów | 0 | 0 | brak wykrytego kopiowania fraz |

Wariant ze stylem miał mocniejsze przejście od lampy do mechanizmu i
konkretniejszy powrót do filamentu w zakończeniu. Wariant bez stylu również
otwierał konkretem, miał silny język metaforyczny i wykonał ten sam ośmioakapitowy
plan. Na jednej parze nie wolno przypisać wszystkich różnic profilowi.

Koszt interwencji był mierzalny: prompt stylowany miał 30 404 znaki wobec
22 242, a całe wywołanie kosztowało o 0,131700 USD więcej. Jednocześnie wynik
był krótszy o 128 słów i wypadł poza kontrakt. Wada harnessu polegała na tym,
że `_draft_features()` nie przekazywało `glebokosc`, więc surowy artefakt nie
oznaczył `DLUGOSC_POZA_KONTRAKTEM`; naprawiono to offline testem.

## 5. Prawdziwość artykułów — inspekcja manualna

Oba teksty wyszły poza ścisłą kartę, mimo jawnego zakazu.

Wariant stylowany przedstawiał bez dowodu jako fakty między innymi istnienie
jaśniejszych starych lamp, filament jako mechanizm każdej oprawy, brak budżetu
retrofitowego, radę miejską jako autora oraz lampy nadal świecące „tonight”.
Część późniejszych rozwinięć była uczciwie oznaczona jako `Suppose` lub
`My reading`, ale pierwsze twierdzenia nie były.

Wariant bez stylu twierdził między innymi, że pilot poprzedził generalizację,
że nie było pozycji retrofitowej, ekip ani grup poszkodowanych oraz że miasto
opublikowało określony zakres informacji. Karta tych zdań nie ustanawiała.

To jest ręczny finding, nie recall modelowego review: DeepSeek nie doszedł do
etapu recenzji. Obecna polityka V3 przy niedostępnej kontroli powinna skierować
tekst do `QUARANTINED_EDITORIAL`, więc finding nie dowodzi automatycznej
publikacji fałszu. Dowodzi, że sam prompt pisarza nie jest wystarczającą obroną.

## 6. Rewizja kontrolowanego błędu

Do stylowanego body dopisano: `The records prove that this system prevented
exactly 12 accidents.` Fable otrzymał jedną bramkę `FAKT_BEZ_POKRYCIA`.

Wynik:

- zdanie zostało usunięte;
- body poza tym zdaniem jest bajtowo identyczne z wersją przed wstrzyknięciem;
- tytuł i podtytuł są identyczne;
- opis `changes` poprawnie wskazuje brak danych o wypadkach;
- nie przeprowadzono live review po rewizji z powodu awarii DeepSeek.

Mechanika minimalnej rewizji ma dodatni wynik live. Pełny wynik autonomicznej
pętli N-011 pozostaje częściowy, ponieważ ponowna recenzja i forma nie zaszły.

## 7. Pięć form Notes

| Forma | Słowa | Bloki | Otwarcie | Ocena formy |
|---|---:|---:|---|---|
| PROSTA | 47 | 1 | `Six minutes went missing...` | zgodna: jeden akapit |
| LICZBA | 49 | 2 | `Six minutes.` | zgodna z hookiem liczbowym |
| SCENA | 50 | 2 | `Your oven clock...` | zgodna wizualnie, ale zakłada typ zegara czytelnika |
| ODWROCENIE | 48 | 3 | `Your oven clock isn't...` | zaczyna od korekty, nie od uczciwej wiary; brak genezy wiary |
| ZACZEP_I_KONKRET | 52 | 3 | `Your oven clock doesn't...` | trzy ruchy; końcowy test dziś jest słabo związany z 2018 |

Wszystkie trafiły w 33–64 słowa, nie użyły em dash, średnika, hashtagów ani
emoji. Formy zmieniły liczbę bloków i hook. Różnorodność głosu była jednak
niska: tylko dwa różne pierwsze słowa, a 3/5 zaczyna się od tych samych trzech
słów `Your oven clock`. W trakcie eksperymentu lista wcześniejszych otwarć nie
była aktualizowana między formami.

Manualne ryzyka prawdziwości obejmują przejście z `synchronous clocks` do
`every one of them`, założenie, że zegar piekarnika czytelnika jest synchroniczny,
oraz metaforę `electricity itself was running slow`. Żadna notka nie dostała
`safe_to_post=true`; fact-check był celowo odroczony do ramienia DeepSeek i nie
został wykonany.

## 8. Ramię DeepSeek

T-132: nowy scout miał niepustą, zamrożoną pamięć z ID replikacji. User prompt miał
23 193 znaki i inny SHA-256 niż T-118. Po 180,875 s dostawca ponownie zamknął
niepełne chunked body. Wynik: 1/23 prób dispatchu, 0 kompletnych odpowiedzi,
UNKNOWN 1,60 USD, pozostałe 22 NOT_RUN.

Artefakt: `.live-experiments/E-014-deepseek-scout-research-live/result.json`,
SHA-256 `1287B8873B1542896BBDD15B9F1D90C4AF51BA79A6D8D98085C5E8B3271B1AF0`.

Nie istnieją więc live wyniki tematów, feasibility, źródeł, klasyfikacji,
syntezy, worth, ślepych sędziów ani fact-checku. Brak wyniku nie jest wynikiem
negatywnym jakości tych ról; jest negatywnym wynikiem wykonalności bieżącego
transportu.

## 9. Porównanie V2 → V3

### Bez zmian lub odziedziczone

- routing scout/research/write/note jest zasadniczo ten sam;
- prompt Notes jest bajtowo identyczny w V2 i V3;
- pisarz, style loader, pięć form i jedno-kandydatowa Note nie zostały
  zaprojektowane od nowa;
- V2 i V3 używają Fable dla artykułu oraz Opusa dla Notes.

### Działa lepiej w V3

- pełne prompt/response, hash, czas i koszt są checkpointowane;
- koszt UNKNOWN nie staje się zerem i nie uruchamia retry;
- modelowe JSON-y mają wersjonowane kontrakty;
- artykuł ma graf provenance, transakcyjny zapis i terminalną kwarantannę;
- niedostępne review/form nie jest już opisane jako „nic nie blokuje”;
- rewizja ma maksymalnie dwie iteracje i pełny recheck w normalnym runtime;
- pin korpusu stylu jest przenośny LF/CRLF.

### Działa gorzej lub pozostaje nieudowodnione

- normalny V3 zależy od DeepSeek już w etapie 1 i trzy razy nie uzyskał tematu;
- fail-closed jest bezpieczniejszy, lecz obecnie zatrzymuje całą redakcję;
- profil stylu zwiększył koszt i w tej parze pogorszył zgodność długości;
- Notes nadal dziedziczą z V2 powtarzalność otwarć;
- prompt pisarza jest dłuższy od V2, ale nadal nie powstrzymał dodawania
  przesłanek spoza karty.

## 10. Budżet i granice wnioskowania

Po E-014 konserwatywna ekspozycja wynosiła 4,61701670 USD: historia
0,07558670, T-118 UNKNOWN 1,60, Anthropic 1,341430 i drugi DeepSeek UNKNOWN
1,60. Nie jest to potwierdzony rachunek DeepSeek 3,20 USD; to pełne rezerwy.

Eksperyment nie dotknął Substacka, sesji, draftu ani publikacji. Nie badano
prawdziwości fikcyjnego rozporządzenia. Jedna para A/B nie estymuje wariancji
ani przewagi stylu. Wyniki manualne są jawnie nieslepe. Pełny research i
niezależni sędziowie nie zaszli.
