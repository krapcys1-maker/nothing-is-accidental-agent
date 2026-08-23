# N-028 — twardy cap kosztu faktycznego

- **Status:** `SCOUT_HARNESS_FIXED_OFFLINE; SHARED_RUNTIME_OPEN`
- **Ustalenie:** A-112
- **Zakres:** związek rezerwacji, `max_tokens` i settlement

## Kontrdowód live

E-018 miało cap etapu 0,04 USD. Model ukończył odpowiedź za 0,049298 USD.
Atomowa rezerwacja zabezpieczyła konkurencję, ale nie ograniczyła maksymalnej
liczby tokenów, a settlement przyjął wyższy koszt. Przekroczenie: 0,009298 USD.

## Naprawa lokalna

Scout-only oblicza przed dispatch najgorszy koszt z konserwatywnego wejścia,
`MAX_TOKENS` i taryfy. Jeśli wynik przekracza cap, odmawia przed I/O. Test
sprawdza odmowę przy normalnym suficie i sukces kontrolny przy małym suficie.

## Brakująca naprawa wspólna

Każde wywołanie modeli musi dostać limit tokenów wyprowadzony z pozostałej
kwoty albo zostać odrzucone przed dispatch. Settlement większy od rezerwacji
nie może być jedyną ochroną. N-020 zachowuje dowód atomowości, lecz jego status
pełnego capu kosztu zostaje ponownie otwarty.

## Kryterium zamknięcia

Kontrdowody dla wszystkich modeli i taryf muszą wykazać, że żadna kombinacja
wejścia oraz maksymalnego wyjścia nie przekroczy run/day/month/provider/global
capu, także po restartach i przy współbieżności.
