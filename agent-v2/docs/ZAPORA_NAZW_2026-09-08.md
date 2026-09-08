# Zapora „ta sama nazwa" — 8 wrzesnia 2026

## Co sie stalo

W przebiegu 11:21 UTC trzej kandydaci odpadli na jednym komunikacie:

    pomijam — ta sama nazwa co w juz wystawionej notce: critical
    pomijam — ta sama nazwa co w juz wystawionej notce: astra's
    pomijam — ta sama nazwa co w juz wystawionej notce: critical

## Skala, zmierzona na zywym banku

Ze **131 wolnych faktow przechodzilo 22 (17%)**, a 94 (72%) odpadalo na tej
jednej zaporze. Czolowka blokujacych to nie tematy, tylko firmy:

    google 17   openai's 14   anthropic 8   minimax's 7   face 7   nvidia's 6

## Naprawy, ktore weszly

### 1. Forma dzierzawcza to ta sama nazwa

`openai's` i `openai` byly dla zapory roznymi slowami. Zwolnienie z korpusu
zrodel dziala na `openai` (30 wystapien w 341 tematach), ale nasze notki pisza
„OpenAI's model" — i taka forma byla rzadka, wiec blokowala. Zwolnienie omijalo
dokladnie te nazwy, dla ktorych powstalo.

Zmierzony skutek: **22 → 28 faktow przechodzi**. Same formy dzierzawcze
odpowiadaly za 34 blokady z 94.

### 2. Zwykle slowa odsiewane w dobra strone

Regula „slowo, ktore w korpusie pada takze z malej litery, nie jest nazwa"
byla wpieta w LICZNIK CZESTOSCI. Pomijanie w liczniku daje czestosc **zero**,
a zero znaczy „rzadka", czyli „blokuje" — regula przeciw falszywym blokadom
dzialala odwrotnie do wlasnego celu. Teraz odsiewa ze zbioru wspolnych nazw.

### 3. Wspolna nazwa to powod do pytania, nie wyrok

Gdy zapora nazw zadziala, rozstrzyga model — `_powtorka_wg_modelu`, ten sam
przyrzad, ktorego bank uzywa przy kazdym wejsciu kandydata. Pytanie pada
wylacznie przy kolizji, na DeepSeeku po 400 tokenow, z sufitem 5 pytan na
jeden wybor. Zawodzi na „to nie powtorka": bez polaczenia albo po nieudanym
wywolaniu material przechodzi.

## Czego NIE udalo sie zrobic i dlaczego

Szukalem progu statystycznego, ktory odrozni firme-aktora od modelu-tematu.
**Cztery proby, wszystkie obalone pomiarem na tych samych danych:**

| sposob | wynik |
|---|---|
| czestosc w banku | `glm53flash` 7 = `minimax` 7 = `claude` 7 = `deepmind` 7 |
| pokrycie slowami | trojka GLM ma 1–3 wspolne rdzenie, czyli MNIEJ niz falszywe blokady (2–4) |
| czestosc w zrodlach | `glm53` ma 4, dokladnie miedzy `google` (2) a `anthropic` (5) |
| udzial wspolnych nazw | GLM 0,33; falszywe 0,12–1,00, mediana 0,71 — GLM w srodku |

Trzecia proba byla juz **wpisana do kodu i zabila zapore calkowicie**:
zalozycielska trojka notek o GLM-5.3-Flash przestala byc lapana, 3 pary z 3
przechodzily. Wycofana tego samego dnia.

Wniosek: roznica miedzy firma a tematem lezy w ZNACZENIU, nie w liczbach.
Dlatego pyta model.

## Co pilnuje, zeby to nie zgnilo

`agent-v2/tests/test_nazwa_pyta_model.py` — 17 sprawdzen, w tym:

- zapora naprawde lapie badana pare (inaczej caly test bylby o niczym),
- model pytany TYLKO przy kolizji nazw — zero wywolan bez niej,
- sufit pytan naprawde dotkniety, nie tylko nieprzekroczony,
- przegladanie pamieci przerywa sie na trzeciej kolizji, a nie po 40 notkach,
- `conn` i `run_id` docieraja z `notki_dnia` do wszystkich trzech wywolan —
  bez tego przewodu zestaw bylby zielony nad martwym mechanizmem.

Kontrdowod odtworzony: po urwaniu jednego przewodu asercja pada, po
przywroceniu wraca.

## Co pozostaje niezmierzone

Ile faktow przepusci model — to widac dopiero na produkcji, bo w zestawie
odpowiedzi sa podstawione. **Dowodem jest slad z przebiegu po wdrozeniu.**
