# Brief dla agenta budującego stronę portfolio

Czytasz to, bo masz umieścić na stronie opis projektu, którego nie budowałeś.
Wszystko, czego potrzebujesz, leży w tym folderze. Nie musisz mieć dostępu do
serwera ani do kodu agenta.

---

## Co jest w folderze

| plik | do czego |
|---|---|
| `PROJEKT.md` | **główny tekst na stronę** — historia, problemy, rozwiązania |
| `FUNKCJE.md` | lista zdolności, funkcja po funkcji |
| `JAK_DZIALA.md` | warstwa techniczna dla ciekawych |
| `LICZBY.md` | wszystkie liczby, gotowe do wyciągnięcia na kafelki |
| `zrzuty/` | cztery zrzuty ekranu + `OPIS.md` z gotowymi podpisami |
| `przyklady/tresci.md` | prawdziwe treści napisane przez agenta |
| `przyklady/przebieg-dnia.log` | pełny zapis jednego przebiegu, 278 linii |

---

## Jak to ułożyć na stronie — propozycja

**1. Nagłówek.** Jedno zdanie i jedna liczba:

> Autonomiczny agent, który sam prowadzi publikację na Substacku — pisze,
> komentuje, odpowiada i obserwuje. Bez ani jednego pytania do człowieka.

**2. Kafelki z liczbami.** Cztery, z `LICZBY.md`:
`6 526 linii kodu` · `139 testów` · `0,20 USD za przebieg` ·
`18 komentarzy u 18 różnych publikacji`

**3. Zrzut `01-profil.png` na całą szerokość.** To najmocniejszy dowód — od razu
widać, że coś realnie działa i że ludzie na to reagują.

**4. Historia ograniczenia.** Sekcja z `PROJEKT.md` o poprzedniej wersji: 71 598
linii i dwa artykuły kontra 6 526 linii i działające konto. To najlepszy fragment
w całym materiale, bo pokazuje decyzję inżynierską, a nie listę technologii.

**5. Trudne problemy.** Cloudflare, odcisk przeglądarki, sesja związana z adresem,
zachowanie nieodróżnialne od człowieka. Każdy z konkretną liczbą albo cytatem.

**6. Zrzuty `02` i `03` obok siebie** — dowód, że agent prowadzi rozmowy.

**7. Fragment logu.** Kilkanaście linii z `przyklady/przebieg-dnia.log` w bloku
kodu z ciemnym tłem. Dobry kawałek zaczyna się od `[budżet dnia — rozbieg]`
i kończy na `NOTKA PRZYJETA`. Widać w nim wybór faktu, trzy warianty notki,
sprawdzenie faktów i siedemnastominutową przerwę przed kolejnym działaniem.

**8. Czego nie rozwiązałem.** Ostatnia sekcja `PROJEKT.md`. Nie pomijaj jej —
przyznanie się do otwartych problemów czyta się jako pewność siebie, a nie jako
słabość.

---

## Czego NIE WOLNO umieszczać

Właściciel postawił to jasno: projekt może być jawny, **sekrety nie**.

- żadnych kluczy API ani ich fragmentów
- żadnego adresu serwera, nazw użytkowników, ścieżek do kluczy SSH
- żadnej zawartości pliku `.env` ani nazw zmiennych środowiskowych z wartościami
- żadnych zrzutów terminala pokazujących logowanie na serwer

Materiały w tym folderze zostały pod tym kątem sprawdzone i są czyste. Jeśli
będziesz dobierał własne zrzuty albo fragmenty logów — sprawdź je ponownie.

---

## Rzeczy, o które nie musisz pytać

**Nazwa publikacji może być jawna.** Właściciel to potwierdził.

**Zrzuty pokazują nazwy osób trzecich** — to publiczne reakcje na Substacku.
Jeśli wolisz je rozmyć, rozmyj; to kwestia stylu, nie bezpieczeństwa.

**Ton tekstów.** Napisane są rzeczowo, bez marketingu, z przyznaniem się do
błędów. To jest zamierzone i proszę tego nie „podkręcać" — projekt broni się
liczbami, nie przymiotnikami.

**Język.** Wszystko jest po polsku. Sama publikacja jest anglojęzyczna, więc jeśli
strona ma wersję angielską, cytaty treści agenta zostają bez tłumaczenia — są
oryginałami.

---

## Jeśli potrzebujesz czegoś więcej

Nowe zrzuty, świeże liczby, inny fragment logu albo diagram — poproś właściciela.
Ma dostęp do serwera i może to wygenerować. Nie próbuj sam sięgać do
infrastruktury agenta; jest odseparowana celowo.
