# N-001 — izolacja ścieżek V2

## Metryka

- **Ustalenia:** A-001, A-026, A-053
- **Status:** FIXED_OFFLINE
- **Start:** 2026-08-21
- **Baza:** codex/agent-v3-gpt, commit 57a9474362b8fa6d120027aa54afe1a918b65b0f
- **Zakres V3:** uruchom-dzien.cmd, wdroz.sh, systemd, aktywne komunikaty V3
- **V2:** brak zmian; wyłącznie materiał porównawczy

## Hipoteza

Jeżeli wszystkie wykonywalne artefakty V3 zostaną odłączone od V2 i unieruchomione jako artefakty produkcyjne, żadne polecenie z V3 nie uruchomi procesu V2 ani publikacji. Kontrdowodem jest choć jedno aktywne odwołanie wykonawcze do agent-v2, AGENT_V2 lub --wyslij.

## Stan przed

- uruchom-dzien.cmd uruchamia agent-v2/run.py --dzien --wyslij;
- wdroz.sh wdraża V2, kopiuje jego unity i zawiera automatyczny git reset --hard;
- trzy usługi w katalogu systemd uruchamiają V2, dwie z --wyslij;
- znacznik w run.py V3 nie chroni przed tymi ścieżkami.

Odciski SHA-256: uruchom-dzien.cmd = c1eed5c205f2dee7242816ea4bd2c57e0618242a1ecb5f613bf5e15d7cf6f60a; wdroz.sh = 126eaa3cbc48574a4c20b37d5326582aca7d9a571f87c82eecdf0e709ae86356.

## Test kontrdowodu

- statyczny skan wykonywalnych plików V3;
- lokalny skrypt nie zawiera --wyslij i wymusza fixture;
- wdroz.sh odmawia przed siecią, Gitem, systemd i Pythonem;
- jednostki systemd są celowo nieuruchamialne.

## Minimalna zmiana i rollback

Nie usuwać historii i nie zmieniać V2. Zastąpić tylko aktywne ścieżki V3 bezpiecznymi wejściami prototypu. Rollback obejmuje wyłącznie pliki V3 z commitu bazowego.

## Dowody po zmianie

- skan aktywnych plików wykonawczych V3: zero odwołań do agent-v2 i AGENT_V2;
- uruchom-dzien.cmd wskazuje wyłącznie 14 testów bezpieczeństwa V3, fixture, aktywny kill switch i brak flagi publikacji;
- wdroz.sh kończy się kodem 64 przed Gitem, siecią, Pythonem i systemd;
- trzy usługi systemd mają ExecStart=/usr/bin/false i RefuseManualStart=yes;
- testy: ExecutableIsolationTest 2/2 PASS; pełna regresja 35/35 plików PASS;
- kontrola V2 po zmianie: numstat nadal 61/10 dla run.py i 21/4 dla stages.py oraz ten sam zastany plik nieśledzony; wartości są identyczne z początkiem partii;
- koszt online: 0 USD; mutacje zewnętrzne: brak.

Odciski po zmianie: uruchom-dzien.cmd = 953395dd8e699aba36f62c9455eb533323f19a4c803e18f8e1e01444bde8d6bf; wdroz.sh = 339829bfe1e39cae2b7ecdd0aafc350b458984d58081190f1768f0b16cce0db8.

## Wynik

Hipoteza utrzymana dla badanego korpusu. V3 nie ma już aktywnej ścieżki wykonawczej do V2. Artefakty wdrożeniowe V3 są celowo inertne.
