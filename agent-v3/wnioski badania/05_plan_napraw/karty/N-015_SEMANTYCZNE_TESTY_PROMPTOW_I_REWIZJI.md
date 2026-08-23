# N-015 — semantyczne testy promptów i rewizji

- **Status:** `OPEN`
- **Ustalenia:** A-020, A-035, A-063–A-065, A-075–A-076, A-083, A-097
- **Zakres:** zamrożony korpus dobrych i wadliwych wejść, rubryki i asercje

## Hipoteza

Wersjonowany zestaw przypadków z oczekiwanymi defektami, pełnymi renderami
promptów i porównaniem przed/po odróżni poprawę faktów od utraty głosu oraz
wykryje sprzeczne instrukcje, których test fraz nie widzi.

## Reuse

Zachować obecne testy placeholderów, historyczne artykuły i płatne harnessy jako
materiał. Dodać warstwę semantyczną zamiast usuwać podłogę statyczną.

## Testy wymagane

- dobre teksty przechodzą, zamrożone kontrprzykłady odpadają;
- `MIXED` nie ukrywa faktu;
- rewizja usuwa wskazaną wadę bez nowej wady głosu;
- konflikt dwóch instrukcji jest wykrywany na pełnym renderze;
- wynik ma asercję, próg i wersję rubryki, nie tylko zapis próbek.

## Kryterium końca

Żaden diagnostyczny wydruk nie jest bramką release. Bramka zwraca jednoznaczny
wynik maszynowy z dowodem dla każdego wymiaru.

