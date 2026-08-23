# Plan łatwej, atomowej promocji Agent V3 do produkcji

**Stan na 2026-08-21:** `NOT_READY; PROTOTYPE_SAFELY_INERT`  
**Zakres:** projekt operacyjny i kryteria maszynowe; bez wdrożenia, publikacji,
systemd, sesji produkcyjnej i zmian V2

## 1. Odpowiedź wykonawcza

V3 nie można dziś bezpiecznie „wrzucić od razu” na produkcję. Można natomiast
zbudować drogę, w której późniejsza promocja będzie jedną atomową operacją na
tym samym, uprzednio przebadanym artefakcie. Warunek: nie wolno zamieniać
prototypu w produkcję przez ręczne usunięcie `/usr/bin/false`, zmianę handle lub
ustawienie jednej zmiennej środowiskowej.

Docelowa operacja ma przyjąć wersjonowany manifest, odtworzyć środowisko,
sprawdzić wszystkie bramki, uruchomić shadow/canary i dopiero po wynikach
maszynowych przełączyć aktywną wersję. Każda porażka pozostawia poprzedni
release aktywny albo automatycznie do niego wraca.

## 2. Co już pomaga

| Element | Stan | Znaczenie dla promocji |
|---|---|---|
| osobna gałąź `codex/agent-v3-gpt` | istnieje | V3 ma własną historię zmian |
| marker prototypu i capability registry | istnieje | bieżący kod nie może trafić w konto produkcyjne |
| inert `wdroz.sh` i usługi systemd | istnieją | przypadkowe wdrożenie jest blokowane |
| `.env.example` z prefiksem `AGENT_V3_*` | istnieje | sekrety V2 nie są kontraktem V3 |
| ledger mutacji i `UNKNOWN` | fundament istnieje | restart/niepewność mogą zatrzymać skutki |
| ledger pochodzenia i kontrakty LLM | fundament istnieje | release może sprawdzać spójność dowodową |
| regresja offline | działa | nadaje się na pierwszą bramkę release |

Te elementy czynią prototyp bezpieczniejszym, ale nie są jeszcze systemem
wydawania.

## 3. Blokery

### P0 — przed jakimkolwiek ruchem produkcyjnym

1. N-004/E-012: replay offline jest 7/7, ale pełny live skauta, researchu,
   pisarza, stylu, rewizji i Notes nadal wymaga obu lokalnych kluczy.
2. N-010: atom artykuł–plik–rewizja–provenance jest `FIXED_OFFLINE`; przed
   produkcją pozostaje test trwałości przy rzeczywistym zaniku zasilania.
3. N-011: mechanika jest `FIXED_OFFLINE` — dwie iteracje, ponowne pełne bramki
   i kwarantanna bez fallbacku; przed produkcją pozostaje kalibracja polityki i
   test prawdziwego modelu.
4. A-090: numerowane, restart-safe migracje SQLite z backupem i próbą
   odtworzenia.
5. A-089: niemutowalny release bundle i osobny kontroler promocji.
6. A-093/N-019: ledger przed pierwszą zmianą edytora jest `FIXED_OFFLINE`;
   przed produkcją potrzebny będzie osobno autoryzowany test izolowanej
   platformy.
7. A-095/N-020: atomowa rezerwacja kosztu przy wielu procesach jest
   `FIXED_OFFLINE`; pozostaje rekoncyliacja z prawdziwym billingiem.
8. A-100/N-022: wspierany kontrakt odnowienia auth i backupu albo jawny status
   `AUTONOMOUS_PRODUCTION_BLOCKED`.
9. Dodatni test izolowanego konta dla każdej capability, zanim analogiczna
   capability będzie w ogóle dostępna w profilu produkcyjnym.

### P1 — przed pełnym autonomicznym ruchem

1. A-088: request ID każdego dostawcy zapisane także przy `UNKNOWN`.
2. A-091: pełny lock zależności z hashami, wersją Pythona i przeglądarki.
3. A-092: shadow, canary, healthcheck, wzajemne wykluczenie wersji i rollback.
4. A-094: profile głosu w bundle i hashe w loaderze/manifestcie.
5. A-099: dokładne external ID każdego opublikowanego artykułu.
6. Telemetria jakości oraz kosztu niezależna od logów procesu.
7. Automatyczna rekoncyliacja `RESERVED/UNKNOWN` z API/eksportami dostawców.

## 4. Jednostka promocji

Promowany ma być katalog release, nie gałąź robocza ani nieczyste drzewo Git.
Minimalny manifest:

```json
{
  "schema": "agent-v3-release@1",
  "release_id": "v3-YYYYMMDD.N",
  "git_commit": "pełny SHA",
  "source_tree_sha256": "hash kanonicznego manifestu plików",
  "python": "dokładna wersja",
  "dependency_lock_sha256": "hash locka z hashami paczek",
  "browser_revision": "dokładna rewizja Chromium",
  "db_schema_version": 1,
  "prompt_contract_manifest_sha256": "hash kontraktów i promptów",
  "voice_asset_manifest_sha256": "hash korpusu i wszystkich profili głosu",
  "test_evidence_sha256": "hash raportu bramek",
  "target_account_id": "niezmienny ID konta, nie tylko handle",
  "previous_release_id": "wersja rollbacku"
}
```

Manifest nie zawiera sekretów. Sekrety są wstrzykiwane z osobnego magazynu
środowiska docelowego i nigdy nie są kopiowane z V2 ani z głównego `.env`.

## 5. Maszyna stanów release

```text
BUILT
  → OFFLINE_VERIFIED
  → MIGRATION_VERIFIED_ON_COPY
  → SHADOW_VERIFIED
  → CANARY_ACTIVE
  → ACTIVE

Każdy błąd przed ACTIVE → REJECTED
Błąd po przełączeniu     → ROLLED_BACK + QUARANTINED
UNKNOWN mutacji/kosztu   → QUARANTINED, bez dalszych dispatchy
```

Nie istnieje przejście z `BUILT` bezpośrednio do `ACTIVE`.

## 6. Docelowa jedna operacja

Przyszły interfejs może wyglądać tak:

```text
release-control promote --manifest releases/v3-YYYYMMDD.N/manifest.json
```

To nazwa projektowa, nie istniejąca obecnie komenda. Kontroler ma:

1. odrzucić nieczyste lub niezgodne hashe;
2. odtworzyć izolowane środowisko dokładnie z locka;
3. uruchomić pełną regresję i replay fixture;
4. wykonać backup SQLite oraz migrację na kopii;
5. sprawdzić inwarianty i odtworzenie backupu;
6. uruchomić release w shadow bez mutacji;
7. wykonać ograniczony canary według autonomicznych limitów;
8. potwierdzić ID konta, ledger, koszty, healthcheck i brak `UNKNOWN`;
9. atomowo przełączyć symlink/slot `current`;
10. utrzymać poprzedni release i bazę do automatycznego rollbacku.

Kontroler nigdy nie używa `git reset --hard`, nie wdraża bezpośrednio z katalogu
roboczego i nie modyfikuje V2.

## 7. Capability policy produkcji

Obecny `Mode` celowo nie ma `production`; to właściwe. Późniejszy profil
produkcyjny powinien powstać dopiero w kontrolerze release i wymagać łącznie:

- manifestu release zgodnego z uruchomionym kodem;
- root-owned znacznika środowiska docelowego, którego repo nie może utworzyć;
- niezmiennego account ID potwierdzonego w sesji runtime;
- aktywnego slotu `current` zgodnego z `release_id`;
- zielonych autonomicznych bramek i braku stanu `UNKNOWN`;
- idempotency key dla każdej mutacji;
- kill switcha sprawdzanego bezpośrednio przed dispatch.

Samo `AGENT_V3_MODE=production` nie może niczego odblokować.

## 8. Migracje i dane

Każda zmiana schematu dostaje numer, transakcję, inwarianty przed/po oraz test
na kopii realnego kształtu bazy. Sekwencja:

1. zamrożenie nowych dispatchy;
2. spójny backup bazy i nieodtwarzalnych artefaktów;
3. checksum backupu;
4. migracja kopii i pełny replay odczytu;
5. migracja właściwego slotu;
6. start nowego release bez schedulerów;
7. healthcheck;
8. dopiero potem przełączenie schedulerów.

Nieudana migracja nie może być tylko wydrukowanym ostrzeżeniem.

## 9. Canary i rollback autonomiczny

Canary powinien ograniczać jednocześnie liczbę mutacji, koszt i czas. Rollback
uruchamia się automatycznie, gdy wystąpi co najmniej jeden warunek:

- niezgodne konto lub sesja;
- `UNKNOWN` mutacji albo kosztu;
- nieprzechodząca bramka źródeł, recenzji lub finalnego grafu;
- przekroczony budżet/limit;
- powtarzalny błąd transportu;
- niezgodność migracji lub healthchecku;
- równoległe działanie dwóch release'ów.

Rollback przełącza kod na poprzedni niemutowalny slot. Migracje destrukcyjne są
niedozwolone, dopóki poprzedni release ma pozostawać opcją powrotu.

## 10. Kryterium „gotowe do łatwej promocji”

V3 otrzyma status `PROMOTABLE`, gdy jedna offline'owa komenda zbuduje release
bundle, odtworzy środowisko od zera, przejdzie pełny replay i test migracji,
a kontroler w testowym środowisku przeprowadzi state machine do `ACTIVE` oraz
automatyczny rollback bez modyfikacji artefaktu. Dopiero wtedy produkcyjna
promocja jest operacją, a nie nowym projektem wdrożeniowym.

## 11. Decyzja bieżąca

Nie zmieniono `wdroz.sh`, usług systemd ani capability policy na uruchamialne.
Nie utworzono release'u, nie wykonano push ani deploymentu. Najbliższa bezpieczna
implementacja operacyjna to numerowane migracje i offline release manifest.
N-004, N-010, N-019 i N-020 mają dowody offline, lecz nie dowody produkcyjne;
otwarte pozostają live E-012, kalibracja/live N-011 i N-022 oraz wskazane próby
trwałości, billingu i izolowanej platformy.
