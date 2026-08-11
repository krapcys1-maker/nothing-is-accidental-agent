# P2-1 — kiedy dwa przewody naprawdę stają się jednym kontraktem

Generowanie tematów i research wyglądały na bezpieczne, bo oba wyłączały retry SDK. To był jednak tylko jeden wymiar kontroli. Każda ścieżka tworzyła własnego klienta Anthropic, nie nazywała geografii ani tieru i przyjmowała techniczny model bezpośrednio z dawnego payloadu.

Naprawa nie stworzyła trzeciego frameworka. Oba joby zamrażają teraz istniejący binding stabilnej roli: TOPIC_GENERATION albo ARTICLE_RESEARCH. Binding musi wskazywać exact `ANTHROPIC`, exact model zgodny z durable intentem i `FORBIDDEN`. Dopiero wtedy wspólny adapter może wysłać jeden request z `global`, `standard_only` i retry `0` na obu poziomach.

Najbardziej użyteczny smoke nie kończył się na przechwyceniu kwargs. Fake SDK przeszedł pełną ścieżkę evidence research: trwały job, jedna synteza, Research Card, trzy rekordy authoritative lineage i pakiet przyjęty przez przygotowanie ARTICLE. Wszystko na nowej bazie tymczasowej, bez sieci i kosztu.

Mocniejsza bramka ujawniła też dług testów. Jedyny pełny przebieg znalazł 15 starych fixture’ów bez authority albo pełnej odpowiedzi fake SDK. Zamiast rozluźnić kontrakt, fixture’y dostały jawne role i model identity. Ich dokładny zestaw przeszedł po naprawie, ale pełnego przebiegu nie powtórzono, bo właściciel dopuścił dokładnie jeden. Dlatego kod jest naprawiony, a formalna bramka nadal uczciwie pozostaje otwarta.

Najkrótsza lekcja: retry zero odpowiada na pytanie „ile razy?”. Frozen authority odpowiada na trudniejsze pytanie „co dokładnie miało prawo zostać wykonane?”.
