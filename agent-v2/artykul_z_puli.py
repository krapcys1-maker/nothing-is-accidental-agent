"""Artykul bierze temat z tej samej puli, co notki.

DLACZEGO TO POWSTALO. Tor artykulu mial wlasnego skauta z wlasna teoria:
temat zasluguje na tysiac slow, gdy ma co najmniej dwa udokumentowane
PRECEDENSY — przeszle katastrofy, po ktorych zmieniono przepis („regulamin to
blizna"). Ta teoria byla dobra dla poprzedniej publikacji, o zwyklych rzeczach
i przepisach za nimi: schodach przeciwpozarowych, chlodzeniu jajek, swiatlach.

Pod AI daje monokulture. Jedyne tematy AI z dwiema spisanymi katastrofami to
zasilki, auta autonomiczne i gielda — wiec trzy artykuly z rzedu wyszly o
zautomatyzowanej biurokracji, a nie o AI.

Tymczasem pula ciekawostek — ta sama, z ktorej biora sie notki — produkuje
dokladnie te tematy, ktorych wlasciciel chce. Zmierzone na przebiegu 25 sierpnia
2026, wszystkie z zrodlem i data:

    Kenia projektuje prawo wiazace OpenAI, Mete i Anthropic swoimi standardami
      pracy; anotatorzy zarabiaja 1,46-3,74 USD/h
    ludzie oceniajacy odpowiedzi systematycznie nagradzaja przytakiwanie,
      i stad sluzalczosc modeli
    NATO kupilo Palantir Maven; w operacji 2026 produkowal cel co 86 sekund
    Stanford: zatrudnienie 22-25-latkow w zawodach wystawionych na AI o 19%
      ponizej trendu
    audyt Cambridge: tylko 4 z 30 agentow publikuje karte bezpieczenstwa
    model, gdy rozpozna, ze jest testowany, odpowiada tak, by chronic wlasne
      preferencje

Wlasciciel zatwierdzil ten rodzaj wprost. Wiec artykul nie wymysla tematu od
zera i nie sprawdza, czy ma dwie katastrofy — bierze SWIEZY fakt z tej puli
i drazy go dalej.

Reszta lancucha zostaje bez zmian: dyskoveria, pobieranie, klasyfikacja,
synteza, bramka warto_pisac, pisarz, recenzent, forma, zapis, grafika.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config      # noqa: E402
import db          # noqa: E402
import llm         # noqa: E402
import stages      # noqa: E402

SYSTEM = (
    "You turn a documented fact into the question an article will answer. "
    "Return only valid JSON."
)

PYTANIE = """Today is {dzis}.

Here is a documented fact this publication has verified, with its source:

  FACT: {fact}
  WHAT PEOPLE ASSUME INSTEAD: {mit}
  WHAT IS ACTUALLY TRUE: {prawda}
  WHO DECIDED IT, AND WHEN: {decyzja}
  WHAT IT MEANS FOR THE READER: {skutek}
  SOURCE: {url} (published {data})

Turn it into an article brief. The article is about **artificial intelligence**
and runs about a thousand words, so the question has to be worth that length:
not "what happened" — that is the note — but **why it happens, who arranged it
that way, and what else runs on the same arrangement.**

The reader has no stake in the specific system. Before writing the question,
answer privately: what does someone who will never touch this thing now know?

Return only valid JSON:

{{"title": "<the working title, a noun phrase, no colon>",
  "question": "<the one question the article answers, ending in a question mark>",
  "broken_belief": "<one plain sentence beginning 'Everyone assumes', or empty if the fact breaks no belief>",
  "why_they_believe_it": "<one sentence on where that belief comes from, or empty>",
  "the_moment": "<the concrete moment a reader can picture, one sentence>",
  "search_terms": ["<3-6 phrases a researcher should search to document this properly>"],
  "sub_questions": ["<4-6 questions THE ARTICLE MUST ANSWER. Not search phrases — questions, each ending in a question mark. Together they should be the skeleton of the piece: what is the arrangement, who set it up, what does it cost and to whom, where else does it run, what would have to change for it to stop. A note answers one of these; an article answers most of them.>"],
  "second_act": "<what happened AFTER the fact itself — a consequence, a reversal, a court case, an amendment, a company changing course. Empty string if nothing did.>",
  "beyond_one_place": "<where the same arrangement runs OUTSIDE the one company, country or product in the fact. Name it concretely. Empty string if it is confined to one place.>"}}

## Before you answer: is this an article at all?

Be honest in `second_act` and `beyond_one_place`, and leave them EMPTY when the
record gives you nothing. A fact with neither is a good NOTE and a bad article:
complete in two sentences, and a thousand words of it would be padding.

You are not being asked to justify writing this. Something else decides that,
and it decides on those two fields. Filling them with hedges to be helpful is
the one thing that breaks this.
"""


def temat_z_faktu(conn, run_id, fakt: dict) -> dict:
    """Zamienia udokumentowany fakt w brief artykulu."""
    from datetime import datetime, timezone

    tekst = llm.call(
        "wybor", SYSTEM,
        PYTANIE.format(
            dzis=datetime.now(timezone.utc).strftime("%d %B %Y"),
            fact=fakt.get("fact", ""),
            mit=fakt.get("wrong_belief", ""),
            prawda=fakt.get("actually", ""),
            decyzja=fakt.get("decision", ""),
            skutek=fakt.get("consequence", ""),
            url=fakt.get("url", ""),
            data=fakt.get("source_date", "brak daty")),
        conn=conn, run_id=run_id)
    brief = llm.parse_json(tekst)
    if not isinstance(brief, dict) or not brief.get("question"):
        raise ValueError("brief bez pytania: %r" % str(tekst)[:200])
    # Pola, ktorych oczekuje reszta lancucha.
    brief.setdefault("kind", "BROKEN_BELIEF" if brief.get("broken_belief")
                     else "SYSTEM_UNDER_TEST")
    brief["zrodlo_faktu"] = fakt.get("url", "")
    brief["data_zrodla"] = fakt.get("source_date", "")
    brief["fakt_wyjsciowy"] = fakt.get("fact", "")
    return brief


def glebokosc_z_oceny(ocena: dict) -> str:
    """RICH / SINGLE / THIN — liczone z tego, co `warto_pisac` ZOBACZYLO.

    SYGNAL BYL MARTWY. Kod czytal `ocena.get("depth")`, a kontrakt
    `warto_pisac.md` pola `depth` NIE MA — produkuje je `wykonalnosc.md`, etap,
    ktorego sciezka z puli w ogole nie wola. Wiec `glebokosc` bylo ZAWSZE
    „RICH": pisarzowi zawsze kazano pisac najglebsza forme, niezaleznie od tego,
    czy fakt to unosi. Jedyny mechanizm, ktory mogl skrocic chudy artykul,
    cicho defaultowal na najdluzszy. Pole czytane, nigdy nieustawiane.

    MODEL OBSERWUJE, KOD DECYDUJE — dlatego nie dopisuje `depth` do promptu i
    nie pytam modelu drugi raz o to samo. `warto_pisac` juz odpowiada na piec
    pytan tak/nie z uzasadnieniem; glebokosc jest ICH SUMA, a suma to robota
    dla kodu. Samoocena „jak gleboki jest ten material" degeneruje do stalej,
    tak samo jak wszystkie inne samooceny w tym potoku.

    Progi: cztery lub piec filarow to RICH, dwa lub trzy SINGLE, jeden albo
    zero THIN. Piec filarow to zlamane przekonanie, nazwany decydent, odczuwalna
    liczba, druga dziedzina i nierozstrzygniety wynik — i to wlasnie ich brak
    daje „lanie wody", bo pisarz nie ma czym wypelnic tysiaca slow poza
    powtarzaniem tezy.
    """
    FILARY = ("contradicted_belief", "named_decider", "felt_number",
              "second_domain", "unsettled_outcome")
    ile = sum(1 for f in FILARY
              if isinstance(ocena.get(f), dict) and ocena[f].get("present"))
    if ile >= 4:
        return "RICH"
    return "SINGLE" if ile >= 2 else "THIN"


def uniesie_artykul(brief: dict) -> tuple[bool, str]:
    """Czy z tego faktu da sie napisac TYSIAC SLOW, czy tylko dwa zdania.

    MODEL OBSERWUJE, KOD DECYDUJE. Prompt briefu prosil o „pytanie warte tej
    dlugosci" i to bylo wszystko — a prosba w prompcie nie jest bramka.
    Wlasciciel nazwal ryzyko wprost: „notatka moze byc o jednej malej kwestii,
    cala informacja w dwoch zdaniach i za bardzo nie ma co rozwijac, a artykul
    jakby wzial te info, to byloby lanie wody".

    Dwa warunki, oba brane z tego, co model ZOBACZYL w rekordzie, a nie z jego
    oceny, czy warto:

    DRUGI AKT — czy po samym fakcie cos jeszcze sie stalo. Skutek, odwrocenie,
    sprawa w sadzie, nowelizacja, firma zmieniajaca kurs. Fakt bez drugiego
    aktu jest kompletny w jednym zdaniu i rozbicie go na akapity daje
    rozdmuchana notke.

    ZASIEG POZA JEDNO MIEJSCE — czy ten sam uklad chodzi gdzies poza jedna
    firma, krajem albo produktem. Bez tego czytelnik bez zwiazku z ta jedna
    rzecza nie ma po co czytac tysiaca slow.

    JEDEN WYSTARCZY, nie oba. Wymaganie obu odrzucaloby dobre tematy: prawo,
    ktore dopiero weszlo, nie ma jeszcze drugiego aktu, ale ma zasieg; awaria
    w jednej firmie nie ma zasiegu, ale ma ciag dalszy, ktory jest cala
    historia. Zadnego z dwoch — to jest notka.

    Ta sama zasada, co przy `warto_pisac`, tylko PRZED researchem: tam ocena
    przychodzi po wydaniu 0,32 USD i tak nic nie blokuje.
    """
    drugi = " ".join(str(brief.get("second_act") or "").split())
    zasieg = " ".join(str(brief.get("beyond_one_place") or "").split())

    # Krotkie wypelniacze („none", „n/a", „unclear") to puste pole napisane
    # inaczej. Model proszony o uczciwosc czasem zamiast pustki wpisuje slowo.
    def _pusty(s: str) -> bool:
        return len(s.split()) < 4 or s.lower().rstrip(".") in {
            "none", "n/a", "na", "unclear", "unknown", "nothing", "not stated"}

    ma_drugi = not _pusty(drugi)
    ma_zasieg = not _pusty(zasieg)
    if ma_drugi or ma_zasieg:
        return True, ("drugi akt: %s" % drugi[:70]) if ma_drugi else (
            "zasieg: %s" % zasieg[:70])
    return False, ("ani drugiego aktu, ani zasiegu poza jedno miejsce — "
                   "to jest notka, nie artykul")


def wybierz_fakt(conn, run_id, ile: int = 8) -> dict:
    """Swiezy fakt z puli ciekawostek, ktory NIE powtarza zadnego artykulu.

    Pula juz przeszla bramke swiezosci (zrodlo nie starsze niz 90 dni dla
    twierdzen o stanie teraz, zadnych wycofywanych modeli, zadnych wersji bez
    potwierdzenia). Tu odsiewamy tylko to, o czym juz pisalismy dluga forma.
    """
    # NAJPIERW SPIZARNIA, DOPIERO POTEM ZAKUPY — tak samo jak w `notki_dnia`.
    #
    # Podlaczylem indeks do notek 30 sierpnia i zostawilem sciezke artykulu na
    # swiezym szukaniu. Zywy test tego samego wieczora pokazal, ile to kosztuje:
    # jedno wywolanie `curiosity`, 18 wyszukiwan, 450 tys. tokenow wejscia i
    # 0,127 USD — po to, zeby wybrac jeden fakt, podczas gdy w indeksie lezaly
    # gotowe, juz oplacone i juz przepuszczone przez bramke.
    #
    # Zmierzone: kazde wyszukiwanie to 10-19 tys. tokenow wejscia, bo serwer
    # prowadzi petle u siebie i rozlicza kazda runde osobno. Nie da sie tego
    # ograniczyc parametrem (`max_uses` i `max_tool_calls` sa ignorowane), wiec
    # jedyny sposob na tanszy artykul to NIE SZUKAC, kiedy nie trzeba.
    fakty = stages.wez_kandydatow(ile)
    if fakty:
        print("  [temat] z indeksu: %d kandydatow (bez wyszukiwania)"
              % len(fakty), flush=True)
    else:
        fakty = stages.znajdz_ciekawostki(conn, run_id, ile=ile)
    if not fakty:
        raise ValueError("pula ciekawostek pusta")

    # DWIE PAMIECI, NIE JEDNA — i to kosztowalo caly artykul.
    #
    # Pierwsza wersja pytala tylko o poprzednie ARTYKULY. 25 sierpnia o 11:28
    # poszla notka o kenijskich anotatorach i stawce 12,50 USD za godzine, a po
    # poludniu artykul wzial z puli dokladnie ten sam fakt i napisal o nim
    # tysiac slow. Zaden artykul o tym nie byl, wiec straznik milczal.
    #
    # Konto ma jednego czytelnika, nie dwoch. Dla niego notka i artykul o tym
    # samym w jeden dzien to po prostu dwa razy to samo.
    wczesniej = list(stages.tematy_do_porownania(conn))
    notki = stages.ostatnie_notki(1000)
    wczesniej.extend(notki)
    print("  [temat] pamiec: %d artykulow + %d notek"
          % (len(wczesniej) - len(notki), len(notki)), flush=True)

    for f in fakty:
        opis = "%s %s" % (f.get("domain") or "", f.get("fact") or "")
        kolizja = next((w for w in wczesniej if w and stages._o_tym_samym(
            opis, w, **stages.POWTORKA_TEMATU)), None)
        if kolizja:
            print("  [temat] pomijam, juz o tym bylo: %s"
                  % (f.get("fact") or "")[:60], flush=True)
            print("          zderza sie z: %s"
                  % " ".join(str(kolizja).split())[:80], flush=True)
            continue
        # RESZTA WRACA DO PULI. Bierzemy osiem, uzywamy jednego — a
        # `wez_kandydatow` oznaczylo jako zuzyte wszystkie osiem. Bez tego
        # kazdy przebieg artykulu palil siedem oplaconych kandydatur.
        stages.zwroc_kandydatow([x for x in fakty if x is not f])
        return f
    print("  [temat] wszystko koliduje — biore pierwszy", flush=True)
    stages.zwroc_kandydatow(fakty[1:])
    return fakty[0]


def main() -> int:
    conn = db.connect()
    run_id = db.start_run(conn, "artykul-z-puli")
    print("== artykul z puli ciekawostek ==", flush=True)

    # --- SCIEZKA Z ZATWIERDZONEJ KARTY ------------------------------------
    #
    # `--z-karty` pomija szukanie tematu i caly research: wczytuje karte
    # zapisana przez `--do-karty` i rusza od pisarza. Dzieki temu obejrzenie
    # materialu przed napisaniem kosztuje 0,38 USD RAZ, a nie dwa razy.
    if "--z-karty" in sys.argv:
        import json as _json
        _plik = config.DATA_DIR / "karta_do_zatwierdzenia.json"
        if not _plik.exists():
            print("BRAK zatwierdzonej karty — najpierw --do-karty", flush=True)
            return 1
        _zapis = _json.loads(_plik.read_text(encoding="utf-8"))
        card = _zapis["card"]
        brief = _zapis["brief"]
        print("  karta wczytana: %s" % brief.get("title"), flush=True)
        print("  pytanie: %s" % str(brief.get("question"))[:130], flush=True)
        return _napisz_i_zapisz(conn, run_id, brief, card)

    fakt = wybierz_fakt(conn, run_id)
    print()
    print("  FAKT:   %s" % (fakt.get("fact") or "")[:200], flush=True)
    print("  ZRODLO: %s (%s)" % (fakt.get("url", "")[:70],
                                 fakt.get("source_date", "brak daty")), flush=True)

    brief = temat_z_faktu(conn, run_id, fakt)
    print()
    print("  TYTUL:  %s" % brief.get("title"), flush=True)
    print("  PYTANIE: %s" % brief.get("question"), flush=True)
    print("  ZLAMANE PRZEKONANIE: %s" % (brief.get("broken_belief") or "(brak)"),
          flush=True)

    # BRAMKA ARTYKULOWA — PRZED RESEARCHEM, bo po nim jest juz za pozno.
    # Odrzucony fakt WRACA DO PULI jako material na notke: nie jest zly, tylko
    # nie unosi tysiaca slow. Probujemy kolejnych, zamiast poddawac sie na
    # pierwszym — dokladnie tak, jak `wybierz_fakt` robi to przy powtorkach.
    unosi, powod = uniesie_artykul(brief)
    proby = 1
    while not unosi and proby < 4:
        print("  ODPADA: %s" % powod, flush=True)
        print("  (fakt zostaje w puli jako material na notke)", flush=True)
        proby += 1
        print()
        print("-- proba %d: nastepny fakt --" % proby, flush=True)
        try:
            fakt = wybierz_fakt(conn, run_id)
        except ValueError as exc:
            print("  %s — koncze" % exc, flush=True)
            return 1
        brief = temat_z_faktu(conn, run_id, fakt)
        print("  TYTUL:  %s" % brief.get("title"), flush=True)
        print("  PYTANIE: %s" % brief.get("question"), flush=True)
        unosi, powod = uniesie_artykul(brief)
    if not unosi:
        print("  ODPADA: %s" % powod, flush=True)
        print(">> po %d probach zaden fakt nie uniesie artykulu — nie pisze."
              " Pula zostaje na notki." % proby, flush=True)
        return 1
    print("  UNIESIE: %s" % powod, flush=True)

    pod = [q for q in (brief.get("sub_questions") or []) if str(q).strip()]
    if pod:
        print()
        print("  PYTANIA, NA KTORE ARTYKUL MA ODPOWIEDZIEC (%d):" % len(pod),
              flush=True)
        for q in pod:
            print("    - %s" % str(q)[:110], flush=True)

    if "--tylko-temat" in sys.argv:
        return 0

    # --- dalej JUZ ISTNIEJACY lancuch, bez zmian ---------------------------
    print()
    print("-- dyskoveria --", flush=True)
    recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
    # PODPYTANIA IDA DO DYSKOVERII, nie tylko do pisarza. Bez tego byly by
    # ozdoba: model wypisalby szesc pytan, research szedlby po jednym glownym,
    # a pisarz dostalby karte, ktora odpowiada na jedno z szesciu. Wlasciciel
    # prosil wprost o to, zeby temat artykulu byl BARDZIEJ ZBADANY niz temat
    # notki — a to znaczy wiecej pytan na wejsciu researchu, nie wiecej slow
    # na wyjsciu pisarza.
    pytanie_do_researchu = brief["question"]
    if pod:
        pytanie_do_researchu = (
            brief["question"]
            + "\n\nThe article must also answer:\n"
            + "\n".join("- %s" % q for q in pod))
    sources = stages.discovery(conn, run_id, pytanie_do_researchu, recent)

    print()
    print("-- pobieranie --", flush=True)
    corpus = stages.fetch(conn, run_id, sources)
    # Druga runda, gdy material chudy — tak samo jak w run.py.
    if len([c for c in corpus if c.get("text")]) < 4:
        print()
        print("-- za chudo — druga runda --", flush=True)
        juz = {c.get("url") for c in corpus}
        dodatkowe = [s for s in stages.discovery(conn, run_id,
                                                 pytanie_do_researchu, recent)
                     if s.get("url") not in juz]
        if dodatkowe:
            corpus = corpus + stages.fetch(conn, run_id, dodatkowe)

    print()
    print("-- klasyfikacja --", flush=True)
    evidence = stages.classify(conn, run_id, brief["question"], corpus)

    print()
    print("-- synteza --", flush=True)
    try:
        card = stages.synthesis(conn, run_id, brief["question"], evidence)
    except Exception as exc:
        print("  synteza padla (%s) — karta zapasowa" % type(exc).__name__,
              flush=True)
        card = stages.fallback_card(brief["question"], evidence)

    # Fakt wyjsciowy zostaje w karcie: to on byl powodem, dla ktorego ten temat
    # w ogole wybralismy, i pisarz ma go widziec razem z reszta dowodow.
    card.setdefault("broken_belief", brief.get("broken_belief") or "")
    card.setdefault("why_they_believe_it", brief.get("why_they_believe_it") or "")

    # --- HAMULEC PRZED NAJDROZSZYM ETAPEM ---------------------------------
    #
    # `--do-karty` konczy tu, po syntezie, przed pisarzem. Kosztuje okolo
    # 0,38 USD zamiast 1,40, bo samo pisanie to 0,76.
    #
    # POWOD JEST POLICZONY. 25 sierpnia zaplacilem CZTERY pisania po 0,76 USD
    # i ani jedna znaleziona wada nie byla w pisaniu:
    #   przebieg 1 — powtorzony temat (wybor tematu)
    #   przebieg 2 — powtorzony temat, tym razem z dzisiejsza notka
    #   przebieg 3 — metaanaliza cytowana z drugiej reki (dyskoveria)
    #                oraz butelka po sosie w naglowku (grafika)
    #   przebieg 4 — filtr adresow blokowal zrodla pierwotne (dyskoveria)
    #
    # Trzy z czterech widac bylo na karcie dowodowej: jakie zrodla, jakiej
    # daty, czy sa pierwotne. Czwarta — powtorke tematu — jeszcze wczesniej,
    # przy samym tytule.
    #
    # 3,04 USD na pisanie, z ktorego nic nie wynikalo poza tym, ze wada byla
    # gdzie indziej.
    if "--do-karty" in sys.argv:
        print()
        print("=" * 72)
        print("KARTA DOWODOWA — STOP PRZED PISARZEM")
        print("=" * 72)
        print("TEZA:", str(card.get("working_thesis", ""))[:400])
        print()
        daty = card.get("source_dates") or {}
        print("DATY ZRODEL: najnowsze %s, najstarsze %s"
              % (daty.get("newest", "?"), daty.get("oldest", "?")))
        if daty.get("note"):
            print("   uwaga:", str(daty["note"])[:200])
        for u in stages.swiezosc_karty(card):
            print("   [%s] %s" % (u.get("gate"), str(u.get("detail"))[:130]))
        print()
        print("LICZBY DO CYTOWANIA (%d):" % len(card.get("citable_numbers") or []))
        for n in (card.get("citable_numbers") or [])[:8]:
            print("   - %s" % str(n)[:170])
        print()
        print("ZRODLA W KORPUSIE:")
        widziane = set()
        for c in (evidence if isinstance(evidence, list) else []):
            h = str(c.get("url") or "")[:70]
            if h and h not in widziane:
                widziane.add(h)
                print("   %-10s %s" % (c.get("class", "?"), h))
        print()
        print("CZEGO NIE USTALONO:")
        for x in (card.get("not_established") or [])[:5]:
            print("   - %s" % str(x)[:150])

        # KARTA ZAPISANA, ZEBY NIE PLACIC DYSKOVERII DRUGI RAZ.
        #
        # Pierwsza wersja hamulca konczyla tu i tyle — a wtedy napisanie
        # zatwierdzonego artykulu wymagalo puszczenia calego lancucha od nowa,
        # czyli oplacenia szukania tematu, dyskoverii, pobierania, klasyfikacji
        # i syntezy PO RAZ DRUGI. Hamulec, ktory oszczedza 0,76 na pisaniu i
        # kaze zaplacic 0,38 na research, oszczedza polowe tego, co obiecuje.
        #
        # `--z-karty` wczytuje ten plik i rusza od pisarza.
        import json as _json
        _plik = config.DATA_DIR / "karta_do_zatwierdzenia.json"
        try:
            _plik.parent.mkdir(parents=True, exist_ok=True)
            _plik.write_text(_json.dumps(
                {"card": card, "brief": brief, "fakt": fakt},
                ensure_ascii=False, indent=1), encoding="utf-8")
            print()
            print(">> karta zapisana: %s" % _plik)
            print(">> zeby napisac TEN artykul bez placenia researchu drugi raz:")
            print("   .venv/bin/python agent-v2/artykul_z_puli.py --z-karty")
        except OSError as exc:
            print("   (karty nie zapisalem: %s)" % exc)
        return 0

    # NORMALNA SCIEZKA — bez `--do-karty` idziemy prosto do pisarza.
    #
    # Ta linia byla przez chwile OSIEROCONA: wyladowala za koncem
    # `_napisz_i_zapisz`, wiec `main` przelatywalo przez `if` powyzej i wypadalo
    # z funkcji, zwracajac None. Przebieg konczyl sie KODEM 0 i bez artykulu —
    # bez wyjatku, bez ostrzezenia, z opłaconym researchem za 0,40 USD i pustym
    # katalogiem. Zlapane zywym przebiegiem 30 sierpnia, nie testem: zaden test
    # nie wolal `main()`, wiec nieosiagalny kod nie mial jak sie ujawnic.
    return _napisz_i_zapisz(conn, run_id, brief, card)


def _napisz_i_zapisz(conn, run_id, brief, card) -> int:
    """Od bramki „warto pisac" do zapisu i grafiki.

    Wydzielone, zeby `--z-karty` mogl tu wejsc z zatwierdzona karta bez
    placenia researchu drugi raz.
    """
    print()
    print("-- czy jest tu luka --", flush=True)
    ocena = stages.warto_pisac(conn, run_id, card)
    print("   werdykt: %s" % str(ocena.get("verdict") or ocena)[:200], flush=True)

    print()
    print("-- pisanie --", flush=True)
    glebokosc = glebokosc_z_oceny(ocena)
    print("   glebokosc: %s" % glebokosc, flush=True)
    draft = stages.write(conn, run_id, card, glebokosc)
    print()
    print("   tytul: %s" % draft.get("title"), flush=True)
    print("   podtytul: %s" % draft.get("subtitle", ""), flush=True)
    # ZAKRES RAZEM Z LICZBA. Sama liczba slow nie mowi, czy artykul jest za
    # krotki — a pasma sa trzy i roznia sie dwuipolkrotnie. `run.py` drukowal
    # tu przez dlugi czas staly cel 1075, czyli wartosc sprzed skalowania.
    _dl = config.dlugosc_dla(glebokosc)
    print("   dlugosc: %d slow (cel %d, zakres %d-%d dla %s)"
          % (len(draft["body"].split()), _dl["cel"], _dl["min"], _dl["max"],
             glebokosc), flush=True)

    print()
    print("-- recenzja --", flush=True)
    raport = stages.review(conn, run_id, card, draft)
    # Dwa zrodla nieopartych faktow, tak jak w run.py: jawna lista recenzenta
    # ORAZ zdania sklasyfikowane jako FACT z `supported: false`. Recenzent
    # wypelnia raz jedno, raz drugie, i branie tylko jednego gubi polowe.
    bez_pokrycia = list(raport.get("unsupported_facts") or [])
    znane = {str(x.get("text", ""))[:60] for x in bez_pokrycia}
    for s in raport.get("sentences") or []:
        if s.get("class") != "FACT" or s.get("supported") is not False:
            continue
        if str(s.get("text", ""))[:60] in znane:
            continue
        bez_pokrycia.append({"text": s.get("text", ""), "why": s.get("why", "")})

    try:
        forma = stages.ocen_forme(conn, run_id, draft)
    except Exception as exc:
        print("  [awaria] obserwacja formy padla (%s) — ide dalej"
              % type(exc).__name__, flush=True)
        forma = {}

    # BRAMKI JAKOSCI — dokladnie te, co w run.py. Pierwsza wersja tego
    # sterownika ich NIE WOLALA: sprawdzala `hasattr(stages, "uwagi_z_formy")`,
    # a ta funkcja mieszka w `gates`, wiec warunek byl zawsze falszywy i uwagi
    # cicho znikaly. Skrot, ktory wylaczal kontrole, nie wygladajac na to.
    import gates
    uwagi = gates.deterministic_floors(
        draft["body"], card,
        poprzednie=stages.poprzednie_teksty(pomin_tresc=draft["body"]))
    uwagi.extend(gates.uwagi_z_formy(forma, draft["body"]))
    # WIEK MATERIALU — jedyne sprawdzenie daty na tej sciezce. Patrz
    # `stages.swiezosc_karty`.
    uwagi.extend(stages.swiezosc_karty(card))
    for item in bez_pokrycia:
        uwagi.append({"gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")})

    print()
    print("-- uwagi (nic nie blokuje) --", flush=True)
    for u in uwagi:
        print("   [%s] %s" % (u.get("gate"), str(u.get("detail"))[:150]), flush=True)
    if not uwagi:
        print("   czysto — zadna uwaga", flush=True)

    status, blokada = gates.verdict(uwagi)
    notatki = [*uwagi,
               {"gate": "DLUGOSC", "detail": "%d slow" % len(draft["body"].split())},
               {"gate": "RECENZJA", "detail": raport.get("summary", "")}]

    # `blocked_by` to NAPIS, nie lista — sqlite nie przyjmie listy i caly
    # artykul przepada po zaplaceniu za niego. Zdarzylo sie raz, 25 sierpnia.
    sciezka = stages.save(conn, run_id, brief, card, draft, status,
                          blokada or "", notatki)
    print()
    print(">> zapisano: %s" % sciezka, flush=True)

    stages.grafika(conn, run_id, draft, sciezka_artykulu=sciezka)

    # --- PUBLIKACJA -------------------------------------------------------
    #
    # DLACZEGO TO TU DOSZLO. Sciezka artykulu byla rozdarta na dwie polowy i
    # zadna nie umiala calej roboty:
    #   `run.py --wyslij` publikuje i ma bramke faktow, ale bierze temat od
    #     skauta — a wlasnie skaut dawal pod AI monokulture (patrz naglowek
    #     tego pliku: trzy artykuly z rzedu o zautomatyzowanej biurokracji),
    #   ten plik bierze temat z puli, ma bramke „uniesie artykul", podpytania
    #     i glebokosc z filarow — i nie umial opublikowac ani jednej linijki.
    # `nia-artykul.service` wskazywal caly czas na te pierwsza. Zastepnik
    # napisano, uzywano recznie i nigdy nie wpieto w zegar.
    #
    # DOMYSLNIE WYLACZONE. Bez `--wyslij` artykul konczy na dysku, tak jak dotad.
    if "--wyslij" not in sys.argv:
        print(">> bez --wyslij: artykul zostaje na dysku", flush=True)
        return 0

    import browser

    # SPRAWDZENIE FAKTOW PRZED PUBLIKACJA — ta sama bramka, co w `run.py`.
    # Zapis zostaje, publikacja nie: artykul jest juz na dysku z okladka, wiec
    # research nie przepada i wlasciciel ma co czytac. Blokujemy wylacznie
    # wyjscie na zewnatrz, bo tam blad kosztuje wiarygodnosc, a nie pieniadze.
    # `zweryfikuj` przy wlasnej awarii przepuszcza — zepsuta weryfikacja nie
    # jest dowodem falszu.
    print()
    print("-- sprawdzenie faktow przed publikacja --", flush=True)
    audyt = stages.zweryfikuj(conn, run_id, draft["body"], draft.get("title", ""))
    if not audyt.get("safe_to_post"):
        print("!! NIE PUBLIKUJE: %s" % str(audyt.get("verdict", ""))[:300],
              flush=True)
        for c in (audyt.get("claims") or []):
            if str(c.get("status")) in ("refuted", "outdated", "unverified"):
                print("   [%s] %s" % (c.get("status"),
                                      str(c.get("claim"))[:150]), flush=True)
        print(">> artykul zapisany (%s), do decyzji wlasciciela" % sciezka,
              flush=True)
        return 0
    print("   przechodzi: %s" % str(audyt.get("verdict", ""))[:150], flush=True)

    print()
    print("-- publikacja --", flush=True)
    wynik = browser.wystaw_artykul(sciezka, wyslij=True)
    print(">> %s%s" % ("OPUBLIKOWANY" if wynik.get("wyslane") else "NIE POSZEDL",
                       "  " + str(wynik.get("blad")) if wynik.get("blad") else ""),
          flush=True)
    return 0





if __name__ == "__main__":
    raise SystemExit(main())
