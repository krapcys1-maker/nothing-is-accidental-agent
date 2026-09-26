# Plan wzrostu na Substacku — badania, nasze liczby, konkretne zmiany

26 września 2026. Zlecenie właściciela: sprawdzić wszystko o botach i o Substacku,
o naturalnym brzmieniu, o szukaniu ciekawych tematów o AI i o tym, dlaczego ludzie
klikają, lajkują, komentują i subskrybują. Bez banałów i bez blogowych „wydaje mi
się". Na końcu konkretny plan.

**Jak czytać oznaczenia źródeł:**

| znak | co to jest |
|---|---|
| **[B]** | badanie naukowe: recenzowane albo working paper instytucji naukowej |
| **[A]** | ankieta instytutu badawczego (Pew, Reuters Institute) |
| **[S]** | Substack o sobie: dokumentacja, post firmy, wypowiedź pracownika |
| **[D]** | analiza danych platformy robiona przez firmę zewnętrzną: duże próby, ale bez recenzji i tylko korelacje |
| **[N]** | nasze pomiary z tego repozytorium |

**Ograniczenie tej pracy.** Polityka sieci tego środowiska zablokowała bezpośrednie
czytanie stron (m.in. substack.com, arxiv.org, pewresearch.org, nature.com, pubmed).
Wszystkie źródła zewnętrzne czytałem przez wyszukiwarkę, czyli przez fragmenty stron
i streszczenia wyników, nie przez pełne teksty. Liczby podaję tak, jak je tam
opisano. Przed cytowaniem czegokolwiek publicznie trzeba otworzyć oryginał. Dostęp
można rozszerzyć w ustawieniach środowiska (Network access).

---

## Najkrócej

1. **Substack nagradza notki, po których ktoś subskrybuje, a nie te z największą
   liczbą polubień.** Tak opisuje feed szef uczenia maszynowego Substacka i tak
   wyglądają nasze liczby: 5 z 6 zapisów w 30 dni przyszło z notek, zero z
   komentarzy pod cudzymi artykułami, zero z artykułów. [S] [N]
2. **Największa rezerwa jest w tematach.** 91% faktów, z których bot robi notki,
   pochodzi z czterech blogów technicznych. Tymczasem 52% Amerykanów bardziej się
   AI obawia, niż na nie cieszy, trzy czwarte spodziewa się mniej miejsc pracy,
   34% pyta chatboty o zdrowie, a ponad 70% rozmów z ChatGPT nie dotyczy pracy.
   Tam jest czytelnik, którego bot dziś nie widzi. [N] [A] [B]
3. **Ciekawość budzi to, o czym czytelnik coś już wie, ale nie wszystko.**
   Dlatego „panel myślenia" w chatbocie (każdy go widział, mało kto wie, co to
   jest) wygrywa z tokenizacją. Pierwsze zdanie ma podać fakt, a zostawić otwarte
   „dlaczego". Nagłówek-pytanie i zawieszony hak obniżają zaangażowanie. [B] [N]
4. **„Brzmieć jak człowiek" przestało być osiągalnym celem.** Od 21 lipca 2026
   każdy czytelnik Substacka może zeskanować notkę, komentarz albo odpowiedź
   detektorem Pangram. Ludzie, którzy sami dużo piszą z AI, rozpoznają tekst
   modelu prawie bezbłędnie. Wygrywa tekst wart przeczytania nawet wtedy, gdy
   wiadomo, że pisał go model, i uczciwość co do tego, jak powstaje. [S] [B]
5. **Najtańszy zasięg to odpowiedzi pod własnymi notkami i szybkie, merytoryczne
   komentarze u ludzi z tą samą publicznością.** Komentarze pod cudzymi artykułami
   kosztują 3,81 USD miesięcznie i mają zero wyświetleń w kanale. [N] [B]
6. **Wzajemne polubienia i restacki między naszymi dwoma botami trzeba wyłączyć.**
   To dokładnie ten wzorzec, którego szukają wykrywacze skoordynowanych kont,
   i zawyża nasze własne liczby. [B] [N]
7. **Do decyzji właściciela, pilne:** obecne oświadczenie „How I make this"
   (odmowa odpowiedzi) kłóci się z nowym promptem odpowiedzi (mówi wprost, że
   używamy AI), z doktryną i najpewniej z art. 50 AI Act, który obowiązuje od
   2 sierpnia 2026.

---

## 1. Skąd startujemy — nasze liczby

| co | liczba | źródło w repo |
|---|---|---|
| subskrybenci / obserwujący (7.09) | 10 / 20 | `docs/ANALIZA_KONTA_2026-09-07.md` |
| zapisy w 30 dni (3.08–2.09) | 6: **5 z notek**, 1 z substack.com, 0 z artykułów, komentarzy i rekomendacji | `docs/ZRODLA_RUCHU_2026-09-02.md` |
| notka: średnio / mediana wyświetleń | 32,6 / 25 (n=91) | `docs/STATYSTYKI_2026-09-06.md` |
| notka zbiera zasięg przez kilka dni | 1 dzień 7,1 · 3 dni 28,5 · 6 dni 54 wyświetlenia | `config.py`, komentarz przy `NOTE_MIX_OTHER_DAY` |
| komentarz: średnio wyświetleń / bez ani jednego | 1,0 / 74% (n=99) | `docs/STATYSTYKI_2026-09-06.md` |
| komentarz pod cudzym artykułem | 0 z 14 ma kartę zasięgu; 14% dostaje polubienie, 6% odpowiedź | tamże |
| koszt komentowania | 728 wywołań i 3,81 USD na 30 dni | tamże |
| odpowiedź pod własną notką | najtańsze wejście: 0,0012 USD (tylko 2 dojrzałe pozycje) | `agent-v2/DO_ZROBIENIA.md` §4 |
| skąd fakty do notek | 32 z 35 (91%) z 4 blogów: pytorch.org, latent.space, simonwillison.net, importai | `docs/POMIAR_TEMATOW_2026-09-08.md` |
| skład banku faktów | 70% branża, 6% „świat" (131 faktów) | `docs/ANALIZA_KONTA_2026-09-07.md` |
| najlepsza notka w audycie 3.09 | „Whatever your chat app labels 'thinking' is not the block the model sent back" — 77 wyświetleń, 18 interakcji | `agent-v2/docs/AUDYT_NOTEK_2026-09-03.md` |
| restacki | 469 i 123 wyświetlenia (26–27.08), potem 9–34 i zero zapisów | `docs/ANALIZA_KONTA_2026-09-07.md` |
| wzajemność | 12 subskrypcji danych innym, 0 odwzajemnionych | `agent-v2/DOKTRYNA.md` §8 |

Z poprzedniej sesji (plik `POLIGON_I_PRODUKCJA.md`, poza repo, nie sprawdzałem):
najlepsza notka od 5.09 dotyczyła „panelu myślenia" i miała około 250 wyświetleń
przy typowych 10–30; najsłabsze tłumaczyły wnętrze modeli (tokenizacja,
przycinanie warstw) i miały 7–13 wyświetleń. Treści NIA to 23% polubień i 39%
restacków Nothing Is Accidental.

**Uczciwie o próbie:** sześć zapisów to za mało, żeby cokolwiek orzekać. Każda
zmiana niżej jest więc eksperymentem z miarą, a nie pewnikiem.

---

## 2. Jak działa Substack

### 2.1. Feed notek jest ustawiony pod subskrypcje

Mike Cohen (Head of AI & ML Engineering w Substacku) w wywiadzie: celem feedu jest,
żeby ludzie odkrywali, subskrybowali i płacili, a nie czas spędzony w aplikacji.
Restack, odpowiedź i udostępnienie pomagają zasięgowi, bo dzieją się na platformie
i pozwalają „przecinać publiczności". Feed buduje liczbowy profil czytelnika:
kraj, język, subskrypcje, obserwowanych, zadeklarowane zainteresowania. [S]
(relacja z wywiadu na blogu, nie oryginalny zapis)

Pomoc Substacka: notki trafiają do subskrybentów i obserwujących, a w zakładce Home
mogą być polecane także innym, np. czytelnikom publikacji, które nas polecają. [S]

Analiza 208 mln wyświetleń 522 782 notek (WriteStack) opisuje dystrybucję jako
turniej: notkę widzi najpierw mała grupa, a jej reakcje decydują, czy pójdzie
dalej. [D] Zgadza się to z badaniem Muchnika (niżej): wczesne reakcje ważą
najwięcej.

**Wniosek:** liczy się to, co notka robi w pierwszych godzinach u pierwszych
czytelników, i to, czy ktoś po niej wchodzi na profil i subskrybuje.

### 2.2. Sieć rekomendacji

- Rekomendacje razem z aplikacją dają 50% wszystkich nowych subskrypcji
  i 25% nowych płatnych (Substack, luty 2024). [S]
- Kto poleca innych, jest według Substacka trzy razy częściej polecany. [S]
- Autorzy, którzy w tygodniu startu dali co najmniej trzy przemyślane notki,
  zyskali o 50% więcej subskrybentów. [S]

U nas rekomendacje dały zero zapisów, bo prawie nikt nas nie poleca. To jest
dźwignia ręczna, dla właściciela (punkt 7).

### 2.3. Linki i konwersja

- 655 056 notek: z linkiem mediana 2 polubienia zamiast 4, średnia 10,7 zamiast
  19,4 (−44%). Ale notki z linkiem do Substacka dają 6,56 subskrybenta na 100
  polubień zamiast 2,22, czyli około trzy razy więcej. [D]
- 194 twórców śledzonych rok do roku: 100 kliknięć w notkę dawało 1,74 darmowego
  subskrybenta w pierwszej połowie 2025 i 0,93 w pierwszej połowie 2026.
  Spadek dotyczy 86% twórców; przyczyny Substack nie podaje. [D]

**Wniosek:** mniej polubień pod notką z linkiem nie jest porażką. A ta sama praca
daje dziś mniej zapisów niż rok temu u wszystkich, nie tylko u nas.

### 2.4. AI na Substacku od 21 lipca 2026

Prezes Chris Best, „Against Claudefishing": Substack wbudował detektor Pangram.
Czytelnik w aplikacji i w czytniku www może zeskanować post, notkę, komentarz
i odpowiedź opublikowane od 21.07.2026 i zobaczyć, jaki procent tekstu wygląda na
ludzki, a jaki na wspomagany AI. Autor może dodać oświadczenie „How I make this"
i wyłączyć wykrywanie. Według relacji prasy nie ma automatycznej etykiety ani kary
w rankingu. [S] Pangram deklaruje około jednego fałszywego alarmu na 10 000;
niezależny test na tekstach parafrazowanych podał 2–2,7%. [D]

**Stan u nas:** `config.WYLACZ_WYKRYWANIE_AI = True` (bot klika „Wyłącz wykrywanie
AI" w `browser.wystaw_artykul`, czyli przy artykułach), a oświadczenie w `prompts/OSWIADCZENIE_AI.md` brzmi: „This publication
doesn't discuss how it's made…". Jednocześnie `prompts/odpowiedz.md` od 26.09 każe
na pytanie wprost odpowiedzieć, że publikacja używa AI do researchu i szkiców.
To są dwie różne odpowiedzi na to samo pytanie.

### 2.5. Zasady Substacka i prawo

- Warunki korzystania zakazują m.in. autoodpowiedzi, spamu i „procesów, które
  działają, gdy nie jesteś zalogowany". Wytyczne treści: Substack może usuwać
  konta za „sztuczną lub nieautentyczną aktywność" w miejscach społecznościowych.
  [S] Masowe polubienia i wzajemne akcje dwóch naszych kont to dokładnie ten obszar.
- **Art. 50 ust. 4 AI Act, od 2 sierpnia 2026:** kto publikuje tekst wygenerowany
  przez AI w celu informowania opinii publicznej o sprawach interesu publicznego,
  musi to ujawnić. Wyjątek: tekst przeszedł ludzką kontrolę i ktoś bierze za niego
  odpowiedzialność redakcyjną. Konto jest w 100% autonomiczne, jego właściciel
  i serwer są w UE, a pisze o sprawach publicznych, więc najpewniej podpada. To nie jest porada prawna,
  tylko rzecz do sprawdzenia z prawnikiem.

---

## 3. Jak rozpoznaje się boty — i co z tego wynika dla nas

Platformy i badacze patrzą na trzy warstwy:

| warstwa | jak się to wykrywa | nasze ryzyko | co robimy |
|---|---|---|---|
| **tekst** | detektory (Pangram w Substacku) i doświadczeni ludzie: 5 takich czytelników większością myli 1 artykuł na 300, także po parafrazie [B] | wysokie, nieuniknione | nie ukrywamy się; tekst ma być wart czytania także jako tekst AI |
| **zachowanie** | ponad tysiąc cech: rytm aktywności, treść, sentyment, sieć; 9–15% aktywnych kont Twittera to boty [B] | średnie | mniej, ale sensowniejszych akcji |
| **sieć** | konta wykonujące te same akcje na tych samych treściach łączy się w sieci koordynacji [B] | **wysokie**: nasze dwa boty lajkują i restackują siebie nawzajem | wyłączyć akcje wobec kont siostrzanych |

Świadomie **nie** proponuję niczego, co służy obchodzeniu wykrywania. Doktryna
tego zabrania („techniczne ukrywanie się też"), przy tej skuteczności detektorów
i tak by nie zadziałało, a wpadka kosztowałaby całe zaufanie.

---

## 4. Dlaczego ludzie klikają, a dlaczego nie

**4.1. Informacja musi komuś do czegoś służyć.** Ludzie szukają informacji z trzech
powodów: żeby lepiej działać, żeby poprawić sobie nastrój i żeby lepiej rozumieć
świat (Sharot i Sunstein, 2020). [B] Test tematu: czy czytelnik może z tym coś
zrobić, czy to go dotyczy, czy zmienia jego obraz świata. Tokenizacja spełnia
tylko trzeci warunek i to słabo.

**4.2. Ciekawość ma kształt odwróconego U.** Najmniejsza jest przy „nie mam
pojęcia" i przy „wiem na pewno"; ludzie płacą czasem i żetonami za odpowiedź na
pytanie, o którym coś już wiedzą, a zaskakującą odpowiedź lepiej zapamiętują
(Kang i in., 2009). [B] „Panel myślenia" jest w szczycie krzywej, „przycinanie
warstw" w lewym ogonie.

**4.3. Zagadka zamiast faktu szkodzi.** Nagłówki-pytania i zapowiedzi dały mniej
zaangażowania niż zwykłe streszczenie, w laboratorium i w teście terenowym (Scacco
i Muddiman, 2020). [B] Clickbait obniża ocenę wiarygodności i jakości (Molyneux
i Coddington, 2020). [B] To samo wyszło w naszym audycie: „Zero." bez rzeczownika.

**4.4. Negatywność: tak w nagłówku, ostrożnie w kanale.** W testach Upworthy (22 743
eksperymenty, 370 mln wyświetleń) każde negatywne słowo podnosiło klikalność
nagłówka o 2,3% (Robertson i in., 2023); replikacja I4R potwierdziła efekt. [B]
Ale w kanałach społecznościowych negatywne posty mediów (6 mln postów z Facebooka,
6 krajów, w tym Polska) dostają o 15% mniej polubień i o 13% mniej komentarzy.
[B] **Wniosek:** stawka i ryzyko tak, czarnowidztwo nie.

**4.5. Co się niesie dalej.** Treści, które budzą podziw, gniew albo niepokój
(wysokie pobudzenie), oraz praktycznie użyteczne (Berger i Milkman, 2012; dane
NYT). [B] Nowość: fałszywe newsy rozchodzą się o 70% częściej, bo są nowsze
(Vosoughi i in., 2018) — nam wolno brać tylko prawdziwą nowość. [B] Treści,
które mówią coś o mnie i o moich relacjach: aktywność mózgu w obszarach „ja"
i „inni" przewidywała, które artykuły NYT o zdrowiu się rozejdą (Scholz i in.,
2017). [B]

**4.6. Czego świadomie nie bierzemy.** Słowa moralno-emocjonalne podnoszą udostępnienia
(+20% na słowo w polityce; replikacja z 2025: około +17%), a posty o „obcej grupie"
udostępnia się dwa razy częściej niż o własnej (Brady i in., 2017; Rathje i in.,
2021). [B] Działa, ale zamienia konto w maszynę do oburzania, psuje zaufanie
potrzebne do subskrypcji i ściąga czytelników, którzy nie subskrybują kont
objaśniających.

**4.7. Większość reaguje bez czytania.** 73% głosów na Reddicie pada bez otwarcia
treści (Glenski i in., 2017), a około 59% linków udostępnionych na Twitterze nikt
nie kliknął (Gabielkov i in., 2016). [B] Pierwsze zdanie notki robi większość
roboty.

---

## 5. Dlaczego lajkują, komentują i subskrybują

**5.1. Stado i przypadek.** Jeden wczesny sztuczny głos „za" zwiększał szansę
kolejnego pozytywnego o 32%, a końcową ocenę o 25% (Muchnik i in., 2013). [B]
W MusicLab (14 341 osób) wpływ społeczny zwiększał nierówność i nieprzewidywalność
sukcesu; jakość decydowała tylko częściowo (Salganik i in., 2006). [B]
**Wniosek:** sukces pojedynczej notki jest w dużej mierze losowy i zależy od
pierwszych reakcji. Trzeba wielu dobrych strzałów. Z tego samego powodu nie wolno
podbijać się własnymi kontami: to zafałszowuje sygnał, który ma nas czegoś uczyć.

**5.2. Komentuje mało kto, ale da się to ułatwić.** Zasada 90-9-1 potwierdziła się
w czterech sieciach (van Mierlo, 2014). [B] Pytanie w poście zwiększa liczbę
komentarzy (de Vries i in., 2012), a dopytywanie w rozmowie zwiększa sympatię, bo
pokazuje, że słuchamy (Huang i in., 2017). [B] U nas pod notkami model milczy
38 razy na 51 i słusznie — pytanie musi być prawdziwe, nie doklejone.

**5.3. Gospodarz, który odpowiada, podnosi poziom rozmowy.** Gdy reporter angażował
się w komentarze, było mniej chamstwa i więcej argumentów opartych na dowodach
(Stroud i in., 2015, eksperyment terenowy). [B]

**5.4. Liczy się moment.** Zaangażowanie pod komentarzem zależy od jego pozycji
w wątku; wcześniejsze komentarze zbierają więcej (Risch i Krestel, 2020, komentarze
Guardiana). [B] Komentarz pod wpisem sprzed kilku dni czyta mało kto.

**5.5. Powtarzany kontakt pomaga, ale do pewnego momentu.** Efekt ekspozycji ma
kształt odwróconego U: sympatia rośnie z liczbą kontaktów, osiąga szczyt i spada
(Montoya i in., 2017, 268 krzywych z 81 prac). [B] Trzy mocne notki dziennie to
lepszy kierunek niż dziesięć.

**5.6. Subskrypcja to decyzja o zaufaniu.** W badaniu o ujawnianiu AI w newsach
zaufanie było głównym powodem decyzji o subskrypcji (FAccT 2026). [B] Płaci za
newsy online 17% ludzi, zaufanie do mediów jest najniższe w historii pomiarów,
a twórców wybiera się, bo są „łatwiejsi do zrozumienia i bliżsi" (Reuters DNR 2026).
[A] Odwiedziny profilu to u nas jedyny widoczny krok przed subskrypcją — profil
musi w jednym zdaniu mówić, co czytelnik dostanie.

**5.7. Wzajemność nie działa na zimno.** U nas 0 z 12. [N] Na Twitterze wzajemność
obserwacji była niska już w 2010 (Kwak i in.). [B]

---

## 6. Naturalny głos — co naprawdę zdradza AI

**6.1. Doświadczeni czytelnicy widzą AI.** Pięciu ludzi, którzy sami dużo piszą
z modelami, większością głosów pomyliło 1 z 300 artykułów, także po parafrazie
i „uczłowieczaniu". Patrzyli na słownictwo typowe dla AI, formalność, oryginalność
i klarowność (Russell, Karpinska, Iyyer, ACL 2025). [B]

**6.2. Zwykli czytelnicy kierują się złymi wskazówkami.** Pierwsza osoba, skróty
i wątki rodzinne uznają za dowód człowieka, dlatego się mylą (Jakesch i in., PNAS
2023, 4600 osób). [B] To nie jest droga dla nas: zmyślone przeżycia są zakazane,
a skaner i tak ich nie weźmie za ludzkie.

**6.3. Modele piszą gęsto i rzeczownikowo**, także gdy prosi się je o styl mówiony;
różnica rośnie po instruowaniu modelu (Reinhart i in., PNAS 2025). [B] To jest
„profesor fizyki kwantowej" z audytu 3.09. Słowa stylu AI („delve" i podobne)
wyraźnie przybyły w nauce: co najmniej 13,5% streszczeń z 2024 przeszło przez LLM
(Kobak i in., 2025). [B]

**6.4. AI ujednolica.** Teksty pisane z pomysłami od AI są pojedynczo lepsze, ale
podobniejsze do siebie (Doshi i Hauser, 2024). [B] To jest mechanizm naszej
„tablicy ogłoszeń": różnorodność trzeba wymuszać kodem (źródła, formy, tematy),
bo model sam wraca do środka.

**6.5. Persona robi różnicę.** Ten sam model był uznawany za człowieka w 73%
rozmów z personą i w 36% bez niej (Jones i Bergen, 2025). [B] Chodzi nie o udawanie
człowieka, tylko o spójny charakter: własne przekonania, własne ulubione pytania,
własny sposób patrzenia. Zalążek jest w `prompts/glos_krotkich.md`.

**6.6. Czy ujawniać AI — co mówią badania.**
- Etykieta „AI" obniża ocenę trafności i chęć udostępnienia, nawet prawdziwych
  i ludzkich nagłówków, bo ludzie zakładają pełną automatyzację bez nadzoru
  (Altay i Gilardi, 2024, 4976 osób). [B]
- Skutek jest wąski: nie zmienia poparcia dla opisanej sprawy, a pokazanie, na
  czym polega użycie AI, łagodzi spadek (2025, 3861 osób). [B]
- Szczegółowe opisy procesu obniżały zaufanie i subskrypcje, jednozdaniowe nie;
  zwiększały za to sprawdzanie źródeł (FAccT 2026). [B]
- Wiersze AI oceniano wyżej od ludzkich, dopóki nie było wiadomo, kto je napisał
  (Porter i Machery, 2024). [B]

**Wniosek:** jeśli właściciel ujawni AI, to jednym zdaniem o nadzorze nad faktami,
np. „AI robi research i szkice; każde twierdzenie ma link do źródła; jeśli czegoś
w źródle nie ma, napisz, poprawię publicznie". Nie esejem o procesie.

**6.7. Co z tego wynika dla promptów** (bez nakazów pozycji, zgodnie z doktryną):
czasowniki zamiast rzeczowników odczasownikowych; jedna myśl na zdanie; jedno
nowe pojęcie na notkę, wyjaśnione zwykłymi słowami; własny osąd z uzasadnieniem;
jeden konkret, którego nie ma w pierwszym akapicie źródła. Lista słów-sygnałów AI
zostaje, ale sama nie wystarczy.

---

## 7. Tematy: jak bot ma znajdować ciekawe rzeczy o AI (eksperyment E6)

### 7.1. Diagnoza z repo

Bank bierze fakty tam, gdzie łatwo je udokumentować, czyli z prasy technicznej.
Trzy pomiary pokazały, że prośby w prompcie tego nie zmieniają; dźwignią są źródła
(`docs/POMIAR_TEMATOW_2026-09-08.md`). Do tego `prompts/ciekawostki.md` każe:
„Aim for three quarters of the material to connect to the supplied channel leads",
a prawie wszystkie kanały w `korpus_kanalow.ZRODLA` to blogi firm, wydania bibliotek
i strony awarii. O tym, co AI robi ludziom, piszą z nich właściwie tylko AI Incident
Database, Komisja UE i częściowo Transformer.

### 7.2. Gdzie jest czytelnik — dane

- 52% dorosłych Amerykanów bardziej się AI obawia, niż na nie cieszy (37% w 2021);
  wśród 18–29 lat 55% (31% w 2021); około trzech czwartych spodziewa się mniej
  miejsc pracy (Pew, sierpień 2026). [A]
- Około połowa dorosłych używa chatbotów, co czwarty codziennie; 64% nastolatków
  13–17 lat; co dziesiąty rodzic dziecka 5–12 lat mówi, że dziecko ich używa
  (Pew, 2026). [A] Niekorzystający: 6 na 10 bez zainteresowania, dalej
  prywatność i trafność. [A]
- 34% dorosłych używa chatbotów w sprawach zdrowia; co czwarty do oceny objawów,
  podobnie wielu do zrozumienia wyników badań; 22%, bo tanio; 18%, bo o tym
  wstydzi się rozmawiać (Pew, 25.08.2026). [A]
- Ponad 70% wiadomości do ChatGPT nie dotyczy pracy; porady praktyczne, szukanie
  informacji i pisanie to prawie 80% rozmów (Chatterji i in., NBER 2025). [B]
- 10% ludzi co tydzień dostaje newsy z chatbotów (17% wśród 18–24 lat); tylko 4%
  klika w źródła (Reuters DNR 2026). [A]
- Najmłodsi pracownicy (22–25 lat) w zawodach najbardziej narażonych na AI:
  −13% zatrudnienia względem innych, dane płacowe ADP (Brynjolfsson, Chandar,
  Chen, Stanford; tablica aktualizowana). [B]

### 7.3. Filtr tematu — trzy pytania, liczone w kodzie

1. **Punkt styku:** czy fakt dotyka czegoś, co czytelnik ma w ręku: produkt, cena
   albo rachunek, praca, szkoła albo dziecko, zdrowie, prawo albo urząd, pieniądze.
   Nowe pole w banku: `styk` (jedna z tych wartości albo `branza`).
2. **Stan wiedzy:** czy czytelnik coś o tym wie (widział, używał, słyszał). Środek
   odwróconego U, nie jego ogony.
3. **Użyteczność:** co czytelnik może z tym zrobić albo co zmienia się w jego
   obrazie świata.

### 7.4. Nowe źródła — pierwotne i o ludziach

Każde trzeba sprawdzić na żywo (tytuł feedu i data ostatniego wpisu), zgodnie
z regułą przy `korpus_kanalow.ZRODLA`:

| źródło | co daje |
|---|---|
| Pew Research Center (AI, nauka, internet) | co ludzie myślą o AI i jak jej używają |
| Stanford Digital Economy Lab, tablica „Canaries" | praca młodych w zawodach narażonych na AI |
| NBER, nowe working papers o AI | praca, zdrowie, edukacja: pomiary, nie prognozy |
| raporty użycia od dostawców (OpenAI Economic Research, Anthropic Economic Index) | jak ludzie naprawdę używają modeli — jako twierdzenia firm o sobie |
| FTC i prokuratorzy stanowi | działania wobec firm AI, oszustwa, chatboty dla dzieci |
| CourtListener | pozwy wobec firm AI: prawa autorskie, szkody |
| FDA, lista urządzeń medycznych z AI | co już jest dopuszczone w medycynie |
| OECD AI Incidents Monitor (obok AI Incident Database) | wypadki i szkody |
| Reuters Institute | newsy, AI i zaufanie |
| strony zmian i cenniki produktów, których ludzie używają | co zmienia się dla użytkownika ChatGPT, Claude, Gemini |

### 7.5. Egzekwowanie w kodzie, bo prośba w prompcie nie jest bramką

- **Limit źródła:** najwyżej 2 fakty z jednego hosta w jednej partii, przy zapisie
  do banku (`stages.dopisz_kandydatow`). Propozycja z `POMIAR_TEMATOW`, nigdy
  niezrobiona.
- **Kwota styku:** co najmniej 1 z 3 notek dziennie z faktem, którego `styk` nie jest
  `branza` (`stages.wez_kandydatow`). Jeśli banku brakuje, przebieg to loguje.
- **Kanały ludzkie osobno:** nowe źródła jako osobna grupa zaczynu z przewagą w co
  drugim szukaniu (mechanizm `ZACZYN_CO_DRUGIE_SZUKANIE` już istnieje).
- **Prompt:** zdanie o „trzech czwartych z kanałów" zastąpić wymogiem połowy faktów
  o tym, gdzie AI trafia w życie ludzi, i poprosić o pole `styk`. To dodatek; bramką
  jest kod.

### 7.6. Jak mierzymy E6

Dwa tygodnie przed i po, na poligonie (Nothing Is Accidental):

- przyrząd z `tests/platne/proba_tematow.py`: co najmniej 8 różnych hostów na 35
  faktów (dziś 7) i co najmniej 40% faktów z polem `styk` różnym od `branza`;
- karta wyników (`karta_wynikow.py`): mediana wyświetleń notki po 72 h, odwiedziny
  profilu na notkę, zapisy na 1000 wyświetleń;
- decyzja: jeśli mediana po 72 h nie spadła, a odwiedziny profilu wzrosły, zmiana
  idzie do NIA.

---

## 8. Co robić z każdym kanałem

| kanał | dane | badania | decyzja |
|---|---|---|---|
| **notki** (3 dziennie) | jedyne źródło zapisów (5 z 6) | pierwsze zdanie i pierwsze reakcje decydują; ekspozycja ma szczyt | zostają 3; tematy wg E6; fakt w pierwszym zdaniu (E7) |
| **odpowiedzi** pod własnymi notkami | najtańsze wejście | gospodarz podnosi poziom; dopytywanie zwiększa sympatię | odpowiadać na każdą merytoryczną, szybko; dopytać, gdy pytanie jest prawdziwe |
| **komentarze pod cudzymi artykułami** (7–9 dziennie) | 0 wyświetleń w kanale, 14% dostaje polubienie, 3,81 USD/mies. | wcześniejsze komentarze zbierają więcej | zmniejszyć do 2–3; tylko pod świeżymi wpisami publikacji z naszą publicznością; nie przenosić na siłę pod notki (6.09: tam model milczy 38 na 51) |
| **restacki** (1–2) | 2 wczesne skoki, potem 9–34 | restack to sygnał wspólnej publiczności | tylko od publikacji, których czytelników chcemy, z jednym zdaniem od siebie; nigdy od NIA |
| **polubienia** (10–16) | brak wpływu na nasz zasięg | wczesny głos zmienia oceny innych; masowe akcje to obszar „nieautentycznej aktywności" | zmniejszyć; lajkować ludzi, z którymi rozmawiamy; wyłączyć NIA |
| **rekomendacje Substacka** | 0 zapisów | 50% nowych subskrypcji idzie przez sieć i aplikację; polecający 3× częściej polecani | właściciel ustawia ręcznie 3–5 dobrych publikacji o AI (nie drugiego bota) |
| **artykuł tygodniowy** | brak przypisanych zapisów; najdroższy | notki z linkiem mają mniej polubień, ale ~3× lepszą konwersję na polubienie | zostaje jako „dom" dla notek z linkiem; o koszcie decyduje właściciel |
| **profil** | jedyny widoczny krok przed zapisem | zaufanie decyduje o subskrypcji | jedno zdanie obietnicy, przypięta najlepsza notka |

---

## 9. Plan — kolejność prac

**Etap 0, już zlecony innemu agentowi.** Poprawka odmowy dostawcy (`llm.py`)
i przywrócenie ochron w promptach (`odpowiedz.md`, `komentarz.md`).

**Etap 1, tydzień 1.**
- Wyłączyć polubienia i restacki treści kont siostrzanych w obu botach
  (`config.KONTA_SIOSTRZANE`, filtr w `browser.polub_w_kanale`,
  `browser.restackuj_w_kanale`, `stages.ocen_restack`). Rozmowy zostają, jak chce
  właściciel.
- Zapisać punkt wyjścia w karcie wyników (dwa tygodnie są).
- Decyzje właściciela: oświadczenie AI i `WYLACZ_WYKRYWANIE_AI`, konsultacja
  art. 50 AI Act, rekomendacje, zdanie obietnicy na profilu.

**Etap 2, tygodnie 1–2: E6 tematy** na poligonie: nowe źródła, limit hostów,
pole `styk`, kwota. Miara z punktu 7.6.

**Etap 2, równolegle: E8 kanały.** Komentarze 2–3 dziennie pod świeżymi wpisami,
odpowiedzi bez zwłoki, restacki celowane, mniej polubień. Miara: koszt na wejście
i na polubienie (tabela z `DO_ZROBIENIA.md` §4), odwiedziny profilu. Inny kanał niż
E6, więc da się je rozdzielić w pomiarze.

**Etap 3, tygodnie 3–4: E7 pierwsze zdanie.** Po napisaniu notki kod sprawdza dwie
wady znane z audytu 3.09: hak do 4 słów niezwiązany w następnym zdaniu
i pytanie zamiast faktu na początku. Wada uruchamia jedną próbę naprawy pierwszego
zdania. Nic nie blokuje i nic nie wycina, zgodnie z doktryną.

**Etap 4: przeniesienie zwycięzców do NIA** (produkcja), po jednym na raz.

**Zasady pomiaru.** Notka dojrzewa 3 dni, więc porównujemy wyniki po 72 h. Jedna
zmiana na raz w tym samym kanale. Progi decyzji zapisujemy przed startem, nie po
wynikach. Przy kilku zapisach miesięcznie patrzymy głównie na odwiedziny profilu
i mediany, nie na same zapisy.

---

## 10. Do decyzji właściciela

1. **Oświadczenie AI.** Dziś: „doesn't discuss how it's made" i wyłączone wykrywanie
   przy artykułach. Prompt odpowiedzi mówi co innego (uczciwie: używamy AI).
   Rekomendacja: jedno zdanie o AI i o nadzorze nad faktami, zostawione
   zobowiązanie do publicznej korekty; wtedy wyłączanie wykrywania traci sens.
2. **Art. 50 AI Act** — sprawdzić z prawnikiem, czy konto podpada; jeśli tak,
   punkt 1 przestaje być wyborem.
3. **Rekomendacje** 3–5 publikacji o AI, które naprawdę warto polecić.
4. **Zdanie obietnicy** na profilu i przypięta notka.
5. **Koszt artykułu tygodniowego** wobec tego, że zapisy przychodzą z notek.

---

## 11. Źródła

### Substack i prawo
- [S] Mike Cohen o algorytmie notek — relacja: https://pubstacksuccess.substack.com/p/the-notes-algorithm-explained-by
- [S] Where do my Substack notes appear?: https://support.substack.com/hc/en-us/articles/14673287580436-Where-do-my-Substack-notes-appear
- [S] How writers and creators are using Notes to reach more subscribers: https://on.substack.com/p/how-publishers-are-using-notes-to-grow
- [S] Substack na X, 22.02.2024 (50% i 25%): https://x.com/Substack/status/1760696631156953443
- [S] Upgrading Substack's recommendation network: https://on.substack.com/p/substacks-recommendations-network
- [S] Chris Best, Against Claudefishing: https://post.substack.com/p/against-claudefishing
- [S] How can I detect AI on Substack?: https://support.substack.com/hc/en-us/articles/50891130623508-How-can-I-detect-AI-on-Substack
- TechCrunch, 22.07.2026: https://techcrunch.com/2026/07/22/substacks-new-tool-tells-you-whos-been-writing-their-newsletters-with-ai/
- [S] Terms of Use: https://substack.com/tos · Content Guidelines: https://substack.com/content
- [D] WriteStack: linki w notkach https://thewritingedge.substack.com/p/how-to-make-urls-in-your-notes-convert · 208 mln wyświetleń https://thewritingedge.substack.com/p/i-analyzed-208485570-note-impressions · spadek konwersji https://thewritingedge.substack.com/p/notes-conversion-fell-by-half
- [D] Pangram, oceny zewnętrzne: https://www.pangram.com/blog/third-party-pangram-evals
- AI Act, art. 50: https://artificialintelligenceact.eu/article/50/ · FAQ Komisji: https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act

### Wykrywanie tekstu AI i boty
- [B] Russell, Karpinska, Iyyer, ACL 2025: https://aclanthology.org/2025.acl-long.267/
- [B] Jakesch, Hancock, Naaman, PNAS 2023: https://www.pnas.org/doi/10.1073/pnas.2208839120
- [B] Reinhart i in., PNAS 2025: https://www.pnas.org/doi/10.1073/pnas.2422455122
- [B] Kobak i in., Science Advances 2025: https://www.science.org/doi/10.1126/sciadv.adt3813
- [B] Doshi, Hauser, Science Advances 2024: https://www.science.org/doi/10.1126/sciadv.adn5290
- [B] Jones, Bergen, 2025: https://arxiv.org/abs/2503.23674
- [B] Porter, Machery, Scientific Reports 2024: https://www.nature.com/articles/s41598-024-76900-1
- [B] Altay, Gilardi, PNAS Nexus 2024: https://academic.oup.com/pnasnexus/article/3/10/pgae403/7795946
- [B] AI labeling reduces the perceived accuracy…, 2025: https://arxiv.org/abs/2506.16202
- [B] Full Disclosure, Less Trust?, FAccT 2026: https://arxiv.org/abs/2601.09620
- [B] Varol i in., ICWSM 2017: https://arxiv.org/abs/1703.03107
- [B] Pacheco i in., ICWSM 2021: https://arxiv.org/abs/2001.05658

### Klikanie, ciekawość, udostępnianie
- [B] Sharot, Sunstein, Nature Human Behaviour 2020: https://www.nature.com/articles/s41562-019-0793-1
- [B] Kang i in., Psychological Science 2009: https://journals.sagepub.com/doi/abs/10.1111/j.1467-9280.2009.02402.x
- [B] Scacco, Muddiman, New Media & Society 2020: https://journals.sagepub.com/doi/abs/10.1177/1461444819863408
- [B] Molyneux, Coddington, Journalism Practice 2020: https://www.tandfonline.com/doi/abs/10.1080/17512786.2019.1628658
- [B] Robertson i in., Nature Human Behaviour 2023: https://www.nature.com/articles/s41562-023-01538-4 · replikacja: https://www.journalofrobustnessreports.org/does-negativity-drive-online-news-consumption/
- [B] Negatywne posty na Facebooku, 6 krajów, 2025: https://arxiv.org/abs/2507.19300
- [B] Berger, Milkman, JMR 2012: https://journals.sagepub.com/doi/10.1509/jmr.10.0353
- [B] Vosoughi, Roy, Aral, Science 2018: https://www.science.org/doi/10.1126/science.aap9559
- [B] Scholz i in., PNAS 2017: https://www.pnas.org/doi/10.1073/pnas.1615259114
- [B] Brady i in., PNAS 2017: https://www.pnas.org/doi/10.1073/pnas.1618923114 · replikacja 2025: https://academic.oup.com/pnasnexus/article/4/11/pgaf327/8285703
- [B] Rathje i in., PNAS 2021: https://www.pnas.org/doi/10.1073/pnas.2024292118
- [B] Glenski i in., 2017: https://arxiv.org/abs/1703.05267
- [B] Gabielkov i in., SIGMETRICS 2016: https://inria.hal.science/hal-01281190v1

### Zaangażowanie i subskrypcja
- [B] Muchnik, Aral, Taylor, Science 2013: https://www.science.org/doi/10.1126/science.1240466
- [B] Salganik, Dodds, Watts, Science 2006: https://www.science.org/doi/10.1126/science.1121066
- [B] van Mierlo, JMIR 2014: https://www.jmir.org/2014/2/e33/
- [B] de Vries, Gensler, Leeflang, 2012: https://journals.sagepub.com/doi/10.1016/j.intmar.2012.01.003
- [B] Huang i in., JPSP 2017: https://pubmed.ncbi.nlm.nih.gov/28447835/
- [B] Stroud i in., JCMC 2015: https://academic.oup.com/jcmc/article/20/2/188/4067559
- [B] Risch, Krestel, ICWSM 2020: https://arxiv.org/abs/2003.11949
- [B] Montoya i in., Psychological Bulletin 2017: https://doi.org/10.1037/bul0000085
- [B] Kwak i in., WWW 2010: https://doi.org/10.1145/1772690.1772751

### Ludzie i AI — ankiety i dane
- [A] Pew, 3.04.2025: https://www.pewresearch.org/internet/2025/04/03/how-the-us-public-and-ai-experts-view-artificial-intelligence/
- [A] Pew, 12.03.2026: https://www.pewresearch.org/short-reads/2026/03/12/key-findings-about-how-americans-view-artificial-intelligence/
- [A] Pew, 17.06.2026: https://www.pewresearch.org/internet/2026/06/17/why-dont-people-use-chatbots/
- [A] Pew, 18.08.2026: https://www.pewresearch.org/short-reads/2026/08/18/young-adults-in-the-us-are-increasingly-wary-of-ai-concerned-it-will-take-jobs/
- [A] Pew, 25.08.2026: https://www.pewresearch.org/science/2026/08/25/from-diagnoses-to-treatments-why-americans-use-ai-chatbots-for-health/
- [B] Chatterji i in., NBER w34255: https://www.nber.org/papers/w34255
- [A] Reuters Institute, Digital News Report 2026: https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2026/dnr-executive-summary · chatboty: https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2026/emerging-uses-ai-chatbots-news-and-what-it-means-journalism
- [B] Brynjolfsson, Chandar, Chen, Canaries in the Coal Mine: https://digitaleconomy.stanford.edu/wp-content/uploads/2025/08/Canaries_BrynjolfssonChandarChen.pdf · tablica: https://digitaleconomy.stanford.edu/project/indicators/canaries-dashboard/
