# Polityka testów i budżetu Agent V3

**Data:** 2026-08-21  
**Tryb domyślny:** offline  
**Zakaz nadrzędny:** żadnej publikacji, draftu na żywym koncie, reakcji, komentarza, follow, subskrypcji ani wdrożenia produkcyjnego

## 1. Cel

Testy mają dowodzić własności autonomicznego systemu redakcyjnego przy najmniejszym możliwym ryzyku i koszcie. Dostęp do internetu i modeli jest narzędziem ostatniego etapu, nie domyślną ścieżką.

## 2. Hierarchia testów

1. **Static** — AST, import graph bez importu, wyszukiwanie kontraktów, hashe, lint dokumentacji.
2. **Unit fixture** — czyste funkcje i wersjonowane fixture'y.
3. **Property/negative** — generowane przypadki, kontrdowody, mutacje wejść.
4. **Offline integration** — tymczasowa baza, fałszywy transport, zamrożony zegar, pełny pipeline.
5. **Browser fixture** — lokalna fałszywa strona; zero połączeń do Substack.
6. **Model replay** — zapisane odpowiedzi modeli; koszt 0 USD.
7. **Paid model eval** — zamrożone wejścia, jawna hipoteza i księgowanie.
8. **Read-only network** — tylko jeśli semantyki odpowiedzi nie da się odtworzyć z fixture'u.

Nie ma obecnie dozwolonego testu mutującego Substack.

## 3. Budżety twarde

| Dostawca | Limit całkowity | Dozwolony cel | Zakazane użycie |
|---|---:|---|---|
| Anthropic | 5.00 USD | ewaluacja rewizji, weryfikacji i odporności promptów | publikacja, żywy agent konta, swobodne eksperymenty bez korpusu |
| DeepSeek | 5.00 USD | ewaluacja pisarza, schematów i regresji na fixture'ach | publikacja, żywy agent konta, brak limitu tokenów |
| GPT/OpenAI | 2.00 USD | wyłącznie testy generowania obrazów | tekst, recenzja, research, sterowanie agentem |

Limity są łączne dla projektu, nie na sesję. Przekroczenie o dowolną kwotę jest błędem testu.

## 4. Rezerwa budżetowa

Planowana maksymalna alokacja:

### Anthropic — 5.00 USD

- 2.00 USD — porównanie rewizji na zamrożonym korpusie;
- 1.25 USD — weryfikacja faktograficzna i schema adherence;
- 1.25 USD — zestaw prompt injection/adversarial;
- 0.50 USD — rezerwa na ponowienie techniczne.

### DeepSeek — 5.00 USD

- 2.00 USD — pisarz przed/po na tych samych evidence cards;
- 1.25 USD — rewizja i zachowanie tezy;
- 1.25 USD — poprawność wersjonowanych JSON schema;
- 0.50 USD — rezerwa na ponowienie techniczne.

### GPT/OpenAI — 2.00 USD

- 1.50 USD — mały, zamrożony zestaw promptów obrazowych;
- 0.50 USD — rezerwa na błąd techniczny.

Alokacja nie jest zobowiązaniem do wydania. Jeżeli offline rozstrzyga hipotezę, koszt pozostaje 0 USD.

## 5. Warunek uruchomienia testu płatnego

Test płatny może zostać wykonany tylko, gdy istnieją:

- karta naprawy;
- pytanie, którego replay/fixture nie rozstrzyga;
- zamrożony input i oczekiwany format;
- limit wywołań, tokenów i kosztu;
- oszacowanie najgorszego kosztu przed startem;
- wolny budżet w `REJESTR_WYDATKOW_ONLINE.md`;
- zapis odpowiedzi pozbawiony sekretów;
- reguła zatrzymania po błędzie schematu lub pierwszym przekroczeniu rezerwy.

## 6. Zasady danych i sekretów

- Klucze są odczytywane wyłącznie z procesu testowego i nigdy nie trafiają do logu.
- Test płatny nie może ładować produkcyjnej sesji przeglądarki.
- Do modelu nie trafiają adresy e-mail, tokeny sesji, dane subskrybentów ani niezanonimizowane identyfikatory kont.
- Każdy fixture ma hash i wersję.
- Cache odpowiedzi modelu ma jawny status testowy i nie jest wejściem do produkcji.

## 7. Metryki ewaluacji tekstu

Nie stosuje się jednego score. Zestaw testowy mierzy osobno:

- pokrycie twierdzeń źródłami;
- nowe fakty dodane bez dowodu;
- zachowanie centralnej tezy;
- usunięcie wskazanych wad;
- poprawność struktury JSON;
- zgodność długości;
- naruszenia stylu;
- wyciek instrukcji;
- stabilność wyniku między powtórzeniami;
- koszt i czas.

Warunek krytyczny jest koniunkcją. Wynik stylistyczny nie kompensuje faktu bez źródła.

## 8. Testy obrazów

Budżet GPT jest wyłącznie obrazowy. Test obrazu używa niewielkiej liczby zamrożonych promptów i mierzy:

- zgodność z tematem i obiektem;
- brak tekstu, logo i przypadkowych symboli, jeśli prompt ich zabrania;
- zgodność proporcji i przeznaczenia;
- powtarzalność zasad stylu;
- koszt na zaakceptowalną próbę.

Wygenerowany obraz pozostaje artefaktem testowym. Nie jest przesyłany na Substack.

## 9. Testy sieciowe

Dozwolone:

- publiczne README i kod źródłowy;
- publiczne strony źródłowe bez logowania;
- nieautoryzowany, tylko-odczytowy test parsera w odizolowanym kliencie;
- wywołania modeli objęte księgą.

Niedozwolone:

- metody POST/PUT/PATCH/DELETE do Substack;
- otwieranie zalogowanego edytora;
- odtwarzanie kliknięć reakcji;
- uruchamianie `--wyslij`, systemd, `wdroz.sh` lub `uruchom-dzien.cmd`;
- test, w którym brak flagi publikacji nadal tworzy draft.

## 10. Hermetyczność

Każdy test offline ustawia:

- tymczasowy katalog danych;
- tymczasową bazę;
- zamrożony czas i losowość;
- fałszywy DNS/HTTP/browser/LLM transport;
- jawnie pusty rejestr możliwości zewnętrznych;
- blokadę gniazd sieciowych;
- kontrolę drzewka plików przed/po.

Test kończy się błędem, jeżeli utworzy plik poza katalogiem tymczasowym lub spróbuje odczytać sekret/sesję.

## 11. Raportowanie

Po każdym teście zapisywane są:

- identyfikator karty naprawy;
- commit i hash fixture'u;
- komenda lub funkcja testowa;
- dozwolone możliwości;
- liczba wywołań i tokenów;
- rzeczywisty koszt;
- wynik każdej metryki;
- nowe ustalenia;
- nieoczekiwane pliki lub próby sieci.

## 12. Aktualny stan

Na dzień utworzenia dokumentu nie wykonano płatnego testu w ramach tej fazy. Kwerenda GitHub i analiza lokalna nie zużyły budżetu modeli.
