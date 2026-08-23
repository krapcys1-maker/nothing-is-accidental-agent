"""Pliki z cudzymi danymi maja byc czytelne TYLKO dla wlasciciela.

Dwie rzeczy na tej maszynie zawieraja dane, ktore nie sa nasze:

- `storage-state-serwer.json` — zalogowana sesja Substacka. Kto ja przeczyta,
  jest nami. Lezala z prawami 0644, czyli czytelna dla kazdego konta na
  serwerze.
- `data/kopie/subskrybenci-*.csv` — adresy e-mail czytelnikow. Pierwsza kopia
  wyladowala z 0664 z tego samego powodu: domyslna umaska, nikt nie ustawil
  inaczej.

Roznica miedzy jednorazowym `chmod` a poprawka w kodzie jest cala pointa:
recznie znaczy „przy pierwszej kopii", a kopii ma byc trzydziesci. Prawo ma
byc ustawiane przy KAZDYM zapisie.

Test jest dwuczesciowy, bo Windows nie ma praw POSIX: statyczna czesc chodzi
wszedzie, funkcjonalna tylko tam, gdzie te prawa cokolwiek znacza.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


kopia_src = pathlib.Path("agent-v2/kopia_subskrybentow.py").read_text(encoding="utf-8")

print("=== 1. KOPIA LISTY ZAMYKA SIE SAMA ===")
sprawdz("skrypt ustawia prawa po zapisie", "chmod(0o600)" in kopia_src)
sprawdz("i robi to przy kazdym zapisie, nie raz",
        kopia_src.find("chmod(0o600)") > kopia_src.find("cel.write_text"),
        "chmod musi stac PO zapisie pliku")
# KONTRDOWOD: brak praw POSIX nie moze kosztowac nas kopii. Windows ma to
# przemilczec, a nie wywalic sie i zostawic liste bez archiwum.
sprawdz("brak praw POSIX nie przerywa archiwizacji", "except OSError" in kopia_src)
sprawdz("i katalog jest poza gitem",
        "agent-v2/data/" in pathlib.Path(".gitignore").read_text(encoding="utf-8"))
sprawdz("skrypt sam o tym przypomina",
        "cudze adresy e-mail" in kopia_src)

print()
print("=== 2. NA POSIX SPRAWDZAMY TO NAPRAWDE ===")
if os.name == "nt":
    print("  (pominiete: Windows nie ma praw POSIX — te same asercje chodza")
    print("   na serwerze, czyli tam, gdzie pliki naprawde leza)")
else:
    import config
    import kopia_subskrybentow as kop

    with tempfile.TemporaryDirectory() as tmp:
        stary = config.DATA_DIR
        config.DATA_DIR = pathlib.Path(tmp)
        kop.KATALOG = config.DATA_DIR / "kopie"
        kop.PRZYCHODZACE = kop.KATALOG / "przychodzace"
        kop.PRZYCHODZACE.mkdir(parents=True)
        (kop.PRZYCHODZACE / "eksport.csv").write_text(
            "Email,Name\nktos@example.com,Ktos\n", encoding="utf-8")
        kop.main()
        zapisane = sorted(kop.KATALOG.glob("subskrybenci-*.csv"))
        sprawdz("kopia powstala", len(zapisane) == 1, zapisane)
        if zapisane:
            prawa = zapisane[0].stat().st_mode & 0o777
            sprawdz("i ma prawa 0600", prawa == 0o600, oct(prawa))
            # Plik zrodlowy ma zniknac — inaczej cudze adresy leza w dwoch
            # miejscach, a to drugie nikogo nie pilnuje.
            sprawdz("plik przychodzacy zostal usuniety",
                    not list(kop.PRZYCHODZACE.glob("*.csv")))
        config.DATA_DIR = stary

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
