# Brief dla agenta budującego landing page

Czytasz to, bo masz zbudować stronę na serwerze, na którym **już pracuje inny
agent**. Ten dokument mówi, co tam zastaniesz, czego nie wolno ruszać i jak się
dostać do swojej części.

---

## Najważniejsze w jednym akapicie

Na tym serwerze działa autonomiczny agent prowadzący konto na Substacku. Chodzi
z harmonogramu kilka razy dziennie, publikuje treści na żywym koncie i ma własną
sesję przeglądarki. **Zatrzymanie go, restart serwera w losowym momencie albo
zabranie mu portu przerywa jego pracę w połowie i może zostawić opublikowaną
treść w niespójnym stanie.** Twoja strona i jego praca są całkowicie rozdzielone
— trzymaj się swojej części, a nie wejdziecie sobie w drogę.

## Twój dostęp

```bash
ssh -i ~/.ssh/id_ed25519_landing web@<IP-SERWERA>
```

Klucz jest już wgrany. Logujesz się jako **`web`**, nie jako `ubuntu`.

To rozdzielenie jest celowe i sprawdzone: użytkownik `web` **nie ma dostępu** do
katalogu agenta (`/home/ubuntu` ma prawa 750). Nie obejdziesz tego i nie próbuj —
tam siedzą klucze API i sesja Substacka właściciela.

## Co jest twoje

| element | ścieżka / wartość |
|---|---|
| katalog strony | `/var/www/landing` (właściciel: `web`) |
| konfiguracja nginx | `/etc/nginx/sites-available/landing` (właściciel: `web`) |
| porty HTTP/HTTPS | **80 i 443 — wolne, twoje** |
| przeładowanie serwera | `sudo systemctl reload nginx` |

`web` ma **wąskie uprawnienia sudo**: wyłącznie `systemctl reload nginx`,
`systemctl status nginx` i `nginx -t`. Nic więcej. To nie jest przeszkoda do
obejścia, tylko zabezpieczenie przed przypadkowym zatrzymaniem cudzej usługi.

Nginx jest zainstalowany i działa, `/var/www/landing/index.html` zawiera stronę
zastępczą. `curl http://localhost/` zwraca 200.

## Czego NIE WOLNO ruszać

**Usługi zaczynające się od `nia-`.** To jest agent Substacka:

```
nia-agent.timer      publikuje 3x dziennie (11:20, 15:00, 20:10 UTC)
nia-artykul.timer    artykuł tygodniowy, wtorki 14:00 UTC
nia-alarm.timer      kontrola sesji i zdrowia, codziennie ~7:00 UTC
nia-chrome.service   przeglądarka z zalogowaną sesją — MUSI działać ciągle
nia-vnc.service      wirtualny ekran dla tej przeglądarki
nia-novnc.service    dostęp do tego ekranu przez przeglądarkę
```

Nie zatrzymuj ich, nie restartuj, nie wyłączaj. Zwłaszcza `nia-chrome`: jest
w nim ręcznie zalogowana sesja Substacka, a jej odtworzenie wymaga człowieka
przy komputerze.

**Porty 5900, 6080 i 9222.** Zajęte przez tę przeglądarkę i jej ekran. Nasłuchują
tylko na `localhost`, więc ci nie przeszkadzają — ale ich nie zajmuj.

**`/home/ubuntu`** — i tak nie wejdziesz, ale żeby było jasno powiedziane.

**Nie restartuj serwera** bez uzgodnienia z właścicielem. Jeśli naprawdę musisz,
sprawdź najpierw, czy agent akurat nie pracuje:

```bash
pgrep -af "[r]un\.py --dzien" && echo "AGENT PRACUJE — poczekaj" || echo "wolne"
```

Nawiasy kwadratowe w `[r]un` są **konieczne**. Bez nich `pgrep` potrafi dopasować
własne polecenie — jeśli wzorzec wystąpi w wierszu procesu, który go uruchamia —
i zawsze odpowie „pracuje". Sprawdzone, nabraliśmy się na to.

Nie próbuj sprawdzać pliku zamka agenta: leży w `/home/ubuntu` i celowo go nie
widzisz. Listę procesów widzisz i to wystarczy.

Jego przebieg trwa około godziny.

## Co jest wspólne i o czym warto pamiętać

**Pamięć i dysk.** Maszyna ma 12 GB RAM i 96 GB dysku, zajęte jest niecałe 6 GB.
Agent ma limit 3 GB na przebieg. Miejsca jest dużo, ale jeśli będziesz budował
coś ciężkiego (obrazy Dockera, `node_modules`, cache), pamiętaj, że **pełny dysk
zatrzyma także agenta** — a on ma alarm przy 80% i 92%.

**Strefa czasowa serwera to UTC** i tak ma zostać. Agent liczy godziny publikacji
w strefie czytelników i przestawienie zegara systemowego popsuje mu harmonogram.

**Firewall.** Nie ma aktywnego. Jeśli będziesz go włączał, **przepuść port 22**,
inaczej odetniesz wszystkim dostęp, łącznie z sobą.

## Jeśli czegoś potrzebujesz spoza swojej części

Poproś właściciela. On ma dostęp jako `ubuntu` i może zrobić to, czego ty nie
możesz. To jest szybsza droga niż szukanie obejścia — i jedyna właściwa.

## Certyfikat HTTPS

Gdy będzie domena, `certbot` wymaga uprawnień, których `web` nie ma. To zadanie
dla właściciela, jednym poleceniem:

```bash
sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d DOMENA
```

Zaplanuj konfigurację nginx tak, żeby certbot mógł ją później uzupełnić — czyli
trzymaj `server_name` aktualne, gdy domena już będzie.

---

## Podsumowanie w trzech zdaniach

Logujesz się jako `web`, pracujesz w `/var/www/landing`, przeładowujesz nginx
jednym dozwolonym poleceniem. Wszystko z przedrostkiem `nia-` należy do innego
agenta i ma działać nieprzerwanie. Gdy czegoś nie możesz — to nie jest błąd
konfiguracji, tylko celowa granica, i po drugiej stronie stoi właściciel.
