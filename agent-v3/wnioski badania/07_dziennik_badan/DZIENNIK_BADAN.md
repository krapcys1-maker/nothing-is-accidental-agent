# Dziennik badań Agent V3

## 2026-08-21 — audyt bazowy

**Działania:** zinwentaryzowano V3, odtworzono przepływ artykułu i dnia, przeanalizowano bazę, pliki stanu, prompty, testy, konfigurację, przeglądarkę i historyczną dokumentację V2.  
**Wynik:** 73 ustalenia A-001–A-073; 14 P0, 43 P1, 16 P2.  
**Koszt modeli:** 0 USD.  
**Mutacje zewnętrzne:** brak.  
**V2:** tylko odczyt.

Kontrole bazowe:

- 117 plików w migawce przed dodaniem dokumentacji;
- 59 plików Python sparsowanych przez AST;
- 0 błędów składni;
- 12 głównych modułów i 11 239 linii;
- 36 zwykłych plików testowych i 10 skryptów testów płatnych;
- identyfikatory A-001–A-073 ciągłe i bez duplikatów;
- odciski dwunastu modułów zgodne z aneksem.

## 2026-08-21 — konsolidacja dokumentacji

**Działania:** utworzono `agent-v3/wnioski badania`; przeniesiono dokumentację audytu, dokumentację zastaną, materiał historyczny V2 oraz dwa materiały wejściowe. Utworzono centralny indeks, metodologię, politykę testów i plan napraw.  
**Powód:** jeden punkt prawdy i rozdzielenie aktualnego audytu od historycznych instrukcji operacyjnych.  
**Zmiany funkcjonalne:** brak.  
**Mutacje zewnętrzne:** brak.  
**V2:** brak zapisu.

Pliki będące aktywnymi promptami albo instrukcjami związanymi ze ścieżką wykonawczą pozostawiono przy kodzie. Ich przeniesienie mogłoby zmienić zachowanie lub utrudnić bezpieczne uruchamianie testów.

## 2026-08-21 — kwerenda repozytoriów podobnych

**Działania:** zweryfikowano sześć projektów wskazanych w materiale wejściowym i jedno nieoficjalne repozytorium referencyjne API. Odczytano README oraz wybrane implementacje bezpieczeństwa, analityki, uczenia, publikacji, logowania i testów. Utrwalono hashe HEAD i daty commitów.  
**Tryb:** płytkie kopie publicznego kodu w katalogu tymczasowym; bez instalacji i wykonania kodu.  
**Koszt modeli:** 0 USD.  
**Mutacje kont:** brak.

Najważniejsze wyniki:

1. Pętla uczenia z `substack-growth-engine-template` zachowuje oryginalny draft, porównuje go z wersją końcową i przenosi reguły głosu, ale jej zależność od zewnętrznej akceptacji, dopasowanie treści oraz brak testów czynią ją niezgodną z celem pełnej autonomii. Do V3 nadaje się sam wzorzec niezmiennego oryginału i różnicy przed/po.
2. `substack-mcp` pokazuje wartościowy wzorzec jawnych klas możliwości, opisów działań natychmiast publicznych, typowanych błędów, timeoutów i testów kontraktu. Jego ograniczenia publikacyjne nie są docelową polityką V3.
3. `substack-author-agent` pokazuje wspólne instrukcje dla kilku SDK i obserwowalność kosztów/tool calli, ale jest doradcą, nie autonomiczną redakcją.
4. `kyarminrox/substack-agent` ma scentralizowane selektory, JSONL i screenshoty, lecz deklaruje się jako scaffolding v0.1 i domyślnie ustawia `SAFE_MODE=false`; nie jest wzorcem bezpiecznej wartości domyślnej.
5. `santhosh-patel/substack-agent` ma wspólną warstwę MCP/API i autoryzację, ale udostępnia natychmiastowe publikowanie oraz automatyczne komentarze; interfejs narzędziowy nie zastępuje polityki autonomii.
6. `drona23/substack-ai-bot` jest liniowym generatorem draftów bez porównywalnej pamięci, bramek i testów; nie jest punktem odniesienia dla docelowej pętli redakcyjnej.
7. `substack-api-reference` jest użytecznym zeszytem obserwacji endpointów, ale sam autor oznacza API jako nieoficjalne i zmienne; V3 musi mieć adapter, testy kontraktowe i degradację, nie rozsiane wywołania.

Pełne dane znajdują się w `../04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md`.

## Kolejny wpis

Następny wpis powstaje przed rozpoczęciem pierwszej naprawy funkcjonalnej. Musi zawierać identyfikator błędu, stan przed zmianą, test kontrdowodu, plan rollbacku oraz potwierdzenie, że ścieżki V2 są poza staged diff.

## 2026-08-21 — korekta celu i kontrola integralności dokumentacji

**Korekta celu:** docelowy V3 ma być w pełni autonomiczny. Z aktualnej specyfikacji usunięto zewnętrzne bramki akceptacyjne. Wprowadzono automatyczne stany kwarantanny, pełną ponowną kontrolę po rewizji, reguły rollout/rollback i koniunkcyjną decyzję publikacyjną. Materiały historyczne pozostają niezmienione jako źródła, ale nie są aktywnym kontraktem.  
**Kontrole:** 25 plików Markdown w katalogu badawczym; 0 uszkodzonych lokalnych linków; 73 unikalne identyfikatory A-001–A-073; 0 brakujących identyfikatorów; 59/59 plików Python poprawnych składniowo według AST; 12/12 odcisków głównych modułów zgodnych z aneksem; 0 plików o nazwach sesji/sekretów i 0 plików pasujących do wzorca jawnie przypisanego sekretu w V3.  
**Kod funkcjonalny:** bez zmian w tej fazie.  
**Koszt modeli:** 0 USD.  
**V2:** istniejące zmiany wykryte, lecz nie dotknięte i niewłączone do zakresu.
