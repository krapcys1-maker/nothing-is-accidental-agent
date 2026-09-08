# Pierwszy pomiar przyrządem — i obalił moją własną zmianę

8 września 2026. Dziesięć szukań przez prawdziwy potok,
`tests/platne/proba_tematow.py --live --ile 10`.
Koszt: **0,3783 USD**, 11 płatnych wywołań. Bank nietknięty (10 przechwyconych
prób zapisu, sha256 przed i po zgodne). Opublikowanych: 0.

## Wynik

```
66 faktów z 10 szukań:   branża 48 (73%)   świat 1 (2%)   oba 1   żadne 16
punkt odniesienia (bank): branża 69%       świat 5%       oba 30  żadne 3
```

Wszystkie dziesięć szukań poszło **bez zaczynu z kanałów** — czyli dokładnie
w warunkach, które wczoraj wprowadziłem jako lekarstwo na monotonię.

**Nie zadziałało.** Świat nie urósł.

### Zastrzeżenie, którego nie pomijam

Te dwie liczby **nie są wprost porównywalne**. Punkt odniesienia to BANK:
zbiór narastający tygodniami, karmiony też furtką wydarzeń i researchem
artykułu, po odsiewie. Pomiar to SUROWE wyjście szukania. Więc „73 wobec 70"
nie jest pogorszeniem — to są dwie różne populacje.

Co **jest** czyste: w tym pomiarze dziesięć szukań bez zaczynu dało **2%
świata**. Hipoteza „zdejmij zaczyn, a siatka dziedzin zacznie działać" jest
tym obalona i nie potrzebuje do tego punktu odniesienia.

## Znalezisko większe niż to, po co szedłem

**Model ignoruje dziedziny, które dostaje.** Zestawienie z pomiaru:

| dostał do przeszukania | co oddał |
|---|---|
| *self-driving*, *copyright, training data and cases filed* | „AI infrastructure and open-source governance", „AI marketplace" |
| *AI in schools, exams and detection tools* | „open-source AI infrastructure" |
| *AI in drug discovery*, *reproducing a published result* | „open-source AI infrastructure", „AI assistant behavior" |
| *the people labelling data, what they are paid* | „open-source AI stack", „answer-engine optimisation" |

Dziesięć szukań dostało **dziesięć różnych zestawów dziedzin** (przyrząd to
potwierdza) i oddało **ten sam wąski wycinek**: infrastruktura open-source,
układy scalone, łańcuch dostaw, zachowanie modelu. Fraza „open-source AI
infrastructure" wraca w szukaniach 3, 7, 9 i 10.

To nie jest „za dużo branży". To jest **jeden akapit branży, powtarzany**.

## Co z tego wynika

Przyczyną monotonii nie jest zaczyn z kanałów i nie jest lista dziedzin. **Obie
te rzeczy sprawdziłem i obie są niewinne.** Model idzie tam, gdzie da się
UDOKUMENTOWAĆ fakt z dokumentem kontrolnym — a to jest prasa techniczna.
„AI w diagnostyce, z dokumentem, który to potwierdza" jest trudne; „chińskie
akceleratory wysłane" jest łatwe.

Czyli dźwignią nie są słowa w prompcie, tylko **źródła, w których szuka**.

## Czego ten pomiar NIE mówi

- Czy zaczyn z kanałów szkodzi. Zmierzyłem tylko warunek bez niego.
- Czy klasyfikator jest dobry. **16 z 66 faktów (24%) nie pasuje do żadnego
  wzorca** — to dużo i może znaczyć, że przyrząd nie widzi części tematów.
- Czy dziesięć szukań wystarczy. Zestawy dziedzin były różne, więc rozkład
  jest prawdziwy, ale 66 faktów to nadal 66.

## Co przyrząd udowodnił o sobie

Obalił moją zmianę w **dwadzieścia minut za 0,38 USD**. Bez niego wierzyłbym
w nią tydzień i tłumaczył sobie skład banku czymkolwiek innym.

Przy pierwszym uruchomieniu sam miał wadę tej samej klasy, którą miał wykrywać:
zameldował „branża 0%, świat 0%" przy **zerze płatnych wywołań** — ciszę jako
pomiar. Teraz drukuje pełne wyjście szukania, gdy nic nie oddało.
