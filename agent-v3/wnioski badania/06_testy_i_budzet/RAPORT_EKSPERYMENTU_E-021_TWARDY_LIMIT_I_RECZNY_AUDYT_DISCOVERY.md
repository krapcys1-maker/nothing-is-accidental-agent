# E-021 — twardy limit i drugi ręczny audyt discovery

**Data:** 2026-08-21  
**Status:** `HARD_SEARCH_CAP_LIVE_PASS; COST_PASS; CONTRACT_PASS; MANUAL_SOURCE_QUALITY_FAIL; FETCH_NOT_RUN`  
**Model:** normalny `deepseek-v4-pro`; ten sam provider i routing co E-020  
**Zakres:** tylko discovery wybranej drogi; bez fetch, classify, synthesis, write i Notes  
**Substack:** zero sesji, odczytu, szkicu, zapisu, publikacji i mutacji

## 1. Hipotezy

H1: oficjalny interfejs DeepSeek zgodny z Anthropic wymusi
`max_uses=8`, którego nie udostępnia `/responses`.

H2: rozdzielenie `class`, `host_role` i `access` zatrzyma zawyżanie mirrorów
oraz źródeł wymagających loginu.

H3: po tych zmianach source set będzie co najmniej tak dobry jak ręczny
baseline BLM/GAO/DOI z E-020.

## 2. Dowód offline przed dispatch

- testy celu: 68/68 PASS;
- postwarunek 9/8 rozlicza tokeny i koszt jako `KNOWN`, `ok=0`, bez `UNKNOWN`;
- strona za loginem odpada;
- mirror nie zwiększa licznika origin-primary;
- pełna regresja: 56/56 PASS w 58,011 s;
- cap: 0,30 USD, zero retry, bez override modelu.

## 3. Wynik live

| Własność | E-020 `/responses` | E-021 bounded Messages |
|---|---:|---:|
| wyszukiwania | 22 | **6** |
| tokeny wejścia | 153 385 | **39 265** |
| tokeny wyjścia | 7 360 | **3 886** |
| koszt | 0,115807 USD | **0,033609 USD** |
| czas | 136,016 s | **55,188 s** |
| URL-e z narzędzia | 17 | 43 |
| raw / exact kept | 10 / 8 | **10 / 10** |
| retry | 0 | 0 |

H1 przeszła. Faktyczna liczba użyć była mniejsza od limitu, koszt spadł o
0,082198 USD (70,98%), a wejście o 74,40%. Nie było fallbacku selektora.

Artefakty:

- `.live-experiments/E-019b-scout-route-depth-live/model-captures.json`,
  ordinal 3;
- `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json`.

| Materiał | SHA-256 |
|---|---|
| system prompt | `b12b84cde976d9a1ed2b3938be7e63f6b1479a7d816105d0c413be1556cc4135` |
| user prompt | `20b1b569e4311ade61632e5c42754b60f9e6811f8c7f44990c7ae3c62c310fa7` |
| raw response | `ab04aedd938b57e513bfd7ec357c1a1592baee1ab7bc54f0fefee0aa981ee866` |

## 4. Ręczna kontrola wszystkich dziesięciu źródeł

| # | Źródło | Dostęp ręczny | Ocena treści |
|---:|---|---|---|
| 1 | IOGCC 2020 orphan-well survey PDF | **FAIL: HTTP 526** | dobry zamysł registry, ale `FULL_TEXT_NO_LOGIN` było fałszywą deklaracją modelu |
| 2 | New Mexico HM56 (2026) | PASS | bardzo mocny current primary: definicja, 1 700 + 3 400 wells, 700 mln–1,6 mld USD liability, median assurance 7 tys. USD |
| 3 | Texas RRC takeover procedure | PASS | mocny origin-primary opis statusu, przejęcia i odpowiedzialności; mało danych o koszcie publicznym |
| 4 | IEEFA Texas liability (2026) | PASS | mocny, aktualny supporting z linkami do RRC: 202 mln USD, 3 632 wells, 575 mln USD historycznie; źródło advocacy, nie urząd |
| 5 | Carbon Tracker Colorado amnesty (2022) | PASS | pełny tekst i ciekawy mechanizm; dotyczy proponowanego wtedy programu oraz kontrastu z Australią, wymaga follow-up statusu |
| 6 | EDF Utah bonding press release (2026) | PASS | supporting, ale zastępuje linkowany oficjalny audit/rule komunikatem; prompt zakazywał substytutu |
| 7 | Texas HB942 bill analysis (2003) | PASS | bardzo czysty origin-primary historyczny opis po co istnieje financial assurance |
| 8 | H.R. 9029 GovInfo (2026) | PASS | official archive, lecz tylko introduced bill; dowodzi politycznej obawy, nie obserwowanego wyniku drugiego aktu |
| 9 | University of Oregon law review (2010) | PASS | pełny PDF; użyteczna historyczna analiza abandoned mines/Superfund i luki finansowej |
| 10 | DOI Federal Register notice przez Justia | PASS | mirror poprawnie oznaczony; dotyczy głównie reporting requirements, nie głównego mechanizmu ani skali |

Pydantic zapisał ostrzeżenie o co najmniej jednym błędowym bloku wyniku
wyszukiwania. Nie przerwało to finalnej odpowiedzi; usage i lista URL-i są
pełne. Ostrzeżenie pozostaje w `stderr` artefaktu.

## 5. Werdykt hipotez

| Hipoteza | Werdykt | Dlaczego |
|---|---|---|
| H1 twardy limit | PASS LIVE | 6/8; bez kosztowego wycieku |
| H2 jawne metadane | PARTIAL | mirror Justia jawny, ale access IOGCC był błędną samodeklaracją |
| H3 jakość vs baseline | **FAIL** | nadal brak BLM 2024, GAO-19-615, DOI current program i DOI FY2025; proposed/supporting źródła wypełniły sloty |

Zestaw ma dobry materiał, ale nie jest jeszcze najlepszym osiągalnym korpusem.
Nie wolno przejść do fetch wyłącznie dlatego, że licznik pokazuje 6 primary,
5 origin/official i 7 why.

## 6. Nowe wady kontraktu

1. `access` było samodeklaracją modelu, lecz nazwa i filtr wyglądały jak
   weryfikacja; IOGCC obalił to wynikiem 526.
2. Kontrakt nie odróżniał dowodu obserwowanego/obowiązującego od projektu lub
   introduced bill.
3. Nie wymagał osobnych ról: causal mechanism, current official scale i
   observed second act.
4. Supporting press release mógł zastąpić linkowany official audit/rule.

Następna wersja ma nazywać dostęp `access_claim`, wymagać ról dowodowych i
statusu materiału, ograniczyć pending/proposed do jednego slotu i nie pozwalać,
aby proposed source sam zaliczał mechanizm, current scale albo second act.

## 7. Budżet

E-021 rozliczono jako 0,033609 USD KNOWN. Po zwolnieniu 0,30 USD rezerwacji:

- DeepSeek KNOWN: 0,29619170 USD;
- DeepSeek UNKNOWN: 4,90 USD;
- ekspozycja DeepSeek: 5,19619170 USD;
- wszystkie KNOWN/EST.: 1,69422570 USD;
- globalna ekspozycja: 6,59422570/10 USD;
- globalny margines: 3,40577430 USD.

Nie było żadnej aktywności na Substacku.

