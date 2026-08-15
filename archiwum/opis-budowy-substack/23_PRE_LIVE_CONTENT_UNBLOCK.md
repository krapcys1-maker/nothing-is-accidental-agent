# Pamięć przed rachunkiem

PRE-LIVE CONTENT FLOW CHECK nie znalazł braku modelu. Opus był już zakwalifikowany, aktywny i przypięty do roli ARTICLE_WRITER. Znalazł coś bardziej przyziemnego: system nie miał jednej legalnej drogi od tej decyzji do transportu. Istniał frozen binding, ale produkcyjny content kończył na `FakeContentWriter`. Dispatcher rozpoznawał tryb płatny, lecz żaden production root nie składał go z jawną zgodą. ARTICLE wymagał niezależnego reviewera, którego dostępne implementacje należały do testów.

Naprawa nie polegała na otwarciu workera. Powstał jeden targetowany entrypoint dla jednego ARTICLE. Operator musi nazwać job, approval, osobę zatwierdzającą, czas wygaśnięcia i dodatni limit kosztu. Root ponownie odczytuje frozen binding i odmawia, jeśli nie widzi dokładnie `ARTICLE_WRITER / OPUS / claude-opus-5 / fallback=FORBIDDEN`. Dopiero wtedy składa istniejący dispatcher, pipeline i writer. Zwykły dispatcher nadal startuje z `allow_paid_content=False`.

Reviewer okazał się problemem innego rodzaju. Pierwsza implementacja wyglądała rozsądnie: fakt dostawał PASS po materialnym pokryciu konceptów z frozen evidence, inferencja przechodziła tylko bez liczb i odwołań do źródeł, a reszta blokowała. Testy były zielone.

To rozwiązanie było błędne. Zdanie może powtórzyć trzy słowa z evidence, a potem dopisać nowy fakt. Lexical overlap zobaczy znajome koncepty i nie zrozumie, że końcówka zmieniła znaczenie. Wcześniejszy ADR-123 opisywał dokładnie tę granicę: warstwa deterministyczna sprawdza kompletność, fingerprinty i legalność evidence, lecz nie może udawać semantycznego reviewera. Heurystykę usunęliśmy.

Istniejący frozen ARTICLE_REVIEWER seam również nie był gotowym wyjściem. Potrafi zamrozić binding, sprawdzić qualification, capability, pricing, returned identity i zapisać terminalny role execution. Nie zapisuje jednak trwałego `IN_FLIGHT` przed providerem. Crash po odpowiedzi, ale przed rekordem, pozwoliłby przy restarcie wykonać drugi płatny review i zgubić pierwszy koszt. Surowe podłączenie adaptera zamieniłoby jeden blocker w okno replayu.

Końcowy controlled root dlatego nie dochodzi do writera. Zatrzymuje się na `CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE`, zanim powstanie SDK, attempt, usage albo koszt i zanim approval zostanie skonsumowany. WriterPort i kompozycja są kandydatami, ale pełny flow pozostaje zablokowany przez B3.

Najciekawszy blocker nie dotyczył jednak providera. Dotychczasowy dedup patrzył głównie na tytuł. Taki system rozpoznaje kopię napisu, ale nie kopię odpowiedzi. „Why airline ticket prices change every few hours” i „Your seat has no stable price” mogą prowadzić do dokładnie tej samej tezy o revenue management, mimo że wyglądają inaczej.

Nowa pamięć nie potrzebuje vector DB. Dla każdego konta zbiera trwałe topics, pytania, najnowszą thesis lub working_thesis z Research Card oraz body rzeczywiście istniejącego contentu albo draftu. Status `USED` nie wygasa. Pusty `content_item`, który powstał przed błędem konfiguracji, nie udaje wcześniejszego artykułu. Porównanie rozdziela dokładny temat, silną parafrazę, tę samą centralną tezę i parafrazę wcześniejszego contentu. Wspólny szeroki obszar nie wystarcza do blokady.

Sześć kontrprób dało oczekiwany podział: identyczny temat, silna parafraza, inny tytuł tej samej tezy, dawny USED topic i wcześniejszy content zostały zatrzymane. Nowa teza o opłatach za bagaż nie została zablokowana tylko dlatego, że nadal dotyczyła linii lotniczych. Ten sam gate działa po topic generation, przed płatnym `durable_provider_v2` research i przed produkcyjnym writerem. Controlled fetch pozostał poza nim — pierwsza pełna suita wykryła, że `dry_run=false` nie znaczy automatycznie „płatny research”, i wymusiła dokładniejsze rozróżnienie.

Model generujący tematy dostaje teraz skróconą pamięć: najwyżej 40 rekordów, każdy ograniczony do title, question, central thesis i statusu. Pełny artykuł nigdy nie trafia do tego promptu. Historia ma pomóc nie proponować w kółko tego samego, ale nie zastępuje gate po odpowiedzi modelu.

Końcowy dowód obejmuje sześć nowych testów: fail-closed root bez reviewera, ordinary paid refusal, sześć kontrprób novelty, finalny bounded topic prompt i ordering przed research oraz writerem. Nie wykonano requestu Anthropic, publikacji, browsera ani migracji produkcyjnej bazy. B1, B2, B4 i B5 mają kandydatów. B3 wymaga production callera i trwałego reviewer lifecycle przed external effect.

Najważniejsza lekcja z tej naprawy jest prosta: system nie powinien pytać o pamięć po otrzymaniu rachunku. Powinien pamiętać, zanim pozwoli wydać pierwszy cent.
