# N-019 — ledger zdalnego szkicu artykułu

- **Status:** `FIXED_OFFLINE; PLATFORM_LIVE_NOT_RUN`
- **Ustalenie:** A-093
- **Zakres:** dodatnia ścieżka `live_test` artykułu; bez uruchamiania platformy

## Hipoteza

Rozdzielenie `draft_write` i `article_publish` na dwa ledgerowane zamiary
zapobiegnie osieroconym szkicom oraz pozwoli wznowić lub zrekoncyliować awarię
bez podwójnego uploadu i bez duplikatu publikacji.

## Test kontrdowodu

Atrapa edytora rejestruje pierwszą operację serwerową. Test starej ścieżki ma
wykazać, że następuje ona przed `mutation_attempts.PENDING`. Test poprawionej
ścieżki wymaga odwrotnej kolejności i stabilnego payload hash.

## Kryteria

1. Rezerwacja `draft_write` przed otwarciem mutującego edytora.
2. Hash tytułu, HTML i obrazu w intencji.
3. Dokładne ID szkicu po pierwszym potwierdzonym zapisie.
4. Restart nie tworzy drugiego szkicu dla tej samej intencji.
5. Publikacja ma osobną próbę zależną od potwierdzonego draftu.

Nie wolno wykonywać testu na żywym koncie przed zielonym kontrdowodem fixture.

## Stan przed

`browser.wystaw_artykul()` otwierało nowy edytor, wypełniało treść, opcjonalnie
wgrywało obraz, przechodziło do ustawień i dopiero przed kliknięciem publikacji
tworzyło próbę rodzaju `article`. Zdalny szkic nie miał własnej intencji.

Zapisane przed zmianą SHA-256: `browser.py`
`ACA904294558676F57A76E69D627395B1017201144A5617DECA65E2AA2843177`,
`mutation_ledger.py`
`333E17E445EE90CFC497BF913A1403650B7D639D613AA9F6A44260FB73C9AE55`.

## Kontrdowód i implementacja

T-088 wykazał na starej ścieżce, że `page.goto()` nowego edytora następuje bez
wiersza `draft_write`. Po minimalnej zmianie:

- manifest `draft-write@1` zawiera SHA-256 tytułu, podtytułu, HTML i obrazu;
- `draft_write` jest zarezerwowane i ma trwały dispatch przed otwarciem nowego
  edytora;
- dokładne numeryczne ID szkicu kończy próbę jako `CONFIRMED`;
- brak ID kończy ją jako `UNKNOWN` i nie pozwala utworzyć `article_publish`;
- restart wznawia tylko ten sam manifest po exact ID;
- `article_publish` jest osobną próbą zależną od próby szkicu;
- ledger szkicu nie zużywa drugiej jednostki `artykuly`; jednostkę wolumenu
  rezerwuje publikacja.

## Dowody po zmianie

- T-089: test celu 4/4 PASS;
- T-090: `test_mutation_ledger.py` 16/16,
  `test_operational_day.py` 14/14 i `test_prototype_safety.py` 14/14 PASS;
- T-091: pełna regresja 45/45 plików PASS, `data/` bez zmian;
- kompilacja `browser.py`, `mutation_ledger.py`, `operational_day.py` i testu
  celu PASS;
- sieć, Substack, sesja i modele: nieużyte; koszt: 0 USD.

Pełny projekt, nieudana próba, wyniki, ograniczenia i odciski znajdują się w
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-008_LEDGER_ZDALNEGO_SZKICU.md`.

## Granica wniosku

Fixture dowodzi kolejności i trwałości, ale nie aktualnego zachowania autosave
ani selektorów prawdziwego Substacka. Test platformowy wymagałby utworzenia lub
zmiany szkicu i pozostaje niedozwolony przy aktualnym poleceniu użytkownika.
