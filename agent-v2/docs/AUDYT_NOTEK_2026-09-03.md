# Audyt wszystkich notek od przestawienia konta na AI

**Data:** 3 wrzesnia 2026. **Zakres:** 34 notki bota od `DATA_PRZESTAWIENIA`
(25 sierpnia) do 3 wrzesnia 19:38 UTC. **Zlecenie wlasciciela:** „przeanalizuj
notki jakie wypuszczamy od czasu kiedy piszemy o ai".

## 0. Skad wziete teksty — i dlaczego NIE z dziennika

Pierwsza proba szla z `data/dziennik.jsonl`. Pomiar pola `tekst`:
**21 z 34 notek ma dokladnie 300 znakow**, urwanych w polowie slowa
(„The difference is one outsourcing cont"). Zapisane `slow` nie zgadza sie
z liczba slow w polu (52 wobec 50, 61 wobec 50, 65 wobec 48).

**Wniosek osobny od tresci: wlasnym dziennikiem nie da sie audytowac wlasnego
pisania.** Teksty do tego audytu pobrane na zywo z
`/api/v1/reader/feed/profile/<id>?types[]=note` — 96 pozycji, po odsianiu
notek recznych wlasciciela i wpisow pod artykulami zostaje 34 z dziennika bota.
Pelna dlugosc: 233-505 znakow, srednio 344.

## 1. O czym piszemy

Podzial wlasny po przeczytaniu wszystkich 34:

| Temat | Ile | Przyklady |
|---|---|---|
| Pieniadze, koszt inferencji, infrastruktura | 9 | Microsoft 24,1 mld, Jalapeno, prad w Irlandii |
| Nawyki czytelnika wobec modelu (refleksja) | 8 | „dwa akapity, ktore pomijam", pisanie pod filtr |
| Prawo i regulacje | 5 | SB 942, prawo autorskie Japonii, AI Act 3% obrotu |
| Bezpieczenstwo i kontrola modelu | 5 | 1200 agentow, szyfrowany lancuch mysli, pauza Astry |
| Pomiar i benchmarki | 5 | wyciek MMLU, 646 mil Nuro, wykrywacze AI |
| Praca ludzi | 1 | 2 USD za godzine w Kenii |
| Medycyna | 1 | rentosertib, 320 pacjentow |

**Powtorzen praktycznie nie ma: 32 rozne historie na 34 notki.** Dwie pary
dotykaja tego samego: #15 i #20 (obie o lipcowym tescie agentow OpenAI, obie
linkuja ten sam artykul — to celowa promocja) oraz #22 i #28 (model wideo
MiniMax H3 dwa dni pod rzad, ale rozne fakty: szybkosc i cena).

## 2. Liczby NIE rozstrzygaja o jakosci — i to jest ustalenie, nie wymowka

* Reakcje: srednia 3,1, mediana 3, zakres 1-8.
* Otwarcie konkretne (liczba lub nazwa w pierwszym zdaniu) — 3,2 reakcji.
  Otwarcie abstrakcyjne — 3,0. **Roznicy nie ma.**
* Notki bez ani jednej liczby w calym tekscie (11 z 34) — 3,1. **Tyle samo.**
* Wyswietlenia sa skazone wiekiem (notka z dzis ma 3, sprzed tygodnia 55),
  ale mediany dzienne nie ukladaja sie monotonicznie (27.08 = 19, 31.08 = 50),
  wiec wiek ich nie tlumaczy w calosci. Sygnalu jakosci tekstu i tak nie daja.
* Dla porownania: 22 notki napisane w tym samym okresie RECZNIE przez
  wlasciciela maja srednio 3,0 reakcji. Bot pisze na poziomie konta.

**Czego to dowodzi:** przy n=34 ani reakcje, ani zasiegi nie karza notki
niezrozumialej. Jesli czekamy, az liczby powiedza nam, ktora notka byla
belkotem, nie doczekamy sie. Poprawa czytelnosci musi isc z redakcji i bramki
w kodzie, nie z pomiaru wyniku.

## 3. Trzy nazwane wady — kazda z cytatem

### 3.1. Hak zawieszony w prozni

Forma LICZBA otwiera notke jednym slowem, ktore nastepne zdanie ma zwiazac
(„Zero. / That's how many permissions you need in Japan…" — dziala).
Zmierzone na 6 notkach otwieranych krotkim hakiem: **2 nie wiaza go wcale.**

**#31 (3.09):** „Zero." → „SemiAnalysis physically tore down Huawei's Kirin
9030 and found US export controls did not stop progress."
Zero **czego**? Notka nigdy tego nie mowi. Czytelnik dostaje liczbe bez
rzeczownika.

**#08 (27.08):** „320 patients." → „Insilico's Phase III trial of
rentosertib…". Tu zwiazek da sie wywnioskowac, ale nie jest powiedziany.

### 3.2. Klotnia z przeciwnikiem, ktorego czytelnik nie zna

Notka zaczyna od obalenia zdania, ktorego czytelnik nigdy nie slyszal.

**#34 (3.09 — ta ze zrzutu wlasciciela):** „Trying it yourself is also a
benchmark. Sample size one, run once, never written down. / I keep hearing
that public tests are useless…"
Czytelnik nie brał udzialu w tym sporze. Dostaje odpowiedz bez pytania.

**#07 (26.08):** „Shelved genius is the most flattering story this industry
tells about itself." — „shelved genius" to nie jest zwrot, ktory ktokolwiek
zna. Dalej „Where I come off it" — po angielsku to zagadka.

**#10 (27.08):** „Predictable wrong beats occasionally brilliant" — ratuje ja
dopiero drugie zdanie z konkretem („right four times and confidently wrong
the fifth").

### 3.3. Nazwa bez wyjasnienia, co to jest

**#16 (31.08):** „On GLM-5.3 Flash, the run that passes a flaky task is the
longer one only 46% of the time… On 900 rollouts across 113 DeepSWE tasks…
Distillation didn't take the capability away."
W jednej notce: `flaky task`, `rollouts`, `DeepSWE`, `distillation` — zadne
nie wyjasnione. To jest dokladnie ta notka, o ktorej wlasciciel mowi, ze
pisze ja profesor fizyki kwantowej.

**#22 (1.09):** „fal's H3 Max… That 35x throughput figure" — 35x wobec czego?
Kto to jest „fal"?

**#28 (2.09):** „outranks the $7.80 parent… It now sits #1 on the
leaderboard" — na jakiej liscie? Czyj „rodzic"?

## 4. Co dziala i czego nie wolno zepsuc

* **#17 (31.08, 92 wyswietlen — najwiecej w calym okresie):** Ox Alpha okazuje
  sie chinskim GLM-5.3-Flash na 100 tys. chinskich ukladow. Nazwa, liczba,
  zaskoczenie, pytanie na koniec.
* **#14 (77 wyswietlen, 18 interakcji — rekord zaangazowania):** „Whatever
  your chat app labels 'thinking' is not the block the model sent back."
  Zdanie, ktore czytelnik moze sprawdzic u siebie w minute.
* **#19 (54 wyswietlen, 7 reakcji) — i to notka BEZ ANI JEDNEJ LICZBY.**
  „Two paragraphs. That's how much of any answer I skip." Konkretne
  zachowanie, nie teza. Dowod, ze problemem nie jest brak faktu, tylko
  abstrakcja.
* **#26 (2.09):** „Paste the same error in as someone else's text and it
  catches it. Leave that error in its own previous answer and it usually
  walks straight past." — termin `weights` uzyty, ale zdanie dziala i bez
  jego rozumienia.
* **#01 (25.08):** 12,50 USD wobec 2 USD za te sama godzine. Nic do
  tlumaczenia.

**Wzor, ktory z tego wychodzi:** dziala KONKRET, nie fakt. #19 nie ma faktu
i jest jedna z najlepszych. #31 ma fakt i jest niezrozumiala.

## 5. Przyczyna strukturalna

Regula „kazda nazwana miara dostaje pol zdania zwyklymi slowami" weszla do
`prompts/notka.md` dzis o 21:10 i na serwer o 22:18 — czyli **po wszystkich
34 notkach z tego audytu.** Zadna notka nie byla jeszcze pisana pod ta regula.

Ale sama regula nie wystarczy i wiemy to z wlasnej historii (patrz
`feedback-prosba-nie-jest-bramka`): dwa artykuly przegralismy, zanim ta sama
klasa problemu zostala naprawiona w KODZIE, a nie w prosbie do modelu.

**Do zbudowania: bramka czytelnosci** odrzucajaca notke, ktora
(a) otwiera sie hakiem do 4 slow i nie wiaze go w nastepnym zdaniu,
(b) uzywa terminu spoza jezyka potocznego bez wyjasnienia obok.
Obie wady sa wykrywalne mechanicznie — dowodem sa pomiary z sekcji 3.
