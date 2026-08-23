# N-003 — izolacja sekretów i sesji

## Metryka

- **Ustalenia:** A-002, A-053
- **Status:** FIXED_OFFLINE
- **Start:** 2026-08-21
- **Baza:** codex/agent-v3-gpt, commit 57a9474362b8fa6d120027aa54afe1a918b65b0f
- **Zakres V3:** config.py, browser.py, alarm.py, .env.example
- **V2:** brak zmian

## Hipoteza

Jeżeli V3 czyta wyłącznie przestrzeń AGENT_V3, własny .env i własną sesję testową, nie przejmie sekretu, sesji ani celu produkcyjnego. Kontrdowodem jest import V3 widzący ogólny lub produkcyjny sekret.

## Stan przed

- config.py ładuje również wspólny .env z korzenia;
- klucze modeli i SMTP nie mają prefiksu V3;
- cel jest wpisany jako produkcyjne nothingisaccidental;
- sesja nie jest związana z handle konta testowego.

Odciski SHA-256: config.py = 724d741f7b1b5287ca9ed67fcb1da15d851c4b2f10331a4855580e9a48ee9657; browser.py = 52f9f523450a65278b53e4131adfbb696b2f0ecc23221b4466dd25719cd18935; alarm.py = a2aad91d2fe57f3f5e073c8d901127fbb4a88afb5f39b95aaf430d49196f0a34.

## Test kontrdowodu

- tylko ANTHROPIC_API_KEY=PRODUCTION_SENTINEL daje pusty klucz V3;
- AGENT_V3_ANTHROPIC_API_KEY=TEST_SENTINEL jest widoczny wyłącznie w V3;
- sesja leży pod agent-v3/data/sessions i zawiera handle celu;
- produkcyjny handle zawsze blokuje mutacje.

## Minimalna zmiana i rollback

Usunąć fallback do korzenia; wprowadzić wyłącznie nazwy AGENT_V3; dostarczyć bezsekretowy .env.example. Rollback nie migruje i nie kopiuje sekretów.

## Dowody po zmianie

- fixture nie ładuje nawet agent-v3/.env i zeruje odziedziczone klucze V3;
- usunięto odczyt .env z korzenia repo;
- klucze modeli, SMTP i alarm mają wyłącznie przestrzeń AGENT_V3;
- test podprocesowy: odziedziczony klucz ogólny oraz namespaced sentinel są niewidoczne w fixture;
- model_test widzi jawnie podany klucz AGENT_V3, a nie ogólną nazwę;
- ścieżka sesji leży pod agent-v3/data/sessions i zawiera handle konta testowego;
- test celu 14/14 PASS; pełna regresja 35/35 plików PASS;
- koszt online: 0 USD; plików sesji nie odczytano ani nie utworzono.

Odciski po zmianie: config.py = 8d275dbb1f235f65e5fa1430dd3f3ff35a6d85f52c364e1a2bd9236196741f5a; browser.py = 9037fd9bb579a1ee60b336da3e4225475e673def3c92eaa2262fa4f5760e95cc; alarm.py = b6a860d6f851dea688d4f3309df388e81d63b8a511eb34e44cd34b8f9bad3727.

## Wynik

Hipoteza utrzymana offline. Sekrety i sesja V3 są odseparowane nazwą, ścieżką, trybem startowym i bramką możliwości.
