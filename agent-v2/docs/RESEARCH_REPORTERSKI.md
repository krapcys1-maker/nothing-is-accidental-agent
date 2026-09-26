# Research reporterski artykułów

Włączony w `artykul_z_puli.py` i w artykułowej ścieżce `run.py` po klasyfikacji
źródeł, przed syntezą. Dotyczy projektu `nothing-is-accidental-agent`.

`research.py` czyta już opłacone fragmenty. DeepSeek Flash przedstawia do trzech
konkurencyjnych wyjaśnień, interesy konkretnych stron, kontrargument i do czterech
pytań. Program sprawdza dosłowne cytaty i identyfikatory źródeł. Brak dowodu nie
może zamienić pytania w rozstrzygnięte. Korzyść firmy nie dowodzi jej intencji.

Spośród otwartych pytań program wybiera wskazane przez model, respektując wysoki
priorytet, brak odpowiedzi i wcześniejsze zapytania. Szuka dokumentów, pobiera je,
wyciąga cytaty jednym wywołaniem na partię i ponownie ocenia materiał. Dopuszcza
różne dokumenty z tej samej domeny. URL musi wystąpić w rzeczywistych wynikach
narzędzia wyszukiwania; same wymyślone przez model adresy nie wystarczą.

## Koszt i zatrzymanie

- Do dwóch dogrywek po wstępnym researchu; do trzech wyszukiwań i trzech nowych
  dokumentów na dogrywkę. Łącznie najwyżej siedem dodatkowych wywołań modelu.
- Trzy nowe etapy (`investigation`, `investigation_search`,
  `investigation_extract`) używają DeepSeek Flash. Po próbie live wyłączono w nich
  ukryte rozumowanie: odpowiedź zawiera jawne hipotezy, dowody i ograniczenia.
  Sufity odpowiedzi: odpowiednio 6000, 6000 i 8000 tokenów.
- `RESEARCH_STOP_USD=0.15` zatrzymuje **następne** wywołanie, gdy zapisany koszt
  dogrywki osiągnie próg. Nie jest gwarancją rachunku: ostatnie wywołanie może go
  przekroczyć, stawki są szacunkowe, a koszt niektórych błędów API jest nieznany.
  Istniejące globalne limity i wyłącznik nadal obowiązują.
- Brak nowych źródeł, brak nowych poprawnych cytatów, komplet odpowiedzi albo
  brak kolejnego sensownego pytania zatrzymuje szukanie wcześniej.
- Ocena identycznego pytania i tych samych fragmentów ma cache na 24 godziny.
  Klucz obejmuje prompt, model, datę, wcześniejsze zapytania i materiał. Zmiana
  dowodów wymaga nowej oceny. To nie jest cache całego Internetu ani całej ścieżki.

Wynik trafia do `data/research/<skrót-pytania>/run-<id>.json`: pytania, hipotezy,
cytaty, adresy, przebieg rund, powód zatrzymania i szacowany koszt. Karta syntezy
otrzymuje `investigation`, a nierozstrzygnięte ważne pytania `not_established`.
Fable nadal pisze artykuł. Nie wymusza się analogii do niezwiązanych dziedzin.

Przy błędzie opcjonalnej dogrywki program zachowuje wcześniejsze dowody i zapisuje
powód błędu; nie ogłasza wówczas udanego śledztwa. Globalny limit kosztu i błędy
preflight przerywają przebieg. Naprawa JSON jest lokalna i ograniczona do dwóch
pomyłek w zamykających nawiasach poza napisami; nie uzupełnia uciętych odpowiedzi
ani nie zmienia tekstu dowodów.

## Sprawdzenie

Z katalogu głównego repozytorium:

```powershell
.venv\Scripts\python.exe agent-v2/tests/test_research_reporterski.py
```

Testy bez sieci sprawdzają dobór kolejnego pytania, limity, cache, koszty,
propagację blokad, cytaty, rzeczywiste wyniki wyszukiwania i zachowanie materiału
po awarii. Próba live powinna korzystać z osobnego katalogu danych i kończyć się
szkicem oraz recenzją. Sam moduł researchu nie publikuje ani nie wysyła wiadomości.

To zbieranie i sprawdzanie publicznych dokumentów. Nie udaje rozmów z informatorami
ani dowodów na ukryte motywy; brak rozstrzygnięcia pozostaje częścią wyniku.
