"""Nasz research na temat, ktory sam sprawdzilem recznie. Porownanie 1:1.

Temat: ukryte zabezpieczenia w Claude Fable 5. Wlasciciel wskazal go z puli
ciekawostek. Ja zrobilem wlasny research w sieci, teraz to samo robi potok —
i porownujemy, czy nasz jest co najmniej tak dobry.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "agent-v2"))

import config
config.DRY_RUN = False
config.DAILY_LIMIT_USD = 6.0

import db        # noqa: E402
import stages    # noqa: E402

FAKT = {
    "domain": "chatbots / Claude",
    "fact": ("Anthropic's Claude Fable 5 launched with hidden safeguards that "
             "silently identified requests targeting frontier LLM development "
             "and limited them without telling the user; after a backlash in "
             "June 2026 Anthropic apologized and made the safeguards visible, "
             "rerouting flagged requests to Opus 4.8 with an explicit notice."),
    "wrong_belief": "When a chatbot refuses or limits you, it tells you it's doing so.",
    "actually": ("Some limits are applied by degrading the model in place — "
                 "through prompt modification, steering vectors or PEFT — so "
                 "the user sees a worse answer, not a refusal."),
    "decision": "Anthropic, published in the Fable 5 system card, June 2026",
    "consequence": ("Your answer can be quietly made worse and you would have "
                    "no way to tell it apart from a bad day."),
    "url": "https://simonwillison.net/2026/Jun/11/anthropic-walks-back-policy/",
    "source_date": "2026-06-11",
}

PYTANIE = ("Why are some AI guardrails invisible while others announce "
           "themselves, who decided which is which, and how would a user ever "
           "know the difference?")


def main() -> int:
    conn = db.connect()
    run_id = db.start_run(conn, "porownanie-researchu")

    print("=" * 78)
    print("NASZ RESEARCH NA TEN SAM TEMAT")
    print("=" * 78)
    print("pytanie:", PYTANIE)
    print()

    recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
    zrodla = stages.discovery(conn, run_id, PYTANIE, recent)
    print()
    print("-- co znalazl (%d) --" % len(zrodla))
    for z in zrodla:
        print("   %-34s %s" % (str(z.get("url", ""))[8:42],
                               str(z.get("why") or z.get("title") or "")[:70]))

    korpus = stages.fetch(conn, run_id, zrodla)
    dobre = [c for c in korpus if c.get("text")]
    print()
    print("-- pobrano %d z %d --" % (len(dobre), len(korpus)))

    if len(dobre) < 4:
        print()
        print("-- druga runda --")
        juz = {c.get("url") for c in korpus}
        extra = [s for s in stages.discovery(conn, run_id, PYTANIE, recent)
                 if s.get("url") not in juz]
        if extra:
            korpus = korpus + stages.fetch(conn, run_id, extra)

    dowody = stages.classify(conn, run_id, PYTANIE, korpus)
    print()
    print("-- material dowodowy --")
    karta = stages.synthesis(conn, run_id, PYTANIE, dowody)

    print()
    print("=" * 78)
    print("KARTA DOWODOWA — TO DOSTANIE PISARZ")
    print("=" * 78)
    print()
    print("TEZA:", karta.get("working_thesis", ""))
    print()
    print("MECHANIZM:", str(karta.get("main_mechanism", ""))[:700])
    print()
    print("POTWIERDZONE TWIERDZENIA:")
    for c in karta.get("confirmed_claims", []):
        print("   -", str(c)[:190])
    print()
    print("LICZBY DO CYTOWANIA:")
    for n in karta.get("citable_numbers", []):
        print("   -", str(n)[:190])
    print()
    print("PARALELE (to, z czego bierze sie dlugosc):")
    for p in karta.get("parallel_mechanisms", []):
        print("   -", str(p)[:190])
    print()
    print("CZEGO NIE USTALONO:")
    for x in karta.get("not_established", []):
        print("   -", str(x)[:190])
    print()
    print("SPRZECZNOSCI:")
    for x in karta.get("contradictions", []):
        print("   -", str(x)[:190])

    import json
    Path("karta_porownanie.json").write_text(
        json.dumps({"karta": karta, "pytanie": PYTANIE, "fakt": FAKT},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(">> karta zapisana do karta_porownanie.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
