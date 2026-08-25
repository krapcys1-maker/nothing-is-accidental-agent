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
  "search_terms": ["<3-6 phrases a researcher should search to document this properly>"]}}
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


def wybierz_fakt(conn, run_id, ile: int = 8) -> dict:
    """Swiezy fakt z puli ciekawostek, ktory NIE powtarza zadnego artykulu.

    Pula juz przeszla bramke swiezosci (zrodlo nie starsze niz 90 dni dla
    twierdzen o stanie teraz, zadnych wycofywanych modeli, zadnych wersji bez
    potwierdzenia). Tu odsiewamy tylko to, o czym juz pisalismy dluga forma.
    """
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
        return f
    print("  [temat] wszystko koliduje — biore pierwszy", flush=True)
    return fakty[0]


def main() -> int:
    conn = db.connect()
    run_id = db.start_run(conn, "artykul-z-puli")
    print("== artykul z puli ciekawostek ==", flush=True)

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

    if "--tylko-temat" in sys.argv:
        return 0

    # --- dalej JUZ ISTNIEJACY lancuch, bez zmian ---------------------------
    print()
    print("-- dyskoveria --", flush=True)
    recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
    sources = stages.discovery(conn, run_id, brief["question"], recent)

    print()
    print("-- pobieranie --", flush=True)
    corpus = stages.fetch(conn, run_id, sources)
    # Druga runda, gdy material chudy — tak samo jak w run.py.
    if len([c for c in corpus if c.get("text")]) < 4:
        print()
        print("-- za chudo — druga runda --", flush=True)
        juz = {c.get("url") for c in corpus}
        dodatkowe = [s for s in stages.discovery(conn, run_id, brief["question"],
                                                 recent)
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

    print()
    print("-- czy jest tu luka --", flush=True)
    ocena = stages.warto_pisac(conn, run_id, card)
    print("   werdykt: %s" % str(ocena.get("verdict") or ocena)[:200], flush=True)

    print()
    print("-- pisanie --", flush=True)
    glebokosc = str(ocena.get("depth") or "RICH").upper()
    draft = stages.write(conn, run_id, card, glebokosc)
    print()
    print("   tytul: %s" % draft.get("title"), flush=True)
    print("   podtytul: %s" % draft.get("subtitle", ""), flush=True)
    print("   dlugosc: %d slow" % len(draft["body"].split()), flush=True)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
