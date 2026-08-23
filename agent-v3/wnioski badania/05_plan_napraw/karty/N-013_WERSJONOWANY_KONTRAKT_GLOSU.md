# N-013 — wersjonowany kontrakt głosu

- **Status:** `OPEN`
- **Ustalenia:** A-021, A-062–A-063, A-074–A-079, A-082, A-094
- **Zakres:** profile marki i gatunków, pisarz, redaktor i krótkie formaty

## Hipoteza

Jeden manifest tożsamości marki, osobne profile gatunków oraz wspólna rubryka
przekazana generatorowi i redaktorowi pozwolą zachować głos po rewizji bez
sztywnych, sprzecznych zakazów.

## Reuse

Zachować korpus próbek, profile pozytywny/negatywny, `style.py` i istniejące
prompty. Włączyć profile spoza V3 jako wersjonowane assety z hashami.

## Testy wymagane

- zmiana jednego bajtu profilu blokuje użycie bez zmiany wersji;
- redaktor otrzymuje ten sam kontrakt głosu co pisarz;
- Notes, komentarz, odpowiedź i restack mają jawny profil gatunku;
- kombinacje ruch–postawa–otwarcie są zgodne;
- rubryka wskazuje cytaty, nie jeden subiektywny score.

## Kryterium końca

Każdy tekst i każda rewizja zapisują `voice_contract_id`, a release manifest
wiąże wszystkie użyte profile i korpus.

