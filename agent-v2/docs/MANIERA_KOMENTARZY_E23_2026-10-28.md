# E23 — maniera komentarza, historia konta, dobór celu wg odpowiadalności autora (28.10.2026)

Podstawa: analiza 24 tys. komentarzy i jej weryfikacja (`KOMENTARZE_STYL_I_ROZMOWA_2026-10-28.md`, sekcja „Wnioski po weryfikacji”).
Decyzja właściciela z 28.10.2026: konto jest do testów, ma mieć „duszę”, ma nie być płaskie i „za każdym razem inne”, a wdrożyć
trzy etapy zaproponowane po analizie. **Wymyślonych osobistych przeżyć nie ma i nie będzie** (decyzja wykonawcy, nie reguła
projektu): prawdziwi ludzie czytają je jako fakty o prawdziwym życiu autora i na tej podstawie komuś ufają (zdrowie, pieniądze, praca).
Zamiast nich konto dostało **prawdziwą ciągłość**: to, co naprawdę opublikowało i z kim naprawdę rozmawiało.

## Co wdrożone

### Etap 1 — dobór celu (obie ścieżki: artykuły i notki, oba ramiona E23)
| zmiana | gdzie | uzasadnienie |
|---|---|---|
| artykuły: najwyżej 3 dni (było 7) | `config.MAKS_WIEK_POSTA_DO_KOMENTARZA_DNI` | pod artykułami starszymi niż 72 h: 0 reakcji na 163 komentarze (≤ 72 h: 12%) |
| notki: najwyżej 24 h (było 36) | `config.MAKS_WIEK_NOTKI_DO_KOMENTARZA_H` | notki starsze niż 2 doby: −24 pkt proc. (N = 42) |
| autor, który odpowiada komentującym, jako kryterium kolejki | `odpowiadalnosc.py`, `kanal.wedlug_odpowiadalnosci`, `run._wedlug_odpowiadalnosci` | autor, który nikomu nie odpisuje, odpowiada nam w ok. 3%; odpisujący większości — w ok. 50%; ok. połowa naszych komentarzy trafiała do pierwszych |

Autor o niskiej odpowiadalności (≤ 5% komentarzy z odpowiedzią autora; artykuły: ostatnie 3 wpisy z ≥ 4 komentarzami, notki: sam wątek z ≥ 2
komentarzami) **schodzi na koniec kolejki, nie jest wykluczany**; 25% takich celów (po adresie, stale) idzie bez kary, żeby nie zamknąć
się w kilku responsywnych kontach (pętla wzajemnych polubień: 4 stałe konta = 35 z 81 nazwanych polubień po 26.09). Niewiedza jest
neutralna (błąd sieci, za mało komentarzy → cel bez kary). Odczyt: publiczne API Substacka, cache `data/odpowiadalnosc.json`, limit 20 nowych
sprawdzeń i 90 s na wywołanie, bez modelu. Wyłącznik: `config.ODPOWIADALNOSC_WLACZONA`.

**Czego świadomie NIE zrobiono (sceptycy):** okna „notka ≤ 6 h” (u nas takie notki mają 33–38% polubień wobec ok. 51% przy 6–24 h, p = 0,02),
globalnej mediany opóźnienia ≤ 3 h, twardego wykluczania autorów.

### Etap 2 — zasady niskiego ryzyka (obowiązują w OBU ramionach)
Bez pochwały / werdyktu / rytualnego „Agreed” na starcie, bez ram zapowiadających myśl („The part worth…”, „Worth pausing on…”), bez linków,
wykrzykników i emoji; długość 40–70 słów (`config.KOMENTARZ_CEL_SLOW`); w odpowiedziach (`odpowiedz.md`) bez pustego wstępu — zgoda jest
dozwolona jako pół zdania, które niesie coś nowego. **Prośba w prompcie nie jest bramką** (lekcja projektu), ale tu LOG, nie bramka (decyzja
właściciela „sprawdzenia są logiem”): `stages.zasady_stylu` zapisuje naruszenia w wyniku kandydata i w logu przebiegu.

### Etap 3 — E23 `maniera_komentarza` (50/50 po adresie celu, 29.10–15.12.2026)
„off” = `prompts/komentarz.md` z zasadami etapu 2. „on” = `prompts/komentarz_b.md` **plus**:
* sedno w pierwszym zdaniu, stanowisko wobec konkretnego twierdzenia z powodem; jawny sprzeciw tylko gdy materiał daje twardą,
  sprawdzalną podstawę (poprawka sceptyków: bez wymuszania sporu), inaczej zgoda z nowym elementem;
* zwykła mowa (skróty, urwane zdania dozwolone, najwyżej jedna pauza lub średnik, bez „nie X, lecz Y” i trójek, bez zamykającego aforyzmu),
  humor tylko z sytuacji, charakter („my”, własne zdanie, przyznanie się do błędu);
* **pytanie na końcu w ok. 25% komentarzy, a CZĘSTOŚĆ USTALA KOD** (`config.MANIERA_PYTANIE_UDZIAL`, los stały po adresie), nie prośba
  w prompcie; pytanie pada PO tezie, nigdy zamiast niej;
* **blok „What this account has already said”** (`historia_konta.py`): do 2 własnych opublikowanych wpisów (notki bez typu MYSL, tytuły
  artykułów) z 60 dni, o podobieństwie cosinusowym ≥ 0,13 (wektory słów ważone rzadkością) i ≥ 2 wspólnych rzadkich terminach; w próbie na
  234 celach trafia w ok. 5% (tylko tam, gdzie konto naprawdę coś już mówiło). Prompt: tylko to się wydarzyło, daty podane z „Today is”,
  nic o przeszłości ponad zapis, historię zignorować, gdy niczego nie wnosi;
* **pamięć rozmówcy** (`stages.pamiec_rozmowcy`) zawsze w ramieniu „on” (E21 skończył się 27.10).

Notki typu MYSL są wyłączone z historii: to rozważania w pierwszej osobie z wymyślonymi nawykami („Every line an assistant writes for work,
I re-read twice”) — w próbie na żywo model powtórzył taki nawyk jako fakt o koncie.

**To jest PACZKA** (zmienia naraz wejście, ton, pytanie i historię). Jeśli B wygra, rozkładamy ją na składniki; jeśli przegra — wiemy tylko, że
paczka nie działa. To świadomy wybór pod polecenie właściciela („dajmy mu duszę”), nie zalecenie czystego eksperymentu.

## Co jest zapisywane w dzienniku (pola komentarza)
`eksperymenty.maniera_komentarza` = `on`/`off`; `maniera_pytanie` (czy ten komentarz miał kończyć się pytaniem), `historia_n` (ile wpisów historii),
`pamiec_b_wymian`; ocena autora: `autor_odp_klasa` (`niska`/`ok`/`nieznana`), `autor_odp` i `autor_odp_n` (gdy znane). Naruszenia zasad stylu
liczy się offline z `tekst` (`stages.zasady_stylu`).

## Reguła decyzji — ZAPISANA Z GÓRY (28.10.2026, przed pierwszym komentarzem w E23)
**Metryka główna:** odsetek komentarzy pierwszego poziomu z odpowiedzią ≥ 15 słów od osoby innej niż my i NIA w ciągu 72 h („rozmowa
merytoryczna”). Baza od 4.10: 22,8% (autor wpisu 28,5%, postronni 2,5%). **Uczciwie: to w ok. 90% odpowiedź autora wpisu, w dużej części grzeczna.**
Dlatego raportujemy ją zawsze rozbitą: autor / postronni.
**Strażnik:** polubienia (≥ 1 polubienie w 72 h, baza 50,2%) — B nie gorsze niż −8 pkt proc. (dolna granica 95% przedziału różnicy).
**Próba:** ok. 380 komentarzy na ramię (przy ok. 18 dziennie ≈ 6 tygodni) wykrywa różnicę ok. 9 pkt proc. w rozmowie i ok. 10 pkt proc. w
polubieniach; przy 190 na ramię tylko ok. 13–14 pkt proc.
**Test manipulacji (po pierwszych 40 komentarzach na ramię):** B ma realnie różnić się od A: start od ram zapowiadających ≈ 0, pauz < 30%,
pytanie ≈ 20–30% (A: ok. 8–10%), 40–70 słów. Jeśli nie — poprawić prompt i liczyć od nowa (lekcja z E17/E18).
**Reguła:**
1. Bez zaglądania w wynik przed 190 na ramię, poza stopem bezpieczeństwa: spadek polubień > 15 pkt proc. albo zarzuty „to bot/AI” pod naszymi komentarzami.
2. Werdykt przy 380 na ramię. **Wdrażamy B**, jeśli rozmowa merytoryczna w B jest wyższa o ≥ +6 pkt proc. (jednostronnie, dolna granica 90%
   przedziału > 0, test permutacyjny z klastrowaniem po autorze wpisu) ORAZ dolna granica 95% przedziału różnicy polubień > −8 pkt proc.
3. Kierunek zgodny i efekt ≥ połowy wykrywalnego, ale warunek niespełniony: jedno przedłużenie do 630 na ramię, potem koniec.
4. Rozmowa ≥ +6 pkt proc. przy spadku polubień ≥ 8 pkt proc.: nie wdrażamy całości, rozkładamy paczkę na składniki.
5. Różnica rozmowy < +3 pkt proc. przy 630 na ramię: wracamy do A i uznajemy, że styl nie jest dźwignią (dźwignią jest dobór celu).
6. Zero nieplanowanych podziałów; podziały po miejscu (artykuły/notki) tylko opisowo.

## Jak ocenić
* Polubienia, odpowiedzi, reakcje (z przedziałem): `python agent-v2/eksperymenty.py --rodzaj komentarz --pole maniera_komentarza --od 2026-10-29`.
* Rozmowa merytoryczna (treść odpowiedzi, rozbicie autor/postronni): potok z analizy 28.10 — `robocze/koment_28_10/crawl_watki.py` → `splaszcz.py` →
  `cechy.py` (poza repozytorium; czyta publiczne API, nie dotyka bota). Wątki naszych komentarzy z okresu E23, grupowanie wg `eksperymenty.maniera_komentarza`.
* Zarzuty „to AI”: wyszukanie w odpowiedziach pod naszymi komentarzami (frazy: AI generated, bot, ChatGPT, slop, LLM).

## Ograniczenia i ryzyka
* Wszystkie dane są obserwacyjne poza samym E23; efekt wczesności i widoczności u rówieśników nie musi przenosić się na nasze konto.
* Własna publiczność rośnie od 4.10 i cztery stałe konta dają dużą część polubień (wzajemność); analiza wrażliwości bez stałych polubiających
  (≥ 3 poprzednich polubień naszych komentarzy) jest częścią oceny.
* Filtr po odpowiadalności autora może zmniejszać rozmowę z postronnymi i wzmacniać pętle wzajemności — dlatego 25% bez kary i neutralna
  niewiedza. Do oceny: udział celów z klasą `niska` i wyniki w obu klasach.
* Odpowiedź autora jest w dużej mierze grzecznościowa (65% to zgoda); nie mierzy jakości komentarza.

## Wycofanie
`config.EKSPERYMENTY["maniera_komentarza"]["do"]` ustawić na datę z przeszłości (ramię „off” = dotychczasowy komentarz z zasadami etapu 2);
`config.ODPOWIADALNOSC_WLACZONA = False`; progi wieku z powrotem na 7 dni i 36 h. Rollback kodu: `git reset --hard <poprzedni commit>` na serwerze.
