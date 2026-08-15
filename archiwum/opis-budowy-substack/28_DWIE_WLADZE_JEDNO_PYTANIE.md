# Dwie władze, jedno pytanie

Reviewer powiedział „przepisz". System usłyszał „koniec". Oba zdania dotyczyły tego samego tekstu i tych samych dowodów.

Artykuł o dziurach w jezdni przeszedł całą drogę: temat, sześciu kandydatów na źródła, trzy pobrane strony, Research Card z rekomendacją, gotowy draft. Na końcu reviewer zablokował 2 z 26 segmentów — początek tekstu opisywał praktykę operacyjną, której zacytowana ustawa nie obejmowała. Ocena była trafna. Reviewer poprosił o jedną poprawkę.

Poprawka nigdy nie powstała. Zadanie skończyło się statusem `FAILED` przy jednej próbie writera i wykorzystanym budżecie 0,28 z sufitu 2,00 USD. Pieniądze nie były przyczyną.

Przekazana diagnoza wskazywała pętlę iterującą po numerach prób. Pętla była niewinna. Nigdy nie dostała drugiego obiegu, bo zadanie kończyło się w środku pierwszego. Dziewięć deterministycznych ewaluacji ma własny agregat, a w nim `BLOCK` bije `REWRITE_ONCE`. Jedna z tych ewaluacji — ta od twierdzeń niepokrytych dowodami — miała `BLOCK` wpisany na sztywno. Werdykt reviewera został nadpisany, zanim ktokolwiek zdążył go przeczytać.

Ciekawsze jest to, co działo się obok. Ręczna ścieżka wznowienia bramkuje się na decyzji reviewera, nie na agregacie. Operator mógł więc uzyskać dokładnie to, czego automat odmawiał. Ta sama ocena, dwie drogi, dwie odpowiedzi.

To nie jest awaria pojedynczego pliku. To skutek posiadania dwóch władz orzekających w tej samej sprawie. Dopóki obie mówiły to samo, nikt nie zauważył, że są dwie. Rozjazd ujawnia się dopiero na pierwszym trudnym przypadku — czyli dokładnie wtedy, gdy najbardziej przeszkadza.

Naprawa nie polega na obniżeniu poprzeczki. Draft dalej nie przechodzi. Dostaje wyłącznie tę jedną próbę, którą reviewer sam mu przyznał. Zmyślone doświadczenie i temat sprzeczny z marką nadal kończą tekst natychmiast, bo tych rzeczy przepisaniem się nie naprawia.

Naprawa miała jednak własną wadę i to ona jest tu najciekawsza. Wąski przebieg testów na plikach, których dotknąłem, wyszedł zielony — 360 na 360. Dopiero pełna suita pokazała dwie porażki i obie mówiły to samo: reviewer został wywołany dwa razy zamiast raz.

Powód jest nieprzyjemnie elegancki. Z perspektywy bramki „reviewer nie policzył wszystkich twierdzeń" wygląda identycznie w dwóch zupełnie różnych sytuacjach: kiedy reviewer przeczytał tekst i uznał, że część zdań nie ma pokrycia, oraz kiedy reviewer w ogóle nie odpowiedział — odmówił, zwrócił nie-JSON albo przedstawił się innym modelem. Pierwsze to opinia redakcyjna. Drugie to awaria. Mój rewrite traktował je tak samo, więc awaria providera zamieniała się w automatyczne drugie płatne wywołanie, bez człowieka w pętli. Dokładnie ta rzecz, której ten projekt zakazuje wprost.

Rewrite jest teraz przyznawany tylko wtedy, gdy reviewer naprawdę wydał werdykt. Nieczytelna odpowiedź nie jest opinią i nie kupuje drugiej próby.

Morał praktyczny jest tańszy niż wygląda: kiedy zmieniasz decyzję bramki, „testy dotkniętych plików" to zła definicja zakresu. Dotknięte jest wszystko, co tę decyzję konsumuje — a to zwykle miejsca, o których nie pamiętasz.

Zostaje pytanie, którego jeszcze nie zamknęliśmy. Bramka, która zablokowała ten tekst, mierzy równocześnie cztery różne rzeczy: werdykt o pojedynczym zdaniu, werdykt o całym dokumencie, prostą heurystykę pokrycia słów i niezgodność writera z własnym raportem. Kiedy taka bramka mówi „nie", nie mówi, na co.

Koszt tej naprawy wyniósł zero. Cała weryfikacja jest offline. Nic nie zostało opublikowane.
