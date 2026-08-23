# E-013 — autonomiczna rewizja i kwarantanna N-011

**Data:** 2026-08-21  
**Zakres:** V3, fixture, prawdziwe `run.main()`, tymczasowe SQLite i pliki  
**Sieć/API/Substack:** nie użyto; T-118 `UNKNOWN` blokował modele  
**Nowy koszt E-013:** 0 USD  
**Status:** `FIXED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN`

## 1. Pytanie badawcze

Czy V3 potrafi bez zewnętrznej akceptacji poprawić tekst, po każdej zmianie
ponownie wykonać review, obserwację formy, deterministyczne bramki i provenance,
a następnie wybrać dokładnie jeden terminalny stan:
`READY_AUTONOMOUS`, `QUARANTINED_EVIDENCE` albo
`QUARANTINED_EDITORIAL`?

## 2. Stan przed i kontrdowód

Poprzednie `editorial.quality_decision()` podejmowało decyzję głównie liczbą
uwag: 0–2 niefaktograficzne uwagi dawały `READY`, 3–5 jedną rewizję, a 6+
`ALARM`. Oznaczało to, że pojedynczy `FRAZA_Z_INSTRUKCJI`,
`WASKA_PODSTAWA` albo inna poważna wada mogła zostać uznana za drobną notatkę.
Po jednej nieudanej rewizji aktywny runtime zapisywał `NEEDS_REVIEW` bez
autonomicznej decyzji końcowej.

Test T-119 rozróżnia starą i nową politykę: jeden przeciek instrukcji musi dać
`REVISE`, wąska podstawa `QUARANTINED_EVIDENCE`, brak kontroli i nieznana
bramka `QUARANTINED_EDITORIAL`. Test nie został uruchomiony na fizycznym
checkoutcie sprzed zmiany; kontrdowód starego wyniku pochodzi z utrwalonego
źródła `editorial.py` o SHA-256
`7D7D73DED8D3DA6738CE0B83F55112F0C0185CB662398BBFCED6AE02F9626323`.

## 3. Wersjonowana polityka

Polityka `autonomous-editorial@1` ma hash
`6c4b7df364516b78f1f16fd9c1aace20ae4580f46a29fde83a177697d818c05e`.
Hash obejmuje maksymalną liczbę iteracji, wszystkie znane bramki, domenę,
reakcję i wagę oraz reakcję na nieznaną bramkę.

- faktografia wymaga rewizji dowodowej;
- `WASKA_PODSTAWA` jest od razu kwarantanną dowodową, bo parafraza nie stworzy
  drugiego źródła;
- brak wymaganej kontroli i nieznana bramka są kwarantanną redakcyjną;
- każdy znany problem formy wymaga rewizji nawet wtedy, gdy jest jedyną uwagą;
- tylko zero uwag daje `READY_AUTONOMOUS`.

Wersja i pełny hash są utrwalane w końcowych notatkach artykułu. Trigger oraz
wynik każdej rewizji przechowują całą decyzję wraz z wersją polityki.

## 4. Pętla rewizji

Limit wynosi dwie iteracje. Każda iteracja wykonuje kolejno:

1. `stages.revise()` na tej samej karcie dowodowej;
2. nowe `stages.review()` i bijekcyjne związanie zdań z claimami;
3. nowe `stages.ocen_forme()`;
4. wszystkie `gates.deterministic_floors()`;
5. `provenance.finalize_card()`;
6. nową decyzję jakości i porównanie postępu.

Brak zmiany treści albo niezmieniony score daje `NO_IMPROVEMENT`. Nowy typ
bramki lub wyższy score daje `REGRESSION`. Oba wyniki kończą się kwarantanną.
Dwie poprawiające iteracje z nierozwiązanymi wadami kończą się
`LIMIT_REACHED`, nigdy publikowalnym fallbackiem. Błąd rewizji albo dowolnej
ponownej kontroli tworzy `KONTROLA_NIEDOSTEPNA` i kwarantannę.

## 5. Wykonywalny kontrakt długości

`gates.deterministic_floors()` przyjmuje teraz faktyczną głębokość i porównuje
liczbę słów z `config.dlugosc_dla()`. Wynik poza zakresem tworzy
`DLUGOSC_POZA_KONTRAKTEM`, który wymaga rewizji. Wydruk starego globalnego
zakresu nie jest już jedynym śladem kontroli długości.

Pierwszy sąsiedni replay T-120 oblał 1/7, ponieważ zamrożony writer fixture
oddawał kilkadziesiąt słów dla kontraktu `RICH`. Nowa bramka prawidłowo
uruchomiła `revise`, którego stary fixture nie obsługiwał. Nie osłabiono bramki.
Zamrożoną odpowiedź rozciągnięto wyłącznie twierdzeniami istniejącymi na karcie
do 920+ słów; T-121 ponownie dał 7/7.

## 6. Scenariusze integracyjne T-122

Trzynaście testów N-011 przeszło:

- fałszywe zdanie o 12 wypadkach zostało usunięte; review i forma wykonały się
  po raz drugi, finalny provenance przeszedł, status `READY_AUTONOMOUS`;
- identyczna rewizja dała `NO_IMPROVEMENT` i `QUARANTINED_EVIDENCE` po jednej
  iteracji;
- usunięcie faktu połączone z nowym zakazanym otwarciem dało `REGRESSION` i
  `QUARANTINED_EDITORIAL`;
- trzy nieoparte fakty, usuwane po jednym, dały `IMPROVED`, następnie
  `LIMIT_REACHED` i `QUARANTINED_EVIDENCE` po dokładnie dwóch iteracjach;
- czysty tekst przeszedł bez zbędnej rewizji;
- aktywne `run.py`, `editorial.py` i `stages.py` nie zawierają
  `NEEDS_REVIEW`.

Wszystkie scenariusze biegły przez zwykłe `run.main()`, prawdziwe kontrakty,
provenance, save N-010 i tymczasową bazę. Nie użyto osobnej kopii orkiestracji.

## 7. Regresja

- T-123: transakcyjny save 7/7, provenance 19/19, kontrakty 11/11, forma
  41/41, bramki 24/24, głębokość 35/35, zakazy pisarza 36/36 i E-012 fixture
  8/8 — wszystkie PASS;
- T-124: 50/50 bezpiecznych plików PASS w 49,622 s; `data/` byte-identical;
- kompilacja `editorial.py`, `gates.py`, `run.py`, `pipeline_replay.py` i testu
  PASS.

## 8. Hashe po zmianie

| Plik | SHA-256 |
|---|---|
| `editorial.py` | `197B87B433A0EE389EE72CD9E67B2782086B40892F6F221D9E9801440B57C6C3` |
| `gates.py` | `776F37878A0FFA27EF07A3EA1FE1CAE1D1577C0F4C14A4E768E5C8C3A200C53D` |
| `run.py` | `8A502100BDC1A3DAF2FA35690035BB72443DC6601D4C4AE576AFA3093730C45B` |
| `pipeline_replay.py` | `069BAA52386E1773094870D842899751923CB321383AE176AAD9AF836E72D2CD` |
| `tests/test_autonomous_revision.py` | `83FF8537DC0F2F153DE65FA9B442459F7E1F9E4CCEDE77A082D14EB3138E57F3` |
| `tests/test_full_pipeline_replay.py` | `2307BF7A6F30414326767779D5AA40673ECD0AEB38EE5B582D3F4845A6BFC058` |

## 9. Ograniczenia

Fixture dowodzi maszyny stanów, ponownych kontroli i braku fallbacku, ale nie
semantycznej skuteczności Claude Fable 5. E-012 miało wykonać taki test, lecz
T-118 zatrzymał wszystkie modele po niepełnym strumieniu DeepSeek i koszcie
`UNKNOWN` 1,60 USD. Live rewizja pozostaje obowiązkowa po rekoncyliacji.

A-019 pozostaje częściowo otwarte: polityka nie opiera się już na samej liczbie
uwag, lecz wagi nie zostały skalibrowane na reprezentatywnym korpusie artykułów.
Nie wolno traktować 13/13 fixture jako estymacji jakości publikacji. A-020,
A-036, A-064 i A-065 mają wykonawczy dowód offline w badanym zakresie.

## 10. Wniosek

N-011 otrzymuje status
`FIXED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN`. Aktywny potok nie
ma już `NEEDS_REVIEW`; po każdej rewizji przechodzi pełny zestaw kontroli, a
brak poprawy, regresja, limit i awaria kończą się autonomiczną kwarantanną.
Substack nie został użyty.
