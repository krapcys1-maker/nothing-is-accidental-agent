# E-024 — live canary bezpiecznego pobierania na ręcznie zaliczonym korpusie

**Data prerejestracji:** 2026-08-21 22:00 +03:00  
**Status:** `LIVE_FETCH_PASS; MANUAL_CONTENT_PASS; 5_OF_6; ZERO_MODEL_CALLS`  
**Koszt modeli/API:** 0,00 USD  
**Substack:** bezwarunkowo zabroniony

## 1. Cel i granica interpretacji

Discovery E-020–E-022 nie zaliczyło ręcznej bramki, a E-023 nie zwróciło
kompletnej odpowiedzi. Nie wolno zatem udawać ciągłości normalnego pipeline'u.
Można niezależnie przetestować następny komponent: czy aktywne `stages.fetch`
i `safe_fetch` pobierają oraz ekstrahują tekst z ręcznie zakwalifikowanych,
publicznych dokumentów potrzebnych tej samej drodze artykułowej.

PASS E-024 dowodzi wyłącznie działania fetchu na wskazanym korpusie. Nie zalicza
discovery, klasyfikacji, syntezy, artykułu ani Notes.

## 2. Korpus i hipotezy

Korpus prerejestrowany przed siecią:

1. DOI FY2024 — current official scale, PDF;
2. BLM 2024 — current official baseline, PDF;
3. GAO-19-615 — mechanizm niewystarczających zabezpieczeń, HTML;
4. OSMRE Abandoned Mine Lands — drugi akt, HTML;
5. IOGCC 2008 — historyczny mechanizm osierocenia, PDF;
6. Capitol Forum — supporting/counterevidence, HTML.

H1: co najmniej 4/6 dokumentów przejdzie aktywny transport i ekstrakcję.  
H2: korpus zachowa przynajmniej po jednym tekście dla `CURRENT_SCALE`,
`CAUSAL_MECHANISM` i `SECOND_ACT`.  
H3: pełny tekst każdej udanej próby będzie ręcznie rozpoznawalny jako właściwy
dokument, a nie challenge, strona błędu, menu albo tekst niepowiązany.  
H4: redirecty, DNS pins, finalny URL, SHA-256 i przyczyna każdej porażki będą
utrwalone.

Warunek STOP: jedna próba na URL, zero fallbacku przeglądarkowego, zero retry,
zero modeli, zero Substacka. Porażka pojedynczego hosta pozostaje wynikiem, nie
powodem do obejścia blokady.

## 3. Artefakty planowane

- `.live-experiments/E-024-safe-fetch-canary/manifest.json`;
- `.live-experiments/E-024-safe-fetch-canary/experiment.db`;
- pełny wyekstrahowany tekst każdego udanego dokumentu jako osobny `.txt`;
- ręczna tabela jakości dopisana do niniejszego raportu po próbie.

## 4. Wynik transportu

Preflight negatywny w trybie fixture zakończył się odmową przed utworzeniem
katalogu. Właściwy przebieg użył `AGENT_V3_MODE=model_test`, wyłączonego kill
switcha i jawnie pustych kluczy wszystkich modeli. Wykonano dokładnie jeden
publiczny GET na prerejestrowany URL, bez retry i bez fallbacku.

| Źródło | Wynik | Znaki tekstu | SHA-256 treści |
|---|---:|---:|---|
| DOI FY2024 | PASS | 82 024 | `0e520a5324b4b6d26918d1351aebad8f12af5af015d809e8eae28a41f019930c` |
| BLM 2024 | PASS | 7 046 | `2ca85dc403009acb5c40568944b0633458e8b97cfc428a4ffddb6810a0ff02fc` |
| GAO-19-615 | PASS | 5 792 | `e6942630600c4f1cfe44402b77da0d327b8881b213e4a1d4181993c64c84641e` |
| OSMRE AML | PASS | 3 338 | `d6b512e03aecf36fa3314c373b49f7f9b1bc7b8b9ecca2e5a0d824f023e04bdc` |
| IOGCC 2008 | PASS | 106 810 | `1e44591efc36990b7ae1339f0ce3b1634cd15cd8f6f9324c5832746c3ff93374` |
| Capitol Forum | **FAIL** | 0 | HTTP 403 |

Nie obchodzono 403. Manifest zachował finalne URL-e, pełne łańcuchy redirectów,
DNS pins, document IDs i przyczynę porażki. Koszt modeli/API: 0,00 USD.
Substack: 0.

## 5. Ręczna kontrola pełnych tekstów

| Dokument | Werdykt ręczny | Co rzeczywiście zawiera | Ograniczenie |
|---|---|---|---|
| DOI FY2024 | PASS | 9 636 wells łącznie, 9 437 stanowych; 4,677 mld USD programu i 1,303 mld USD obligated | PDF ma powtarzalne nagłówki stron; liczby ogółem i stanowe trzeba rozróżniać |
| BLM 2024 | PASS | 8 500 idled wells, ponad 1 500 plugged w 2023, ryzyko dla podatnika i nowe minima bonds 150/500 tys. USD | factsheet, nie pełny audyt metodologiczny |
| GAO-19-615 | PASS | 89 nowych orphaned wells, ok. 46 mln USD ryzyka i 84% bonds prawdopodobnie za niskich | strona raportu 2019 zawiera również status rekomendacji z lutego 2026 |
| OSMRE AML | PASS | legacy mines sprzed SMCRA 1977; opłata od bieżącego wydobycia; 14,233 mld zebrane i 6,569 mld grantów do 2025 | drugi akt, nie dowód skali szybów naftowych |
| IOGCC 2008 | PASS | operator unknown/insolvent, boom–bust, średnio 60 lat do regulacji, ok. 60 tys. na listach i ponad 90 tys. nieudokumentowanych | historyczny; nie wolno używać jako current scale; tabele mają szum ekstrakcji |

H1 PASS: 5/6. H2 PASS: wszystkie trzy role mają pełny tekst. H3 PASS: 5/5
udanych ekstrakcji to właściwe dokumenty. H4 PASS: pełna telemetria utrwalona.

## 6. Nowa wada granicy A-130

Discovery zachowuje `published_at`, `evidence_status` i `evidence_roles`, ale
aktywny prompt klasyfikacji ich nie dostaje, synteza usuwa je z payloadu, a
`evidence_manifest` provenance ich nie przechowuje. GAO jest kontrprzykładem:
dokument opublikowany w 2019 ma na żywej stronie fragment aktualizowany w 2026.
Sama data dokumentu nie może być automatycznie datą każdego twierdzenia.

Przed live classify należy zachować metadane przez fetch, classify, synthesis i
manifest, dodać `retrieved_at`, a promptom powiedzieć, że data publikacji jest
kontekstem dokumentu, data pobrania momentem obserwacji, natomiast data
twierdzenia musi wynikać z dokładnego fragmentu.

## 7. Naprawa A-130 i regresja

Po E-024, bez ponownego pobierania któregokolwiek URL-a:

- `stages.fetch` nadaje jeden `retrieved_at` użyty jednocześnie w zwracanym
  dokumencie i w wierszu `sources.at`;
- classify dostaje `published_at`, `retrieved_at`, `evidence_status` oraz
  `evidence_roles` i jawny zakaz przenoszenia daty dokumentu na każde
  twierdzenie;
- synteza przenosi te pola do payloadu;
- `evidence_manifest` provenance zachowuje je trwale.

Kontrtest strony 2019 z fragmentem „As of February 2026” przeszedł 3/3. Sześć
plików testów celu i sąsiednich przeszło 107/107. Pełna bezpieczna regresja po
zmianie przeszła 57/57 plików w 61,004 s. Wszystkie te próby były fixture z
kill switchem i dry-run, koszt 0 USD, bez sieci i Substacka.

Werdykt E-024 pozostaje `LIVE_FETCH_PASS; MANUAL_CONTENT_PASS`. A-130 jest
`FIXED_OFFLINE`, lecz prawdziwe classify nadal wymaga osobnego live dowodu po
rekoncyliacji E-023.

T-196 potwierdził końcową integralność bez błędów: ciągłe A-001–A-130 i
T-001–T-195, pięć zgodnych hashy tekstów E-024, 57 poprawnych linków, V2 3/3 i
`git diff --check` PASS.
