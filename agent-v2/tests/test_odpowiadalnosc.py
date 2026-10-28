# -*- coding: utf-8 -*-
"""Odpowiadalnosc autora wpisu (28.10.2026, `odpowiadalnosc.py`).

PO CO TEN TEST. Analiza komentarzy (965 watkow) pokazala, ze autor, ktory nikomu nie odpisuje, odpowiada
nam w ok. 3% przypadkow, a odpisujacy wiekszosci — w ok. 50%. Modul ocenia to z JEGO wczesniejszych
watkow i odklada takie cele na koniec kolejki. Test pilnuje: co sie liczy jako 'komentarz od innych' i
'odpowiedz autora' (bez nas, kont siostrzanych i samego autora; tylko bezposrednia odpowiedz), progow
'niska' (<= 5%) i 'nieznana' (za malo komentarzy), cache (TTL, blad nie jest powtarzany), limitu zapytan,
tego, ze awaria sieci NIGDY nie rzuca ani nie karze celu, oraz ze kara to 'na koniec kolejki', a nie wyciecie
(probka bez kary zostaje na miejscu).

BEZ PYTESTA i bez sieci (pobieranie podstawiane). Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_odpowiadalnosc.py
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import odpowiadalnosc as O   # noqa: E402

KAT = pathlib.Path(tempfile.mkdtemp())
zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1500]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        w = fn(*a, **k)
    return w, log.getvalue()


AUTOR = 111
OBCY = [201, 202, 203, 204, 205]


def kom(uid, dzieci=(), **extra):
    return {"id": uid * 10, "user_id": uid, "handle": "u%d" % uid, "children": list(dzieci), **extra}


print("=== 1. LICZENIE W ARTYKULE ===")
tr = [kom(201, [kom(AUTOR)]), kom(202), kom(203, [kom(204)]), kom(205, [kom(901, [kom(AUTOR)])])]
sprawdz("odpowiedz autora liczy sie tylko BEZPOSREDNIA (wnuk-autor nie)", O.policz_artykul(tr, {AUTOR}) == (4, 1), O.policz_artykul(tr, {AUTOR}))
sprawdz("komentarz autora wpisu nie jest 'od innych' i nie liczy sie do mianownika",
        O.policz_artykul(tr + [kom(AUTOR)], {AUTOR}) == (4, 1))
sprawdz("konto siostrzane (NIA, uid z config) nie liczy sie do mianownika",
        O.policz_artykul([kom(547272980, [kom(AUTOR)]), kom(201)], {AUTOR}) == (1, 0), config.KONTA_SIOSTRZANE)
sprawdz("nasz uchwyt i uchwyt siostry nie licza sie do mianownika",
        O.policz_artykul([kom(300, handle="nothingisaccidental"), kom(301, handle="NIA1503032"), kom(201)], {AUTOR}) == (1, 0))
sprawdz("usuniety komentarz nie liczy sie, usunieta odpowiedz autora tez nie",
        O.policz_artykul([kom(201, [kom(AUTOR, deleted=True)]), kom(202, deleted=True)], {AUTOR}) == (1, 0))
sprawdz("metadata.is_author w odpowiedzi liczy sie jako autor, nawet bez zgodnego uid",
        O.policz_artykul([kom(201, [kom(777, metadata={"is_author": True})])], {AUTOR}) == (1, 1))
sprawdz("komentarz pierwszego poziomu z metadata.is_author (autor pod innym uid) nie jest od innych",
        O.policz_artykul([kom(777, metadata={"is_author": True}), kom(201)], {AUTOR}) == (1, 0))
sprawdz("smieci na wejsciu nie wywracaja liczenia", O.policz_artykul([None, "x", {}, {"children": None, "user_id": 5}], {AUTOR}) == (1, 0),
        O.policz_artykul([None, "x", {}, {"children": None, "user_id": 5}], {AUTOR}))

print("=== 2. LICZENIE W NOTCE (odpowiedzi opakowane {type, comment}) ===")
wat = {"rootComment": {"user_id": AUTOR},
       "commentBranches": [
           {"comment": kom(201), "descendantComments": [{"type": "comment", "comment": kom(AUTOR)}]},
           {"comment": kom(202), "descendantComments": []},
           {"comment": kom(AUTOR), "descendantComments": []},
           {"comment": kom(203), "descendantComments": [{"type": "comment", "comment": kom(204)}]}]}
sprawdz("notka: galezie od innych = 3, z odpowiedzia autora = 1", O.policz_notke(wat) == (3, 1), O.policz_notke(wat))
sprawdz("notka bez korzenia (brak uid autora) → (0, 0), nie wyjatek", O.policz_notke({"commentBranches": [{"comment": kom(201)}]}) == (0, 0))
sprawdz("notka: galaz z odpowiedzia w ksztalcie bez opakowania tez dziala",
        O.policz_notke({"rootComment": {"user_id": AUTOR},
                        "commentBranches": [{"comment": kom(201), "descendantComments": [kom(AUTOR)]}]}) == (1, 1))

print("=== 3. PROGI ===")
sprawdz("klasa: 5% to jeszcze 'niska' (<=), 5,1% juz 'ok'", O._klasa(0.05) == "niska" and O._klasa(0.051) == "ok" and O._klasa(0.0) == "niska")
sprawdz("klasa: brak wyniku = nieznana", O._klasa(None) == "nieznana")
sprawdz("za malo komentarzy → brak wyniku; dokladnie minimum → jest",
        O._wynik(3, 0, 4) is None and O._wynik(4, 0, 4) == 0.0 and O._wynik(4, 2, 4) == 0.5)

print("=== 4. OCENA: ARTYKULY (podstawione pobieranie) ===")
ZAPYTANIA = []
SRODOWISKO = {}


def pobierz(url):
    ZAPYTANIA.append(url)
    return SRODOWISKO.get(url, SRODOWISKO.get("*"))


def archiwum(host, posty):
    SRODOWISKO["https://%s/api/v1/archive?sort=new&search=&offset=0&limit=8" % host] = posty


def komentarze(host, pid, komy):
    SRODOWISKO["https://%s/api/v1/post/%s/comments?token=&all_comments=true&sort=best_first" % (host, pid)] = {"comments": komy}


TERAZ = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
swiezo = (TERAZ - timedelta(days=5)).isoformat()


def post(pid, slug, ile=6, data=None):
    return {"id": pid, "slug": slug, "comment_count": ile, "post_date": data or swiezo,
            "publishedBylines": [{"id": AUTOR}]}


# host 'milczy': 5 komentarzy, zero odpowiedzi autora → niska
archiwum("milczy.example", [post(1, "a"), post(2, "b")])
komentarze("milczy.example", 1, [kom(u) for u in OBCY[:3]])
komentarze("milczy.example", 2, [kom(u) for u in OBCY[:3]])
# host 'gada': 4 komentarze, 3 z odpowiedzia → ok
archiwum("gada.example", [post(3, "c")])
komentarze("gada.example", 3, [kom(201, [kom(AUTOR)]), kom(202, [kom(AUTOR)]), kom(203, [kom(AUTOR)]), kom(204)])
# host 'pusty': za malo komentarzy → nieznana
archiwum("pusty.example", [post(4, "d", ile=2)])
komentarze("pusty.example", 4, [kom(u) for u in OBCY])                       # gdyby ktos go czytal, bylaby to „niska"
# host 'wielu': cztery kwalifikujace sie wpisy, czyta sie tylko ostatnie trzy (ODPOWIADALNOSC_POSTY)
archiwum("wielu.example", [post(11, "p1"), post(12, "p2"), post(13, "p3"), post(14, "p4")])
for _i in (11, 12, 13):
    komentarze("wielu.example", _i, [kom(u) for u in OBCY[:3]])
komentarze("wielu.example", 14, [kom(u, [kom(AUTOR)]) for u in OBCY])      # czwarty wpis: wszyscy z odpowiedzia
# wpis, ktory wlasnie rozwazamy, nie liczy sie do oceny autora
archiwum("wyklucz.example", [post(5, "ten-wpis"), post(6, "inny")])
komentarze("wyklucz.example", 5, [kom(201, [kom(AUTOR)]) for _ in range(5)])
komentarze("wyklucz.example", 6, [kom(u) for u in OBCY[:4]])

plik = KAT / "odp1.json"
cele = [{"url": "https://milczy.example/p/x", "id": "x"}, {"url": "https://gada.example/p/y"},
        {"url": "https://pusty.example/p/z"}, {"url": "https://wyklucz.example/p/ten-wpis"},
        {"url": "https://wielu.example/p/q"}]
wynik, _ = cicho(O.ocen, cele, notki=False, teraz=TERAZ, plik=plik, pobierz=pobierz)
kl = {c["url"].split("/")[2]: c["_odp_autora"] for c in wynik}
sprawdz("milczacy autor: wynik 0,0 i klasa niska", kl["milczy.example"]["wynik"] == 0.0 and kl["milczy.example"]["klasa"] == "niska", kl["milczy.example"])
sprawdz("odpisujacy autor: 3/4 i klasa ok", kl["gada.example"]["wynik"] == 0.75 and kl["gada.example"]["klasa"] == "ok", kl["gada.example"])
sprawdz("za malo komentarzy: nieznana, bez kary", kl["pusty.example"]["klasa"] == "nieznana" and kl["pusty.example"]["wynik"] is None)
sprawdz("wpis z mniej niz 4 komentarzami wedlug archiwum nie jest czytany (nawet gdyby mial ich wiecej)", kl["pusty.example"]["n"] == 0, kl["pusty.example"])
sprawdz("czyta sie najwyzej ODPOWIADALNOSC_POSTY (3) ostatnich wpisow: czwarty, z samymi odpowiedziami, nie zmienia oceny",
        kl["wielu.example"]["n"] == 9 and kl["wielu.example"]["wynik"] == 0.0 and kl["wielu.example"]["klasa"] == "niska", kl["wielu.example"])
sprawdz("rozwazany wpis jest pominiety w ocenie autora (liczy sie tylko drugi, bez odpowiedzi)",
        kl["wyklucz.example"]["wynik"] == 0.0 and kl["wyklucz.example"]["n"] == 4, kl["wyklucz.example"])
sprawdz("ocen() nie zmienia wejsciowych slownikow", all("_odp_autora" not in c for c in cele))
sprawdz("gdy poprzednie wpisy wystarczaja, watek rozwazanego wpisu NIE jest czytany",
        not any("/api/v1/posts/" in u and "gada.example" in u for u in ZAPYTANIA), [u for u in ZAPYTANIA if "gada.example" in u])
# mala publikacja: w archiwum tylko rozwazany wpis → ocena z jego wlasnego watku (zeby nie zostawac „nieznana")
for _host, _id, _odp in (("maly.example", 21, False), ("malyok.example", 22, True)):
    archiwum(_host, [post(_id, "ten")])
    SRODOWISKO["https://%s/api/v1/posts/ten" % _host] = {"id": _id, "publishedBylines": [{"id": AUTOR}]}
    komentarze(_host, _id, [kom(u, [kom(AUTOR)] if _odp else []) for u in OBCY])
wynik_m, _ = cicho(O.ocen, [{"url": "https://maly.example/p/ten"}, {"url": "https://malyok.example/p/ten"},
                            {"url": "https://nieistnieje.example/p/ten"}], notki=False, teraz=TERAZ, plik=KAT / "odp_maly.json", pobierz=pobierz)
sprawdz("mala publikacja bez poprzednich wpisow: ocena z watku rozwazanego wpisu (milczacy = niska, odpisujacy = ok)",
        [c["_odp_autora"]["klasa"] for c in wynik_m[:2]] == ["niska", "ok"] and wynik_m[0]["_odp_autora"]["n"] == 5, [c["_odp_autora"] for c in wynik_m])
sprawdz("a gdy i wpisu nie da sie pobrac — nieznana, bez wyjatku", wynik_m[2]["_odp_autora"]["klasa"] == "nieznana")
n1 = len(ZAPYTANIA)
wynik2, _ = cicho(O.ocen, cele, notki=False, teraz=TERAZ + timedelta(days=1), plik=plik, pobierz=pobierz)
sprawdz("drugie wywolanie w TTL nie pyta sieci (cache z dysku)", len(ZAPYTANIA) == n1, (n1, len(ZAPYTANIA)))
sprawdz("a wynik jest ten sam", [c["_odp_autora"] for c in wynik2] == [c["_odp_autora"] for c in wynik])
wynik3, _ = cicho(O.ocen, cele[:1], notki=False, teraz=TERAZ + timedelta(days=config.ODPOWIADALNOSC_TTL_DNI + 1), plik=plik, pobierz=pobierz)
sprawdz("po TTL pyta ponownie", len(ZAPYTANIA) > n1, (n1, len(ZAPYTANIA)))

print("=== 5. AWARIE I LIMITY ===")
plik2 = KAT / "odp2.json"
ZAPYTANIA.clear()
SRODOWISKO.clear()
wynik, _ = cicho(O.ocen, [{"url": "https://zepsuty.example/p/a"}], notki=False, teraz=TERAZ, plik=plik2, pobierz=pobierz)
sprawdz("brak odpowiedzi sieci → nieznana, cel NIE jest karany",
        wynik[0]["_odp_autora"]["klasa"] == "nieznana" and wynik[0]["_odp_autora"]["wynik"] is None, wynik[0])
n = len(ZAPYTANIA)
cicho(O.ocen, [{"url": "https://zepsuty.example/p/b"}], notki=False, teraz=TERAZ + timedelta(hours=2), plik=plik2, pobierz=pobierz)
sprawdz("nieudane zapytanie nie jest powtarzane w ciagu doby", len(ZAPYTANIA) == n, (n, len(ZAPYTANIA)))
cicho(O.ocen, [{"url": "https://zepsuty.example/p/b"}], notki=False, teraz=TERAZ + timedelta(hours=config.ODPOWIADALNOSC_BLAD_TTL_H + 1), plik=plik2, pobierz=pobierz)
sprawdz("po dobie probuje ponownie", len(ZAPYTANIA) > n)


def rzuca(url):
    raise RuntimeError("siec padla")


wynik, _ = cicho(O.ocen, [{"url": "https://rzuca.example/p/a"}], notki=False, teraz=TERAZ, plik=KAT / "odp3.json", pobierz=rzuca)
sprawdz("wyjatek z pobierania nie wychodzi z ocen()", wynik[0]["_odp_autora"]["klasa"] == "nieznana", wynik)
plik_zly = KAT / "odp4.json"
plik_zly.write_text("{nie json", encoding="utf-8")
wynik, _ = cicho(O.ocen, [{"url": "https://gada.example/p/a"}], notki=False, teraz=TERAZ, plik=plik_zly, pobierz=pobierz)
sprawdz("uszkodzony plik cache jest ignorowany i nadpisywany", wynik[0]["_odp_autora"]["klasa"] == "nieznana" and json.loads(plik_zly.read_text("utf-8")) is not None)
stare = config.ODPOWIADALNOSC_MAKS_ZAPYTAN
config.ODPOWIADALNOSC_MAKS_ZAPYTAN = 2
SRODOWISKO.clear()
for _i in range(1, 6):
    archiwum("h%d.example" % _i, [post(_i, "a")])
    komentarze("h%d.example" % _i, _i, [kom(u) for u in OBCY[:4]])
wynik, _ = cicho(O.ocen, [{"url": "https://h%d.example/p/q" % i} for i in range(1, 6)], notki=False, teraz=TERAZ, plik=KAT / "odp5.json", pobierz=pobierz)
config.ODPOWIADALNOSC_MAKS_ZAPYTAN = stare
sprawdz("limit nowych sprawdzen: dokladnie 2 oceny, reszta nieznana", [c["_odp_autora"]["klasa"] for c in wynik] == ["niska"] * 2 + ["nieznana"] * 3,
        [c["_odp_autora"]["klasa"] for c in wynik])
sprawdz("cel bez adresu i bez numeru nie wywraca oceny", cicho(O.ocen, [{}], notki=False, teraz=TERAZ, plik=KAT / "odp6.json", pobierz=pobierz)[0][0]["_odp_autora"]["klasa"] == "nieznana")

print("=== 6. OCENA: NOTKI ===")
SRODOWISKO.clear()
SRODOWISKO["https://substack.com/api/v1/reader/comment/777/replies?comment_id=777"] = {
    "rootComment": {"user_id": AUTOR},
    "commentBranches": [{"comment": kom(201), "descendantComments": []}, {"comment": kom(202), "descendantComments": []}]}
SRODOWISKO["https://substack.com/api/v1/reader/comment/888/replies?comment_id=888"] = {
    "rootComment": {"user_id": AUTOR},
    "commentBranches": [{"comment": kom(201), "descendantComments": [{"type": "comment", "comment": kom(AUTOR)}]}]}
wynik, _ = cicho(O.ocen, [{"id": 777}, {"id": 888}, {"id": 999}], notki=True, teraz=TERAZ, plik=KAT / "odp7.json", pobierz=pobierz)
kl = [c["_odp_autora"]["klasa"] for c in wynik]
sprawdz("notka: 2 komentarze bez odpowiedzi autora = niska; 1 komentarz = nieznana (min. 2); brak watku = nieznana",
        kl == ["niska", "nieznana", "nieznana"], kl)

print("=== 7. KOLEJNOSC ===")
config.ODPOWIADALNOSC_PROBA_BEZ_FILTRA = 0.25
urls = ["https://host%d.example/p/a" % i for i in range(400)]
bez = sum(1 for u in urls if O.bez_kary({"url": u}))
sprawdz("probka bez kary to ok. 25% (deterministyczna, po adresie)", 70 <= bez <= 130 and O.bez_kary({"url": urls[3]}) == O.bez_kary({"url": urls[3]}), bez)
config.ODPOWIADALNOSC_PROBA_BEZ_FILTRA = 0.0
SRODOWISKO.clear()
archiwum("niska.example", [post(1, "a")]); komentarze("niska.example", 1, [kom(u) for u in OBCY[:4]])
archiwum("dobra.example", [post(2, "a")]); komentarze("dobra.example", 2, [kom(201, [kom(AUTOR)]), kom(202, [kom(AUTOR)]), kom(203), kom(204)])
cele = [{"url": "https://niska.example/p/1", "n": 1}, {"url": "https://dobra.example/p/1", "n": 2},
        {"url": "https://nieznana.example/p/1", "n": 3}, {"url": "https://niska.example/p/2", "n": 4}]
wynik, log = cicho(O.wedlug_odpowiadalnosci, cele, notki=False, teraz=TERAZ, plik=KAT / "odp8.json", pobierz=pobierz)
sprawdz("niska odpowiadalnosc → na koniec; reszta w dotychczasowej kolejnosci (stabilnie)", [c["n"] for c in wynik] == [2, 3, 1, 4], [c["n"] for c in wynik])
sprawdz("nikt nie jest wyciety", len(wynik) == len(cele))
sprawdz("log mowi, ile znanych i ile niskich", "znana u 3 z 4" in log and "niska u 2" in log, log)
config.ODPOWIADALNOSC_PROBA_BEZ_FILTRA = 1.0
wynik, _ = cicho(O.wedlug_odpowiadalnosci, cele, notki=False, teraz=TERAZ, plik=KAT / "odp8.json", pobierz=pobierz)
sprawdz("przy 100% probie bez kary kolejnosc sie nie zmienia", [c["n"] for c in wynik] == [1, 2, 3, 4], [c["n"] for c in wynik])
config.ODPOWIADALNOSC_PROBA_BEZ_FILTRA = 0.0
config.ODPOWIADALNOSC_WLACZONA = False
sprawdz("wylacznik oddaje ta sama liste bez zapytan", O.wedlug_odpowiadalnosci(cele, notki=False, pobierz=rzuca) is cele)
config.ODPOWIADALNOSC_WLACZONA = True
sprawdz("pusta lista", O.wedlug_odpowiadalnosci([], notki=False) == [])

print("=== 8. POLA DO DZIENNIKA ===")
sprawdz("bez oceny — zadnych pol (stare wpisy, atrapy)", O.pola_dziennika({"url": "x"}) == {})
sprawdz("nieznana: tylko klasa", O.pola_dziennika({"_odp_autora": {"wynik": None, "n": 0, "klasa": "nieznana"}}) == {"autor_odp_klasa": "nieznana"})
sprawdz("znana: klasa, wynik i liczba komentarzy",
        O.pola_dziennika({"_odp_autora": {"wynik": 0.5, "n": 6, "klasa": "ok"}}) == {"autor_odp_klasa": "ok", "autor_odp": 0.5, "autor_odp_n": 6})
sprawdz("wynik 0,0 tez sie zapisuje (zero to informacja)",
        O.pola_dziennika({"_odp_autora": {"wynik": 0.0, "n": 5, "klasa": "niska"}}).get("autor_odp") == 0.0)

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
