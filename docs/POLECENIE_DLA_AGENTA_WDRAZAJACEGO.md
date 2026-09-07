# Polecenie dla agenta, który ma postawić drugiego bota na serwerze

*Do wklejenia w całości. Napisane 7 września 2026, sprawdzone na żywym
serwerze — wszystkie ścieżki, nazwy jednostek i godziny są odczytane, nie
zapamiętane.*

---

Postaw na serwerze **drugą, niezależną kopię** bota Substack, piszącą na
**inne konto** niż ta, która już tam działa. Pracujesz na żywym serwerze, na
którym stoi działająca produkcja — **niczego w niej nie zmieniasz.**

## Czego NIE WOLNO ruszać

- katalogu `~/nothing-is-accidental-agent` ani jego `data/`
- jednostek `nia-agent`, `nia-alarm`, `nia-artykul` (service i timer)
- **nie kopiuj katalogu `data/` z pierwszego bota.** To jest pamięć pierwszego
  konta: dziennik, bank faktów, historia publikacji, sesja. Druga kopia ma
  zacząć z pustym katalogiem, inaczej odziedziczy cudzą historię i będzie
  unikać powtórek, których sama nie popełniła.
- **nie zajmuj się logowaniem do Substacka.** Hasło wpisuje właściciel sam,
  ręcznie, przez zdalny pulpit. Twoje zadanie kończy się na przygotowaniu
  osobnej przeglądarki (punkt 5).

## Dostęp

    ssh -i ~/.ssh/id_ed25519_nia_vps ubuntu@57.131.139.221

Istniejąca produkcja: `~/nothing-is-accidental-agent`, gałąź `main`,
`.venv/bin/python`, wdrożenie przez `bash agent-v2/wdroz.sh`.

## Co masz zrobić, po kolei

**1. Nowy katalog i klon.** Sklonuj to samo repozytorium do
`~/drugi-agent` (albo innej nazwy, byle NIE do katalogu pierwszego bota).
Gałąź `main`.

**2. Własne środowisko.** Osobny `.venv` w nowym katalogu, zainstalowane
zależności i przeglądarki Playwrighta. Nie współdziel `.venv` z pierwszym
botem.

**3. Własny `.env`** w nowym katalogu. Klucze API mogą być te same co
u pierwszego bota. **Cztery pozycje muszą być inne:**

    SUBSTACK_HANDLE=<uchwyt drugiego konta>
    MARKA=<nazwa drugiej publikacji, tak jak ma się pojawiać w tekstach>
    MONTHLY_LIMIT_USD=<sufit tej kopii, w dolarach>
    PODWYZKA_MIESIECZNA_USD=0

Ostatnia linia jest obowiązkowa. Bez niej druga kopia odziedziczy wrześniową
podwyżkę sufitu do 150 USD, która była decyzją o **pierwszym** koncie.

**UWAGA O BUDŻECIE, powiedz to właścicielowi wprost:** sufity są liczone
**per kopia, nie per karta**. Każda kopia czyta swoje wydatki z własnej bazy
i nie widzi drugiej. Dwie kopie z sufitem 40 USD to **80 USD rachunku**, bez
żadnego ostrzeżenia w logu. `MONTHLY_LIMIT_USD` ustaw tak, żeby SUMA obu miała
sens.

**4. Sprawdź, że kopia widzi swoje ustawienia** — zanim cokolwiek uruchomisz:

    cd ~/drugi-agent && .venv/bin/python -c "
    import sys; sys.path.insert(0,'agent-v2')
    import config, browser
    print('uchwyt      :', config.SUBSTACK_HANDLE)
    print('marka       :', config.MARKA)
    print('profil==publ:', browser.PROFIL_HANDLE == config.SUBSTACK_HANDLE)
    print('sufit mies. :', config.sufit_miesieczny())
    print('katalog dan.:', config.DATA_DIR)"

Uchwyt i marka muszą być **drugiego** konta, a `katalog danych` musi wskazywać
na `~/drugi-agent/agent-v2/data`, nie na katalog pierwszego bota. Jeśli
którakolwiek z tych rzeczy się nie zgadza — zatrzymaj się i zgłoś.

**5. Osobna przeglądarka do logowania.** Pierwszy bot ma jednostkę
`nia-chrome.service`, która trzyma Chrome z profilem
`/home/ubuntu/chrome-serwer` na porcie debugowania **9222** i jest zalogowana
na pierwsze konto. Dla drugiego konta zrób **osobną jednostkę** z:
- innym katalogiem profilu (np. `/home/ubuntu/chrome-serwer-2`),
- innym portem debugowania (np. **9223**),
- tym samym adresem startowym `https://substack.com/sign-in`.

Nie loguj się sam. Powiedz właścicielowi, że ma się zalogować przez zdalny
pulpit, i podaj mu port.

**6. Zestaw testów w nowej kopii** — przed jakimkolwiek uruchomieniem
produkcyjnym, z korzenia nowego katalogu:

    for t in agent-v2/tests/test_*.py; do
      PYTHONIOENCODING=utf-8 .venv/bin/python "$t" >/dev/null 2>&1 || echo "OBLANY: $t"
    done

Ma nie oblać się **nic**. W pierwszej kopii cały zestaw (166 plików) świeci
na zielono, łącznie z `test_czas` — ten pada wyłącznie na Windowsie.

**7. Przebieg na sucho, bez publikowania:**

    cd ~/drugi-agent && .venv/bin/python agent-v2/run.py --dzien

Bez `--wyslij` nic nie idzie w świat. Sprawdź w wyjściu, że agent widzi swoje
konto i swój katalog danych. Dopiero gdy to jest czyste, przechodź dalej.

**8. Własne jednostki systemd.** Trzy, wzorowane na istniejących, ale z
`WorkingDirectory=/home/ubuntu/drugi-agent` i własnym `.venv`:

| jednostka | odpowiednik | co robi |
|---|---|---|
| `drugi-agent.service` + `.timer` | `nia-agent` | dzień pracy |
| `drugi-alarm.service` + `.timer` | `nia-alarm` | kontrola zdrowia |
| `drugi-artykul.service` + `.timer` | `nia-artykul` | artykuł tygodniowy |

**Godziny MUSZĄ być przesunięte** względem pierwszego bota. Dzisiejszy zegar
pierwszej kopii (UTC):

    nia-agent    11:20, 17:00, 19:20, 21:30, 23:40   (Persistent=true, RandomizedDelaySec=600)
    nia-alarm    07:00
    nia-artykul  wtorki 14:00

Wybierz inne minuty — rozsunięcie nic nie kosztuje, a dwa Chrome'y startujące
w tej samej sekundzie to jedyne miejsce, gdzie te kopie mogłyby sobie wejść
w drogę. Serwer ma zapas (11,7 GB RAM, z tego 9,7 wolne, 6 rdzeni, obciążenie
0,05; jeden przebieg bierze szczytowo 265–475 MB), więc chodzi o higienę,
nie o wydajność.

**9. Włącz timery dopiero na końcu**, po zielonym zestawie testów, czystym
przebiegu na sucho i po tym, jak właściciel potwierdzi, że drugie konto jest
zalogowane.

## Na koniec zamelduj

- ścieżkę nowej kopii i jej commit,
- wynik zestawu testów w nowej kopii,
- ustawiony `MONTHLY_LIMIT_USD` **i sumę obu kopii**,
- nazwy i godziny trzech nowych jednostek,
- port przeglądarki dla drugiego konta.

## Jedna pułapka pomiarowa, żebyś w nią nie wpadł

Jeśli będziesz porównywać zachowanie dwóch wersji kodu przez `git worktree`,
pamiętaj, że drzewo robocze **nie ma katalogu `data/`** — dziennik nie jest
w repozytorium. Każdy test, który czyta dziennik, przechodzi tam niezależnie
od wersji kodu. Takie porównanie mierzy obecność danych, a nie wersję.
