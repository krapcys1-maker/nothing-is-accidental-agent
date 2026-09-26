# Odzyskanie pustej odpowiedzi wyszukiwarki

Pełna próba wdrożonego sterownika artykułu 25.09.2026 wykonała osiem wyszukiwań,
lecz odpowiedź `discovery` nie zawierała końcowego tekstu. Koszt był zapisany,
ale próba parsowania pustego tekstu zatrzymała artykuł przed etapem `research`.

Gdy tekst jest pusty, a narzędzie zwróciło rzeczywiste URL-e, `stages.discovery`
wywołuje jeden raz `discovery_recovery`. DeepSeek Flash wybiera dokumenty z tej
listy, bez narzędzia wyszukiwania. Kod odrzuca każdy adres nieobecny na liście,
także wymyśloną ścieżkę w prawdziwej domenie. Pobieranie oraz sprawdzanie cytatów
odbywa się potem normalnie. Brak URL-i lub nieudany odzysk kończy etap błędem;
nie ma pętli ponowień ani dopisywania źródeł z pamięci.

Limit: 80 adresów wejściowych, istniejący limit wyników discovery, 6000 tokenów
wyjścia, wyłączone rozumowanie. Globalne limity wydatków obowiązują normalnie.
Niepusta, niepoprawnie sformatowana odpowiedź zachowuje dotychczasowy mechanizm
odzysku. Poprawna odpowiedź nie kupuje dodatkowego wywołania.

Próba samego odzysku użyła 49 rzeczywistych adresów z API, odtworzyła obserwowany
brak tekstu i wykonała prawdziwe wywołanie naprawcze. Oddało 10 adresów, 0 nowych
wyszukiwań, koszt szacunkowy $0.000796. To kontrolowane odtworzenie awarii,
nie twierdzenie, że drugie naturalne wywołanie także zwróciło pusty tekst.

Testy bez sieci: `tests/test_discovery_empty_recovery.py` — 7 przypadków,
w tym propagacja globalnego limitu, zachowanie kanału rozliczeń i brak powtórek
przy poprawnej odpowiedzi.
