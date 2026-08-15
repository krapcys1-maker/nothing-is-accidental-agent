"""Alarm do właściciela — jedyny kanał, którym agent mówi „stało się źle".

Agent chodzi bez nadzoru, więc cicha awaria jest gorsza od głośnej: gdy sesja
Substacka wygaśnie, a nikt się nie dowie, konto milczy przez tydzień i dopiero
wtedy ktoś zauważa. Ostrzeżenie wypisane na stdout serwera nie dociera do nikogo.

Alarm jest RZADKI z założenia. Ten sam problem nie zgłasza się częściej niż raz
na dobę, bo kanał, który dzwoni co godzinę, przestaje być czytany po dwóch dniach
— a wtedy jest gorszy niż jego brak.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import config

HISTORIA = config.DATA_DIR / "alarmy.json"
CISZA_GODZIN = 24


def _ustawienia() -> dict[str, str]:
    return {
        "do": os.environ.get("ALARM_EMAIL_TO", "").strip(),
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": os.environ.get("SMTP_PORT", "587").strip(),
        "user": os.environ.get("SMTP_USER", "").strip(),
        # Google pokazuje haslo aplikacji w czterech grupach po cztery znaki
        # i ludzie wklejaja je ze spacjami. Dziala, ale przez przypadek —
        # wycinamy je, zeby nie bylo zagadka za trzy miesiace.
        "haslo": os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip(),
    }


def skonfigurowany() -> bool:
    u = _ustawienia()
    return bool(u["do"] and u["user"] and u["haslo"])


def _ostatnio(klucz: str) -> datetime | None:
    if not HISTORIA.exists():
        return None
    try:
        dane = json.loads(HISTORIA.read_text(encoding="utf-8"))
        return datetime.fromisoformat(dane[klucz])
    except (ValueError, KeyError, OSError):
        return None


def _zapisz(klucz: str) -> None:
    dane = {}
    if HISTORIA.exists():
        try:
            dane = json.loads(HISTORIA.read_text(encoding="utf-8"))
        except ValueError:
            pass
    dane[klucz] = datetime.now(timezone.utc).isoformat()
    HISTORIA.parent.mkdir(parents=True, exist_ok=True)
    HISTORIA.write_text(json.dumps(dane, ensure_ascii=False, indent=1),
                        encoding="utf-8")


def wyslij(klucz: str, temat: str, tresc: str) -> bool:
    """Wysyła alarm. `klucz` identyfikuje RODZAJ problemu, nie pojedynczy wypadek.

    Zwraca True, gdy poszedł. Nigdy nie rzuca wyjątkiem: alarm, który wywala
    agenta, byłby gorszy od problemu, który zgłasza.
    """
    u = _ustawienia()
    if not skonfigurowany():
        print(f"  [alarm NIEWYSLANY — brak konfiguracji] {temat}", flush=True)
        return False

    poprzednio = _ostatnio(klucz)
    if poprzednio and datetime.now(timezone.utc) - poprzednio < timedelta(
            hours=CISZA_GODZIN):
        print(f"  [alarm pominiety — zglaszany w ciagu doby] {temat}", flush=True)
        return False

    wiadomosc = EmailMessage()
    wiadomosc["Subject"] = f"[agent NIA] {temat}"
    wiadomosc["From"] = u["user"]
    wiadomosc["To"] = u["do"]
    wiadomosc.set_content(
        f"{tresc}\n\n--\nagent-v2, {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
        f"serwer: {os.uname().nodename if hasattr(os, 'uname') else 'lokalnie'}\n"
    )
    try:
        with smtplib.SMTP(u["host"], int(u["port"]), timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(u["user"], u["haslo"])
            s.send_message(wiadomosc)
        _zapisz(klucz)
        print(f"  [alarm wyslany] {temat}", flush=True)
        return True
    except Exception as exc:
        print(f"  [alarm NIE POSZEDL: {type(exc).__name__}] {temat}", flush=True)
        return False


def sprawdz_sesje_i_ostrzez() -> None:
    """Pilnuje jedynej rzeczy, która zatrzymuje agenta bez żadnego błędu."""
    import browser

    dni = browser.dni_do_wygasniecia()
    if dni is None:
        wyslij("sesja-brak", "Brak sesji Substacka",
               "Agent nie ma pliku sesji i nie moze nic wystawic.")
    elif dni <= 0:
        wyslij("sesja-wygasla", "Sesja Substacka WYGASLA",
               "Agent nie wystawi juz nic, dopoki nie odnowisz sesji.\n"
               "Zaloguj sie w Chrome na swoim komputerze i wykonaj:\n"
               "  python agent-v2/browser.py sesja\n"
               "a potem skopiuj data/storage-state.json na serwer.")
    elif dni <= browser.OSTRZEGAJ_PONIZEJ_DNI:
        wyslij("sesja-konczy", f"Sesja Substacka wygasa za {dni} dni",
               f"Zostalo {dni} dni. Odnow ja, zanim agent zamilknie.\n"
               "Zaloguj sie w Chrome i wykonaj:\n"
               "  python agent-v2/browser.py sesja")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("skonfigurowany:", skonfigurowany())
        wyslij("test", "Test kanalu alarmowego",
               "Jesli to czytasz, alarmy dochodza.")
    else:
        sprawdz_sesje_i_ostrzez()
