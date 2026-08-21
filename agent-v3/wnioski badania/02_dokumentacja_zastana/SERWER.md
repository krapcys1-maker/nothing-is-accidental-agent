# Serwer — instalacja krok po kroku

> **Ten dokument opisuje pierwszą instalację i jest już historią.** Serwer stoi
> i działa. Jeśli wracasz do agenta po przerwie, chcesz
> **[JAK_WROCIC.md](JAK_WROCIC.md)** — tam jest aktualny sposób logowania
> (użytkownik `ubuntu`, nie `root`), codzienne polecenia i lista rzeczy, które
> zmienialiśmy w systemie.

Maszyna: **OVH VPS-3, Ubuntu 26.04, Frankfurt, `57.131.139.221`**.

Robimy to w **dwóch etapach**, celowo. Etap 1 odpowiada na jedno pytanie i nic
poza tym nie rusza. Dopiero jego wynik decyduje, czy Etap 2 ma sens.

---

## Etap 1 — jedno pytanie: czy sesja żyje z adresu serwera

To jest najdroższe ryzyko w całym projekcie i najtańsze do sprawdzenia. Sesja
Substacka została założona z domowego adresu IP. Jeśli Substack wiąże ją
z adresem, to z Frankfurtu nie zadziała — a wtedy cała droga przez przeglądarkę
wymaga przemyślenia od nowa i lepiej wiedzieć to teraz niż po tygodniu pracy.

### 1.1 Na serwerze — instalacja

```bash
apt update && apt install -y python3 python3-venv python3-pip git
git clone https://github.com/krapcys1-maker/nothing-is-accidental-agent.git
cd nothing-is-accidental-agent
python3 -m venv .venv
.venv/bin/pip install -r agent-v2/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m playwright install-deps chromium
mkdir -p agent-v2/data
```

Repozytorium jest publiczne, więc klonowanie nie wymaga logowania. Sprawdzone:
w historii nigdy nie było `.env` ani żadnego klucza.

### 1.2 Z twojego komputera — przeniesienie sekretów

Dwa pliki, których celowo nie ma w gicie. Wysyłasz je **ty**, bo to twoje
sekrety i nie mają przechodzić przez nic po drodze.

```bash
scp "C:/Users/user/Desktop/agent project/.env" root@57.131.139.221:~/nothing-is-accidental-agent/.env
scp "C:/Users/user/Desktop/agent project/agent-v2/data/storage-state.json" root@57.131.139.221:~/nothing-is-accidental-agent/agent-v2/data/storage-state.json
```

### 1.3 Na serwerze — sprawdzenie

```bash
cd ~/nothing-is-accidental-agent && .venv/bin/python agent-v2/browser.py serwer
```

Nic nie publikuje, nie polubia i nie zmienia. Sam odczyt.

**Wynik dobry** wygląda tak — sprawdzone lokalnie przed wysłaniem:

```
  plik sesji: jest, wazna 89 dni
  ciasteczko sesji: JEST
  odpowiedz API: {'status': 200, 'nazwa': 'Nothing Is Accidental', 'id': 528224862}
  kompozytor notek widoczny: True

  WYNIK: sesja dziala z tego adresu. Mozna isc dalej.
```

**Wynik zły** kończy się zdaniem `sesja NIE dziala stad`. Wtedy **stop** — nie
instalujemy nic więcej, tylko wracamy do projektowania logowania.

---

## Etap 2 — dopiero po zielonym świetle z Etapu 1

Nie opisuję go tu jeszcze szczegółowo, bo jego kształt zależy od wyniku wyżej.
Zostaje do zrobienia, w tej kolejności:

1. **Zamek na pliku.** Cron odpali agenta o 6:00, gdy poprzedni przebieg jeszcze
   trwa — dwa procesy naraz to dwa razy ten sam artykuł. To nie jest kwestia
   „czy", tylko „kiedy".
2. **Zapis PRZED działaniem, nie po.** Artykuł poszedł, notka nie, restart —
   i artykuł idzie drugi raz.
3. **Kanał, który dociera do właściciela.** Ostrzeżenie o wygasającej sesji
   wypisuje się dziś na ekran, którego na serwerze nie ma. Agent zamilknie,
   a właściciel dowie się po tygodniu, patrząc na profil.
4. **`systemd` z restartem i `enable`**, żeby wracał po restarcie maszyny.

## Czego NA PEWNO nie robimy

**Nie mówimy agentowi, że stoi w Niemczech.** Im mniej wie o swoim położeniu,
tym mniej się psuje. Wewnątrz wszystko liczy się w UTC, a godziny publikacji
w strefie CZYTELNIKÓW (`America/New_York`, już w `config.py`). Dzięki temu
przeniesienie serwera nie zmienia niczego, a zmiany czasu po obu stronach
Atlantyku — Europa 25 października, Ameryka tydzień później — obsługuje
biblioteka stref, nie nasz kod. Wpisanie „jesteśmy w CEST" tworzy błąd, który
wybucha dokładnie w tym tygodniu różnicy.

## Limity: dwie różne miary, celowo

- **Koszty API — miesiąc kalendarzowy**, bo tak liczą Anthropic i DeepSeek.
  Sufit ma się pokrywać z fakturą, inaczej nie chroni portfela.
- **Działania społeczne — ruchome 30 dni**, nie okno od 15 do 15. Przy oknie
  stałym agent może wypalić cały zapas obserwowań w trzy ostatnie dni i zamilknąć
  na cztery tygodnie; ruchome okno z definicji na to nie pozwala.
