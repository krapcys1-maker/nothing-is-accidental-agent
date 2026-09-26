# Jak pisze Nothing Is Accidental

Audyt i zmiany z 26 września 2026.

Późniejsze dopracowanie notek, komentarzy i naprawy tekstu wraz z płatnymi próbami: [prosty język, charakter i lekki humor](<C:/Users/user/Desktop/agent project/agent-v2/docs/NOTKI_I_KOMENTARZE_PROSTO_NATURALNIE.md>). Pełny zbiór promptów zawiera już te nowsze instrukcje; poniższe wyniki liczbowe opisują wcześniejszy audyt.

Nowy kierunek: dociekliwy redaktor, który tłumaczy trudny temat komuś spoza branży. Ma własny osąd, umie pochwalić konkretną poprawę, podważyć słaby argument i przyznać rację. Najpierw daje czytelnikowi zrozumienie sprawy. Charakter wynika z tego, co zauważa i jak rozumuje.

Pełny tekst wspólnego głosu jest w [glos_krotkich.md](<C:/Users/user/Desktop/agent project/agent-v2/prompts/glos_krotkich.md>). Pomimo historycznej nazwy pliku obejmuje teraz również artykuły. [Pełny zbiór promptów](<C:/Users/user/Desktop/agent project/agent-v2/docs/PELNE_PROMPTY_GLOSU.md>) zawiera wszystkie 35 plików Markdown, instrukcje systemowe, opisy form z konfiguracji, kod składania kontekstu oraz pięć zatwierdzonych przykładów stylu artykułów.

## Co ma być słychać w tekście

- **Prostota:** kto co zrobił, jak to działa, z czego wynika wniosek. Terminy techniczne trzeba wyjaśnić przez ich znaczenie, a nie tylko rozwinąć skrót.
- **Dociekliwość:** dlaczego tak jest, kto korzysta, kto płaci, jakie są inne wyjaśnienia i czego trzeba się dowiedzieć. Dobór pytań zależy od materiału.
- **Samodzielny osąd:** zgoda, krytyka i uznanie wymagają powodu. Brak obowiązkowego sprzeciwu.
- **Charakter:** bezpośredniość, konkret, czasem suchy humor. Dopuszczona pierwsza osoba jako stanowisko redakcyjne, naturalna uprzejmość i różna długość zdań.
- **Rzetelność:** możliwa korzyść nie dowodzi intencji. Hipoteza ma być rozpoznawalna jako hipoteza. Naturalny głos nie wymaga wymyślonej biografii ani udawanych doświadczeń.

## Od tematu do publikacji

| Etap | Co otrzymuje i co robi | Instrukcje |
|---|---|---|
| Wyszukiwanie tematów | Bieżące wydarzenia, obserwowane kanały, pytania czytelników, wcześniejsze publikacje i obszary zainteresowań. Wybiera przydatne pytanie do zbadania. | `ciekawostki.md`, `skaut.md`, opcjonalnie `fedreg.md` |
| Bank materiałów | Porządkuje znaleziska, usuwa powtórki i proponuje różne uzasadnione ujęcia. Nie wymaga już mitu do obalenia. | `bank.md`, `parowanie.md`, `powtorka.md` |
| Pytanie na artykuł | Z konkretnego ustalenia buduje pytanie i osobne kierunki badania. Temat może być głęboki w jednej dziedzinie. | `artykul_z_puli.py`: `SYSTEM`, `PYTANIE` |
| Zdobywanie źródeł | Wyszukuje dokumenty, czyta je i wyciąga dokładne fragmenty. Rozróżnia stanowisko firmy i niezależne ustalenie. | `dyskoveria.md`, `dyskoveria_odzysk.md`, `klasyfikacja.md` |
| Pogłębianie researchu | Sprawdza luki, konkurencyjne wyjaśnienia i kontrdowody; szuka dalszych źródeł tylko wtedy, gdy są potrzebne. | `research_ocena.md`, `research_szukanie.md`, `research_wyciag.md` |
| Karta dla pisarza | Łączy potwierdzone fakty, liczby, sprzeczności i niewiadome. Zachowuje znaczenie i zakres źródeł. | `synteza.md` |
| Ocena materiału na artykuł | Ocenia, ile treści materiał rzeczywiście uniesie. Dodana droga: przydatne wyjaśnienie poparte konkretnym fragmentem źródłowym. | `warto_pisac.md`, `wykonalnosc.md`, `bibliotekarz.md` |
| Pisanie artykułu | Wspólny głos, karta faktów, opcjonalne próbki stylu i wcześniejsze uwagi. Pisze **Fable**. | `glos_krotkich.md`, `pisarz.md`, dwa profile artykułów |
| Przygotowanie notki | Wyjaśnia znaczenie materiału i wybiera istotne pytania. Jest to krótka notatka robocza dla pisarza. | `rozbior.md` |
| Pisanie notki | Wspólny głos, materiał, analiza, typ i opcjonalna forma. Dostaje również historię otwarć i zakończeń. Pisze **DeepSeek Flash**. | `glos_krotkich.md`, `notka.md`, `NOTE_TYPES`, `NOTE_FORMS` |
| Wybór rozmów | Szuka postów, do których można dodać coś konkretnego. Pod własnymi tekstami priorytet mają sensowne pytania i korekty. | `cele.md`, `kogo_odpowiedziec.md` |
| Komentarz | Czyta pełny dostępny tekst, sprawdza wcześniejszy pomysł z zajawki, odpowiada na rzeczywistą treść. | `komentarz.md` + wspólny głos |
| Odpowiedź | Korzysta z komentarza czytelnika i dostępnego własnego tekstu. Może sięgnąć do wyszukiwania, gdy potrzebuje sprawdzić fakt. | `odpowiedz.md` + wspólny głos |
| Restack | Wybiera konkretną wartość cudzego wpisu i dodaje krótką reakcję. | `restack.md` + wspólny głos |
| Kontrola i korekta | Sprawdza twierdzenia, zakres źródeł i aktualność. Opinia nie zwalnia z prawdziwości jej faktycznych przesłanek. Naprawa dotyczy zakwestionowanych faktów. | `recenzent.md`, `weryfikacja.md`, `naprawa.md`; `forma.md` zbiera obserwacje o formie |
| Zapis i publikacja | Kod zapisuje wynik, stosuje istniejące limity, kontroluje powtórki oraz wywołuje publikację. Po potwierdzeniu zapisuje historię. | `stages.py`, `run.py`, `artykul_z_puli.py`, `browser.py` |
| Obrazek artykułu | Osobny brief obrazu; nie ustala sposobu pisania tekstu. | `grafika.md` |

Plik ze szablonem to tylko część wejścia modelu. Przed nim jest komunikat systemowy, a dalej rzeczywiste źródła i kontekst. Komentarze, odpowiedzi i restacki dostają krótką pamięć udanych wcześniejszych wypowiedzi, żeby nie powtarzać tego samego otwarcia. Ta pamięć nie jest źródłem nowych faktów. Niektóre obsługiwane ścieżki, np. osobny skaut, nie są uruchamiane przy każdej publikacji.

## Co ograniczało głos i co zostało zmienione

Usunąłem obowiązkowe bardzo krótkie zdanie w każdej notce, nakaz mocnej opinii, limity liczby terminów technicznych, zakazy interpunkcji, sztywne liczby akapitów i przymus konkretnego zakończenia. Formy notek są teraz propozycjami sposobu opowiedzenia tematu. Kod nie losuje już długości komentarza/odpowiedzi ani zakończenia i liczby analogii w artykule.

Usunąłem wymóg, żeby każdy materiał obalał przekonanie i żeby jego skutek był koniecznie opisany słowami „you/your”. Wybór tematów i pytania do artykułu nie wymuszają już określonej liczby katastrof, precedensów ani przykładów z innych branż. Zachowana preferencja tematów z obserwowanych kanałów wynika z wcześniejszego ustawienia kierunku publikacji.

Długi, dublujący instrukcje fragment `po_ludzku.md` przestał być dołączany. Profile artykułów zostały skrócone i podporządkowane wspólnemu głosowi. Zatwierdzony korpus przykładów pozostał bez zmian.

Weryfikator rozróżnia aktualność i historię: pojawienie się nowszej wersji modelu nie unieważnia prawdziwego, odpowiednio datowanego opisu starszej wersji. Kontrola faktów nie powinna usuwać tematu tylko dlatego, że opisuje przeszłość.

## Jakie granice pozostają

Pozostają źródła dla konkretnych faktów, rozróżnienie wiedzy i przypuszczeń, ochrona przed poleceniami w cudzych tekstach, poprawny format odpowiedzi dla programu, limity kosztów i unikanie duplikatów. Nie dokładam nowego etapu modelowego ani dodatkowego płatnego recenzenta.

Długości pozostają wskazówkami planowania: zwykła notka około 33–120 słów, wyjaśniająca 120–200, komentarz/odpowiedź zwykle 20–70, artykuł według ilości materiału. Restack zachowuje techniczny limit 40 słów. Naprawa faktów ma zachować niezakwestionowane zdania. Część kontroli jakości działa jako ostrzeżenia; nie stanowi gwarancji bezbłędności każdego tekstu.

Harmonogram, dni ciszy, liczba publikacji oraz modele nie były przedmiotem tej zmiany. Artykuły nadal pisze Fable; krótkie formy i research korzystają z DeepSeek Flash.

## Co pokazały rzeczywiste wywołania

Wykonałem płatne porównanie poprzednich i nowych promptów na tym samym materiale testowym, potem kolejne próby po poprawkach. Materiał był kontrolowany i częściowo fikcyjny: służył ocenie pisania, nie przygotowaniu wiadomości o rzeczywistych firmach. Testy obejmowały notki, komentarz, odpowiedź, restack, analizę oraz szkic artykułu Fable. Osobna próba łączy rzeczywistą analizę z pisaniem notki i sprawdza brief artykułu oraz recenzję.

Próby ujawniły zarówno poprawę, jak i błędy. Analiza początkowo zbyt długo szukała motywów bez podstaw; została zawężona do pytań ważnych dla danego materiału. W komentarzu model dopisał nieudokumentowane wymaganie przyłączenia fabryki do sieci; po poprawce wyjaśnił samą kolejkę eksportową. Fable pisał czytelniej, ale nadal zdarzały mu się zbyt szerokie twierdzenia o kosztach i przepisach. To powód, dla którego uproszczenie stylu nie obejmuje rezygnacji z kontroli faktów.

Przykład komentarza z końcowej próby, tłumaczenie z angielskiego:

> Kolejka przyłączeniowa dla eksportu to lista oczekujących na zgodę na oddawanie energii do publicznej sieci. Jeśli fabryka zużywa własną energię słoneczną na miejscu i nie wysyła jej do sieci, ta kolejka wypada z harmonogramu. To konkretna korzyść. Zarobek wykonawcy jest osobną kwestią.

To próbka szkicu, nie opublikowany komentarz. W tym audycie nie uruchamiałem publikacji. Płatne generowanie i potwierdzenie publikacji to dwa różne testy.

## Rozmiar instrukcji i koszty

Sam szablon artykułu skrócił się o około 82%, notki o 86%, odpowiedzi o 71%, skauta o 89%, a wyszukiwania ciekawostek o 79%. To porównanie znaków szablonów. Całe wejście zawiera również wspólny głos, źródła, historię i przykłady, dlatego rachunek nie spada automatycznie o ten sam procent.

W kontrolowanej parze złożony prompt notki miał około 26,7 tys. znaków przed zmianą i 7,6 tys. po pierwszej zmianie; artykułu odpowiednio 41,9 tys. i 15,2 tys. Końcowe doprecyzowania nieco zwiększyły nowe instrukcje. Niektóre krótkie formaty otrzymały więcej objaśniających wskazówek. Wyniki pojedynczych prób nie wystarczają do prognozy miesięcznego kosztu.

## Pliki do przejrzenia

- [Pełne prompty i składanie kontekstu](<C:/Users/user/Desktop/agent project/agent-v2/docs/PELNE_PROMPTY_GLOSU.md>).
- [Wspólny głos](<C:/Users/user/Desktop/agent project/agent-v2/prompts/glos_krotkich.md>).
- [Porównanie przed i po](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/live-comparison.json>).
- [Próby po doprecyzowaniu](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/live-final.json>).
- [Ostatni szkic artykułu](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/live-article-final.json>).
- [Analiza → notka, brief i recenzja](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/live-pipeline.json>).
- [Wyniki testów kodu](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/tests-final.json>).

## Wynik techniczny i ograniczenia

Końcowa kontrola serwera: **26 września 2026, 05:51 UTC**. Wszystkie **23 wdrożone pliki** zgadzają się z lokalnymi wersjami. Załadowanie pięciu przypiętych przykładów stylu przeszło poprawnie. Harmonogramy pozostają aktywne; procesy dziennego przebiegu i artykułu były w chwili kontroli bezczynne. Potwierdzone modele: `claude-fable-5-1` dla artykułów i `deepseek-flash` dla krótkich tekstów oraz researchu.

| Próba | Wywołania | Szacowany koszt USD |
|---|---:|---:|
| Poprzednie i nowe prompty, przebieg 289 | 14 | 0,574940 |
| Nowe prompty po doprecyzowaniu, przebieg 290 | 7 | 0,195805 |
| Ostatni szkic Fable, przebieg 291 | 1 | 0,189720 |
| Analiza → notka, brief artykułu i recenzja, przebieg 292 | 4 | 0,018040 |
| **Razem** | **26** | **0,978505** |

Wszystkie cztery przebiegi zakończyły się statusem `DONE`. Koszty są wyliczeniem lokalnego licznika; stawki mają oznaczenie `price_verified=0`, więc nie przedstawiam ich jako rachunku dostawcy. Kontrola stanu potwierdziła brak zmian w chronionych plikach publikacji i banku materiałów. To testy rzeczywistych API na kontrolowanym materiale, bez pełnego wyszukiwania w sieci ani publikowania.

Końcowa recenzja wykryła zdanie Fable: „If you have already paid for the evidence-gathering team, the new law adds little to your bill.” Materiał potwierdzał istnienie zespołu, ale nie wysokość przyszłych kosztów. Recenzent wskazał ten brak poprawnie. Nie wychwycił wszystkich nadinterpretacji: podtytuł zmieniał napięty budżet małej firmy w niemożność poniesienia kosztu, a zakończenie przeceniało jej większego konkurenta jako już gotowego do spełnienia wymogu. W tej próbie recenzent otrzymał treść artykułu bez podtytułu. Szkic nie został opublikowany. **Nie traktuję tej próby jako potwierdzenia pełnej poprawności faktów.**

Notka z rzeczywistego łańcucha analiza → pisanie poprawnie wyjaśniała, że 100 widocznych i 900 ukrytych tokenów oznacza w podanym przykładzie rozliczenie 1000 tokenów wyjściowych. Nie przypisała temu typowej proporcji ani ceny w walucie. Nadal mogła prościej wyjaśnić sam „token” i krócej opisać zastrzeżenia. Nowy głos jest kierunkiem i wspólną instrukcją, a pojedyncza udana próbka nie dowodzi, że każdy kolejny tekst będzie równie czytelny.

**24 uruchomione pliki testowe przeszły.** Obejmują składanie głosu, wybór modeli, temat artykułu, ochronę przed wstrzyknięciem instrukcji, naprawę tekstu i kontrolę budżetu. Dwa dodatkowe starsze testy nadal mają błędy: `test_pusty_budzet_nie_sprawdza` zgłasza cztery porażki, a `test_artykul_nie_ginie_po_drodze` kończy się na pustej puli testowych kandydatów. Oba zachowania odtworzyłem również na kodzie sprzed tych zmian. Nie oznaczam całego zestawu testów jako zielonego.

Szczegóły: [zbiorczy wynik](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/summary.json>) oraz [potwierdzenie serwera](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-full-audit-20260926/server-verification.json>).
