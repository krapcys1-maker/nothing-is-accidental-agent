# Testy płatne i sieciowe — nie są zwykłą regresją

Ten katalog zawiera 13 skryptów Python. Mogą wykonywać prawdziwe wywołania
modeli, publicznej sieci lub generowania obrazu. Nie uruchamiaj ich pętlą i nie
traktuj samego wydruku próbek jako wyniku akceptacyjnego.

## Stan bezpieczeństwa uprzęży

`test_provenance_live.py`, `test_full_pipeline_live.py` oraz
`test_editorial_system_live.py` oraz `test_editorial_continuation_live.py` mają aktualny, jawny kontrakt eksperymentu:
syntetyczny korpus, tryb `model_test`, tymczasową bazę, listę etapów, brak
Substacka i maszynowy wynik. Pozostałe skrypty są materiałem historycznym.
Niektóre używają `/tmp`, domyślnego `config.DB_PATH` albo istniejącego zasiewu;
do czasu N-004 nie są bramką release i nie wolno uruchamiać ich bez uprzedniego
przeniesienia do wspólnego launchera izolacyjnego.

| Plik | Transport lub cel | Status |
|---|---|---|
| `test_provenance_live.py` | modele, zamrożony korpus | aktualny kontrolowany harness |
| `test_full_pipeline_live.py` | modele rdzenia, pełne `run.main`, zamrożone wejście | kontrolowany harness E-010; live nieukończony |
| `test_editorial_system_live.py` | scout, research, styl A/B, rewizja i Notes | kontrolowany harness E-012; 32-call symulacja PASS; live zatrzymany na pierwszym Scoucie |
| `test_editorial_continuation_live.py` | izolowane ramiona Anthropic/DeepSeek | E-014: Anthropic 8/8; DeepSeek zatrzymany; kolejne DeepSeek blokowane przez N-025 |
| `porownanie_v1_v2.py` | pełny potok modeli i obraz | historyczny; brak wspólnego preflightu |
| `test_bibliotekarz.py` | model i domyślna baza | historyczny; może zmienić roboczą bazę V3 |
| `test_fedreg_pelna_sciezka.py` | publiczna sieć i modele | historyczny |
| `test_integracja.py` | pełny płatny przebieg bez publikacji | historyczny |
| `test_notki_ab.py` | dwa modele | historyczny |
| `test_notki_szeroki_material.py` | model | diagnostyczny; brak wyniku maszynowego |
| `test_notki_z_banku.py` | model i domyślna baza | historyczny |
| `test_slepa_ocena_notek.py` | dwa modele | diagnostyczny; brak wyniku maszynowego |
| `test_style.py` | generowanie obrazów | historyczny |
| `test_warto.py` | model i istniejące karty | historyczny |

## Warunki przyszłego uruchomienia

Każdy skrypt dopuszczony ponownie do użycia musi najpierw otrzymać:

1. `AGENT_V3_MODE=model_test`, aktywny capability preflight i zakaz Substacka;
2. tymczasowy katalog danych i nową bazę, bez kopiowania stanu roboczego;
3. jawny plan liczby dispatchy i maksymalnego kosztu;
4. trwałą rezerwację budżetu przed pierwszym dispatch;
5. zamrożone wejście, wersjonowaną rubrykę i jednoznaczny wynik maszynowy;
6. artefakt z surowymi odpowiedziami, tokenami, kosztem i hashami;
7. wpis T-xxx oraz raport w `wnioski badania/06_testy_i_budzet/`.

Budżet dostawcy nie zezwala na podmianę modelu. Test normalnego V3 korzysta z
domyślnego routingu bez `AGENT_V3_CHEAP`, `AGENT_V3_WRITER` ani innego
override. Każde odstępstwo wymaga osobnego, jawnego polecenia; nie wolno
ukrywać go w runtime `MODEL_FOR.update(...)`.

Budżety całego programu badawczego: Anthropic 5 USD, DeepSeek 5 USD i
OpenAI/GPT obrazy 2 USD, zawsze pod wspólnym limitem 10 USD. Znany/estymowany
koszt to 1,41701670 USD, a trzy nierozliczone próby DeepSeek rezerwują łącznie
4,80 USD. Konserwatywna ekspozycja wynosi 6,21701670 USD. Nie uruchamiaj
żadnego kolejnego DeepSeek do rekoncyliacji T-118/T-132/T-136; blokuje go także
kod N-025. Rozdzielenie katalogu nie jest zgodą na wydatek.
