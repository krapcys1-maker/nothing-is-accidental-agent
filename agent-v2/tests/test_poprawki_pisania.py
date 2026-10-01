# -*- coding: utf-8 -*-
"""Poprawki po przegladzie tresci 1.10.2026 (decyzja wlasciciela: „ok to popraw").

1. CELE KOMENTARZY: bez tekstow starszych niz 7 dni (notek — 48 h), bez cichych
   notek (0 reakcji i 0 komentarzy), zywe watki najpierw, najwyzej 3 komentarze
   + restacki u jednego autora w 7 dni. Zmierzone przed: 7 z 12 komentarzy pod
   artykulami pod tekstami starszymi niz 2 miesiace; pod notkami 8% z reakcja
   (NIA, wybierajaca zywe watki: 48%); jeden autor — 16 komentarzy w tydzien.
2. ZAPOWIEDZI ARTYKULU: poprzednie ida do pisarza, a powtorka powyzej progu
   pisze sie jeszcze raz (29.09 i 30.09 wyszly dwie prawie identyczne).
3. ZAKONCZENIA: gdy jedna z dwoch ostatnich notek skonczyla sie brakiem
   dowodu, kolejna dostaje polecenie, a gdy mimo to konczy sie brakiem — ten
   sam pisarz przenosi zastrzezenie przed koniec (zastrzezenie zostaje).
4. DLUGOSC WPROST w zwyklym oknie; nic nie tniemy (decyzja z 9.09).
5. ODPOWIEDZI w skali komentarza czytelnika.
6. POPRAWKA ZDANIA W ARTYKULE widzi zdanie przed nim i nie powtarza go.

BEZ PYTESTA, bez sieci, bez platnych wywolan — model to atrapa. Z korzenia repo.
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config  # noqa: E402

KATALOG = pathlib.Path(tempfile.mkdtemp())
_stary_katalog = config.uzyj_katalogu_danych(KATALOG)

import kanal   # noqa: E402
import llm     # noqa: E402
import stages  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


TERAZ = datetime.now(timezone.utc)


def temu(**k):
    return (TERAZ - timedelta(**k)).isoformat()


def dziennik(*wpisy):
    (KATALOG / "dziennik.jsonl").write_text(
        "\n".join(json.dumps(w, ensure_ascii=False) for w in wpisy) + "\n", encoding="utf-8")


# Dwie zapowiedzi MiMo z 29.09 17:43 i 30.09 11:42 — wyszly prawie slowo w slowo.
LINK = "https://nothingisaccidental.substack.com/p/british-workers-are-paying-for-ai"
ZAPOWIEDZ_1 = (
    "Nearly two thirds of UK working adults use generative AI for work, and 17% of those users "
    "pay for at least one tool themselves. Deloitte estimates that comes to £958 million a year "
    "in personal spending. The tempting conclusion is that employers have left staff to foot the "
    "bill. The survey makes that harder to claim: 34% of users have tools their employer pays "
    "for, 17% use in-house ones, and a third use something their workplace already covers. "
    "Personal and employer money sit side by side, not in place of each other. So the honest "
    "picture is mixed funding with a soft headline number attached. " + LINK)
ZAPOWIEDZ_2 = (
    "If you've ever quietly put a chatbot subscription on your own card to finish a work task "
    "faster, you're exactly the person a new Deloitte survey is trying to count. The headline says "
    "UK workers spend £958 million a year of their own money on AI tools for their jobs. The "
    "tempting reading: employers have abandoned staff to pay their way. The survey makes that "
    "harder to claim. Personal spending sits alongside employer spending, not in place of it. So "
    "the honest picture is mixed funding, with a headline number attached. " + LINK)
INNA = (
    "Around half of the workers in the survey never had any training on using these tools "
    "safely, and a third of Scottish staff could not say whether their employer even has an AI "
    "policy. When nobody says what is allowed, a quiet personal subscription is the easy "
    "default. " + LINK)

try:
    print("=== 1. CELE KOMENTARZY: WIEK, ZYCIE WATKU ===")
    sprawdz("artykul sprzed 8 dni odpada", kanal.za_stary_cel({"data": temu(days=8)}, False))
    sprawdz("artykul sprzed 6 dni zostaje", not kanal.za_stary_cel({"data": temu(days=6)}, False))
    sprawdz("notka sprzed 50 h odpada, sprzed 47 h zostaje",
            kanal.za_stary_cel({"data": temu(hours=50)}, True)
            and not kanal.za_stary_cel({"data": temu(hours=47)}, True))
    sprawdz("nieznana data liczy sie jako stara", kanal.za_stary_cel({"data": ""}, False))
    wieki_dni = [0.44, 298, 36, 328, 126, 533, 71, 37, 262, 7.3, 0.41, 242]   # 28.09-1.10
    zostalo = [w for w in wieki_dni if not kanal.za_stary_cel({"data": temu(days=w)}, False)]
    sprawdz("SEDNO: z 12 celow pod artykulami z 28.09-1.10 zostaja tylko 2 mlodsze niz doba",
            zostalo == [0.44, 0.41], zostalo)
    sprawdz("cichy watek: 0 reakcji i 0 komentarzy",
            kanal.cichy_watek({"reakcje": 0, "odpowiedzi": 0})
            and not kanal.cichy_watek({"reakcje": 1, "odpowiedzi": 0}))
    sprawdz("zywy watek: 2 komentarze albo 5 reakcji",
            kanal.zywy_watek({"odpowiedzi": 2}) and kanal.zywy_watek({"komentarze": 0, "reakcje": 5})
            and not kanal.zywy_watek({"komentarze": 1, "reakcje": 4}))
    cele = [{"id": "a", "reakcje": 3, "odpowiedzi": 0}, {"id": "b", "reakcje": 8, "odpowiedzi": 2},
            {"id": "c", "reakcje": 1, "odpowiedzi": 0}, {"id": "d", "reakcje": 6, "odpowiedzi": 0}]
    sprawdz("zywe najpierw, w grupach kolejnosc bez zmian",
            [x["id"] for x in kanal.zywe_najpierw(cele)] == ["b", "d", "a", "c"])

    print()
    print("=== 2. LIMIT U JEDNEGO AUTORA ===")
    dziennik(
        {"kiedy": temu(days=1), "rodzaj": "komentarz", "udane": True, "komu": "kaan",
         "publikacja": "Kaan Y"},
        {"kiedy": temu(days=2), "rodzaj": "komentarz", "udane": True, "komu": "kaan",
         "publikacja": "Kaan Y"},
        {"kiedy": temu(days=3), "rodzaj": "restack", "udane": True, "komu": "Kaan Y"},
        {"kiedy": temu(days=10), "rodzaj": "komentarz", "udane": True, "komu": "kaan",
         "publikacja": "Kaan Y"},
        {"kiedy": temu(days=1), "rodzaj": "komentarz", "udane": False, "komu": "kaan",
         "publikacja": "Kaan Y"},
        {"kiedy": temu(days=1), "rodzaj": "odpowiedz", "udane": True, "komu": "kaan"},
        {"kiedy": temu(days=1), "rodzaj": "komentarz", "udane": True, "komu": "ola",
         "publikacja": "Ola"})
    lim = kanal.LimitAutorow.z_dziennika()
    sprawdz("liczy 7 dni, udane komentarze i restacki; bez odpowiedzi, porazek i starych",
            lim.ile({"uchwyt": "kaan"}) == 2 and lim.ile({"autor": "Kaan Y"}) == 3, dict(lim.licznik))
    sprawdz("restack, ktory zna tylko nazwe, widzi tez komentarze u tej osoby",
            not lim.wolno({"autor": "kaan y"}))
    sprawdz("cel z uchwytem i nazwa: liczy sie wieksze z dwoch", not lim.wolno(
        {"uchwyt": "kaan", "pub": "Kaan Y"}))
    sprawdz("inny autor wolny", lim.wolno({"uchwyt": "ola", "pub": "Ola"}))
    lista = [{"uchwyt": "ola", "pub": "Ola", "id": i} for i in range(4)]
    sprawdz("w jednej liscie autor dostaje tylko to, co zostalo z limitu (3 - 1 = 2)",
            [x["id"] for x in lim.odsiej(lista)] == [0, 1] and lim.ile({"uchwyt": "ola"}) == 1)
    lim.zapisz({"uchwyt": "ola", "pub": "Ola"})
    sprawdz("udane wystawienie podnosi licznik", lim.ile({"uchwyt": "ola"}) == 2)
    notki = [
        {"id": 1, "uchwyt": "ola", "pub": "Ola", "reakcje": 9, "odpowiedzi": 3, "data": temu(hours=5)},
        {"id": 2, "uchwyt": "x1", "pub": "X1", "reakcje": 0, "odpowiedzi": 0, "data": temu(hours=5)},
        {"id": 3, "uchwyt": "x2", "pub": "X2", "reakcje": 2, "odpowiedzi": 0, "data": temu(hours=5)},
        {"id": 4, "uchwyt": "x3", "pub": "X3", "reakcje": 7, "odpowiedzi": 0, "data": temu(hours=60)},
        {"id": 5, "uchwyt": "x4", "pub": "X4", "reakcje": 6, "odpowiedzi": 1, "data": temu(hours=9)},
        {"id": 6, "uchwyt": "kaan", "pub": "Kaan Y", "reakcje": 9, "odpowiedzi": 4, "data": temu(hours=3)}]
    with contextlib.redirect_stdout(io.StringIO()):
        po = kanal.odsiej_cele(notki, lim, notki=True)
    sprawdz("sito notek: stara (60 h), cicha i ponad limit odpadaja, zywe najpierw",
            [x["id"] for x in po] == [1, 5, 3], [x["id"] for x in po])

    print()
    print("=== 3. ZAPOWIEDZI ARTYKULU ===")
    p12 = stages.powtorzenie(ZAPOWIEDZ_2, [ZAPOWIEDZ_1])
    sprawdz("dwie zapowiedzi z 29-30.09 sa ponad progiem (kalibracja na prawdziwej parze)",
            p12 > stages.PROG_POWTORZENIA_ZAPOWIEDZI, round(p12, 3))
    p13 = stages.powtorzenie(INNA, [ZAPOWIEDZ_1])
    sprawdz("KONTRDOWOD: zapowiedz z innej strony tego samego artykulu jest ponizej",
            p13 < stages.PROG_POWTORZENIA_ZAPOWIEDZI, round(p13, 3))
    dziennik({"kiedy": temu(hours=20), "rodzaj": "notka", "udane": True, "tekst": ZAPOWIEDZ_1},
             {"kiedy": temu(hours=10), "rodzaj": "notka", "udane": True, "tekst": "Inna notka."})
    sprawdz("poprzednie zapowiedzi znajduja sie po adresie artykulu",
            stages.zapowiedzi_artykulu(LINK) == [ZAPOWIEDZ_1]
            and stages.zapowiedzi_artykulu(LINK + "?r=1") == [ZAPOWIEDZ_1]
            and stages.zapowiedzi_artykulu(None) == [])

    PROMPTY = []
    ODPOWIEDZI = []

    def atrapa(etap, system, user, conn=None, run_id=None, **k):
        PROMPTY.append((etap, user))
        if etap == "reply":
            return json.dumps({"reply": "Fair point.", "kind": "answer"})
        if "## TAIL" in user:
            return json.dumps({"tail": ODPOWIEDZI.pop(0)})
        if etap == "note" and ODPOWIEDZI:
            return json.dumps({"note": ODPOWIEDZI.pop(0)})
        return json.dumps({"note": "x"})

    _oryg = {n: getattr(stages, n) for n in ("zweryfikuj", "ostatnie_otwarcia", "rozbior")}
    _oryg_call = llm.call
    try:
        llm.call = atrapa
        stages.zweryfikuj = lambda *a, **k: {"claims": [], "safe_to_post": True}
        stages.ostatnie_otwarcia = lambda rodzaj="notka", ile=8: []
        stages.rozbior = lambda *a, **k: {}
        ODPOWIEDZI[:] = [ZAPOWIEDZ_2, INNA]
        with contextlib.redirect_stdout(io.StringIO()):
            w = stages.note(None, 0, "ARTYKUL", {"claims": ["x"]}, link=LINK, etap="note")
        kand = (w.get("candidates") or [{}])[0]
        prompt_zap = [u for e, u in PROMPTY if e == "note"][0]
        sprawdz("pisarz zapowiedzi dostaje poprzednie zapowiedzi jako dane",
                "Promotion notes already published for this article" in prompt_zap
                and "tempting conclusion" in prompt_zap)
        sprawdz("SEDNO: powtorka pisze sie jeszcze raz i wychodzi wersja z innej strony",
                kand.get("note") == INNA and kand.get("powtorzenie_zapowiedzi", 1) < 0.15,
                (kand.get("note", "")[:60], kand.get("powtorzenie_zapowiedzi")))

        print()
        print("=== 4. ZAKONCZENIE BRAKIEM NAJWYZEJ CO TRZECIA NOTKA ===")
        dziennik(
            {"kiedy": temu(hours=30), "rodzaj": "notka", "udane": True,
             "tekst": "Clean ending.\n\nIt matters for your bill."},
            {"kiedy": temu(hours=10), "rodzaj": "notka", "udane": True,
             "tekst": "Elegant maths.\n\nThe post gives no speed number. I'd want the clock."})
        sprawdz("ostatnie zakonczenie brakiem znalezione",
                stages.zakonczenia_brakiem(2) == ["I'd want the clock."], stages.zakonczenia_brakiem(2))
        NOTKA = ("Shopify says it cut the cost of its AI features by 96%.\n\n"
                 "Every mistake the model makes gets written back into it daily. Nobody has "
                 "tested the quality claim from outside yet.")
        OGON = ("Nobody has tested the quality claim from outside yet, but the loop itself is "
                "the point: corrections your users make stop going nowhere.")
        PROMPTY.clear()
        ODPOWIEDZI[:] = [NOTKA, OGON]
        with contextlib.redirect_stdout(io.StringIO()):
            w = stages.note(None, 0, "CIEKAWOSTKA", {"fact": {"fact": "f"}}, etap="note")
        kand = (w.get("candidates") or [{}])[0]
        sprawdz("polecenie zakonczenia idzie do pisarza, gdy ostatnia notka skonczyla sie brakiem",
                "## Ending" in [u for e, u in PROMPTY if e == "note"][0])
        sprawdz("SEDNO: zastrzezenie przeniesione przed koniec, akapit i pierwsza czesc nietkniete",
                kand.get("zakonczenie_przeniesione") is True
                and kand.get("note", "").startswith("Shopify says it cut the cost of its AI features by 96%.\n\n")
                and kand["note"].endswith("stop going nowhere.")
                and "Nobody has tested" in kand["note"], kand.get("note"))
        sprawdz("ten sam pisarz przepisuje koniec (E11 porownuje pisarzy, nie naprawiacza)",
                [e for e, u in PROMPTY if "## TAIL" in u] == ["note"])

        def przenies(ogon, tekst=NOTKA):
            ODPOWIEDZI[:] = [ogon]
            with contextlib.redirect_stdout(io.StringIO()):
                return stages.przenies_zastrzezenie(None, 0, "note", tekst)

        sprawdz("odrzucone: nowy koniec znow konczy sie brakiem",
                przenies("The loop matters. Nobody has tested it yet.") == "")
        sprawdz("odrzucone: nowa liczba spoza notki",
                przenies("Nobody has tested the quality claim from outside yet; 40% savings follow.") == "")
        sprawdz("odrzucone: zastrzezenie zgubione",
                przenies("The loop is the point: corrections stop going nowhere.") == "")
        z_linkiem = NOTKA + "\n\n" + LINK
        nowa = przenies(OGON, z_linkiem)
        sprawdz("link na koncu zostaje na swoim miejscu", nowa.endswith("going nowhere.\n\n" + LINK), nowa[-90:])
        sprawdz("notka z E18 (pytanie) i seria nie dostaja polecenia zakonczenia",
                "_konce_brakiem = ([] if (wariant or {}).get(\"pytanie\") or seria" in pathlib.Path(
                    "agent-v2/stages.py").read_text(encoding="utf-8"))

        print()
        print("=== 5. DLUGOSC WPROST, ODPOWIEDZI W SKALI CZYTELNIKA ===")
        p = stages.z_dlugoscia("A\n" + stages.ZDANIE_O_DLUGOSCI % (60, 120) + "\nB", 60, 120)
        sprawdz("zwykle okno podane wprost zamiast „planning range”",
                stages.POLECENIE_DLUGOSCI % (60, 120, 120) in p and "planning range" not in p)
        sprawdz("widelki odpowiedzi: krotka reakcja / komentarz / wywod",
                [stages.widelki_odpowiedzi(n) for n in (2, 40, 120)] == [(8, 35), (20, 60), (30, 90)])
        PROMPTY.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            stages.reply_to(None, 0, {"text": "great point, love it", "author": "a", "under": "b"}, {})
        pr = [u for e, u in PROMPTY if e == "reply"]
        sprawdz("SEDNO: odpowiedz na 4 slowa dostaje sufit 35 slow",
                pr and "The reader wrote 4 words. Answer at the same scale: no more than 35 words." in pr[0],
                pr[0][-160:] if pr else "brak wywolania")

        print()
        print("=== 6. POPRAWKA ZDANIA W ARTYKULE NIE POWTARZA POPRZEDNIEGO ===")
        CIALO = ("Separately, one in six users (17%) say they pay for at least one tool themselves "
                 "for work purposes. That 17% is the base for the £958 million. Nothing else.")
        KARTA = {"confirmed_claims": [{"claim": "17% pay", "evidence": "17% pay; £958 million",
                                       "url": "https://x"}]}
        PROMPTY.clear()

        def naprawa(nowe):
            def f(etap, system, user, conn=None, run_id=None, **k):
                PROMPTY.append((etap, user))
                return json.dumps({"poprawki": [{"nr": 1, "nowe": nowe}]})
            return f

        llm.call = naprawa("Separately, one in six users (17%) say they pay for at least one tool "
                           "themselves for work purposes.")
        cialo, log = stages.popraw_bez_pokrycia(None, 0, CIALO, KARTA,
                                                [{"text": "That 17% is the base for the £958 million."}])
        sprawdz("naprawiacz widzi zdanie przed poprawianym",
                "sentence just before it" in PROMPTY[-1][1] and "one in six users" in PROMPTY[-1][1])
        sprawdz("SEDNO: poprawka powtarzajaca poprzednie zdanie -> zdanie bez pokrycia znika",
                "base for the" not in cialo and cialo.count("one in six users") == 1
                and any("powtarzala" in x for x in log), (cialo, log))
        llm.call = naprawa("Deloitte puts the resulting annual figure at £958 million.")
        cialo, log = stages.popraw_bez_pokrycia(None, 0, CIALO, KARTA,
                                                [{"text": "That 17% is the base for the £958 million."}])
        sprawdz("KONTRDOWOD: zwykla poprawka wchodzi w miejsce zdania",
                "Deloitte puts the resulting annual figure at £958 million." in cialo, cialo)
    finally:
        llm.call = _oryg_call
        for n, f in _oryg.items():
            setattr(stages, n, f)

    print()
    print("=== 7. PODLACZENIE W PRZEBIEGU ===")
    RUN = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
    sprawdz("komentarze pod artykulami: sito przed ocena celow i w kolejnych rundach",
            "unikalne = _sito_celow(kanal, unikalne, limit_autorow, notki=False)" in RUN
            and "dobrane = _sito_celow(kanal, dobrane, limit_autorow, notki=False)" in RUN)
    sprawdz("dyskusje: sito notek przed ocena i zywe najpierw po niej",
            "notki = _sito_celow(kanal, notki, limit_autorow, notki=True)" in RUN
            and "cele = _zywe_najpierw(kanal, limit_autorow.odsiej(cele))" in RUN)
    sprawdz("restacki dostaja ten sam limit", "limit_autorow=limit_autorow)" in RUN)
    sprawdz("udany komentarz podnosi licznik autora (oba bloki)", RUN.count("limit_autorow.zapisz(cel)") == 2)
finally:
    config.przywroc_katalog_danych(_stary_katalog)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
