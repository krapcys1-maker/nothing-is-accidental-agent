# Cień pamięci (etap N1), 1.11.2026

Zlecenie właściciela (1.11): konto NIE ma być kontem badawczym nad pamięcią; bot ma mieć osobowość, wspomnienia, uczyć się na bieżąco i mieć własne cele. Plan etapów jest uzgodniony z sesją badawczą „Pamięć LLM" (`D:\Pamiec LLM\WSPOLNY_PLAN.md`, wersja 1.1): N1 to wyłącznie **cień**, czyli zapis tego, co wstrzyknęłaby pamięć, bez żadnego wpływu na teksty. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Co robi

Dla każdego komentarza (oba ramiona E23, oba bloki komentarzy w `run.py`) `pamiec_cien.cien_komentarza` liczy, jakie wpisy własnej, opublikowanej historii zwróciłaby `historia_konta.powiazane` przy trzech progach: produkcyjnym (dokładnie `HISTORIA_KONTA_*`, czyli to, co dostaje E23 „on") oraz dwóch luźniejszych (`PAMIEC_CIEN_PROFILE`), i dopisuje jeden rekord do `data/pamiec_cien.jsonl`. Bez modelu, bez sieci, ok. dziesiątek milisekund na komentarz.

Rekord (uzgodniony z sesją badawczą, `WSPOLNY_PLAN.md` §5): tożsamość (`record_id`, `schema_version`, `code_commit`, `run_id` natywny, `occurred_at`, `task_type`, `arm_e23`, `active_experiments`), czas i korpus (`as_of`, `index_snapshot`: rozmiar puli, najnowszy wpis, okno, rozmiar dziennika), zapytanie jako skrót kluczowany HMAC-SHA256 i długość (autor też skrót), strategia (`config_digest`, bez embeddera), wyniki dla trzech profili (`item_id`, rodzaj, wiek, ranga, wynik, liczba rzadkich terminów, szacunek tokenów; agregaty), `would_arm` z zamrożonej funkcji losowania (nieużywany), `status`/`error_code`, `latency_ms`.

## Czego NIE robi

- Nie zmienia żadnego tekstu, wyboru celu, ramienia ani wyniku `dane_maniery` (test: słownik zwracany i słownik celu identyczne z cieniem, z awarią cienia i z wyłączonym).
- Nie zapisuje tekstu celu, nazwy autora ani adresu (tylko skróty kluczowane; klucz w `data/.cien_klucz`, tryb 0600, poza repozytoriami), nie zapisuje tekstów wpisów historii (tylko skrót id), nie zapisuje wyników (`skutek`, statystyk).
- Nie zapisuje promptów (hak na `llm.call` to osobna decyzja właściciela; dziś nie).
- Nie zatrzymuje komentarza: każdy wyjątek jest połykany (fail-open); błąd liczenia zostawia rekord ze `status: error`.

## Wyłączenie i wycofanie

`config.PAMIEC_CIEN = False` (wymaga wdrożenia) albo `git reset --hard <poprzednia wersja>` na serwerze. W `NIA_TRYB=test` moduł nie pisze do pliku domyślnego. Limity: 2 s na rekord (status `timeout`), 25 MB na plik (potem przestaje pisać, jeden komunikat w logu).

## Zmiany w istniejącym kodzie

- `historia_konta.powiazane`: opcjonalne `min_podobienstwa`, `min_rzadkich`, `ile`, `statystyki`; wynik niesie `rzadkie`. Domyślne zachowanie bez zmian (test: jawne progi równe `config` dają ten sam wynik; 113 testów E23 bez zmian poza jedną asercją o tekście wywołania).
- `run.dane_maniery`: parametry `run_id` i `zadanie`, wywołanie `pamiec_cien.cien_komentarza` w `try/except` przed rozgałęzieniem on/off.
- `config.py`: `PAMIEC_CIEN`, `PAMIEC_CIEN_PROFILE`, `PAMIEC_CIEN_PULA`.

## Dowody i ograniczenia

- Testy: `tests/test_pamiec_cien.py` (40 sprawdzeń), `tests/test_maniera_komentarza.py` (113); mutacje `robocze/mutacje_cien.py` (26 zepsuć kodu; wynik w sekcji „Wdrożenie”).
- Zapytanie cienia to tytuł i tekst celu, tak jak w `dane_maniery`; `journal_ref` jest `null` (wpis dziennika powstaje dopiero po publikacji), więc łączymy po czasie i skrócie zapytania.
- Cień mierzy tylko, co zwróciłaby pamięć leksykalna (cosinus wag idf). Nie mówi, czy komentarz byłby lepszy z pamięcią: to zadanie protokołu oceny (P1) i etapów N2 i N3.
- Karta celów i charakteru (`docs/KARTA_AGENTA.md`) jest dokumentem; do promptów wejdzie dopiero w N3.
- Dane na serwerze zawierają skróty zapytań do komentarzy. Katalog `data/` jest ignorowany przez Git, a repo NIE jest publiczne, więc pliku `pamiec_cien.jsonl` ani klucza nie wolno commitować ani kopiować do żadnego repo.
