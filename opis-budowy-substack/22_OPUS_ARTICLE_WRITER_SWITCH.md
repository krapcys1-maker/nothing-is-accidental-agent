# OPUS ARTICLE_WRITER SWITCH

## Dlaczego zmieniliśmy model, ale nie wynik

Pierwsza realna kwalifikacja Fable zakończyła się odmową providera. System zapisał ją jako `FAIL / PROVIDER_REFUSAL`, razem z 151 tokenami wejścia, 3 tokenami wyjścia i kosztem `0.001660 USD`. Nie było retry. Nie było fallbacku. Nie powstała capability ani aktywacja.

Właściciel podjął więc nową decyzję dotyczącą przyszłości: primary family dla `ARTICLE_WRITER` ma być Opus. Ta decyzja nie zmienia przeszłości. Fable pozostaje w rejestrze i historii dokładnie z tym wynikiem, który naprawdę zwrócił provider.

## Co zmieniło się technicznie

Rdzeń routingu już obsługiwał rodziny modeli, więc nie potrzebował przebudowy. Zmieniliśmy kanoniczne mapowanie `ARTICLE_WRITER` z `FABLE` na `OPUS`, dodaliśmy jawny krok schematu `0031` i uogólniliśmy wąski caller kwalifikacyjny tak, by miał dwa osobne zamrożone kontrakty: historyczny Fable oraz bieżący Opus.

Opus ma w repo własną frozen identity: family `OPUS`, logical version `5`, technical ID `claude-opus-5`, pricing ref `anthropic-opus-5-standard-2026-08`, global inference i standard-only request tier. Same dane katalogowe nie są jednak kwalifikacją.

## Najważniejsze „nie”

Po zmianie Opus nie stał się automatycznie `PASS`, `ACTIVE` ani live-ready. Nowy intent writer’a przed osobną kwalifikacją i aktywacją kończy się fail-closed. Produkcyjna baza nie została zmigrowana. Nie wykonano realnego API, sieci, browsera ani publikacji.

Test migracji utrwala najważniejszą własność: istniejący frozen intent Fable nadal zwraca dokładnie dawny binding po przełączeniu polityki. Nowe decyzje nie przepinają starych działań na inny model.

## Nieudana pierwsza regresja

Pierwszy pełny przebieg miał 25 czerwonych testów. Nie ujawniły one dziury w bramkach produkcyjnych. Ujawniły, że historyczne fixture Fable były uruchamiane pod nową polityką Opus, a część starych asercji nadal liczyła 30 migracji. Rozdzieliliśmy historyczny kontrakt 0030 od bieżącego 0031 i dopisaliśmy nowy szczebel do oczekiwań. Żadna bramka nie została osłabiona.

## Stan kandydacki

Kod jest kandydatem do niezależnego review. Kolejne kroki — produkcyjna migracja 0030→0031 i realna kwalifikacja Opusa — wymagają osobnych decyzji właściciela. Dopiero prawdziwy `PASS` może otworzyć drogę do capability, aktywacji i nowych bindingów.
