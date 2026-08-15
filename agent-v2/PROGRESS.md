# agent-v2 — księga prac

Jedna strona, aktualizowana po każdym skończonym etapie. Czytaj od góry.

**Zasada nadrzędna: każdy etap dostaje test live natychmiast po napisaniu.**

---

## Stan: ŁAŃCUCH DZIAŁA OD KOŃCA DO KOŃCA

Pierwszy artykuł powstał 2026-08-15: `data/articles/0012-the-additive-with-no-number.md`

| etap | stan | test live | koszt |
|---|---|---|---|
| 0. środowisko, budżet, log kosztów | **działa** | tak | 0 |
| 1. skaut tematów (Claude) | **działa** | tak | $0,0503 |
| 2. ocena wykonalności (DeepSeek) | **działa** | tak | $0,0005 |
| 3. dyskoveria źródeł (Claude + web search) | **działa** | tak | $0,6007 |
| 4. pobranie (HTTP) | **działa** | tak | 0 |
| 5. klasyfikacja + wyciąg (DeepSeek) | **działa** | tak | $0,0186 |
| 6. synteza — karta dowodowa (Claude) | **działa** | tak | $0,1756 |
| 7. pisanie (Claude + styl) | **działa** | tak | $0,1779 |
| 8. recenzja — rozliczanie zdań (Claude) | **działa** | tak | $0,2476 |
| 9. zapis (baza + .md) | **działa** | tak | 0 |

**Czysty przebieg: $1,27.** Cała budowa z testami i jednym przepisaniem: $1,4872.

## Budżet złożoności

| | limit | jest |
|---|---|---|
| pliki `.py` w `agent-v2/` | 10 | **7** |
| tabele w bazie | 4 | **4** |
| warstwy między `run.py` a modelem | 1 | **1** (`llm.py`) |

`config.py` · `db.py` · `llm.py` · `stages.py` · `gates.py` · `style.py` · `run.py`.
Prompty to pliki `.md`, nie kod. Zero migracji, zero triggerów, zero zgód.

## Decyzje właściciela z 2026-08-15

1. **Nic nie blokuje artykułu.** Skoro temat przeszedł odsiew i research jest
   opłacony, nie ma stanu „zablokowany i koniec". Cztery bramki
   (fakt bez pokrycia, liczba spoza korpusu, zmyślone przeżycie, nieistniejące
   badanie) zgłaszają uwagi; artykuł zawsze trafia do szuflady.
2. **Pisarz ma swobodę interpretacji.** Fakt wymaga pokrycia; analogia,
   interpretacja i argument nie są faktami — mają być tylko widoczne jako myśl
   autora. To stąd bierze się ciekawość tekstu.
3. **Skaut nie nazywa instytucji w pytaniu.** To był powód dwunastu tematów
   pod rząd o `gov.uk`. Dostępność źródeł sprawdza dopiero DeepSeek, po
   zróżnicowaniu.
4. **Zero przepisywania.** Jedno podejście.
5. **Korpus stylu wchodzi do repo** (`prompts/styl/`), przypięty SHA-256.

## Co zadziałało lepiej, niż zakładano

- **Skaut po naprawie**: 6 tematów, 6 dziedzin, zero Wielkiej Brytanii.
- **Opus 5 nie zmyślił ani jednej liczby.** Zmierzone, nie założone. Obawa
  o halucynacje liczb okazała się przeniesieniem doświadczeń ze słabszego modelu.
- **DeepSeek do przemiału korpusu**: 321 tys. znaków za $0,0186. W Opusie samo
  wejście kosztowałoby ok. $0,40.
- **Karta dowodowa sama obaliła założenie tematu** i powiedziała, czego nie wie.

## Co złapały testy live (i czego nie złapałby test na atrapie)

- **Konsola Windows cp1252** wywalała agenta na polskich znakach. Na serwerze
  z UTF-8 by przeszło — czyli błąd wychodzący tylko na jednym komputerze.
- **Blokady botów są realne**: PMC dwa razy odmówił automatowi, USDA dał 403,
  MDPI pustą stronę. 6 pobrań z 10. Odmowy zapisane, nie obchodzone.
- **Mój własny próg trafności wyrzucił najlepsze źródło liczbowe** (praca
  o atmosferze modyfikowanej na szpinaku, 12 liczb, ocena 0,20). Po usunięciu
  progu: 57 fragmentów zamiast 23, 18 liczb zamiast 9.
- **Dwa miejsca liczyły to samo i dały różne odpowiedzi** — doraźna kontrola
  liczb w `run.py` uznała `E 938` za zmyślone, a `gates.py` nie. Duplikat
  skasowany; jedno pytanie ma jedną implementację.

## Otwarte

- **Stawki DeepSeeka niepotwierdzone.** Koszt liczony szacunkiem; każde takie
  wywołanie ma w bazie `price_verified = 0`. Do sprawdzenia na fakturze.
- **`instrukcja dla pisania artykulow/` leży poza `agent-v2/`.** Działa, ale
  łamie zasadę „wszystko nowego agenta w `agent-v2/`".
- **Brak testów kontradowodowych** — 19 gotowych do przeniesienia z archiwum.
- **Reguła różnorodności domen** działa dopiero od drugiego artykułu (pierwszy
  nie ma historii w nowej bazie; kąty startowe wzięte ze starej).
- **Notki i komentarze nie istnieją** i nie powstaną bez osobnej decyzji.

## Dziennik

### 2026-08-15 — pierwszy artykuł
Temat: „The Bag Of Salad That Puffs Up" → artykuł „The Additive With No Number".
10 źródeł znalezionych, 6 pobranych, 6 pierwotnych, 57 fragmentów, 18 liczb.
Recenzja: 65 zdań — 34 fakty (wszystkie z pokryciem), 13 wnioskowań, 18 prozy.
Zero uwag z bramek. 1253 słowa.

### 2026-08-15 — audyt planu przed budową
Warstwa jakości do przeniesienia „w całości" miała 4 220 linii w 8 plikach,
22 pary zdublowanych liczb (stała kontra zdanie w prompcie) i udokumentowany
w kodzie przypadek dwóch bramek zaprzeczających sobie. Zamiast przenoszenia:
napisana od nowa, cztery bramki, żadna nie blokuje.
