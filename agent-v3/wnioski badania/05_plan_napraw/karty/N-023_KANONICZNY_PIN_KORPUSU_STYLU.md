# N-023 — kanoniczny pin korpusu stylu

- **Status:** `FIXED_OFFLINE; LIVE_WRITER_OPEN`
- **Ustalenie:** A-102
- **Zakres:** `style.py`, preflight E-012 i prawdziwy loader stylu w N-004

## Kontrdowód

Na checkoutcie Windows bieżący korpus ma surowy SHA-256 `0b05cefa…`, podczas
gdy pin treści w `config.py` wynosi `d4e4e6bf…`. Różnica pochodzi wyłącznie z
CRLF/LF. `style.load_examples()` odmawiał pracy, więc normalny pisarz nie mógł
wykonać ani jednego dispatchu. Replay N-004 tego nie widział, ponieważ
podmieniał oba loadery stylu atrapami.

## Hipoteza

Jeśli pin jest liczony po kanonizacji wyłącznie `CRLF/CR -> LF`, identyczna
treść przejdzie na Windows i Unix, a każda inna zmiana bajtowa nadal zostanie
odrzucona.

## Reuse i zmiana

Zachować istniejący pin, wybrane pięć akapitów i ich osobne skróty. Dodać tylko
`canonical_bytes()` i `corpus_sha256()`. Preflight pełnego live ma ładować
styl przed pierwszym kosztem. N-004 ma używać prawdziwego loadera.

## Dowód

- ten sam tekst LF i CRLF daje `d4e4e6bf…`;
- dopisanie jednego bajtu zmienia hash;
- pięć przypiętych akapitów przechodzi;
- pełna 32-call symulacja E-012 przechodzi 8/8;
- N-004 przechodzi 7/7 bez atrapy stylu;
- finalna regresja T-117: 49/49, `data/` bez zmian.

## Ograniczenie

Nie wykonano jeszcze prawdziwego dispatchu Fable 5, ponieważ brak lokalnych
kluczy. Naprawa dowodzi osiągalności pisarza i integralności wejścia, nie jakości
tekstu live.
