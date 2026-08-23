# E-022 — role dowodowe i kontrolowany FAIL drugiego aktu

**Data:** 2026-08-21 21:12–21:13 +03:00  
**Status:** `HARD_SEARCH_CAP_LIVE_PASS; COST_PASS; CONTRACT_FAIL_MISSING_SECOND_ACT; MANUAL_SOURCE_QUALITY_FAIL; FETCH_NOT_RUN`  
**Model:** normalny `deepseek-v4-pro`; bez zmiany providera ani routingu  
**Zakres:** tylko discovery wybranej drogi; Scout i feasibility z zaakceptowanego cache  
**Substack:** zero sesji, odczytu, szkicu, zapisu, publikacji i mutacji

## 1. Pytanie i hipotezy

Dokładna droga artykułu:

> How does an orphaned oil well become a public problem decades after the
> company that drilled it disappears?

H1: twardy limit nadal zatrzyma wyszukiwanie na maksymalnie 8 użyciach.

H2: `discovery@3` nie pozwoli, aby proposed/pending albo supporting summary
udawały current scale, mechanism lub second act.

H3: model znajdzie zestaw niegorszy od zamrożonego baseline BLM/GAO/DOI i
wszystkie trzy role przejdą exact-URL gate.

## 2. Dowód offline i rezerwacja

- testy celu `discovery@3`: 70/70 PASS;
- pełna regresja: 56/56 PASS w 58,061 s;
- jeden logiczny call, `max_uses=8`, retry=0;
- predispatch worst case: 0,28411284 USD;
- rezerwacja: 0,30 USD;
- bez fetchu, browsera runtime, classify, synthesis, write i Notes.

## 3. Wynik live

| Własność | E-021 | E-022 |
|---|---:|---:|
| wyszukiwania | 6 | **8/8** |
| tokeny wejścia | 39 265 | **40 253** |
| tokeny wyjścia | 3 886 | **8 088** |
| koszt | 0,033609 USD | **0,042581 USD** |
| czas | 55,188 s | **111,047 s** |
| URL-e z narzędzia | 43 | **46** |
| raw / po exact+claim | 10 / 10 | **10 / 6** |
| retry | 0 | 0 |

H1 przeszła. H2 zadziałała jako fail-closed: przebieg stanął na
`ValueError: dyskoveria nie pokryła kwalifikowanymi źródłami ról: SECOND_ACT`.
Nie zapisano wyniku discovery do cache i nie uruchomiono następnego etapu.

Artefakty:

- `.live-experiments/E-019b-scout-route-depth-live/model-captures.json`,
  ordinal 4 — pełny system prompt, pełny user prompt i raw JSON;
- `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json`
  — usage, koszt, stdout, stderr i końcowy status.

| Materiał | SHA-256 |
|---|---|
| system prompt | `b12b84cde976d9a1ed2b3938be7e63f6b1479a7d816105d0c413be1556cc4135` |
| user prompt | `18eec0b38f99f83ef2bfaebc1307ab2e93fabb90cbd6737a6860aa07d6df1118` |
| raw response | `277ddb4de7b3a9d7f9ba700df81b5892dd38171fb3134ee556069cb61ff8f0ba` |

W `stderr` pozostało ostrzeżenie serializatora Pydantic o błędowym bloku
`web_search_tool_result_error`. Usage było kompletne, koszt `KNOWN`, a finalny
JSON poprawny składniowo.

## 4. Ręczna kontrola wszystkich dziesięciu propozycji

| # | Propozycja modelu | Gate | Ręczne wejście i ocena |
|---:|---|---|---|
| 1 | [DOI FY2024 Annual Report](https://www.doi.gov/sites/default/files/documents/2024-11/fy-2024-owpo-annual-congressional-reportfinal-publishing.pdf) | KEEP | **PASS, HTTP 200 PDF.** Mocny origin-primary/current scale: 4,677 mld USD programu, 1,303 mld USD obligated, 9 437 wells plugged przez stany. |
| 2 | [OSMRE Reclaiming Abandoned Mine Lands](https://www.osmre.gov/programs/reclaiming-abandoned-mine-lands) | DROP: exact URL nie wystąpił w wynikach sesji | **Treściowo PASS, HTTP 200.** Najlepszy drugi akt: fundusz utworzony dla legacy coal mines; 14,233 mld USD zebrane i 6,569 mld USD grantów do 2025. Model podał realny adres, ale odtworzył go spoza wyniku tej sesji. |
| 3 | [IOGCC 2008 — Protecting Our Country's Resources](https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/protecting_our_countrys_resources-the_states_case-2008.pdf) | KEEP | **PASS, HTTP 200 PDF.** Silny historyczny mechanizm: operator unknown/insolvent, boom-bust, średnio 60 lat przed regulacją; około 60 tys. na listach i ponad 90 tys. undocumented. Stary, więc nie może być current scale. |
| 4 | [IOGCC 2019/2020 report](https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/2020_03_04_updated_idle_and_orphan_oil_and_gas_wells_report.pdf) | DROP: `access_claim=UNKNOWN` | **HTTP 200 PDF, ale wybór merytorycznie przestarzały.** Istnieją nowsze raporty IOGCC 2021 i supplemental 2024; opis „most recent” w raw jest fałszywy na 2026-08-21. |
| 5 | [National Academies workshop proceedings](https://nap.nationalacademies.org/read/28035/chapter/3) | DROP: exact URL nie wystąpił | **HTTP 200 po redirect.** Użyteczny supporting/background, ale to proceedings of a workshop, nie consensus study; model podał 2024, katalog wskazuje publikację 2025. Nie zastępuje current audit. |
| 6 | [NRDC AB 1167](https://www.nrdc.org/bio/ann-alexander/ab-1167-putting-brakes-orphan-well-catastrophe) | KEEP | **Treść dostępna w publicznym indeksie, direct client 403.** Dobry opis transferu słabych aktywów i Rincon/Greka, ale advocacy summary zastępuje oficjalny rekord podpisanej ustawy, wbrew pkt 9 promptu. `FULL_TEXT_NO_LOGIN` nie jest wiarygodnym access claim dla automatu. |
| 7 | [The Capitol Forum — ownership investigation](https://thecapitolforum.com/early-bids-for-orphan-well-plugging-reveal-cracks-in-states-ability-to-accurately-track-well-ownership-active-operators-are-poised-to-further-exploit-state-processes-to-offload-retirement-ob/) | KEEP | **PASS, HTTP 200.** Mocny supporting i kontrdowód: 203 wells / 29,6 mln USD oraz odpowiedzi urzędów pokazują błędy ewidencji i spór o odpowiedzialność. Wymaga triangulacji z dokumentami stanowymi. |
| 8 | [NCSL — States Tackle Orphaned Wells](https://www.ncsl.org/state-legislatures-news/details/states-tackle-orphaned-oil-and-gas-wells) | DROP: exact URL nie wystąpił | **Treść widoczna po publicznym redirect, direct client 403.** Użyteczne tło o niewystarczających bonds, lecz artykuł z 2022 i summary, nie current official record. |
| 9 | [Environment California AB 2461](https://environmentamerica.org/california/media-center/11283/) | KEEP | **Direct client 403; exact page nie otworzyła się w ręcznym readerze.** Jedyny proposed/pending, lecz advocacy press release. To dopuszczalny sygnał sporu, nie dowód mechanizmu lub skutku. |
| 10 | [Payne Institute — DOI methane data](https://payneinstitute.mines.edu/dois-orphaned-well-methane-leakage-insights-and-vcm-implications/) | KEEP | **HTTP 200 w direct client; reader okresowo 403.** Liczby zgadzają się z DOI, ale po wybraniu samego DOI jest to redundantna interpretacja wtórna, nie nowa rola dowodowa. |

Podsumowanie direct HTTP: 7/10 odpowiedziało 200; NRDC, NCSL i Environment
California zwróciły 403. Dostęp przez indeks nie jest równoważny stabilnemu
automatycznemu pełnemu tekstowi.

## 5. Ręczny werdykt bramek

| Bramka | Werdykt | Dowód |
|---|---|---|
| maksymalnie 8 wyszukiwań | PASS | dokładnie 8 |
| finalne URL-e z bieżących wyników | FAIL dla 4/10 | OSMRE, IOGCC 2019/2020, NAP i NCSL odpadły; IOGCC dodatkowo przez claim |
| current official scale | PASS | DOI FY2024 |
| obserwowany mechanizm, nie tylko proposal | PASS z ograniczeniem | IOGCC 2008 + Capitol Forum; brak nowszego audytu GAO |
| observed second act | **FAIL runtime** | OSMRE treściowo istnieje, ale nie było exact URL w wyniku sesji |
| maksymalnie 1 proposed | PASS | dokładnie 1 |
| nie gorzej niż baseline BLM/GAO/DOI | **FAIL** | nadal brak BLM 2024 i GAO-19-615; DOI tylko częściowo pokrywa baseline |
| brak mylącego access claim | **FAIL** | trzy direct 403 mimo `FULL_TEXT_NO_LOGIN` |

Końcowy ręczny status E-022 to `MANUAL_FAIL`. H3 została odrzucona. Fetch,
classify, synthesis, article, Notes i cała powierzchnia Substack pozostały
nieuruchomione.

## 6. Znalezione przyczyny i poprawka po E-022

1. Jeden model jednocześnie wyszukiwał i finalizował listę. Potrafił podać
   realny, dobry oficjalny URL z pamięci, którego nie było w wynikach bieżącej
   sesji; exact gate słusznie go usuwał, ale zestaw tracił obowiązkową rolę.
2. Capture utrwalał finalny JSON i liczbę URL-i, lecz nie pełną listę adresów
   zwróconych przez narzędzie. Nie dało się odtworzyć wszystkich 46 decyzji
   exact-URL po zakończeniu procesu.
3. Model nie wykonał samokontroli finalnych adresów mimo jawnej instrukcji.

Poprawka offline rozdziela dwa requesty tego samego modelu w jednym logicznym
zadaniu: bounded web search, a następnie beznarzędziowy exact-URL selector,
który widzi raw draft i wyłącznie adresy faktycznie zwrócone w tej sesji.
Runner odtąd zapisuje obydwa pełne prompty, obydwie raw odpowiedzi, ich hashe,
tokeny oraz pełną listę search-result URL-i. Nie jest to retry i nie zmienia
modelu. Lista wejściowa selektora ma twardy limit 16 000 znaków, ujęty w
predispatch worst case.

Po zmianie 72/72 testów celu przeszło. Pierwsza szeroka komenda była nieważna:
wadliwy glob Windows uruchomił 69 zamiast 56 plików, w tym sześć płatnych
launcherów. Kill switch i dry-run zablokowały wszystkie przed API; koszt 0 USD.
Jeden właściwy harness dał w tym przebiegu pojedynczy FAIL, którego 10 osobnych
powtórzeń nie odtworzyło (10/10 PASS). Poprawny, prerejestrowany korpus z
jawnym wyłączeniem `tests/platne` następnie przeszedł **56/56 w 58,480 s**.
Nieważnej próby nie usunięto z rejestru.

## 7. Budżet

E-022 rozliczono jako 0,042581 USD KNOWN. Po zwolnieniu 0,30 USD rezerwacji:

- DeepSeek KNOWN: 0,33877270 USD;
- DeepSeek UNKNOWN: 4,90 USD;
- ekspozycja DeepSeek: 5,23877270 USD;
- wszystkie KNOWN/EST.: 1,73680670 USD;
- globalna ekspozycja: 6,63680670/10 USD;
- globalny margines: 3,36319330 USD.

Nie było żadnej aktywności na Substacku.
