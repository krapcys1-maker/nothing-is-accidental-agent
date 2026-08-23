"""Pin korpusu stylu dotyczy TRESCI, nie ustawienia gita na danej maszynie.

Korpus stylu to jedyna rzecz odrozniajaca to konto od tysiaca innych, wiec
loader ma odmowic, gdyby ktos po cichu podmienil glos. I odmawia — tyle ze
odmawial takze wtedy, gdy tresc byla identyczna, a git zmaterializowal plik
z CRLF zamiast LF.

KOSZTOWALO TO OPLACONY RESEARCH. Przebieg 13 (18 sierpnia) stoi w bazie
produkcyjnej jako FAILED na etapie `write` z powodem „korpus stylu nie zgadza
sie z przypietym hashem". Research zaplacony, artykulu nie ma.

Plik przeczyl przy tym sam sobie: `split_paragraphs` normalizowal konce linii
z komentarzem „styl konca linii nie zmienia numeracji", a dwa wiersze wyzej
skrot liczyl sie z surowych bajtow, wiec konce linii rozstrzygaly o tym, czy
pisarz w ogole ruszy.

KONTRDOWOD jest tu najwazniejszy: sprawdzamy nie tylko, ze nowy sposob
przepuszcza CRLF, ale i ze STARY sposob by go ODRZUCIL. Bez tego test
przechodzilby tak samo przed naprawa.
"""
import hashlib
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import style    # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


TEKST = b"Pierwszy akapit korpusu.\n\nDrugi akapit korpusu.\n"
Z_CRLF = TEKST.replace(b"\n", b"\r\n")

print("=== 1. TEN SAM TEKST, INNY CHECKOUT, TEN SAM SKROT ===")
kan = style.bajty_kanoniczne
sprawdz("CRLF i LF daja te same bajty kanoniczne", kan(Z_CRLF) == kan(TEKST))
sprawdz("samo CR tez jest normalizowane", kan(b"a\rb") == kan(b"a\nb"))
sprawdz("i skroty sie zgadzaja",
        hashlib.sha256(kan(Z_CRLF)).hexdigest()
        == hashlib.sha256(kan(TEKST)).hexdigest())

# KONTRDOWOD: stary sposob (surowe bajty) MUSI dawac inny wynik, inaczej
# naprawa nie byla potrzebna, a ten test niczego nie dowodzi.
sprawdz("stary sposob dawal ROZNE skroty — dlatego to bylo zepsute",
        hashlib.sha256(Z_CRLF).hexdigest() != hashlib.sha256(TEKST).hexdigest())

print()
print("=== 2. STRAZ NADAL GRYZIE ===")
# Normalizujemy WYLACZNIE konce linii. Kazda inna roznica ma zatrzymac pisarza.
sprawdz("podmienione slowo daje inny skrot",
        kan(TEKST) != kan(TEKST.replace(b"Drugi", b"Trzeci")))
sprawdz("dopisana spacja tez", kan(TEKST) != kan(TEKST + b" "))
sprawdz("usuniety akapit tez",
        kan(TEKST) != kan(b"Pierwszy akapit korpusu.\n"))

print()
print("=== 3. PRAWDZIWY KORPUS PRZECHODZI NA TYM DYSKU ===")
p = config.STYLE_CORPUS
sprawdz("korpus istnieje", p.exists(), p)
if p.exists():
    surowe = p.read_bytes()
    ile_crlf = surowe.count(b"\r\n")
    print("    sekwencji CRLF w pliku na tym dysku: %d" % ile_crlf)
    sprawdz("skrot kanoniczny zgadza sie z przypietym w configu",
            hashlib.sha256(kan(surowe)).hexdigest() == config.STYLE_CORPUS_SHA256,
            hashlib.sha256(kan(surowe)).hexdigest()[:16])
    if ile_crlf:
        # Na maszynie z CRLF stary sposob MUSI oblac — to jest dowod, ze ta
        # naprawa nie jest kosmetyczna. Na Linuksie ten warunek nie zachodzi
        # i wtedy po prostu go nie sprawdzamy.
        sprawdz("a stary sposob oblalby TEN plik",
                hashlib.sha256(surowe).hexdigest() != config.STYLE_CORPUS_SHA256)
    else:
        print("    (plik ma LF — stary sposob te by przeszedl; roznica widoczna")
        print("     tylko na checkoucie z CRLF, np. na Windowsie wlasciciela)")

print()
print("=== 4. LOADER NAPRAWDE WCZYTUJE ===")
try:
    fragmenty = style.load_examples()
    sprawdz("load_examples() nie rzuca", True)
    sprawdz("i oddaje fragmenty", len(fragmenty) > 0, len(fragmenty))
    sprawdz("kazdy ma tekst",
            all(str(f.get("text", "")).strip() for f in fragmenty))
except Exception as exc:
    sprawdz("load_examples() nie rzuca", False, "%s: %s" % (type(exc).__name__, exc))

print()
print("=== 5. JEDNO MIEJSCE PRAWDY ===")
zrodlo = pathlib.Path("agent-v2/style.py").read_text(encoding="utf-8")
# Normalizacja ma byc w JEDNEJ funkcji, nie przepisana dwa razy — inaczej
# rozjedzie sie przy nastepnej zmianie.
sprawdz("split_paragraphs korzysta z tej samej funkcji",
        "bajty_kanoniczne(raw).decode" in zrodlo)
sprawdz("i skrot tez", "hashlib.sha256(bajty_kanoniczne(raw))" in zrodlo)
sprawdz("nie ma juz hashowania surowych bajtow",
        "hashlib.sha256(raw).hexdigest()" not in zrodlo)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
