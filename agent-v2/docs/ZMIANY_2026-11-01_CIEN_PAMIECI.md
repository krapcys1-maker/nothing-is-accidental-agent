# Cień pamięci (etap N1), 1.11.2026

Zlecenie właściciela (1.11): konto NIE ma być kontem badawczym nad pamięcią; bot ma mieć osobowość, wspomnienia, uczyć się na bieżąco i mieć własne cele. Plan etapów jest uzgodniony z sesją badawczą „Pamięć LLM" (plik WSPOLNY_PLAN.md, wersja 1.1, poza tym repozytorium): N1 to wyłącznie **cień**, czyli zapis tego, co wstrzyknęłaby pamięć, bez żadnego wpływu na teksty. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Co robi

Przy każdej PRÓBIE komentarza (oba ramiona E23, oba bloki komentarzy w `run.py`; rekord powstaje przy wyborze celu, a nie przy publikacji, więc cel, pod którym model zamilknie, też go ma, a pole `publish_run` mówi, czy przebieg publikował) `pamiec_cien.cien_komentarza` liczy, jakie wpisy własnej, opublikowanej historii zwróciłaby `historia_konta.powiazane` przy trzech progach: produkcyjnym (dokładnie `HISTORIA_KONTA_*`, czyli to, co dostaje E23 „on") oraz dwóch luźniejszych (`PAMIEC_CIEN_PROFILE`), i dopisuje jeden rekord do `data/pamiec_cien.jsonl`. Bez modelu i sieci, ok. 60 ms na rekord. Po każdym zapisie w logu przebiegu stoi linia `[cien] rekord status=... pozycji(produkcja)=... ms=...`, a po awarii `[cien] nie zapisalem (...)`.

## Rekord (uzgodniony z sesją badawczą)

- **Tożsamość:** `record_id`, `schema_version`, `code_commit`, `run_id` (+ `run_id_basis`), `journal_ref: null` (+ `journal_ref_basis: none_at_decision_time`), `occurred_at`, `as_of`, `task_type`, `arm_e23`, `eksperymenty` (nazwy eksperymentów trwających w dniu decyzji), `mode`, `publish_run`.
- **Zapytanie:** `query.hmac` (skrót treści zapytania), `query.target_hmac_gdzie` (skrót wartości, którą dziennik zapisze jako `gdzie`: to **klucz złączenia z wpisem dziennika** po publikacji, razem z czasem; komentarz pod notką → `note/c-<id>`, pod artykułem → pełny adres), `query.target_hmac` (skrót adresu celu tak, jak go zna `run`, czyli `cel["url"]`; dla artykułów to ta sama wartość, dla notek różni się prefiksem adresu; patrz „Wdrożenie”), `query.author_hmac` (uchwyt znormalizowany: bez `@`, małe litery), `query.key_id`, `query.chars`. Wszystkie skróty to HMAC-SHA256 z kluczem, a `key_id` (8 znaków skrótu klucza) czyni widoczną utratę lub wymianę klucza.
- **Strategia:** `strategy.id`, `config_digest`, `embedder: null`, trzy profile z progami.
- **Wyniki** (`results.<profil>`): pozycje (`item_id` = skrót wpisu, `kind`, `age_days`, `rank`, `score`, `rare_terms`, `reason`, `tokens_est`) oraz agregaty: `n_candidates` PRZED obcięciem do limitu profilu (dla profilu „produkcja" wprost z `historia_konta.powiazane`), `n_candidates_capped`, `n_returned`, `tokens_entries`, `tokens_overhead` (stała część bloku), `tokens_total`, `over_budget`.
- **Migawka indeksu:** `index_snapshot` (`pool_size`, `newest_item_at`, `window_days`, `journal_bytes`), `would_arm` (zamrożona funkcja losowania `pamiec_n3` < 10%, nieużywana w cieniu).
- **Status:** `ok`; `degraded` z `degraded_reason` = `no_key` (nie da się odczytać ani utworzyć klucza) albo `no_index` (brak dziennika); `timeout` (etykieta nadawana po policzeniu, gdy przekroczono 2 s; to nie jest przerwanie); `error` + `error_code` (pełny szkielet rekordu, bez pozycji). Ten sam rekord błędu powstaje, gdy wyszukiwanie wyrzuci wyjątek.

## Czego NIE robi

- Nie zmienia żadnego tekstu, wyboru celu, ramienia ani wyniku `dane_maniery` (test: słownik zwracany i słownik celu identyczne z cieniem, z awarią cienia i z wyłączonym).
- Nie zapisuje tekstu celu, nazwy autora ani adresu (tylko skróty kluczowane), nie zapisuje tekstów wpisów historii (tylko skrót), nie zapisuje wyników (`skutek`, statystyk) ani promptów (hak na `llm.call` to osobna decyzja właściciela; dziś nie).
- Nie zatrzymuje komentarza: każdy wyjątek jest połykany (fail-open).

## Dane i prywatność

Repozytorium bota na GitHubie jest **publiczne**. Plik `data/pamiec_cien.jsonl` i klucz `data/.cien_klucz` leżą w katalogu `data/`, który jest ignorowany przez Git (test sprawdza `git check-ignore`) i nie jest kopiowany przez `wdroz.sh`; klucz ma tryb 0600. Klucz leży **obok** rekordów, więc nigdy nie wolno kopiować `data/` w całości do laboratorium, do repo ani do kopii roboczych: eksportować można tylko `pamiec_cien.jsonl`, bez klucza. Bez klucza z rekordu nie da się odtworzyć tekstu, autora ani adresu celu.

## Wyłączenie, wycofanie, limity

`config.PAMIEC_CIEN = False` (wymaga wdrożenia) albo `git reset --hard <poprzednia wersja>` na serwerze. W `NIA_TRYB=test` moduł nie pisze do pliku domyślnego, a katalog danych wskazuje wywołujący (`katalog=config.DATA_DIR` z modułu `run`), więc testy z podmienioną konfiguracją nie piszą do prawdziwego `data/`. Limit rozmiaru 25 MB (potem przestaje pisać, jeden komunikat w logu); zapis dopisuje `\n`, jeśli poprzednia linia została ucięta.

## Zmiany w istniejącym kodzie

- `historia_konta.powiazane`: opcjonalne `min_podobienstwa`, `min_rzadkich`, `ile`, `statystyki`; wynik niesie `rzadkie` i `cos` (cosinus niezaokrąglony: porównania z progami robi się na nim). Domyślne zachowanie bez zmian (113 testów E23 bez zmian poza asercją o tekście wywołania).
- `run.dane_maniery`: parametry `run_id`, `zadanie`, `wyslij`; wywołanie `pamiec_cien.cien_komentarza` w `try/except` przed rozgałęzieniem on/off (po awarii linia w logu).
- `wdroz.sh`: kontrola „moduły wstają" importuje `historia_konta` i `pamiec_cien`.
- `config.py`: `PAMIEC_CIEN`, `PAMIEC_CIEN_PROFILE`, `PAMIEC_CIEN_PULA`.

## Dowody i ograniczenia

- Testy: `tests/test_pamiec_cien.py` (66 sprawdzeń), `tests/test_maniera_komentarza.py` (113), `tests/test_nadwyzka_pod_notkami.py` (atrapa `dane_maniery` odwzorowuje nowy podpis). Mutacje kodu (`robocze/mutacje_cien.py`): wynik w sekcji „Wdrożenie”.
- Zapytanie cienia to tytuł i tekst celu, tak jak w `dane_maniery`. Pole `lang` i liczba terminów zapytania nie są zapisywane (do dodania w razie potrzeby N2).
- Cień mierzy tylko, co zwróciłaby pamięć leksykalna (cosinus wag idf). Nie mówi, czy komentarz byłby lepszy z pamięcią: to zadanie protokołu oceny (P1) i etapów N2 i N3.
- Karta celów i charakteru (`docs/KARTA_AGENTA.md`) jest dokumentem; do promptów wejdzie dopiero w N3.

## Wdrożenie

**1.11.2026, 15:04 RO (13:04 UTC), `b6271bc` → `b1d0f18`.** Pełny zestaw na serwerze: 24 czerwone = baza, zero nowych (wcześniej jeden nowy, atrapa ze starym podpisem `dane_maniery`: lokalne testy celowane nie zastępują pełnego zestawu na serwerze). Żywy test na prawdziwym dzienniku: ok, 52-82 ms, klucz 0600, zero znaków `@`.

**Pierwszy przebieg produkcyjny (run 549, 19:05-20:14 RO, status DONE, 68 min):**

- 4 rekordy (po jednym na komentarz pod notką), status `ok` 4/4, `latency_ms` p50 63, p95 66, max 66; zero znaków `@`; jeden `key_id`; `run_id` 549 istnieje w `runs`; `mode` produkcja, `publish_run` true; w logu 4 linie `[cien] rekord status=ok` i żadnej `nie zapisalem` ani `zapis nieudany`.
- Brak wycieku tekstów celów: 15 charakterystycznych słów z trzech losowych komentarzy, żadne nie występuje w pliku.
- Cień niczego nie zmienił: czas przebiegu 68 min (poprzednie 40 przebiegów dzień-DONE: mediana 90, max 102), proporcja ramion E23 3 on / 1 off (od 29.10: 19 on / 15 off / 8 bez ramienia), `historia_n` = 0 dla trzech komentarzy ramienia „on" zgodne z `n_candidates` profilu „produkcja" = 0.
- Profil „luźny" dał 0 kandydatów, „szeroki" 0/2/4/1: materiał do kalibracji progu N3 (przy progu produkcyjnym pamięć trafia rzadko).

**Wykryta rozbieżność (naprawiona w 5ff6b0c+):** dokument i docstring twierdziły, że `target_hmac` = HMAC wartości `gdzie` z dziennika. Na produkcji 0 z 5 wpisów łączyło się po `target_hmac`: komentarze pod notkami dziennik zapisuje jako `note/c-<id>` (`browser.wystaw_odpowiedz`), a cień haszował pełny adres `https://substack.com/note/c-<id>`. Test z wersji pierwszej sprawdzał tylko artykuł (pełny adres), więc tego nie widział. Dodano `query.target_hmac_gdzie` (z `gdzie_dziennika`) oraz test sprzężenia ze źródłem `browser.py`. Cztery rekordy z przebiegu 549 mają tylko `target_hmac`; łączy się je przez prefiks `https://substack.com/` + `gdzie`. Odpowiedzi (`rodzaj: odpowiedz`) nie mają rekordu cienia, bo idą ścieżką bez haka (poza zakresem N1).
