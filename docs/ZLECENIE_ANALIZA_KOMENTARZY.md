# Zlecenie: dlaczego komentarze nie dzialaja i co z tym zrobic

Prompt do przekazania modelowi, ktory ma dostep do repozytorium i do bazy
produkcyjnej (odczyt). Napisany 5 wrzesnia 2026.

**Nie skracaj tego promptu przed wyslaniem.** Liczby ponizej sa zmierzone i
sa po to, zeby model nie zaczynal od zera ani nie zgadywal.

---

## KONTEKST

Konto na Substacku prowadzone w calosci przez agenta, bez czlowieka w petli.
Pisze notki (krotkie wpisy), komentarze pod cudzymi wpisami, odpowiedzi na
komentarze i raz w tygodniu artykul. Kod: `agent-v2/`, glownie `stages.py`
(pisarze i bramki), `run.py` (dzien), `config.py`, prompty w
`agent-v2/prompts/*.md`. Historia wywolan modelu w tabeli `calls`
(kolumny `purpose`, `akcja`, `tokens_in`, `tokens_out`, `web_searches`,
`cost_usd`, `run_id`). Wszystko, co konto wystawilo i co do niego wrocilo,
w `agent-v2/data/dziennik.jsonl` (jeden JSON na wiersz, pole `rodzaj`).

## POMIAR, OD KTOREGO ZACZYNAMY

Od przestawienia konta na AI (22 sierpnia 2026) do 5 wrzesnia:

| co | wystawione | reakcje przychodzace | na sztuke | koszt 14 dni | koszt reakcji |
|---|---|---|---|---|---|
| notki | 56 | 159 | 2,84 | 6,58 USD | 0,041 USD |
| komentarze + odpowiedzi | 145 | 19 | **0,13** | 4,94 USD | **0,26 USD** |
| artykuly | 3 | 4 | 1,33 | 12,25 USD | jedyne zrodlo subskrypcji |

Reakcje przychodzace z `dziennik.jsonl`, `rodzaj = "skutek"`:
`note_like` 112, `note_reply` 47, `comment_like` 12, `comment_reply` 7,
`post_like` 3, `post_reply` 1, `follow` 7, `free_subscription` 4.

Dwie dodatkowe obserwacje, ktore moga, ale nie musza byc zwiazane:

* reaguje **30 roznych osob**, a jedna (`chaosengine2026`) odpowiada za 35 z
  214 reakcji, czyli 16% calosci;
* pole `forma` jest **puste w 32 z 56 notek**, wiec dzis nie da sie zmierzyc,
  czy formy notek w ogole sie od siebie roznia.

**Komentarz jest 22 razy mniej skuteczny od notki i 6 razy drozszy za
reakcje, a wystawiamy go prawie trzy razy czesciej.** To jest przedmiot tego
zlecenia.

## CZEGO NIE ROBIMY

Nie szukamy sposobu na wiecej komentarzy. Nie proponujemy kupowania zasiegu,
wzajemnosci „ja tobie ty mnie", ani ukrywania, ze konto jest prowadzone przez
maszyne. Nie proponujemy zdjecia bramki sprawdzajacej fakty: zmierzone, ze
w tygodniu 29.08-04.09 zlapala **14 bledow faktycznych w 87 tekstach**
(8 poprawionych, 6 zablokowanych), w tym zmyslona date i naciagniete
przypisanie tezy pracy naukowej.

## ETAP 1 — ANALIZA (najpierw; bez propozycji)

Odpowiedz na ponizsze pytania **liczbami z bazy i z dziennika**, kazda
odpowiedz z zapytaniem, ktorym ja uzyskales. Tam, gdzie danych nie ma,
napisz „nie da sie ustalic" i podaj, co trzeba by zaczac zapisywac.

1. **Gdzie umieraja komentarze.** Ile celow wybieramy, ile z nich konczy sie
   cisza (i z jakiego powodu), ile komentarzem wystawionym, a ile odpada na
   bramce. Interesuje mnie lejek, nie suma.
2. **Czy komentarz trafia tam, gdzie ktos jest.** Ile reakcji ma cudzy wpis,
   pod ktorym komentujemy, w chwili komentowania. Czy komentarze z reakcjami
   roznia sie pod tym wzgledem od tych bez.
3. **Kiedy komentujemy.** Ile czasu mija od publikacji cudzego wpisu do
   naszego komentarza. Czy komentarze z reakcjami sa wczesniejsze.
4. **Ktory komentarz dostal reakcje.** Wyciagnij te 19 reakcji i pokaz teksty,
   ktore je dostaly, obok losowej probki tych bez. Szukamy roznicy w TEKSCIE,
   nie w metryce: dlugosc, otwarcie, czy zawiera liczbe, czy zadaje pytanie,
   czy odnosi sie do konkretnego zdania cudzego wpisu.
5. **Kto reaguje.** Czy 30 osob reagujacych to ci, pod ktorymi komentujemy,
   czy zupelnie inni. Jesli inni — to znaczy, ze komentarze nie buduja tego,
   po co istnieja.
6. **Ile kosztuje jeden komentarz naprawde.** Rozbij na etapy (`cele`,
   `comment`, `factcheck`, `naprawa_komentarza`, `reply`) i podaj, ktory z
   nich jest najdrozszy na jeden WYSTAWIONY komentarz, nie na wywolanie.
7. **Czy prompt komentarza prosi o rzeczy, ktorych nikt nie sprawdza.**
   Przejdz `agent-v2/prompts/komentarz.md` regula po regule i przypisz kazdej
   jedna z trzech etykiet: sprawdza to KOD na wyjsciu modelu / sprawdza tylko
   TEST obecnosc frazy w pliku / to jest PROSBA i nic jej nie pilnuje.

## ETAP 2 — RAPORT I PROPOZYCJE (dopiero po etapie 1)

Dla kazdego znaleziska podaj **piec rzeczy i nic wiecej**:

1. **Co** — jedno zdanie, bez ozdobnikow.
2. **Gdzie** — plik i numer linii albo nazwa funkcji.
3. **Ile to kosztuje** — z jednostka (USD na dobe, reakcje na sztuke,
   procent rachunku). Jesli szacujesz, podaj wzor obok liczby.
4. **Darmowe sprawdzenie** — polecenie albo zapytanie, ktore mozna uruchomic
   od razu, razem ze **zdrowa odpowiedzia**: co znaczy wynik dobry.
5. **Najmniejsza poprawka i jej KONTRDOWOD** — co zmierzyc przed i po, i
   **jaki wynik ma znaczyc, ze poprawke trzeba cofnac**. Propozycja bez
   kontrdowodu nie jest przyjmowana.

Uporzadkuj od najwiekszej spodziewanej poprawy, nie od najlatwiejszej.

Rozwaz jawnie takze **rozwiazania odejmujace**: mniej komentarzy o wiekszej
wadze, komentowanie tylko tam, gdzie ktos naprawde jest, albo przeniesienie
czesci budzetu z komentarzy na notki — skoro notka daje 2,84 reakcji, a
komentarz 0,13. Odpowiedz „przestac komentowac" jest dopuszczalna, jesli
liczby ja niosa; napisz wtedy wprost, co tracimy.

## ZASADY, KTORE OBOWIAZUJA W TYM PROJEKCIE

* **Prosba w prompcie nie jest bramka.** To konto stracilo dwa artykuly na
  tym, ze regula stala w prompcie, a nikt jej nie liczyl. Jesli proponujesz
  regule, powiedz, co ma ja EGZEKWOWAC w kodzie.
* **Kod 200 nie jest sprawdzeniem.** Trzy zrodla udawaly przez tydzien, ze
  dzialaja, bo kontrola patrzyla na kod odpowiedzi zamiast na tresc.
* **Zielony zestaw testow to nie dowod.** Dowodem jest slad z produkcji po
  wdrozeniu.
* **Darmowa opcja w prompcie degeneruje do stalej.** Jesli model moze czegos
  nie wypelnic, nie wypelni; wymuszony wybor dziala, prosba nie.
* Nie zmyslaj liczb. Kazda liczba w raporcie ma pochodzic z zapytania, ktore
  podajesz obok, albo byc oznaczona jako szacunek ze wzorem.

## FORMAT ODPOWIEDZI

Najpierw etap 1 w calosci — same ustalenia, zero propozycji. Potem etap 2.
Na koncu jedna sekcja: **czego nie dalo sie ustalic i co trzeba zaczac
zapisywac**, zeby nastepnym razem dalo sie.
