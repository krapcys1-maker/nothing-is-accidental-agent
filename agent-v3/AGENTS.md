# Agent V3 — instrukcja wejścia do pracy

Ten katalog jest prototypem badawczym autonomicznego agenta redakcyjnego. Nie
buduj nowego agenta. Stabilizuj i rozwijaj istniejący potok V2/V3 jedną
udowodnioną własnością naraz.

## Nienaruszalny zakres

1. Zmieniaj wyłącznie `agent-v3`.
2. `agent-v2` jest tylko do odczytu. Nie formatuj, nie naprawiaj, nie stage'uj i
   nie commituj żadnego jego pliku.
3. Stan V2, który trzeba zachować dokładnie:
   - `agent-v2/run.py`: istniejący diff `61/10`, SHA-256
     `047D99A9E528C2DA02196F0C17C03D363F5E04D2B276703824C50B4593F1198F`;
   - `agent-v2/stages.py`: istniejący diff `21/4`, SHA-256
     `4CD67809D76A39B35F3B80242F0053041B6ED00638C0B6A2500D0FADC771A1CA`;
   - `agent-v2/tests/test_rytm_zegar.py`: istniejący plik nieśledzony, SHA-256
     `4CDF113EDC3FA6437A4204D6D3E05FE243898A9424281FEE61842EAEA588CA5D`.
4. V3 nie jest produkcją. Nie publikuj, nie twórz zdalnych szkiców, nie używaj
   żywej sesji, nie lajkuj, nie komentuj, nie restackuj, nie obserwuj, nie
   subskrybuj, nie wdrażaj, nie uruchamiaj systemd i nie wykonuj push/release.
5. Nie osłabiaj `TO_JEST_KOPIA_TESTOWA`, capability gates, kill switcha,
   inertnych unitów systemd ani `wdroz.sh`.
6. Docelowy bot jest w pełni autonomiczny. Wynik ma być maszynowo wybierany,
   poprawiany, kwarantannowany, mierzony i wycofywany. Nie dodawaj zewnętrznej
   bramki akceptacji treści.
7. Wszystkie ustalenia, plany, próby, porażki i wyniki zapisuj w
   `wnioski badania/`. Kod bez śladu badawczego jest pracą niedokończoną.

## Najpierw przeczytaj — w tej kolejności

1. `wnioski badania/00_INDEKS_DOKUMENTACJI.md`
2. `wnioski badania/01_audyt/AUDYT_STANU_BIEZACEGO_V3_2026-08-21.md`
3. `wnioski badania/01_audyt/MACIERZ_ODZIEDZICZENIA_V2_V3.md`
4. `wnioski badania/01_audyt/MAPA_DZIALANIA_AGENTA_V3.md`
5. `wnioski badania/01_audyt/SPOSTRZEZENIA_AUDYTOWE.md`
6. `wnioski badania/01_audyt/AUDYT_PROMPTOW_I_GLOSU_REDAKCYJNEGO.md`
7. `wnioski badania/04_badania_porownawcze/ANALIZA_10_ARTYKULOW_I_10_NOTES_SUBSTACK_2026-08-21.md`
8. `wnioski badania/05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md`
9. kartę konkretnej naprawy z `wnioski badania/05_plan_napraw/karty/`
10. `wnioski badania/06_testy_i_budzet/POLITYKA_TESTOW_I_BUDZETU.md`
11. `wnioski badania/06_testy_i_budzet/REJESTR_WYNIKOW_TESTOW.md`
12. `wnioski badania/07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md`
13. `wnioski badania/05_plan_napraw/PLAN_PROMOCJI_V3_DO_PRODUKCJI.md`

Potem przeczytaj kod związany z wybraną kartą oraz odpowiednik w V2. Odczyt V2
ma odpowiedzieć, co już istnieje; nie jest zgodą na zmianę V2.

## Aktualny stan dowodowy

- Gałąź lokalna: `codex/agent-v3-gpt`; nic nie zostało opublikowane ani
  wdrożone.
- Rejestr: A-001–A-130, w tym P0=25, P1=90, P2=15.
- Fundamenty co najmniej `FIXED_OFFLINE`: N-001–N-003, N-005–N-009 i N-017.
- N-004 ma pełny replay offline 7/7. Po E-024 finalna regresja całego
  bezpiecznego korpusu wynosi 57/57.
- E-007: 7 dispatchy modeli, 6 kompletnych odpowiedzi, 1 płatna niepełna;
  łączny koszt znany/estymowany 0,07558670 USD.
- N-019 ma dowód offline: 4/4 testy celu i pełna regresja 45/45 plików PASS;
  żywa platforma nie była użyta.
- N-020 ma dowód atomowości offline, ale E-018 ponownie otworzyło zakres capu
  faktycznego: rezerwacja 0,04 USD została rozliczona na 0,049298 USD. N-028
  ma lokalną odmowę worst-case dla Scout-only; wspólny runtime pozostaje open.
- N-010 ma dowód offline: 7/7 metod fault injection, pełną regresję 48/48 i
  transakcyjny atom plik–DB–rewizja–provenance. Zanik zasilania nadal nie jest
  udowodniony.
- N-011 ma dowód offline: 13/13 scenariuszy decyzji i pętli, pełny replay 7/7
  oraz regresję 50/50. Stany końcowe to `READY_AUTONOMOUS`,
  `QUARANTINED_EVIDENCE` i `QUARANTINED_EDITORIAL`; kalibracja polityki i
  prawdziwy model rewizji pozostają otwarte.
- E-014 rozdzieliło dostawców, aby awaria DeepSeek nie ukryła pozostałych ról.
  Anthropic wykonał 8/8 dispatchy: dwa artykuły Fable (styl i ablacja), jedną
  minimalną rewizję Fable i pięć form Notes Opus. Koszt znany to 1,341430 USD.
  Transport oraz schematy przeszły, ale jakość jest tylko częściowa: tekst
  stylowany miał 817 słów przy kontrakcie 900–1250, oba warianty dopisały
  przesłanki nieobecne w zamrożonej karcie, a Notes miały zbieżne otwarcia.
- T-118, T-132 i T-136 wykonały trzy materialnie odmienne live dispatchy
  `scout` na DeepSeek Pro. Wszystkie zakończyły się `incomplete chunked read`
  bez odpowiedzi, usage i request ID. Trzy rezerwy `UNKNOWN` po 1,60 USD dają
  4,80 USD ekspozycji. Skrócenie promptu o 67,5% nie usunęło awarii.
- N-025 zmieniło transport DeepSeek na SSE. E-016 potwierdziło live pełny
  Scout: 2 197/15 714 tokenów, 0,032564 USD. Jakość starego Scouta była ujemna:
  6/6 tematów nasyconych, w tym proceduralny boil-water notice.
- E-017 feasibility przeszło za 0,005868 USD. Discovery `/responses` zakończyło
  się `UNKNOWN` 0,10 USD; N-026 ma parser SSE 4/4 offline.
- E-018: jeden live DeepSeek Pro zwrócił 6 uniwersów artykułowych i 5
  odrzuconych zalążków. Transport/schema PASS, exact raw replay 6/6 PASS.
  Live użył jeszcze starego system promptu; jego otwarta wersja ma tylko dowód
  offline. Raport zawiera wszystkie pomysły i drogi artykułowe.
- T-162: publiczny, odczytowy benchmark 10 artykułów i 10 Notes potwierdził
  wartość konkretnych wejść Scouta, ale nie dowiódł downstreamu. Ujawnił A-115:
  prompt Notes miesza zasięg, rozmowę i konwersję jedną rubryką.
- E-019: exact raw E-018 przeszedł dwa live feasibility Flash. F1 kosztował
  0,020601 USD i został ręcznie odrzucony za brak route depth. F2 kosztował
  0,019462 USD, ocenił 24/24 dróg i został ręcznie odrzucony, bo selektor
  wybrał SINGLE przed RICH. Po deterministycznej poprawce, bez nowego calla,
  wygrał Afterlife/orphaned well: RICH, 0,90, cztery rodziny źródeł; publiczne
  dokumenty BLM/GAO/DOI istnieją.
- E-020 wykonało normalne live discovery Pro za 0,115807 USD: transport,
  schema i exact URL przeszły, lecz ręczny audyt odrzucił segment. Responses
  wykonało 22 wyszukiwania przy limicie 8, mieszało mirrory z origin-primary,
  zachowało niedostępny UNT i report za loginem oraz pominęło silniejsze
  BLM/GAO/DOI. Pipeline zatrzymano przed fetch.
- E-021 wymusiło `max_uses=8` i zeszło do 6 wyszukiwań za 0,033609 USD, ale
  ręczny audyt odrzucił błędny access claim, źródła proposed i słabszy zestaw
  niż baseline. E-022 użyło 8/8 wyszukiwań za 0,042581 USD; kontrakt poprawnie
  zatrzymał brak exact `SECOND_ACT`, a ręczny audyt ponownie nie dopuścił
  fetchu. E-023 urwało pierwszy stream przed usage; selector nie wystartował,
  retry=0, a 0,30 USD pozostaje `UNKNOWN`. Naprawa trace przeszła 73/73, pełna
  regresja 56/56; DeepSeek jest zablokowany do rekoncyliacji E-023.
- E-024 niezależnie przetestowało aktywny publiczny fetch bez modeli: 5/6
  dokumentów i wszystkie trzy role dowodowe przeszły ręczną kontrolę; Capitol
  Forum dał 403 bez obejścia. A-130 zachowuje published/retrieved/status/roles
  przez classify, synthesis i provenance; testy 107/107, pełna regresja 57/57.
- Aktualny audyt i eksperymenty znalazły A-093–A-130. A-101–A-103 naprawiono
  offline. T-079 odtwarza przekroczenie limitu 0,25 → 0,50 USD przy dwóch
  rezerwacjach; A-102 blokadę pisarza przez CRLF/LF, a A-103 brak ignorowania
  pełnego artefaktu live.
- Produkcyjna promocja ma status `NOT_READY`; sam prototyp jest bezpiecznie
  inertny.

## Priorytety

1. E-023/A-129/N-026 — nie wykonywać kolejnego calla DeepSeek, dopóki
   nieznany koszt nie zostanie zrekoncyliowany. Historyczny capture pozostaje
   dowodem wady; poprawiony trace ma dowód offline 73/73 i 56/56.
2. N-028 — każdy kolejny call liczyć w globalnym capie 10 USD; utrzymywać
   4,90 USD historycznych `UNKNOWN` oraz 0,30 USD E-023 `UNKNOWN`. Nigdy nie
   używać Substacka. Po przyszłej rekoncyliacji wrócić wyłącznie do discovery,
   a każdy URL znów sprawdzić ręcznie przed fetch.
3. N-014 — izolacja danych w promptach.
4. N-012/N-021 — dokładne ID publikacji, metryki, kohorty i uczenie.
5. N-018/N-022 — promowalny bundle, migracje i autonomia operacyjna.

Jeżeli nowy audyt ujawni P0, zatrzymaj niższy priorytet, zapisz finding i kartę,
a następnie pracuj nad P0.

## Protokół jednej zmiany

1. Zapisz `git status --short --branch`, hashe plików celu i dokładny stan V2.
2. Przeczytaj kartę i odpowiednie implementacje V3/V2.
3. Sprawdź reuse: wskaż funkcję, tabelę, prompt lub test, który już realizuje
   większość zadania.
4. Zbuduj kontrdowód starej wady w fixture lub tymczasowej bazie.
5. Wprowadź minimalną zmianę tylko w V3.
6. Uruchom test celu, testy sąsiednie i pełną regresję offline.
7. Sprawdź katalog `data/`, brak sekretów, linki, ciągłość ID i niezmienność V2.
8. Zaktualizuj kartę, rejestr testów, rejestr ustaleń i dziennik badań.
9. Nie nazywaj zmiany `CLOSED`, jeśli dowód obejmuje tylko fixture.

## Testy i koszty

Domyślnie pracuj w `AGENT_V3_MODE=fixture`, z aktywnym kill switchem i bez
sieci. Zwykła regresja obejmuje `tests/test_*.py` poza platformowym
`test_czas.py`; nie obejmuje `tests/platne/`.

Live model test jest dopuszczalny tylko wtedy, gdy konkretnej własności nie da
się rozstrzygnąć fixturem, karta zawiera hipotezę, plan dispatchy, maksymalny
koszt i warunek stopu, a wynik trafia do księgi. Bieżący twardy budżet całego
programu wynosi łącznie **10 USD**, z uwzględnieniem kosztu historycznego
E-007. Limity dostawców są dodatkowymi sublimitami, ale nie sumują się ponad
limit globalny:

- Anthropic: maksymalnie 5 USD;
- DeepSeek: maksymalnie 5 USD;
- OpenAI/GPT obrazy: maksymalnie 2 USD.

Każda rezerwacja musi mieścić się w pozostałym limicie globalnym. Znany lub
estymowany koszt wynosi 1,73680670 USD. T-118, T-132, T-136 i E-017-D zachowują
łącznie 4,90 USD jako `UNKNOWN`, a E-023 dalsze 0,30 USD, więc konserwatywna
ekspozycja wynosi 6,93680670 USD, a saldo globalne 3,06319330 USD. DeepSeek ma
5,53877270/5 USD ekspozycji i pozostaje zablokowany do rekoncyliacji E-023.
Historycznych `UNKNOWN` nie wolno traktować jako zera. Każdy przyszły call
wymaga wpisu przed i po, zero retry oraz ręcznego STOP na granicy segmentu.

Budżet dostawcy nie jest zgodą na zmianę modelu. Test normalnego V3 ma używać
domyślnego routingu bez `AGENT_V3_CHEAP`, `AGENT_V3_WRITER` ani innego
override; dla provenance oznacza to DeepSeek Flash dla `classify` i DeepSeek
Pro dla `synthesis/review`. Nie wolno wykonywać
`config.MODEL_FOR.update(...)`, podmieniać routingu w pamięci ani wybierać
modelu porównawczego bez osobnego, jawnego polecenia użytkownika. Przed każdym
live-testem wypisz model, etapy, liczbę dispatchy i maksymalny koszt.

Nie uruchamiaj starszych plików `tests/platne/` jako automatycznej bramki.
Nowy `test_full_pipeline_live.py` ma ścisły preflight, ale starsze uprzęże nadal
nie mają wspólnej izolacji. Live test nie
może dotykać Substacka, chyba że osobna karta po pełnym fixture PASS jawnie
definiuje izolowane konto, capability, budżet mutacji i dokładną rekoncyliację.
Obecna instrukcja nie daje takiej zgody.

Pierwotny pełny eksperyment E-012 używał normalnego routingu i maksymalnie 32 dispatchy:
DeepSeek v4 Pro 14, DeepSeek v4 Flash 10, Claude Fable 5 trzy oraz Claude Opus 5
pięć. Jego twardy cap nowych kosztów to 4,50 USD. Przed startem trzeba ponownie
wypisać te modele, role, liczbę żądań i cap. `editorial_live_experiment.py`
blokuje `substack.com` i subdomeny także w publicznym fetchu; eksperyment nie
może dostać żadnej capability platformowej.

Po trzech awariach DeepSeek nie wolno uruchamiać E-012 jako całości. Izolowany
harness kontynuacyjny E-014 zachowuje osobne ledgery dostawców, zero retry i
ten sam zakaz Substacka. Ramię Anthropic jest zakończone; ramię DeepSeek jest
zablokowane przez N-025.

## Zasady dokumentacji naukowej

- Oddzielaj fakt, inferencję, hipotezę i decyzję projektową.
- Każdy finding ma ID A-xxx, priorytet, ścieżkę dowodu, skutek, kryterium
  obalenia i status.
- Każdy test ma ID T-xxx, środowisko, wynik PASS/FAIL, ograniczenia, skutki
  uboczne i koszt.
- Nie usuwaj wyników nieudanych; wyjaśnij, dlaczego próba była nieważna lub co
  obaliła.
- Nie uogólniaj pojedynczego live PASS na cały potok.
- Nie używaj liczby testów, promptów lub etapów jako dowodu jakości tekstu.
- Każda reguła uczona z wyników wymaga próby, horyzontu, kohorty,
  kontrprzykładu, ograniczonego rollout'u i automatycznego rollbacku.

## Łatwa późniejsza promocja

Nie włączaj produkcji. Buduj tak, aby przyszła promocja przyjmowała jeden
niemutowalny manifest obejmujący kod, runtime, zależności, prompty, profile
głosu, migracje, wynik replayu i dowody testów. Następnie: migracja na kopii,
shadow, canary, atomowe przełączenie i automatyczny rollback. Szczegóły są w
`PLAN_PROMOCJI_V3_DO_PRODUKCJI.md`.

## Pierwsza czynność kolejnego agenta

Po przeczytaniu wymaganych plików nie twórz nowej architektury. Przeczytaj
raporty E-018–E-024 oraz N-027/N-028. Live potwierdził sześć pól, 24 oceny
dróg i feasibility, a ręczna kontrola dopuściła do discovery wyłącznie
`Afterlife`/orphaned well. E-020, E-021 i E-022 są ręcznymi FAIL jakości
discovery; E-023 nie dotarło do wyniku i zachowuje 0,30 USD `UNKNOWN`.
Najpierw zrekoncyliuj E-023; do tego czasu nie wysyłaj nic do DeepSeek.
E-024 zaliczyło fetch 5/6 i ręczną jakość 5/5, ale nie jest obejściem
niezaliczonego discovery ani zgodą na live classify.
Następnie wykonuj jeden segment naraz, czytaj pełny raw i zatrzymuj każdy
treściowy FAIL nawet przy zielonym JSON. Nie przechodź do pisarza przed ręcznym
zaliczeniem zapytań, URL-i, pobranych dokumentów, fragmentów i syntezy. Każdy
koszt licz konserwatywnie w globalnych 10 USD; zero retry. Żaden test nie może
otworzyć Substacka, odczytać go ani użyć jego sesji.
