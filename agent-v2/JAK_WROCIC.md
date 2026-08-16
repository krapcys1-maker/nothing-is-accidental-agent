# Jak wrócić do agenta — ściąga na później

Ten plik istnieje po to, żeby za trzy miesiące nikt nie siedział godzinę nad
pytaniem „dlaczego to nie działa" albo „jak ja się tu w ogóle logowałem".
Zapisane jest wszystko, co zmienialiśmy, i po co.

---

## Dostęp

```bash
ssh -i ~/.ssh/id_ed25519_nia_vps ubuntu@57.131.139.221
```

Klucz leży na komputerze właściciela w `~/.ssh/`. **Jest bez hasła** — musi taki
być, żeby agent działał bez człowieka. Kto ma dostęp do tego komputera, ma dostęp
do serwera. To **jedyny klucz** wpisany dla `ubuntu`.

### Gdyby klucz zginął — trzy drogi, wszystkie sprawdzone

1. **Logowanie hasłem po SSH.** `PasswordAuthentication` jest **włączone**, a
   `ubuntu` ma ustawione hasło. Czyli `ssh ubuntu@57.131.139.221` bez klucza
   zadziała.
2. **Konsola KVM w panelu OVH** (VPS-3, Frankfurt). Działa nawet gdy SSH padnie
   całkowicie — to samo hasło.
3. **Reset hasła z panelu OVH**, gdyby hasło też przepadło.

Uwaga do rozważenia przy okazji: włączone logowanie hasłem na publicznym IP to
zarazem nasza siatka bezpieczeństwa i cel dla botów zgadujących hasła. Zostawione
świadomie jako droga powrotu. Jeśli kiedyś zostanie wyłączone
(`PasswordAuthentication no`), **najpierw** dopisz drugi klucz zapasowy, bo
inaczej zostaje tylko konsola OVH.

Drugi klucz, `~/.ssh/id_ed25519_landing`, należy do **innego projektu** (strona
żony) i loguje jako użytkownik `web`. Nie ma dostępu do agenta i tak ma zostać.

## Gdzie co leży

| co | gdzie |
|---|---|
| kod agenta | `/home/ubuntu/nothing-is-accidental-agent` |
| sekrety | tamże, `.env` (prawa 600, poza gitem) |
| sesja Substacka | `agent-v2/data/storage-state.json` |
| dziennik działań | `agent-v2/data/dziennik.jsonl` |
| baza | `agent-v2/data/agent-v2.db` |
| logi przebiegów | `journalctl -u nia-agent.service` |

## Co zmienialiśmy w systemie i po co

**`/home/ubuntu` ma prawa 750, nie 755.** Zrobione świadomie, gdy dołożyliśmy
drugi projekt: użytkownik `web` nie może zajrzeć do katalogu agenta ani do jego
kluczy API. Dla nas jako `ubuntu` nic się nie zmienia — sprawdzone.

Gdyby kiedyś jakiś proces zgłaszał brak dostępu do plików agenta, to jest
pierwsze miejsce do sprawdzenia:

```bash
stat -c "%a %U" /home/ubuntu     # ma być: 750 ubuntu
```

**Użytkownik `web` z wąskim sudo.** Plik `/etc/sudoers.d/web-nginx` pozwala mu
wyłącznie przeładować i sprawdzić nginx. Nie ruszaj tego pliku przy debugowaniu
agenta — nie ma z nim nic wspólnego.

**nginx zajmuje porty 80 i 443.** Agent ich nie używa; jego przeglądarka słucha
na 5900, 6080 i 9222, wyłącznie na localhost.

**Firewalla nie ma** i tak jest dziś. Gdyby ktoś go kiedyś włączał — najpierw
port 22, inaczej odcina wszystkich, łącznie z sobą.

## Codzienne polecenia

```bash
# co agent zrobił i gdzie się pomylił
.venv/bin/python agent-v2/alarm.py przeglad 3

# kontrola zdrowia (sesja, dysk, cisza, powtórki)
.venv/bin/python agent-v2/alarm.py

# czy sesja Substacka żyje
.venv/bin/python agent-v2/browser.py serwer

# ręczny przebieg dnia BEZ publikowania
.venv/bin/python agent-v2/run.py --dzien

# wdrożenie nowej wersji ze sprawdzeniem i cofnięciem
bash agent-v2/wdroz.sh
```

### Czy agent akurat pracuje

Pytaj **zamka**, bo to on faktycznie pilnuje, żeby nie było dwóch przebiegów:

```bash
flock -n agent-v2/data/agent.lock -c true && echo wolne || echo PRACUJE
```

Przez listę procesów też się da, ale **tylko z nawiasami**:

```bash
pgrep -af "[r]un\.py --dzien"
```

Bez nawiasów `pgrep -f` potrafi dopasować własne polecenie i zawsze odpowie, że
agent pracuje. Nabraliśmy się na to raz — stąd ta uwaga.

## Harmonogram

```
nia-agent.timer     11:20, 15:00, 20:10 UTC   rutyna dnia
nia-artykul.timer   wtorki 14:00 UTC          artykuł tygodniowy
nia-alarm.timer     ~07:00 UTC                kontrola sesji i zdrowia
```

Godziny są w UTC i **strefa serwera ma zostać na UTC**. Agent przelicza je na
strefę czytelników sam; przestawienie zegara systemowego popsuje mu okno
publikacji.

## Rzecz, która zatrzyma agenta bez żadnego błędu

**Wygaśnięcie sesji Substacka.** Ważna do około 13 listopada 2026. Alarm mailowy
przychodzi na 14 dni przed.

Odnowienie wymaga człowieka, bo Substack loguje przez link na e-mail:

1. na komputerze uruchom `bash ~/polacz-z-serwerem.cmd` — otworzy pulpit serwera
   w przeglądarce
2. zaloguj się w tamtejszym Chrome na Substacka
3. `.venv/bin/python agent-v2/browser.py serwer` — potwierdzi, że sesja działa

Sesja **musi** powstać na serwerze, nie na komputerze właściciela: sesja z innego
adresu IP jest odrzucana przez Cloudflare przy publikowaniu. To było odkrycie,
które kosztowało pół wieczoru.

## Wyłącznik awaryjny

```bash
# zatrzymanie agenta bez odinstalowywania
sudo systemctl disable --now nia-agent.timer nia-artykul.timer

# albo miękko, przez konfigurację
echo "KILL_SWITCH=true" >> .env
```

Pierwsze zatrzymuje harmonogram, drugie blokuje wszystkie płatne wywołania przy
najbliższym uruchomieniu.
