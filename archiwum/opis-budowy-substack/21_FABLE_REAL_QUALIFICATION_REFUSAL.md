# Pierwsza realna kwalifikacja Fable: odmowa też jest wynikiem

10 sierpnia 2026 system dostał zgodę na dokładnie jeden realny request kwalifikacyjny. Nie na „próby aż zadziała”, nie na aktywację modelu i nie na dalszy etap C5. Jeden approval, jeden request, retry równe zero i fallback zabroniony.

Przed callem sprawdziliśmy trwałą zgodę, osobną akceptację 30-dniowej retencji, envelope 13952/2048, cap 0.241920 USD, wersję promptu, cennik, budżet i brak wcześniejszego runu. Dopiero potem system atomowo skonsumował approval i zapisał `IN_FLIGHT`, zanim przekroczył granicę providera.

Provider odpowiedział jako `claude-fable-5`, w trybie globalnym i standardowym. Zużył 151 tokenów wejścia i 3 wyjścia. Odpowiedzią była jednak odmowa. Deterministyczny walidator nie próbował jej reinterpretować jako częściowego sukcesu. Durable outcome został zapisany jako `FAIL / PROVIDER_REFUSAL`, z kosztem 0.001660 USD.

Najważniejsze wydarzyło się później: nic. Nie było retry. Nie było fallbacku. Nie powstała capability, activation ani policy update. Registry pozostał kandydatem z wynikiem FAIL. System zachował się zgodnie z kontraktem właśnie w chwili, gdy najłatwiej byłoby ten kontrakt rozmiękczyć.

To nie jest gotowość live ani porażka całego projektu. To pierwszy produkcyjny dowód, że odmowa providera może zostać rozliczona uczciwie i zatrzymać proces bez udawania, że approval obejmował drugą szansę.
