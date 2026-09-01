1. `agent-v2/stages.py:4`
   Cytat: „Awaria = proces kończy się z kodem błędu i wypisuje, na czym stanął; uruchamiasz od nowa.”
   Co mówi kod: zwykła awaria `warto_pisac` jest łapana i przebieg idzie dalej (`agent-v2/run.py:2380`–`agent-v2/run.py:2384`), tak samo awaria recenzji (`agent-v2/run.py:2455`–`agent-v2/run.py:2461`) i obserwacji formy (`agent-v2/run.py:2533`–`agent-v2/run.py:2536`).
   Rozbieżność: nie każda awaria etapu kończy proces z błędem, bo trzy awarie etapów są jawnie zamieniane na dalsze wykonanie.

2. `agent-v2/stages.py:142`
   Cytat: „Etap 8 — recenzja: rozliczenie każdego zdania (Claude).”
   Co mówi kod: funkcja wywołuje cel `review` (`agent-v2/stages.py:148`), a ten jest przypisany do `DEEPSEEK_PRO` (`agent-v2/config.py:146`).
   Rozbieżność: recenzję wykonuje DeepSeek Pro, nie Claude.

3. `agent-v2/stages.py:701`
   Cytat: „Obrót zestawu wg numeru dnia: bez tego poniedziałek i sobota dostawały identyczny plan i tydzień wyglądał jak jeden dzień powtórzony sześć razy.”
   Co mówi kod: obrót używa `numer % len(mix)` (`agent-v2/stages.py:705`), a `mix` ma pięć elementów (`agent-v2/config.py:1571`), więc dni o numerach 0 i 5 z listy (`agent-v2/stages.py:693`–`agent-v2/stages.py:696`) nadal dostają identyczną kolejność.
   Rozbieżność: zastosowany obrót nie rozróżnia poniedziałku i soboty, choć komentarz właśnie tym uzasadnia obrót.

4. `agent-v2/stages.py:750`
   Cytat: „GRAFIKA NIGDY NIE ZABIJA ARTYKUŁU.”
   Co mówi kod: obsługa wyjątków kończy się przed zapisem pliku (`agent-v2/stages.py:754`–`agent-v2/stages.py:777`), natomiast `mkdir` i `write_bytes` są poza `try` (`agent-v2/stages.py:780`–`agent-v2/stages.py:783`), a ich wyjątek zatrzymuje przebieg przed publikacją (`agent-v2/run.py:2600`, `agent-v2/run.py:2651`–`agent-v2/run.py:2660`).
   Rozbieżność: błąd zapisu grafiki może zatrzymać publikację artykułu, mimo obietnicy, że każda awaria grafiki kończy się artykułem bez grafiki.

5. `agent-v2/stages.py:925`
   Cytat: „Sam podział jest losowany, więc dwa dni nigdy nie wyglądają tak samo.”
   Co mówi kod: każde wywołanie niezależnie losuje liczbę sesji, godziny, wagi i minuty (`agent-v2/stages.py:930`–`agent-v2/stages.py:939`) i nie przechowuje poprzedniego wyniku ani nie odrzuca powtórzeń.
   Rozbieżność: losowanie dopuszcza identyczny wynik w dwa dni, więc nie daje gwarancji „nigdy”.

6. `agent-v2/stages.py:1447`
   Cytat: „Notka z kupletem jest nadal lepsza niz brak notki, a przy trzech kandydatach zwykle jest z czego wybierac za darmo.”
   Co mówi kod: `NOTE_CANDIDATES` wynosi 1 (`agent-v2/config.py:864`), a pętla tworzy dokładnie tyle kandydatów (`agent-v2/stages.py:2188`).
   Rozbieżność: sortowanie nie wybiera spośród trzech kandydatów, lecz z listy jednoelementowej.

7. `agent-v2/stages.py:1498`
   Cytat: „Zostaje kryterium SORTOWANIA, nie bramka: przy 53% i trzech kandydatach sortowanie zwykle ma z czego wybierac, a odrzucanie kosztowaloby polowe notek.”
   Co mówi kod: `NOTE_CANDIDATES = 1` (`agent-v2/config.py:864`), a sortowana lista powstaje z tylu iteracji (`agent-v2/stages.py:2188`, `agent-v2/stages.py:2246`–`agent-v2/stages.py:2247`).
   Rozbieżność: przy jednym kandydacie sortowanie nie ma opisanego wyboru spośród trzech.

8. `agent-v2/stages.py:1512`
   Cytat: „Kandydatow mamy trzech, wiec da sie wybrac tego, ktory nie powtarza otwarcia — i to jest sprawdzenie w kodzie, nie zyczenie w prompcie.”
   Co mówi kod: konfiguracja ustawia jednego kandydata (`agent-v2/config.py:864`), a sama funkcja w innym docstringu przyznaje, że sortowanie listy jednoelementowej nic nie robi (`agent-v2/stages.py:1456`–`agent-v2/stages.py:1459`).
   Rozbieżność: kod nie ma trzech kandydatów i nie może przez wybór zagwarantować niepowtórzonego otwarcia.

9. `agent-v2/stages.py:2234`
   Cytat: „Przy pieciu notkach dziennie po trzech kandydatow to roznica miedzy pietnastoma sprawdzeniami a szescioma.”
   Co mówi kod: liczba kandydatów na notkę wynosi 1 (`agent-v2/config.py:864`) i steruje pętlą generowania (`agent-v2/stages.py:2188`).
   Rozbieżność: rachunek opiera się na trzech kandydatach na notkę, których bieżący kod nie generuje.

10. `agent-v2/stages.py:2412`
    Cytat: „Ta funkcja jest wolana raz na przebieg, a przebiegow jest trzy dziennie — wiec drugi przebieg dostawal nastepny artykul z kolejki i tego samego dnia wychodzila druga notka promujaca, a trzeciego dnia trzecia.”
    Co mówi kod: `PRZEBIEGOW_DZIENNIE` wynosi 5 (`agent-v2/config.py:1847`), a timer ma pięć wpisów `OnCalendar` (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: funkcja może być wołana w pięciu, a nie trzech zaplanowanych przebiegach dziennie.

11. `agent-v2/stages.py:2784`
    Cytat: „Pięć notek na jeden dzień, każda z innego materiału.”
    Co mówi kod: parametr `ile` przycina listę typów do dowolnej żądanej części (`agent-v2/stages.py:2800`–`agent-v2/stages.py:2801`), a zwykły caller przekazuje bieżący przydział `na_teraz["notki"]` (`agent-v2/run.py:1223`–`agent-v2/run.py:1224`).
    Rozbieżność: funkcja może zwrócić mniej niż pięć notek i w normalnym przebiegu dostaje właśnie częściowy przydział.

12. `agent-v2/stages.py:3510`
    Cytat: „Etap 6 — karta dowodowa (Claude).”
    Co mówi kod: funkcja wywołuje cel `synthesis` (`agent-v2/stages.py:3530`), przypisany do `DEEPSEEK_PRO` (`agent-v2/config.py:138`).
    Rozbieżność: kartę dowodową tworzy DeepSeek Pro, nie Claude.

13. `agent-v2/stages.py:3872`
    Cytat: „Etap 3 — dyskoveria źródeł (Claude + wyszukiwanie po stronie dostawcy).”
    Co mówi kod: funkcja wywołuje cel `discovery` (`agent-v2/stages.py:3921`–`agent-v2/stages.py:3924`), przypisany do `DEEPSEEK_PRO` (`agent-v2/config.py:136`).
    Rozbieżność: dyskowerię wykonuje DeepSeek Pro, nie Claude.

14. `agent-v2/stages.py:4253`
    Cytat: „Wybiera temat: najpierw GLEBOKOSC, potem pewnosc i liczba zrodel.”
    Co mówi kod: głębokość, pewność i liczba źródeł zajmują dopiero pozycje 7–9 po niepowtórzeniu, nośności, artykułowości, rankingu modelu, świeżości i wątkach (`agent-v2/stages.py:4353`–`agent-v2/stages.py:4361`), a sortowanie używa tej krotki malejąco (`agent-v2/stages.py:4389`–`agent-v2/stages.py:4390`).
    Rozbieżność: głębokość nie jest pierwszym kryterium wyboru, lecz siódmym.

15. `agent-v2/stages.py:4280`
    Cytat: „TO JEST NAJWAZNIEJSZY KLUCZ PO NOSNOSCI i powod, dla ktorego ranking w ogole przepisano.”
    Co mówi kod: po `nosny(a)` krotka sortowania sprawdza jeszcze `artykulowy(a)` i `wlasny_ranking(a)`, zanim dojdzie do `swiezy(a)` (`agent-v2/stages.py:4354`–`agent-v2/stages.py:4357`).
    Rozbieżność: świeżość nie jest kluczem bezpośrednio po nośności, bo wyprzedzają ją dwa inne kryteria.

16. `agent-v2/stages.py:4439`
    Cytat: „Etap 1 — skaut tematów (Claude).”
    Co mówi kod: funkcja wywołuje cel `scout` (`agent-v2/stages.py:4456`), przypisany do `DEEPSEEK_PRO` (`agent-v2/config.py:113`).
    Rozbieżność: skauta wykonuje DeepSeek Pro, nie Claude.

17. `agent-v2/stages.py:4903`
    Cytat: „Research o Substacku mowi, ze notka zyje 7-10 dni i ze licza sie godziny szczytu — a nasz agent budzi sie trzy razy dziennie i musi wtedy COS napisac.”
    Co mówi kod: konfiguracja przewiduje pięć przebiegów dziennie (`agent-v2/config.py:1847`), zgodnie z pięcioma godzinami timera (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: agent budzi się według harmonogramu pięć, a nie trzy razy dziennie.

18. `agent-v2/run.py:977`
    Cytat: „ILE JUZ DZIS POSZLO — pytamy Substacka, nie wlasnej ksiegowosci.”
    Co mówi kod: `run.py` woła `browser.ile_dzis_wystawione()` (`agent-v2/run.py:983`), a wynik decyzyjny tej funkcji pochodzi z `z_dziennika_dzis()` (`agent-v2/browser.py:836`), czyli z własnego dziennika.
    Rozbieżność: bieżący przydział jest liczony z własnej księgowości, nie z danych Substacka.

19. `agent-v2/run.py:1039`
    Cytat: „Bazy sa wiec wazne tylko w obrebie jednego przebiegu i musza zniknac razem z nim; `dzien()` bywa wolane wiecej niz raz w jednym procesie (testy, `--dwa-razy`), a stara baza przeniosla by hamulec na nastepny.”
    Co mówi kod: parser definiuje wszystkie opcje od `--stop-after` do `--wyslij` (`agent-v2/run.py:2074`–`agent-v2/run.py:2082`) i nie definiuje `--dwa-razy`.
    Rozbieżność: komentarz odwołuje się do opcji CLI, która nie istnieje w bieżącym kodzie.

20. `agent-v2/run.py:1206`
    Cytat: „Bez niej pierwsza notka wychodzila zawsze kilka minut po starcie zegara, wiec trzy razy dziennie o tej samej porze co do kwadransa.”
    Co mówi kod: liczba przebiegów dziennych wynosi 5 (`agent-v2/config.py:1847`), a timer uruchamia je o pięciu porach (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: opisywany wzorzec występuje pięć, a nie trzy razy dziennie.

21. `agent-v2/run.py:1216`
    Cytat: „Zwloka jest ozdobna (chowa, ze trzy przebiegi dziennie startuja o tej samej minucie); notki nie sa.”
    Co mówi kod: `PRZEBIEGOW_DZIENNIE = 5` (`agent-v2/config.py:1847`) i timer zawiera pięć startów (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: zwłoka maskuje rytm pięciu, nie trzech przebiegów dziennie.

22. `agent-v2/run.py:2456`
    Cytat: „Recenzja nic nie blokuje, więc jej brak też nie może. Artykuł trafia do szuflady z adnotacją, że nie został rozliczony zdanie po zdaniu — właściciel wie, na co patrzy.”
    Co mówi kod: po obsłużeniu awarii recenzji wykonanie dochodzi do gałęzi `args.wyslij` (`agent-v2/run.py:2602`) i bezwarunkowo wywołuje publikację (`agent-v2/run.py:2651`–`agent-v2/run.py:2652`).
    Rozbieżność: na ścieżce `--wyslij` artykuł nie kończy w szufladzie, lecz jest publikowany mimo braku recenzji.

23. `agent-v2/run.py:2598`
    Cytat: „Grafika NIGDY nie zatrzymuje artykulu: brak czterech centow na obrazek nie moze wyrzucic do kosza researchu za czterdziesci.”
    Co mówi kod: wywołanie `stages.grafika` nie ma lokalnej osłony (`agent-v2/run.py:2600`), zapis pliku grafiki odbywa się poza `try` (`agent-v2/stages.py:780`–`agent-v2/stages.py:783`), a wyjątek przechodzi do kończącego przebieg `except` (`agent-v2/run.py:2658`–`agent-v2/run.py:2660`).
    Rozbieżność: wyjątek podczas zapisu grafiki może zatrzymać przebieg przed publikacją artykułu.

24. `agent-v2/run.py:2623`
    Cytat: „ZAPIS ZOSTAJE, PUBLIKACJA NIE.”
    Co mówi kod: negatywny `safe_to_post` jest tylko wypisywany (`agent-v2/run.py:2638`–`agent-v2/run.py:2649`), po czym `browser.wystaw_artykul` jest wywoływane bezwarunkowo (`agent-v2/run.py:2651`–`agent-v2/run.py:2652`).
    Rozbieżność: wynik weryfikacji niczego nie blokuje i publikacja następuje również przy zastrzeżeniach.

25. `agent-v2/browser.py:1188`
    Cytat: „Przy budzecie okolo 1,2 obserwacji na dobe to mniej wiecej jeden dzien na siedem zjadany na kims, kogo juz obserwujemy — i do 1 wrzesnia zapisywany jako PORAZKA.”
    Co mówi kod: miesięczne widełki obserwacji wynoszą 10–16 (`agent-v2/config.py:1707`), a norma dzienna jest ich środkiem podzielonym przez 30 (`agent-v2/config.py:1733`), czyli około 0,43 na dobę.
    Rozbieżność: komentarz zawyża bieżący budżet obserwacji z około 0,43 do 1,2 dziennie.

26. `agent-v2/browser.py:2375`
    Cytat: „Dlatego widelki sa inne: 30-44 obserwacje miesiecznie, ale tylko 6-12 subskrypcji.”
    Co mówi kod: bieżące widełki to 10–16 obserwacji i 12–20 subskrypcji miesięcznie (`agent-v2/config.py:1707`–`agent-v2/config.py:1708`).
    Rozbieżność: obie pary widełek są inne niż w kodzie, a subskrypcji jest obecnie planowanych więcej, nie mniej, niż obserwacji.

27. `agent-v2/browser.py:2666`
    Cytat: „Dziennik jest jedynym licznikiem obserwacji dnia, wiec falszywe „nie udalo sie" kosztuje CALA dzienna norme (przy 30-44 miesiecznie to okolo 1,2 obserwacji na dobe — czyli zwykle jedyna tego dnia), a falszywe „udalo sie" kosztuje jeden slot.”
    Co mówi kod: `FOLLOW_MIESIECZNIE` wynosi 10–16 (`agent-v2/config.py:1707`), co w obliczeniu normy daje średnio około 0,43 dziennie (`agent-v2/config.py:1733`).
    Rozbieżność: podane miesięczne widełki i wynik 1,2 na dobę nie odpowiadają bieżącemu budżetowi.

28. `agent-v2/browser.py:2722`
    Cytat: „limit jest szerszy niz przy subskrypcji: 30-44 obserwacje miesiecznie wobec 6-12 subskrypcji.”
    Co mówi kod: obserwacje mają limit 10–16, a subskrypcje 12–20 miesięcznie (`agent-v2/config.py:1707`–`agent-v2/config.py:1708`).
    Rozbieżność: limit obserwacji jest obecnie węższy od limitu subskrypcji, czyli relacja jest odwrotna od opisanej.

29. `agent-v2/config.py:111`
    Cytat: „Pisanie zostaje u Opusa 5, bo to jest produkt.”
    Co mówi kod: cel `write` jest przypisany do `FABLE` (`agent-v2/config.py:145`), zdefiniowanego jako `claude-fable-5` (`agent-v2/config.py:106`).
    Rozbieżność: artykuły pisze Fable 5, nie Opus 5.

30. `agent-v2/config.py:115`
    Cytat: „Dyskoveria MUSI być u Anthropic (DeepSeek nie ma wyszukiwania), ale nie musi być u Opusa: wybór adresów to praca mechaniczna, nie ocena.”
    Co mówi kod: `DEEPSEEK_PRO` jest opisany jako model z server-side `web_search` (`agent-v2/config.py:108`), `discovery` jest do niego przypisane (`agent-v2/config.py:136`), a implementacja przekazuje DeepSeekowi narzędzie `web_search` (`agent-v2/llm.py:234`–`agent-v2/llm.py:247`).
    Rozbieżność: DeepSeek ma wyszukiwanie po stronie dostawcy i to właśnie on wykonuje dyskowerię.

31. `agent-v2/config.py:152`
    Cytat: „Notki i komentarze na DeepSeeku — decyzja właściciela.”
    Co mówi kod: `note` jest przypisane do `CLAUDE`, a tylko `comment` do `DEEPSEEK_PRO` (`agent-v2/config.py:197`–`agent-v2/config.py:198`).
    Rozbieżność: komentarze są na DeepSeeku, lecz notki są na Claude Opus.

32. `agent-v2/config.py:152`
    Cytat: „Przy ~$0,002 za sztukę można wygenerować kilkanaście kandydatów i wybrać najlepszego, co dla czterdziestu słów działa lepiej niż jedno drogie podejście.”
    Co mówi kod: `NOTE_CANDIDATES` wynosi 1 (`agent-v2/config.py:864`) i tyle razy wykonywana jest pętla generowania notki (`agent-v2/stages.py:2188`).
    Rozbieżność: bieżący kod generuje jednego, a nie kilkunastu kandydatów do wyboru.

33. `agent-v2/config.py:246`
    Cytat: „Dyskoveria zostaje u Claude'a nawet tutaj: DeepSeek nie ma wyszukiwania po stronie dostawcy, więc bez niej nie ma czego pobierać.”
    Co mówi kod: `DEEPSEEK_PRO` ma server-side `web_search` (`agent-v2/config.py:108`), a `_call_deepseek_responses` wysyła `tools: [{"type": "web_search"}]` (`agent-v2/llm.py:234`–`agent-v2/llm.py:247`).
    Rozbieżność: kod implementuje dokładnie to wyszukiwanie po stronie dostawcy, którego komentarz DeepSeekowi odmawia.

34. `agent-v2/config.py:849`
    Cytat: „Sensowne tylko dlatego, że DeepSeek kosztuje grosze — u Fable'a byłoby to nie do obronienia.”
    Co mówi kod: notki są kierowane do `CLAUDE` (`agent-v2/config.py:197`), a liczba kandydatów wynosi 1 (`agent-v2/config.py:864`).
    Rozbieżność: generowanie kandydatów nie odbywa się na DeepSeeku i nie tworzy puli, z której wybiera się jednego.

35. `agent-v2/config.py:850`
    Cytat: „Trzech kandydatow, nie pieciu: odkad kazda notka dostaje WLASNY fakt, piaty wariant tego samego zdania niczego nie dokladal, a placilismy za niego i za jego weryfikacje.”
    Co mówi kod: `NOTE_CANDIDATES = 1` (`agent-v2/config.py:864`).
    Rozbieżność: ustawienie bezpośrednio pod komentarzem określa jednego kandydata, nie trzech.

36. `agent-v2/config.py:1746`
    Cytat: „Dwa-cztery to tyle, ile czlowiek naprawde uzna za warte podania dalej.”
    Co mówi kod: `RESTACK_DZIENNIE` wynosi `(1, 2)` (`agent-v2/config.py:1825`–`agent-v2/config.py:1829`).
    Rozbieżność: komentarz uzasadnia widełki 2–4, podczas gdy kod stosuje 1–2 restacki dziennie.

37. `agent-v2/config.py:1943`
    Cytat: „Bez niej pierwsza notka wychodzila zawsze kilka minut po starcie zegara, wiec trzy razy dziennie o tej samej porze co do kwadransa.”
    Co mówi kod: konfiguracja ma pięć przebiegów dziennie (`agent-v2/config.py:1847`), realizowanych przez pięć wpisów timera (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: pierwsza notka może ujawniać pięć startów dziennie, nie trzy.

38. `agent-v2/config.py:2113`
    Cytat: „Termin w sekundach, który realnie pokrywa podany sufit tokenów.”
    Co mówi kod: funkcja zwraca minimum z wyliczonego terminu i 300 sekund (`agent-v2/config.py:2109`, `agent-v2/config.py:2120`–`agent-v2/config.py:2121`), choć sam docstring wskazuje wyliczenia sięgające 965 sekund (`agent-v2/config.py:2115`–`agent-v2/config.py:2116`).
    Rozbieżność: dla dużych limitów tokenów zwracany termin jest obcięty i nie pokrywa podanego sufitu.

39. `agent-v2/config.py:2170`
    Cytat: „Wymieniala CZTERY bramki, nie byla przez nic czytana, a bramek jest dzis dwanascie deterministycznych i cztery obserwacyjne.”
    Co mówi kod: `deterministic_floors` może zwrócić 13 różnych nazw bramek: po jednej w `agent-v2/gates.py:164`, `agent-v2/gates.py:169`, `agent-v2/gates.py:182`, `agent-v2/gates.py:188`, `agent-v2/gates.py:193`, `agent-v2/gates.py:199`, `agent-v2/gates.py:205`, `agent-v2/gates.py:214`, `agent-v2/gates.py:221`, `agent-v2/gates.py:228`, `agent-v2/gates.py:233`, `agent-v2/gates.py:239` i `agent-v2/gates.py:244`.
    Rozbieżność: funkcja będąca wskazanym źródłem prawdy definiuje 13, a nie 12 deterministycznych typów bramek.

40. `agent-v2/norma.py:80`
    Cytat: „KIEDY PROCENT COS ZNACZY — TRZY LICZBY, TRZY ROZNE PYTANIA.”
    Co mówi kod: ten sam blok stwierdza, że progi są cztery (`agent-v2/norma.py:111`), a cztery stałe stoją w `agent-v2/norma.py:144`, `agent-v2/norma.py:180`, `agent-v2/norma.py:197` i `agent-v2/norma.py:234`.
    Rozbieżność: sekcja ma cztery liczby odpowiadające czterem pytaniom, nie trzy.

41. `agent-v2/norma.py:412`
    Cytat: „Skutek dla wlasciciela: mail o wolumenach nadal potrafi zaalarmowac o subskrypcjach (plan ~2 na tydzien), o ktorych ten licznik swiadomie milczy.”
    Co mówi kod: norma subskrypcji to środek widełek 12–20 podzielony przez 30 (`agent-v2/config.py:1708`, `agent-v2/config.py:1728`), czyli około 3,7 tygodniowo.
    Rozbieżność: bieżący plan to około 3,7, a nie około 2 subskrypcje tygodniowo.

42. `agent-v2/alarm.py:165`
    Cytat: „Agent chodzi trzy razy dziennie, wiec doba bez sladu znaczy, ze trzy przebiegi z rzedu sie nie odbyly.”
    Co mówi kod: agent ma pięć przebiegów dziennie (`agent-v2/config.py:1847`) i pięć czasów uruchomienia (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: doba ciszy odpowiada pięciu planowym przebiegom, nie trzem.

43. `agent-v2/alarm.py:187`
    Cytat: „Suma norm dziennych z configu to okolo 30 dzialan. Sufit 60 jest wiec podwojeniem tego, co zaplanowane: dosc luzny, zeby nie krzyczec na dobry dzien, i dosc ciasny, zeby zlapac zapetlenie.”
    Co mówi kod: `normy_dzienne` sumuje 5 notek, średnio 13 polubień, 19 komentarzy, 1,5 restacku, 16/30 subskrypcji i 13/30 obserwacji (`agent-v2/config.py:1571`, `agent-v2/config.py:1600`, `agent-v2/config.py:1614`, `agent-v2/config.py:1707`–`agent-v2/config.py:1708`, `agent-v2/config.py:1724`–`agent-v2/config.py:1733`, `agent-v2/config.py:1829`), czyli około 39,5 działania dziennie.
    Rozbieżność: sufit 60 jest około 1,52-krotnością bieżącej normy, nie jej podwojeniem.

44. `agent-v2/alarm.py:263`
    Cytat: „Wszystkie trzy przebiegi agenta (11:20, 19:20, 23:40 UTC) leza PO nim, wiec o siodmej rano kubelek "dzisiaj" jest pusty z definicji.”
    Co mówi kod: timer uruchamia agenta także o 17:00 i 21:30, łącznie pięć razy (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: wyliczenie pomija dwa z pięciu codziennych przebiegów.

45. `agent-v2/alarm.py:320`
    Cytat: „Alarm chodzi o 07:00 UTC, a przebiegi agenta o 11:20, 19:20 i 23:40 — wiec o siodmej "dzisiaj" jest jeszcze puste i pytanie o nie zawsze odpowiadalo zero.”
    Co mówi kod: harmonogram zawiera również 17:00 i 21:30 (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: komentarz przedstawia niepełny, trzyczęściowy harmonogram zamiast bieżących pięciu uruchomień.

46. `agent-v2/alarm.py:426`
    Cytat: „Przy tempie 6-12 subskrypcji miesiecznie sto osob to okolo jedenastu miesiecy pracy.”
    Co mówi kod: miesięczne widełki subskrypcji wynoszą 12–20 (`agent-v2/config.py:1708`), czyli przy ich środku 100 osób odpowiada około 6,25 miesiąca.
    Rozbieżność: komentarz używa starych widełek i prawie dwukrotnie zawyża czas potrzebny na 100 subskrypcji.

47. `agent-v2/gates.py:1`
    Cytat: „Cztery bramki, które blokują. Reszta to notatki.”
    Co mówi kod: `verdict` niezależnie od listy uwag zawsze zwraca `("SAVED", None)` (`agent-v2/gates.py:531`–`agent-v2/gates.py:539`), a ścieżki produkcyjne używają właśnie tego wyniku (`agent-v2/run.py:2554`, `agent-v2/artykul_z_puli.py:1292`).
    Rozbieżność: żadna z bramek przekazanych do `verdict` nie blokuje artykułu.

48. `agent-v2/db.py:1`
    Cytat: „Baza: cztery tabele, zero migracji, zero triggerów, zero CHECK-ów z limitami.”
    Co mówi kod: przy każdym połączeniu wywoływane jest `_dopisz_brakujace_kolumny` (`agent-v2/db.py:92`–`agent-v2/db.py:94`), które dla istniejących baz wykonuje `ALTER TABLE ... ADD COLUMN` (`agent-v2/db.py:114`–`agent-v2/db.py:124`).
    Rozbieżność: kod automatycznie migruje schemat istniejącej bazy przez dodawanie brakujących kolumn.

49. `agent-v2/db.py:64`
    Cytat: „która z czterech bramek”
    Co mówi kod: jedyny produkcyjny werdykt zawsze zwraca `blocked_by=None` (`agent-v2/gates.py:531`–`agent-v2/gates.py:539`), a oba produkcyjne wywołania pobierają tę wartość z `gates.verdict` (`agent-v2/run.py:2554`, `agent-v2/artykul_z_puli.py:1292`).
    Rozbieżność: pole nie wskazuje żadnej z czterech bramek, bo bieżący werdykt nigdy nie zwraca blokady.

50. `agent-v2/llm.py:4`
    Cytat: „Bez rezerwacji, bez rekoncyliacji, bez ponowień — świadomy kompromis: jeśli proces zginie w połowie wywołania, koszt tego wywołania nie trafi do logu.”
    Co mówi kod: konfiguracja ustawia dwa ponowienia (`agent-v2/config.py:507`–`agent-v2/config.py:511`), a `llm.call` wykonuje pętlę prób i ponawia błędy przejściowe (`agent-v2/llm.py:489`–`agent-v2/llm.py:513`).
    Rozbieżność: warstwa LLM ma automatyczne ponowienia, mimo że docstring wyklucza je wprost.

51. `agent-v2/artykul_z_puli.py:1325`
    Cytat: „Zapis zostaje, publikacja nie: artykul jest juz na dysku z okladka, wiec research nie przepada i wlasciciel ma co czytac.”
    Co mówi kod: negatywny wynik audytu jest tylko drukowany (`agent-v2/artykul_z_puli.py:1351`–`agent-v2/artykul_z_puli.py:1359`), po czym publikacja jest wywoływana bezwarunkowo (`agent-v2/artykul_z_puli.py:1361`–`agent-v2/artykul_z_puli.py:1363`).
    Rozbieżność: weryfikacja nie blokuje wyjścia na zewnątrz i artykuł jest publikowany także z zastrzeżeniami.

52. `agent-v2/kopia_subskrybentow.py:4`
    Cytat: „Przy tempie 6-12 subskrypcji miesiecznie sto osob to okolo jedenastu miesiecy pracy systemu, a regulamin pozwala zamknac konto natychmiast i w wylacznej ocenie Substacka.”
    Co mówi kod: `SUBSKRYPCJE_MIESIECZNIE` wynosi 12–20 (`agent-v2/config.py:1708`), co przy środku widełek daje około 6,25 miesiąca na 100 osób.
    Rozbieżność: docstring używa nieobowiązujących widełek i zawyża czas prawie dwukrotnie.

53. `agent-v2/wzajemnosc.py:1043`
    Cytat: „Trzy do pieciu wierszy dla codziennej kontroli.”
    Co mówi kod: bez zrzutów funkcja zwraca jeden wiersz (`agent-v2/wzajemnosc.py:1046`–`agent-v2/wzajemnosc.py:1048`), z danymi tworzy cztery wiersze bazowe (`agent-v2/wzajemnosc.py:1050`–`agent-v2/wzajemnosc.py:1078`) i może dodać dwa ostrzeżenia (`agent-v2/wzajemnosc.py:1080`–`agent-v2/wzajemnosc.py:1096`), osiągając sześć.
    Rozbieżność: rzeczywisty zakres liczby wierszy to 1 albo 4–6, nie 3–5.

54. `agent-v2/tests/test_artykul_przed_publikacja.py:18`
    Cytat: „Ze miedzy wejsciem w galaz `--wyslij` a wywolaniem `browser.wystaw_artykul` stoi `stages.zweryfikuj`, i ze przy niepowodzeniu sciezka WRACA zamiast publikowac. Zapis artykulu ma zostac — blokujemy wyjscie na zewnatrz, nie prace.”
    Co mówi kod: po negatywnym `safe_to_post` kod tylko wypisuje zastrzeżenia (`agent-v2/run.py:2638`–`agent-v2/run.py:2649`) i następnie publikuje (`agent-v2/run.py:2651`–`agent-v2/run.py:2652`); sam test sprawdza brak `return` (`agent-v2/tests/test_artykul_przed_publikacja.py:112`–`agent-v2/tests/test_artykul_przed_publikacja.py:115`).
    Rozbieżność: ścieżka nie wraca przy niepowodzeniu weryfikacji i nie blokuje publikacji.

55. `agent-v2/tests/test_obserwowanie_przez_menu.py:439`
    Cytat: „Prog jest niesymetryczny swiadomie — falszywe „nie udalo sie" kosztuje cala dzienna norme (przy 30-44/mies to ~1,2 obserwacji na dobe, czyli zwykle jedyna tego dnia), falszywe „udalo sie" kosztuje jeden slot.”
    Co mówi kod: miesięczne widełki wynoszą 10–16 (`agent-v2/config.py:1707`), a norma dzienna liczy ich środek przez 30 (`agent-v2/config.py:1733`), czyli około 0,43.
    Rozbieżność: komentarz testu podaje nieobowiązujące widełki i niemal trzykrotnie za dużą normę dzienną.

56. `agent-v2/tests/test_promocja.py:13`
    Cytat: „Funkcja jest wolana raz na przebieg, a przebiegow jest trzy dziennie — wiec drugi przebieg brał nastepny artykul z kolejki i tego samego dnia wychodzila DRUGA notka promujaca, tyle ze innego tekstu.”
    Co mówi kod: konfiguracja ustala pięć przebiegów dziennie (`agent-v2/config.py:1847`), zgodnie z pięcioma wpisami timera (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: funkcja jest uruchamiana w ramach pięciu, nie trzech planowych przebiegów dziennych.

57. `agent-v2/tests/test_promocja.py:122`
    Cytat: „Trzy przebiegi dziennie wolaja te funkcje trzy razy.”
    Co mówi kod: `PRZEBIEGOW_DZIENNIE` wynosi 5 (`agent-v2/config.py:1847`) i timer ma pięć uruchomień (`agent-v2/systemd/nia-agent.timer:48`–`agent-v2/systemd/nia-agent.timer:52`).
    Rozbieżność: bieżący harmonogram może wołać funkcję pięć razy dziennie, nie trzy.

58. `agent-v2/tests/test_restack_petla.py:14`
    Cytat: „Przy `ile=1` — czyli w typowym przypadku, bo budzet 2-4 restacki rozklada sie na 3-4 przebiegi — KAZDA taka przerwa byla w calosci pusta.”
    Co mówi kod: budżet restacków wynosi 1–2 (`agent-v2/config.py:1825`–`agent-v2/config.py:1829`), a przebiegów jest pięć (`agent-v2/config.py:1840`–`agent-v2/config.py:1847`).
    Rozbieżność: uzasadnienie typowego `ile=1` podaje nieaktualne zarówno widełki budżetu, jak i liczbę przebiegów.

59. `agent-v2/tests/test_restack_petla.py:162`
    Cytat: „To jest przypadek z produkcji: budzet 2-4 restacki na 3-4 przebiegi = 1.”
    Co mówi kod: produkcyjny budżet to 1–2 restacki (`agent-v2/config.py:1825`–`agent-v2/config.py:1829`) rozdzielane na pięć przebiegów (`agent-v2/config.py:1847`).
    Rozbieżność: opis przypadku produkcyjnego używa dwóch wartości innych niż bieżąca konfiguracja.

60. `agent-v2/tests/test_forma.py:225`
    Cytat: „Nadal sortujemy, nie odrzucamy: przy 53% i trzech kandydatach na notke sortowanie zwykle ma z czego wybierac, a odrzucanie kosztowaloby polowe.”
    Co mówi kod: `NOTE_CANDIDATES` wynosi 1 (`agent-v2/config.py:864`), a pętla tworzenia kandydatów używa tej wartości (`agent-v2/stages.py:2188`).
    Rozbieżność: sortowanie nie ma trzech kandydatów, z których mogłoby wybierać.

61. `agent-v2/tests/test_obietnice_bez_pokrycia.py:3`
    Cytat: „Trzy usterki jednej rodziny, wszystkie potwierdzone na produkcji:”
    Co mówi kod: plik zawiera pięć osobnych sekcji usterek, zaczynających się w `agent-v2/tests/test_obietnice_bez_pokrycia.py:42`, `agent-v2/tests/test_obietnice_bez_pokrycia.py:129`, `agent-v2/tests/test_obietnice_bez_pokrycia.py:157`, `agent-v2/tests/test_obietnice_bez_pokrycia.py:175` i `agent-v2/tests/test_obietnice_bez_pokrycia.py:202`.
    Rozbieżność: docstring zapowiada trzy usterki, lecz test opisuje i sprawdza pięć.

62. `agent-v2/stages.py:1107`
    Cytat: „Gdy kanaly nie odpowiadaja, oddajemy pusty napis i prompt radzi sobie sama siatka dziedzin.”
    Co mówi kod: po wyjątku funkcja zwraca niepusty napis `"(could not be fetched today)"` (`agent-v2/stages.py:1111`–`agent-v2/stages.py:1116`), a po pustej odpowiedzi inny niepusty napis `"(nothing fetched today)"` (`agent-v2/stages.py:1117`–`agent-v2/stages.py:1118`).
    Rozbieżność: w obu opisanych przypadkach funkcja zwraca tekst zastępczy, a nie pusty napis.

63. `agent-v2/db.py:102`
    Cytat: „To nie jest system migracji i ma nim nie byc — projekt stoi na zasadzie „zmiana schematu to nowa kolumna z wartoscia domyslna, nigdy przepisywanie danych".”
    Co mówi kod: `_dopisz_brakujace_kolumny` sprawdza schemat istniejących tabel i wykonuje `ALTER TABLE ... ADD COLUMN` dla brakujących kolumn (`agent-v2/db.py:114`–`agent-v2/db.py:124`), a `connect` uruchamia ją automatycznie (`agent-v2/db.py:92`–`agent-v2/db.py:94`).
    Rozbieżność: funkcja realizuje automatyczną migrację schematu przez dodawanie kolumn, choć komentarz zaprzecza, że jest to system migracji.

64. `agent-v2/PROMPT_DLA_AGENTA.md:20`–`agent-v2/PROMPT_DLA_AGENTA.md:22`; `agent-v2/START_TUTAJ.md:93`–`agent-v2/START_TUTAJ.md:99`; `agent-v2/dokumentacja-zrodla/wstep.md:44`–`agent-v2/dokumentacja-zrodla/wstep.md:48`; `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:44`–`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:48`
    Cytat: „Agent prowadzący Substacka „Nothing Is Accidental" — teksty wyjaśniające ukryte systemy, bodźce i decyzje za zwyczajnymi rzeczami” oraz „Agent prowadzi [...] Substacka [...], który wyjaśnia ukryte systemy, bodźce i decyzje stojące za zwykłymi rzeczami.”
    Co mówi kod: 25 sierpnia 2026 lista tematów została w całości przestawiona z codziennej infrastruktury na sztuczną inteligencję (`agent-v2/config.py:879`–`agent-v2/config.py:881`), system wyszukiwania faktów zamawia fakty o AI (`agent-v2/stages.py:1095`–`agent-v2/stages.py:1100`), a prompt pisarza definiuje publikację jako pismo o AI (`agent-v2/prompts/pisarz.md:1`–`agent-v2/prompts/pisarz.md:4`).
    Rozbieżność: cztery dokumenty nadal przedstawiają dawną tematykę „ukrytych systemów za zwykłymi rzeczami” jako bieżący mandat agenta.

65. `agent-v2/alarm.py:683`–`agent-v2/alarm.py:689`; kopie w `agent-v2/dokumentacja-zrodla/rozdzial_dzien.md:1790`–`agent-v2/dokumentacja-zrodla/rozdzial_dzien.md:1792` i `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:3872`
    Cytat: „Publikacja o tym, dlaczego zwykle rzeczy sa takie, jakie sa, przegralaby sama ze soba w kilka miesiecy.”
    Co mówi kod: bieżący system wyszukiwania materiału nazywa publikację marką o sztucznej inteligencji (`agent-v2/stages.py:1095`–`agent-v2/stages.py:1100`), tak samo robi prompt pisarza (`agent-v2/prompts/pisarz.md:1`–`agent-v2/prompts/pisarz.md:4`).
    Rozbieżność: uzasadnienie sposobu liczenia reakcji nadal opisuje profil pisma sprzed przestawienia na AI, a to samo zdanie zostało powielone w dwóch dokumentach.

66. `agent-v2/stages.py:3193`–`agent-v2/stages.py:3197`; kopie w `agent-v2/dokumentacja-zrodla/rozdzial_bramki.md:865`–`agent-v2/dokumentacja-zrodla/rozdzial_bramki.md:867` i `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:4791`
    Cytat: „`as an aid` jest w naszej tematyce wyjatkowo prawdopodobne, bo piszemy o etykietach i urzadzeniach, ktore czemus POMAGAJA.”
    Co mówi kod: bieżące dziedziny tematów obejmują trening, pamięć, tokenizację, dostrajanie, wyszukiwanie, agentów i systemy multimodalne (`agent-v2/config.py:896`–`agent-v2/config.py:905`), a system wyszukiwania ogranicza fakty do AI (`agent-v2/stages.py:1095`–`agent-v2/stages.py:1100`).
    Rozbieżność: komentarz i jego dwie kopie nadal uzasadniają regułę dawną tematyką etykiet i urządzeń, choć bieżącą tematyką jest AI.

67. `agent-v2/prompts/synteza.md:86`–`agent-v2/prompts/synteza.md:88`; kopie w `agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:3530`–`agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:3532` i `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:11894`–`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:11896`
    Cytat: „`main_mechanism` — the hidden system the article exists to explain”.
    Co mówi kod: `synthesis` ładuje ten prompt i wywołuje model (`agent-v2/stages.py:3518`–`agent-v2/stages.py:3530`), po czym pełne pole `main_mechanism` trafia w karcie do promptu pisarza (`agent-v2/stages.py:465`–`agent-v2/stages.py:471`; `agent-v2/prompts/pisarz.md:478`–`agent-v2/prompts/pisarz.md:480`).
    Rozbieżność: określenie „hidden system” nie zostało usunięte i nadal aktywnie ustawia mechanizm każdego artykułu, mimo że sam temat artykułu jest już ograniczony do AI (`agent-v2/prompts/pisarz.md:1`–`agent-v2/prompts/pisarz.md:4`).

68. `agent-v2/prompts/ciekawostki.md:380`–`agent-v2/prompts/ciekawostki.md:384`; kopie w `agent-v2/dokumentacja-zrodla/prompty.md:36`–`agent-v2/dokumentacja-zrodla/prompty.md:43`, `agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:759`–`agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:763` i `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:9127`
    Cytat: „`domain`: `<the everyday area it belongs to>`”.
    Co mówi kod: funkcja `znajdz_ciekawostki` ładuje ten prompt (`agent-v2/stages.py:1299`–`agent-v2/stages.py:1304`) i przekazuje go modelowi z systemową instrukcją wyszukiwania faktów o AI (`agent-v2/stages.py:1095`–`agent-v2/stages.py:1100`; `agent-v2/stages.py:1320`–`agent-v2/stages.py:1324`).
    Rozbieżność: dawne pole klasyfikujące fakt według „everyday area” nadal znajduje się w aktywnym kontrakcie odpowiedzi; nie da się ustalić z samego kodu, czy przesuwa ono wybór tematów, ponieważ w tym samym wywołaniu model dostaje jawną instrukcję o AI.

69. `agent-v2/prompts/fedreg.md:84`–`agent-v2/prompts/fedreg.md:88`; kopie w `agent-v2/dokumentacja-zrodla/prompty.md:56`–`agent-v2/dokumentacja-zrodla/prompty.md:63`, `agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:1019`–`agent-v2/dokumentacja-zrodla/zalacznik_prompty.md:1023` i `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:9387`
    Cytat: „`domain`: `<the everyday area this belongs to>`”.
    Co mówi kod: `kandydaci_z_fedreg` łączy ten prompt z komunikatem systemowym, który definiuje markę jako wyjaśniającą budowę, wdrażanie i regulowanie AI (`agent-v2/stages.py:6179`–`agent-v2/stages.py:6197`); widoczne wywołanie funkcji znajduje się w płatnym teście (`agent-v2/tests/platne/test_fedreg_pelna_sciezka.py:40`–`agent-v2/tests/platne/test_fedreg_pelna_sciezka.py:48`).
    Rozbieżność: określenie „everyday area” nadal jest w prompcie i trzech kopiach dokumentacyjnych; nie da się ustalić jego wpływu na produkcję, ponieważ w repozytorium nie ma udokumentowanego produkcyjnego wywołania tej ścieżki poza testem.

70. `agent-v2/config.py:1350`–`agent-v2/config.py:1353`; `agent-v2/config.py:1525`; `agent-v2/config.py:1571`; `agent-v2/stages.py:1206`; `agent-v2/stages.py:1300`
    Cytat: „`CIEKAWOSTKA`”, „`znajdz_ciekawostki`” i „`ciekawostki.md`”.
    Co mówi kod: `CIEKAWOSTKA` nadal jest aktywnym typem notki w obu mieszankach dnia (`agent-v2/config.py:1525`; `agent-v2/config.py:1571`), ale jej system i sam prompt definiują publikację jako poświęconą AI (`agent-v2/stages.py:1095`–`agent-v2/stages.py:1100`; `agent-v2/prompts/ciekawostki.md:6`–`agent-v2/prompts/ciekawostki.md:10`).
    Rozbieżność: nazewnictwo „ciekawostka” nie zostało usunięte, lecz oznacza dziś format notki o AI, a nie powrót do dawnej dziedziny tematów.

71. `agent-v2/tests/test_prompty_o_ai.py:213`–`agent-v2/tests/test_prompty_o_ai.py:228`; `agent-v2/tests/test_prompty_o_ai.py:309`–`agent-v2/tests/test_prompty_o_ai.py:315`; `agent-v2/audyt_tematow.py:273`–`agent-v2/audyt_tematow.py:279`
    Cytat: „ZADEN PROMPT NIE UCZY NA PRZEDMIOTACH”, „fedreg.md nie ma juz ani jednej linii z epoki przedmiotow” i „zaden prompt nie uczy na epoce przedmiotow”.
    Co mówi kod: wykrywacz sprawdza tylko zamkniętą listę słów (`agent-v2/tests/test_prompty_o_ai.py:100`–`agent-v2/tests/test_prompty_o_ai.py:120`) dopasowywaną przez `trafienia_w_linii` (`agent-v2/tests/test_prompty_o_ai.py:180`–`agent-v2/tests/test_prompty_o_ai.py:185`), na której nie ma fraz `hidden system` ani `everyday area`; frazy te pozostają odpowiednio w `agent-v2/prompts/synteza.md:86`, `agent-v2/prompts/ciekawostki.md:384` i `agent-v2/prompts/fedreg.md:88`.
    Rozbieżność: oba zielone werdykty świadczą tylko o braku słów z niepełnej listy, a nie o usunięciu wszystkich instrukcji i sformułowań dawnej tematyki.
