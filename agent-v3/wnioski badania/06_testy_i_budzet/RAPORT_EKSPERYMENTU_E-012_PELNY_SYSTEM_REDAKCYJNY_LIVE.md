# E-012 — pełny system redakcyjny live: projekt, preflight i blocker stylu

**Data:** 2026-08-21  
**Żądanie właściciela:** przebadać live skauta, wybór tematów, research, pisarza,
wpływ stylu, rewizję i autora Notes  
**Substack:** bezwarunkowo zabroniony; brak odczytu, sesji i mutacji  
**Stan API:** `STOPPED_FAIL_CLOSED_AFTER_DISPATCH_1; COST_UNKNOWN`  
**Nowy koszt:** 0 USD potwierdzone; 1,60 USD nierozliczonej ekspozycji  
**Ekspozycja programu:** 1,67558670 USD, w tym 0,07558670 USD
znane/estymowane i 1,60 USD `UNKNOWN`

## 1. Dlaczego E-010 nie wystarcza

E-010 uruchamia prawdziwe modele tylko dla rdzenia na zamrożonym wejściu.
Skaut, feasibility i discovery są fixture, profil stylu był podmieniony, a Notes
nie należą do próby. Taki replay odpowiada na pytanie o integrację kodu, lecz
nie na pytanie, jak faktycznie zachowują się poszczególne role.

E-012 rozdziela dwa ramiona:

1. naturalny łańcuch live od dwóch replikacji scouta przez research i kartę;
2. kontrolowane próby pisarza, ablacji stylu, rewizji oraz pięciu form Notes na
   tym samym materiale, aby awaria discovery nie zasłoniła pozostałych ról.

## 2. Hipotezy

- **H-SCOUT:** dwie identycznie zasilone próby oddają sześć unikalnych tematów,
  mierzalny udział tematów `nosny/na_artykul` i pozwalają oszacować stabilność,
  zamiast oceniać pojedynczą listę „na oko”.
- **H-CHAIN:** wybrany temat daje co najmniej jeden dokładnie znaleziony i
  pobrany dokument, dosłowne fragmenty oraz związaną kartę provenance.
- **H-STYLE:** przy tej samej karcie, modelu, głębokości, ruchu końcowym i
  liczbie paraleli tekst z zatwierdzonym profilem różni się od ablacji w
  mierzalnych cechach i ślepej rubryce. Jedna para jest wynikiem wstępnym,
  nie estymacją populacyjną.
- **H-REVISION:** kontrolowane wstrzyknięcie fałszywego zdania o 12 wypadkach
  zostaje wykryte, usunięte przez Fable i nie wraca po ponownej recenzji.
- **H-NOTES:** pięć form na identycznym fakcie daje różne struktury ekranu,
  zachowuje 33–64 słowa i przechodzi osobną weryfikację faktów albo jawnie
  wybiera ciszę.

## 3. Dokładny plan dispatchy i kosztu

Maksimum to 32 wywołania `llm.call`:

| Model normalnego V3 | Maks. | Etapy |
|---|---:|---|
| DeepSeek v4 Pro | 14 | scout ×2, discovery, synthesis, warto_pisac, review/forma, dwaj ślepi sędziowie, kontrole rewizji |
| DeepSeek v4 Flash | 10 | feasibility, classify maks. ×4, factcheck Notes maks. ×5 |
| Claude Fable 5 | 3 | tekst ze stylem, ablacja, rewizja |
| Claude Opus 5 | 5 | pięć form Notes |

Discovery może wykonać dodatkowy wewnętrzny request wyboru spośród już
znalezionych URL, ale pozostaje jedną pozycją ledgeru. Retry po odpowiedzi,
która mogła zostać naliczona, jest zabroniony.

Twardy cap nowych kosztów to 4,50 USD. Z historią maksymalna ekspozycja programu
wynosi 4,57558670 USD, poniżej globalnego limitu 10 USD i poniżej obu sublimitów
5 USD nawet wtedy, gdy cały nowy koszt przypadłby jednemu dostawcy. Domyślny
limit runu 1,60 USD pozostaje, a osobne runy współdzielą atomowy limit doby
4,50 USD w jednej bazie.

## 4. Granice bezpieczeństwa

`editorial_live_experiment.py`:

- działa wyłącznie w `AGENT_V3_MODE=model_test`;
- dopuszcza tylko `MODEL_CALL` i `PUBLIC_WEB_READ`;
- nie importuje browsera;
- odrzuca każdą domenę `substack.com` i `*.substack.com` przed fetch;
- ogranicza publiczny fetch do czterech URL;
- wymaga nowego workspace wewnątrz `agent-v3`;
- sprawdza exact routing przed i po;
- utrwala pełne system/user/response, ich SHA-256, czas, kontrakty, provenance,
  ledger kosztu i bazę eksperymentu;
- zapisuje `result.partial.json` po każdym dispatchu;
- po `RESERVED/UNKNOWN` zatrzymuje wszystkie dalsze wywołania;
- nie zna flagi publikacji, sesji ani platformowej capability.

Artefakt po przyszłym live powstanie w
`.live-experiments/E-012-editorial-system-live/result.json`.

## 5. Próby offline i nieudane wyniki

### T-110 — kalibracja testu

Pierwsza wersja testów uprzęży: 5/6 PASS. Metryka stabilności poprawnie karała
drugi temat bez odpowiednika i dała średnią 0,4286; arbitralna asercja wymagała
>0,5. Metryki nie poluzowano. Skorygowano tylko fixture do progu >0,4.

### T-111/T-112 — safety i rzeczywisty preflight

Po korekcie 6/6 PASS, a routing 2/2, atomowy budżet 7/7, replay 7/7 i capability
14/14. Rzeczywisty launcher w `model_test`, kill switch 0 i dry-run false
odmówił przed I/O: brak obu lokalnych kluczy. Workspace przed i po nie istniał;
0 dispatchy, 0 USD.

### T-113 — pełna symulacja odkrywa A-102

Pełna atrapa transportu doszła przez scout, discovery, cztery fetch/classify,
syntezę i ocenę. Normalny `write_with_style` padł przed modelem:

- oczekiwany pin: `d4e4e6bf928421d6a0eed6a6cafc796807ea289b275ff1a7aced49329de6638e`;
- surowy hash checkoutu Windows: `0b05cefa6701e6447c44810b686828a83c19ca7ffb29066778a13c24207acb1d`.

Treść była identyczna; różnicą były wyłącznie LF/CRLF. N-004 nie wykrywał
wady, bo zastępował `style.load_examples/load_profiles` fixturem. Jest to
finding A-102, a nie błąd modelu ani klucza.

### N-023/T-114 — naprawa blockeru

`style.canonical_bytes()` normalizuje wyłącznie zakończenia linii przed hashem.
Pin i pięć osobnych skrótów akapitów pozostają bez zmian. Zmiana jednego bajtu
nadal jest odrzucana. Preflight ładuje styl przed kosztem, a N-004 nie podmienia
już loadera. Pełna 32-call symulacja: 8/8 PASS. Replay: 7/7 PASS.

T-115 zachowuje nieważne uruchomienie `test_forma_artykulu.py` z katalogu
`agent-v3`, zakończone `ModuleNotFoundError: config`. Prawidłowe powtórzenie z
korzenia dało 29/29, 36/36, 35/35 oraz replay 7/7 PASS. T-117: finalna regresja
49/49 w 49,359 s, `data/` bez zmiany.

### T-118 — pierwszy rzeczywisty live E-012

Po zapisaniu lokalnego `agent-v3/.env` okazało się, że klucze są niepuste, ale
mają historyczne nazwy `DEEPSEEK_API_KEY` i `ANTHROPIC_API_KEY`. Dla jednego
procesu przypisano ich wartości w pamięci do namespacowanych nazw V3. Nie
zmieniono pliku, modeli, promptów, routingu ani limitów. Przed dispatch launcher
wypisał plan 14×Pro, 10×Flash, 3×Fable, 5×Opus i cap 4,50 USD.

Pierwsze żądanie `scout` na `deepseek-v4-pro` trwało 180,86 s. Dostawca
zamknął połączenie bez kompletnego body:
`RemoteProtocolError: peer closed connection without sending complete message
body (incomplete chunked read)`. Nie odebrano odpowiedzi, tokenów, request ID
ani rozliczenia.

Ledger poprawnie zapisał `UNKNOWN`, `ok=0`, `reserved_usd=1.60`, zero kosztu
potwierdzonego i brak automatycznego retry. Uprząż zatrzymała pozostałe 31
dispatchy. Routing pozostał niezmieniony, `browser` nie został zaimportowany,
jedyną zażądaną capability było `MODEL_CALL`; publiczny fetch i Substack nie
zostały dotknięte.

Artefakt `result.json` ma 27 722 bajty i SHA-256
`323FA3E264FFAD4E6A9F9D92A80531373F08DB05F966A2B87C350D1EDCECB59C`.
Hash końcowego checkpointu bazy utrwalony w artefakcie to
`d6b5fc79281bb827d45dd74098c20bdc8dc31c24f38128ad45e23358f6c049d2`.
Artefakt znajduje się lokalnie w
`.live-experiments/E-012-editorial-system-live/result.json`.

### T-125/T-126 — izolacja artefaktu A-103/N-024

Pierwsza kontrola końcowa wykazała, że raw `result.json` nie był ignorowany
przez Git. Nie zawierał wartości kluczy, ale przechowuje pełne prompty i może
przechowywać odpowiedzi. Lokalny `.gitignore` obejmuje teraz `.env` oraz cały
`.live-experiments/`. Powtórzenie potwierdziło ignorowanie obu ścieżek, zero
wycieków dokładnych wartości kluczy i niezmieniony hash artefaktu.

## 6. Czego nadal nie wiemy

Wykonano prawdziwy dispatch skauta, ale nie otrzymano kompletnego wyniku. Nie
istnieje więc lista tematów, druga replikacja, research, teksty Fable, pięć
Notes Opusa ani pomiar wpływu stylu. T-118 dowodzi zachowania transportu i
fail-closed ledgeru przy niepełnym strumieniu; nie dowodzi jakości żadnej roli.

Nie wolno ponawiać E-012 ani uruchamiać ramienia Anthropic, dopóki `UNKNOWN`
DeepSeek nie zostanie zrekoncyliowane z dowodem dostawcy albo jawnie rozliczone
w budżecie jako pełne 1,60 USD. Nawet po takiej rekoncyliacji kolejna próba
musi dostać nowy workspace i ponownie wypisać routing, liczbę wywołań i cap.

## 7. Wniosek

Kompletna, maszynowo oceniana uprząż istnieje i ujawniła realny blocker
pisarza pominięty przez wcześniejszy fixture. Blocker jest naprawiony offline.
Pierwszy rzeczywisty live doszedł tylko do jednego niekompletnego żądania
skauta i został prawidłowo zatrzymany. Stan E-012 to
`STOPPED_FAIL_CLOSED_AFTER_DISPATCH_1; COST_UNKNOWN`, a nie PASS ani wynik
jakościowy. Pełne badanie ról pozostaje otwarte po rekoncyliacji kosztu.
