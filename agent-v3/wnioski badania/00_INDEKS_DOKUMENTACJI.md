# Agent V3 — centralny indeks badań i dokumentacji

**Stan:** prototyp badawczy; audyt i projektowanie napraw, bez wdrożenia  
**Data konsolidacji:** 2026-08-21  
**Gałąź robocza:** `codex/agent-v3-gpt`  
**Commit bazowej migawki:** `00ab0c4`  
**Zakres zapisu:** wyłącznie `agent-v3` oraz związany z nim wpis w głównym `.gitignore`  
**Materiał porównawczy:** `agent-v2` wyłącznie do odczytu

## Cel katalogu

Ten katalog jest jednym punktem prawdy o badaniu Agent V3. Zawiera:

- opis działania agenta;
- kompletny audyt i rejestr błędów;
- materiały historyczne i hipotezy wejściowe;
- porównanie z publicznymi repozytoriami;
- plan napraw wykonywanych błąd po błędzie;
- politykę testów i kosztów;
- dziennik badań, wersje badanego korpusu i zasady replikacji.

Nie jest to instrukcja uruchamiania produkcji. Żaden dokument w tym katalogu nie upoważnia do publikowania, wdrażania usług, uruchamiania timerów ani korzystania z żywej sesji Substack.

## Najkrótsza odpowiedź: gdzie jesteśmy

V3 nie trzeba projektować od zera. Rdzeń research–synteza–pisanie–recenzja–bramki–dystrybucja jest rozbudowany, ale system nie jest jeszcze wiarygodną autonomiczną redakcją. Rejestr obejmuje 130 ustaleń: P0=25, P1=90 i P2=15. E-014 wykonało izolowane ramię Anthropic 8/8. E-016 potwierdziło live transport SSE DeepSeek, a E-018 zmieniło jednostkę pracy na uniwersum artykułowe. E-019 ręcznie zatrzymało dwa technicznie zielone wybory, oceniło wszystkie 24 drogi i wskazało RICH orphaned well. E-020–E-022 trzykrotnie zatrzymały discovery po ręcznej kontroli źródeł. E-023 urwało pierwszy stream przed usage; 0,30 USD pozostaje `UNKNOWN`. E-024 niezależnie zaliczyło live fetch 5/6 oraz ręczną jakość tekstu 5/5, po czym A-130 zachowało czas i status dowodu przez dalsze granice; pełna regresja wynosi 57/57. Konserwatywna ekspozycja wynosi 6,93680670/10 USD; DeepSeek jest zablokowany do rekoncyliacji E-023. Nadal zero Substacka.

Karty N-001–N-003, N-005–N-009 i N-017 mają status co najmniej FIXED_OFFLINE;
N-016 naprawia okresowy cennik Sonnet 5, a N-018 dokumentuje fundament łatwej
przyszłej promocji. V3 nie uruchamia V2, ma centralny
rejestr możliwości, odseparowane sekrety i sesję, trwały ledger mutacji,
zamrożoną dobę, bezpieczny transport researchu, 22 wersjonowane kontrakty oraz
pełny graf dokument–fragment–twierdzenie–zdanie–cytowanie. Test provenance
przechodzi 19/19 metod, kontrakty 11/11 i 94/94 podtesty, taryfa 4/4, N-017 7/7,
a N-019 4/4, N-020 7/7, pełny replay N-004 7/7 oraz transakcyjny zapis N-010
7/7. N-023 usunęło blocker CRLF/LF loadera stylu, a N-011 dodało
wersjonowaną pętlę rewizji i kwarantannę. Aktualna regresja obejmuje 57/57
plików.

Pierwszy test modeli live został wykonany bez Substacka i produkcji, ale jego
ramię Anthropic nie było testem normalnej konfiguracji V3. Uprząż bez osobnej
zgody nadpisała w pamięci routing trzech etapów na Sonnet i wykonała cztery
żądania; to błąd autoryzacji oraz metodologii. Standardowa konfiguracja tych
etapów wskazywała DeepSeek. Eksporty potwierdziły 7 dispatchy, 6 kompletnych
odpowiedzi i jedną płatną, lecz niepełną syntezę DeepSeek. Historyczny wynik i
koszt zachowano, automatyczny override usunięto, a test routingu blokuje jego
powrót. Pełny replay offline normalnego V3 jest zielony. Otwarty pozostaje
pełny live. E-014 oddzieliło dostawców: ramię Anthropic jest wykonane, a ramię
DeepSeek zatrzymało się na pierwszym Scoucie. E-015 obaliło hipotezę, że główną
przyczyną jest sam rozmiar promptu, i dodało offline transport SSE. E-016
potwierdziło ten transport live, E-017 rozdzieliło feasibility i discovery, a
E-018 zbadało samą jakość Scouta oraz wykryło lukę capu kosztowego.

## Zalecana kolejność czytania

1. [`../AGENTS.md`](../AGENTS.md) — obowiązująca instrukcja wejścia kolejnego agenta.
2. [`01_audyt/AUDYT_STANU_BIEZACEGO_V3_2026-08-21.md`](01_audyt/AUDYT_STANU_BIEZACEGO_V3_2026-08-21.md) — pełny ponowny audyt aktualnego kodu po fundamentach.
3. [`01_audyt/MACIERZ_ODZIEDZICZENIA_V2_V3.md`](01_audyt/MACIERZ_ODZIEDZICZENIA_V2_V3.md) — co już istnieje w V2/V3 i czego nie budować ponownie.
4. [`01_audyt/DOKUMENTACJA_AUDYTU.md`](01_audyt/DOKUMENTACJA_AUDYTU.md) — skrót wyniku audytu.
5. [`01_audyt/MAPA_DZIALANIA_AGENTA_V3.md`](01_audyt/MAPA_DZIALANIA_AGENTA_V3.md) — jak agent działa i gdzie przebiegają granice odpowiedzialności.
6. [`01_audyt/MONOGRAFIA_AUDYTOWA_V3.md`](01_audyt/MONOGRAFIA_AUDYTOWA_V3.md) — pełna praca audytowa.
7. [`01_audyt/SPOSTRZEZENIA_AUDYTOWE.md`](01_audyt/SPOSTRZEZENIA_AUDYTOWE.md) — 130 ustaleń z priorytetami oraz statusem napraw offline/live.
8. [`01_audyt/AUDYT_PROMPTOW_I_GLOSU_REDAKCYJNEGO.md`](01_audyt/AUDYT_PROMPTOW_I_GLOSU_REDAKCYJNEGO.md) — role agentów, kontrakty promptów, styl pisania i dziedziczenie z V2.
9. [`04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md`](04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md) — zweryfikowane inspiracje z publicznego kodu.
10. [`04_badania_porownawcze/ANALIZA_10_ARTYKULOW_I_10_NOTES_SUBSTACK_2026-08-21.md`](04_badania_porownawcze/ANALIZA_10_ARTYKULOW_I_10_NOTES_SUBSTACK_2026-08-21.md) — publiczny benchmark 10 artykułów i 10 Notes oraz porównanie z E-018/E-014.
11. [`05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md`](05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md) — kolejność poprawiania V3 błąd po błędzie.
12. [`06_testy_i_budzet/POLITYKA_TESTOW_I_BUDZETU.md`](06_testy_i_budzet/POLITYKA_TESTOW_I_BUDZETU.md) — co wolno uruchamiać i za ile.
13. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-001_FUNDAMENT_IZOLACJI.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-001_FUNDAMENT_IZOLACJI.md) — projekt, nieudane próby, wyniki i ograniczenia pierwszej naprawy.
14. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-002_LEDGER_MUTACJI.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-002_LEDGER_MUTACJI.md) — maszyna stanów, restart, potwierdzenia i kwarantanna UNKNOWN.
15. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-003_DOBA_I_BUDZET.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-003_DOBA_I_BUDZET.md) — wspólna strefa, zamrożony plan, atomowy budżet i kontrdowody awarii.
16. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-004_BEZPIECZNY_FETCH.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-004_BEZPIECZNY_FETCH.md) — threat model SSRF, DNS pinning, exact URL, limity zasobów i ograniczenia dowodu offline.
17. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-005_WERSJONOWANE_SCHEMATY_LLM.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-005_WERSJONOWANE_SCHEMATY_LLM.md) — 22 kontrakty, parser ścisły, telemetria i autonomiczne fallbacki fail-closed.
18. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md) — graf pochodzenia, zdania MIXED, liczby i trwały ledger offline.
19. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md) — prawdziwe modele, surowe wyniki, koszt, awaria DeepSeek oraz errata nieuprawnionego override Sonnet.
20. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-008_LEDGER_ZDALNEGO_SZKICU.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-008_LEDGER_ZDALNEGO_SZKICU.md) — kontrdowód kolejności, manifest szkicu, restart i osobna publikacja bez Substacka.
21. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-009_ATOMOWA_REZERWACJA_KOSZTU_MODELU.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-009_ATOMOWA_REZERWACJA_KOSZTU_MODELU.md) — konkurencyjny kontrdowód 0,50/0,25 USD i atomowy check-and-reserve.
22. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-010_PELNY_REPLAY_POTOKU.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-010_PELNY_REPLAY_POTOKU.md) — zwykłe `run.main` na pełnym replayu, ujemna awaria i fail-closed preflight live.
23. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-011_TRANSAKCYJNY_ZAPIS_ARTYKULU.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-011_TRANSAKCYJNY_ZAPIS_ARTYKULU.md) — fault injection, atom plik–DB–rewizja–provenance i restart-safe recovery.
24. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-012_PELNY_SYSTEM_REDAKCYJNY_LIVE.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-012_PELNY_SYSTEM_REDAKCYJNY_LIVE.md) — pełny plan live ról, koszt, preflight, symulacja i finding blokera stylu.
25. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-013_AUTONOMICZNA_REWIZJA_I_KWARANTANNA.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-013_AUTONOMICZNA_REWIZJA_I_KWARANTANNA.md) — wersjonowana polityka, dwie iteracje, pełne rechecki i terminalna kwarantanna.
26. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-014_RAMIONA_DOSTAWCOW_STYL_REWIZJA_NOTES.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-014_RAMIONA_DOSTAWCOW_STYL_REWIZJA_NOTES.md) — live Fable/Opus, ręczna analiza tekstów, styl A/B, rewizja, Notes oraz druga awaria Scouta.
27. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-015_SKROCONY_SCOUT_I_TRANSPORT_SSE.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-015_SKROCONY_SCOUT_I_TRANSPORT_SSE.md) — trzecia awaria live, test hipotezy rozmiaru promptu i rygorystyczny transport SSE offline.
28. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-018_SCOUT_UNIWERSA_ARTYKULOW.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-018_SCOUT_UNIWERSA_ARTYKULOW.md) — pełny live Scout: wszystkie pomysły, drogi artykułowe, raw hashe, V2/V3, ręczna ocena i budżet.
29. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-019_RECZNY_AUDYT_SCOUTA_I_WYBOR_DROGI.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-019_RECZNY_AUDYT_SCOUTA_I_WYBOR_DROGI.md) — dwa ręczne FAIL, wszystkie 24 oceny dróg, finalny temat RICH, źródła i koszt.
30. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-020_LIVE_DISCOVERY_I_RECZNY_AUDYT_ZRODEL.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-020_LIVE_DISCOVERY_I_RECZNY_AUDYT_ZRODEL.md) — pełny prompt i raw hashes, 10 kandydatów, ręczny FAIL 22/8, źródła brakujące oraz budżet.
31. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-021_TWARDY_LIMIT_I_RECZNY_AUDYT_DISCOVERY.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-021_TWARDY_LIMIT_I_RECZNY_AUDYT_DISCOVERY.md) — live limit 6/8, pełne 10 źródeł i ręczny FAIL jakości.
32. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-022_ROLE_DOWODOWE_I_FAIL_SECOND_ACT.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-022_ROLE_DOWODOWE_I_FAIL_SECOND_ACT.md) — live 8/8, role dowodowe, dokładne URL-e, pełny audyt propozycji i brak `SECOND_ACT`.
33. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-023_NIEPELNY_STREAM_I_TRACE_REQUESTU.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-023_NIEPELNY_STREAM_I_TRACE_REQUESTU.md) — urwany stream, koszt `UNKNOWN`, zero retry i naprawa śladu requestu.
34. [`06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-024_LIVE_SAFE_FETCH_CANARY.md`](06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-024_LIVE_SAFE_FETCH_CANARY.md) — live safe-fetch 5/6, ręczna kontrola pięciu pełnych tekstów i temporalna wada provenance.
35. [`05_plan_napraw/karty/N-025_STREAMING_I_REKONCYLIACJA_DEEPSEEK.md`](05_plan_napraw/karty/N-025_STREAMING_I_REKONCYLIACJA_DEEPSEEK.md) — historia trzech `UNKNOWN` i kryteria rekoncyliacji.
36. [`05_plan_napraw/karty/N-026_STREAMING_RESPONSES_DEEPSEEK.md`](05_plan_napraw/karty/N-026_STREAMING_RESPONSES_DEEPSEEK.md) — SSE dla normalnego discovery `/responses`.
37. [`05_plan_napraw/karty/N-027_SCOUT_UNIWERSA_ARTYKULOW.md`](05_plan_napraw/karty/N-027_SCOUT_UNIWERSA_ARTYKULOW.md) — nowy kontrakt jakości pomysłu i ograniczenia dowodu live.
38. [`05_plan_napraw/karty/N-028_TWARDY_CAP_KOSZTU_FAKTYCZNEGO.md`](05_plan_napraw/karty/N-028_TWARDY_CAP_KOSZTU_FAKTYCZNEGO.md) — przekroczenie 0,04→0,049298 USD i wymagany wspólny limit wyjścia.
39. [`05_plan_napraw/PLAN_PROMOCJI_V3_DO_PRODUKCJI.md`](05_plan_napraw/PLAN_PROMOCJI_V3_DO_PRODUKCJI.md) — manifest, migracje, shadow/canary i atomowy rollback bez bieżącego wdrożenia.
40. [`06_testy_i_budzet/artefakty/E-007_rekonsyliacja_dostawcow/README.md`](06_testy_i_budzet/artefakty/E-007_rekonsyliacja_dostawcow/README.md) — hashe załączników i rekoncyliacja 7 wywołań.
41. [`06_testy_i_budzet/REJESTR_WYNIKOW_TESTOW.md`](06_testy_i_budzet/REJESTR_WYNIKOW_TESTOW.md) — komplet prób PASS i FAIL.
42. [`07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md`](07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md) — metoda, poziomy dowodu i ograniczenia.

## Struktura katalogu

| Katalog | Rola | Status epistemiczny |
|---|---|---|
| `01_audyt/` | audyt bazowy i bieżący, mapa reuse V2/V3, 130 ustaleń, audyt promptów i aneks techniczny | obserwacja kodu, eksperymentów i wnioski audytora |
| `02_dokumentacja_zastana/` | dokumenty skopiowane lub przeniesione z wcześniejszego etapu projektu | materiał historyczny; nie zawsze aktualny kontrakt V3 |
| `03_materialy_wejsciowe/` | wcześniejsze propozycje i notatki z internetu wraz z ich krytyczną analizą | źródło hipotez, nie dowód |
| `04_badania_porownawcze/` | datowane badania publicznych repozytoriów oraz benchmark 10 artykułów i 10 Notes Substack | dowód źródłowy + jawne inferencje |
| `05_plan_napraw/` | backlog, wykonane fundamenty, N-010/N-019/N-020/N-023 i plan promowalności N-018 | plan oraz dowody zmian |
| `06_testy_i_budzet/` | matryca, budżety, rejestr prób, artefakty i raporty E-001–E-024 | polityka oraz wyniki eksperymentów |
| `07_dziennik_badan/` | chronologia, metoda, migawki i decyzje | ślad replikacyjny |

## Dokumentacja zastana

Dokumenty w `02_dokumentacja_zastana/` zostały zachowane, ponieważ opisują genezę i wcześniejszy model działania. Nie wolno automatycznie traktować ich jako aktualnej instrukcji V3. Szczególnie ostrożnie należy czytać pliki z nazwą V2, komendy wdrożeniowe i stwierdzenia, że „nic nie blokuje”. Aktualny stan ustala audyt, a nie wiekowy opis.

## Dokumentacja operacyjna pozostawiona przy kodzie

Niektóre pliki Markdown są jednocześnie wejściami wykonywalnymi albo instrukcjami ściśle związanymi z lokalizacją kodu. Nie zostały przeniesione, aby nie zmienić zachowania prototypu:

- `agent-v3/prompts/*.md` — aktywne prompty i polityki treści;
- `agent-v3/tests/URUCHOM.md` — instrukcja testów lokalnych;
- `agent-v3/tests/platne/PRZECZYTAJ.md` — ostrzeżenia przy testach płatnych;
- `agent-v3/pomiary/PRZECZYTAJ.md` — instrukcja pomiaru sieciowego;
- pliki Markdown w `tests/fixtures/` — dane testowe, nie dokumentacja projektu.

Są skatalogowane w aneksie audytu i pozostają częścią badanego korpusu.

## Zasady nadrzędne

1. V2 jest materiałem porównawczym i nie wolno go modyfikować, formatować, stage'ować ani commitować.
2. Naprawy mogą dotyczyć tylko V3.
3. Offline jest domyślnym trybem testu.
4. Dostęp do internetu nie oznacza zgody na zmianę konta zewnętrznego.
5. Nie wolno publikować, tworzyć żywych draftów, lajkować, komentować, restackować, obserwować, subskrybować ani wdrażać produkcji.
6. Każda naprawa ma własną hipotezę, test kontrdowodu, test regresji i wpis w dzienniku.
7. „Kliknięto” nie znaczy „wykonano”; sukces wymaga potwierdzenia u źródła i powiązania z konkretną próbą.
8. Brak danych nie może być zapisywany jako zero ani sukces.
9. Reguły redakcyjne mogą aktualizować się autonomicznie wyłącznie po spełnieniu wersjonowanego kontraktu: minimalna próba, stabilność w czasie, kontrprzykład, ograniczony rollout i automatyczny rollback.
10. Dokumenty rozróżniają fakt, inferencję, hipotezę i decyzję projektową.

## Konwencja dowodowa

- **Fakt F** — bezpośrednio odtworzony z lokalnego kodu, testu, historii Git albo wskazanego źródła pierwotnego.
- **Inferencja I** — logiczny wniosek z jednego lub kilku faktów; musi być oznaczony jako wniosek.
- **Hipoteza H** — przypuszczenie wymagające eksperymentu.
- **Decyzja D** — świadomy wybór projektowy, którego nie da się wyprowadzić wyłącznie z danych.

## Stan Git i publikacji

Gałąź `codex/agent-v3-gpt` jest gałęzią prototypową. W trakcie badań nie
wykonano push, publikacji, release'u, obrazu produkcyjnego ani skryptu
wdrożeniowego. Lokalna nazwa gałęzi nie jest zgodą na wysłanie jej gdziekolwiek.

Commit `00ab0c4` jest punktem bazowym badanego prototypu. Nie oznacza, że ustalenia zostały naprawione; oznacza, że bazowy przedmiot badania ma stabilny identyfikator w historii. A-084 i A-085 powstały później podczas eksperymentów E-003/E-004 i mają własne ślady kontrdowodu.

Do commitu wolno włączać tylko potwierdzone ścieżki V3 oraz związane z V3 reguły ignorowania danych. Istniejące zmiany w `agent-v2` są poza zakresem.

## Następny krok

N-027 ma jeden pełny live Scout, exact raw replay 6/6 oraz dwa normalne live
feasibility. E-019 oceniło 24/24 dróg, ręcznie zatrzymało dwa pozornie zielone
wybory i na tym samym raw po naprawie wskazało `Afterlife`/orphaned well jako
RICH. E-020–E-022 nie zaliczyły ręcznej bramki discovery, więc fetch, synteza,
artykuł i Notes słusznie nie powstały. E-023 wysłało pierwszy request, ale
stream urwał się przed usage; selector nie wystartował, retry=0 i 0,30 USD
pozostaje `UNKNOWN`. E-024 niezależnie zaliczyło aktywny fetch 5/6 i ręczną
jakość 5/5 bez modeli; nie zalicza to discovery. A-130 zachowuje metadane czasu,
statusu i roli dowodu przez classify, synthesis i provenance, z dowodem offline
107/107 oraz pełną regresją 57/57. DeepSeek ma 5,53877270 USD konserwatywnej ekspozycji, a
cały program 6,93680670/10 USD. Następną czynnością jest rekoncyliacja E-023;
do tego czasu żaden kolejny call DeepSeek nie jest dopuszczony. Po
rekoncyliacji wolno wrócić wyłącznie do discovery wybranej drogi, z wpisem
przed i po callu, zero retry, ręcznym audytem wszystkich URL-i i bez Substacka.
A-115 wymaga rozdzielenia celów Notes przed przyszłą naprawą. Dla
późniejszej promocji N-018 wymaga numerowanych migracji i offline release
manifestu, a N-022 wspieranego kontraktu auth/backup. Stany niepewne przechodzą
do automatycznej rekoncyliacji lub kwarantanny, nigdy do publikacji przez
fallback.
