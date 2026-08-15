"""Jedno polecenie uruchamiające — to samo lokalnie i na serwerze.

    python agent-v2/run.py
    python agent-v2/run.py --stop-after scout
    python agent-v2/run.py --use-cache          # nie płać drugi raz za etap N-1

Bez interaktywnych promptów: na serwerze nie ma komu odpowiedzieć. Logi na
stdout, żeby harmonogram je przechwycił.
"""

from __future__ import annotations

import argparse
import os
import json
import sys
import traceback
from typing import Any, Callable

import config
import db
import gates
import stages

STAGES = (
    "scout", "feasibility", "discovery", "fetch",
    "classify", "synthesis", "write", "review",
)

CACHE_DIR = config.DATA_DIR / "cache"


def _utf8_stdout() -> None:
    """Konsola Windows domyślnie cp1252 i wywala się na polskich znakach.

    Serwer ma UTF-8, więc bez tego błąd wychodzi wyłącznie na jednym z tych
    dwóch komputerów — czyli najgorszy możliwy rodzaj błędu.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cached(stage: str, produce: Callable[[], Any], use_cache: bool) -> Any:
    """Zapisuje wynik etapu i oddaje go z dysku zamiast płacić drugi raz.

    Zasada z briefu: testując etap N, użyj zapisanego wyniku etapu N-1.
    """
    path = CACHE_DIR / f"{stage}.json"
    if use_cache and path.exists():
        print(f"  [{stage}] z pamięci podręcznej — bez opłaty", flush=True)
        return json.loads(path.read_text(encoding="utf-8"))
    value = produce()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


class JuzDziala(RuntimeError):
    pass


def zajmij_zamek():
    """Nie pozwala dwóm przebiegom działać naraz.

    Na serwerze harmonogram odpali agenta o stałej godzinie niezależnie od tego,
    czy poprzedni przebieg się skończył. Dwa procesy naraz to dwa razy ten sam
    artykuł i dwa razy ta sama notka — a tego nie da się cofnąć. To nie jest
    kwestia „czy", tylko „kiedy", więc zamek jest przed pierwszym uruchomieniem
    z harmonogramu, nie po pierwszej wpadce.

    Zamek trzyma system plików, nie my: przy zabiciu procesu blokada znika sama,
    więc nie zostawia po sobie zakleszczenia, które trzeba by odblokowywać ręcznie.
    """
    sciezka = config.DATA_DIR / "agent.lock"
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    uchwyt = open(sciezka, "w", encoding="utf-8")
    try:
        try:                      # Linux, czyli serwer
            import fcntl
            fcntl.flock(uchwyt, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:       # Windows, czyli komputer właściciela
            import msvcrt
            msvcrt.locking(uchwyt.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        uchwyt.close()
        raise JuzDziala(
            f"Inny przebieg już działa (zamek: {sciezka}). Kończę bez zmian."
        ) from None
    uchwyt.write(f"{os.getpid()}\n")
    uchwyt.flush()
    return uchwyt


def main() -> int:
    _utf8_stdout()
    try:
        _zamek = zajmij_zamek()   # trzymany do końca procesu
    except JuzDziala as exc:
        print(f"  {exc}", flush=True)
        return 0
    parser = argparse.ArgumentParser(description="agent-v2 — jeden artykuł do szuflady")
    parser.add_argument("--stop-after", choices=STAGES, help="zatrzymaj się po tym etapie")
    parser.add_argument("--use-cache", action="store_true", help="użyj zapisanych wyników etapów")
    parser.add_argument("--topics", type=int, default=6, help="ile tematów ma zwrócić skaut")
    args = parser.parse_args()

    conn = db.connect()
    run_id = db.start_run(conn)
    stage = "start"

    print(f"== przebieg {run_id} ==", flush=True)
    print(
        f"   baza: {config.DB_PATH}   "
        f"sufit przebiegu: {config.RUN_LIMIT_USD} USD"
        f"{'   TANIO (DeepSeek)' if config.CHEAP_MODE else ''}"
        f"{'   DRY_RUN' if config.DRY_RUN else ''}",
        flush=True,
    )

    try:
        stage = "scout"
        topics = cached(stage, lambda: stages.scout(conn, run_id, args.topics), args.use_cache)
        print(f"\n-- tematy ({len(topics)}) --", flush=True)
        for i, topic in enumerate(topics):
            print(f"{i}. {topic.get('title')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "feasibility"
        assessments = cached(
            stage, lambda: stages.feasibility(conn, run_id, topics), args.use_cache
        )
        topic, verdict = stages.pick_topic(topics, assessments)
        print("\n-- odsiew wykonalności --", flush=True)
        for a in assessments:
            mark = "TAK " if a.get("feasible") else "nie "
            print(
                f"  {mark} [{a.get('index')}] pewność={a.get('confidence')}"
                f" źródeł~{a.get('expected_primary_sources')}  {a.get('note', '')[:110]}",
                flush=True,
            )
        print(f"\n>> wybrany temat: {topic.get('title')}", flush=True)
        print(f"   {topic.get('question')}", flush=True)
        print(f"   uzasadnienie: {verdict.get('note', '')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "discovery"
        recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
        sources = cached(
            stage,
            lambda: stages.discovery(conn, run_id, topic["question"], recent),
            args.use_cache,
        )
        print(f"\n-- znalezione źródła ({len(sources)}) --", flush=True)
        for s in sources:
            print(
                f"  [{s.get('class', '?'):9}] {s.get('host')}"
                f"{'  DLACZEGO' if s.get('answers_why') else ''}"
                f"{'  LICZBY' if s.get('has_numbers') else ''}",
                flush=True,
            )
            print(f"      {s.get('title', '')[:100]}", flush=True)
        primary = sum(1 for s in sources if s.get("class") == "PRIMARY")
        why = sum(1 for s in sources if s.get("answers_why"))
        print(
            f"\n   pierwotnych: {primary}/{config.MIN_PRIMARY_SOURCES}   "
            f"wyjaśniających DLACZEGO: {why}/{config.MIN_WHY_SOURCES}   "
            f"organizacji: {len({s.get('host') for s in sources})}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "fetch"
        print("\n-- pobieranie --", flush=True)
        corpus = cached(stage, lambda: stages.fetch(conn, run_id, sources), args.use_cache)
        chars = sum(len(s.get("text", "")) for s in corpus)
        print(
            f"\n   pobrano {len(corpus)}/{len(sources)}   "
            f"{chars} znaków   pierwotnych: "
            f"{sum(1 for s in corpus if s.get('class') == 'PRIMARY')}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "classify"
        print("\n-- klasyfikacja i wyciąg fragmentów --", flush=True)
        evidence = cached(
            stage,
            lambda: stages.classify(conn, run_id, topic["question"], corpus),
            args.use_cache,
        )
        n_ex = sum(len(s["excerpts"]) for s in evidence)
        n_num = sum(len(s["numbers"]) for s in evidence)
        print(
            f"\n   materiał dowodowy: {len(evidence)} źródeł, {n_ex} fragmentów, "
            f"{n_num} liczb   pierwotnych: "
            f"{sum(1 for s in evidence if s['class'] == 'PRIMARY')}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        # Od tego miejsca artykuł MUSI powstać. Temat jest wybrany, research
        # zrobiony i opłacony — żaden dalszy etap nie ma prawa zabić przebiegu.
        stage = "synthesis"
        print("\n-- synteza --", flush=True)
        try:
            card = cached(
                stage,
                lambda: stages.synthesis(conn, run_id, topic["question"], evidence),
                args.use_cache,
            )
        except Exception as exc:
            print(f"  [awaria] synteza padła ({exc}) — składam kartę z dowodów", flush=True)
            card = stages.fallback_card(topic["question"], evidence)
        print(f"\n   teza: {card.get('working_thesis', '')}", flush=True)
        print(f"\n   mechanizm: {card.get('main_mechanism', '')[:400]}", flush=True)
        print(f"\n   potwierdzone twierdzenia ({len(card.get('confirmed_claims', []))}):", flush=True)
        for c in card.get("confirmed_claims", []):
            print(f"     • {c.get('claim', '')[:150]}", flush=True)
        print(f"\n   liczby ({len(card.get('citable_numbers', []))}):", flush=True)
        for n in card.get("citable_numbers", []):
            print(f"     • {n.get('value')} — {n.get('means', '')[:110]}", flush=True)
        for label, key in (("niepewne", "uncertain_claims"),
                           ("sprzeczności", "contradictions"),
                           ("czego nie ustalono", "not_established")):
            items = card.get(key) or []
            if items:
                print(f"\n   {label} ({len(items)}):", flush=True)
                for item in items:
                    print(f"     • {str(item)[:150]}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "write"
        print("\n-- pisanie --", flush=True)
        try:
            draft = cached(stage, lambda: stages.write(conn, run_id, card), args.use_cache)
        except Exception as exc:
            # Jedno powtórzenie na Opusie, bo tu ginie cały opłacony research.
            # Opus jest sprawdzonym pisarzem tego potoku; jeśli skonfigurowany
            # model odmówił albo padł, powtórka na nim ma największą szansę.
            print(
                f"  [awaria] pisarz ({config.MODEL_FOR['write']}) padł: {exc}"
                f" — powtarzam na {config.CLAUDE}",
                flush=True,
            )
            config.MODEL_FOR["write"] = config.CLAUDE
            draft = stages.write(conn, run_id, card)
        words = len(draft["body"].split())
        print(f"\n   tytuł: {draft.get('title')}", flush=True)
        print(f"   podtytuł: {draft.get('subtitle', '')}", flush=True)
        print(
            f"   długość: {words} słów "
            f"(cel {config.TARGET_WORDS}, zakres {config.MIN_WORDS}-{config.MAX_WORDS})",
            flush=True,
        )
        print(f"   akapit o granicach: {draft.get('limits_paragraph_present')}", flush=True)
        # Czy liczba jest w korpusie, liczy WYŁĄCZNIE gates.py. Stała tu druga
        # implementacja tego samego pytania i natychmiast dała inną odpowiedź
        # (uznała 'E 938' za zmyślone) — to jest ta sama choroba, przez którą
        # przepisujemy starego agenta.
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "review"
        print("\n-- recenzja --", flush=True)
        try:
            report = cached(
                stage, lambda: stages.review(conn, run_id, card, draft), args.use_cache
            )
        except Exception as exc:
            # Recenzja nic nie blokuje, więc jej brak też nie może. Artykuł
            # trafia do szuflady z adnotacją, że nie został rozliczony zdanie
            # po zdaniu — właściciel wie, na co patrzy.
            print(f"  [awaria] recenzja padła ({exc}) — zapisuję bez niej", flush=True)
            report = {"sentences": [], "unsupported_facts": [],
                      "summary": f"recenzja niedostępna: {type(exc).__name__}"}
        sentences = report.get("sentences", [])
        counts = {k: sum(1 for s in sentences if s.get("class") == k)
                  for k in ("FACT", "INFERENCE", "PROSE")}
        unsupported = report.get("unsupported_facts", []) or []
        print(
            f"   zdań: {len(sentences)}   fakty: {counts['FACT']}   "
            f"wnioskowanie: {counts['INFERENCE']}   proza: {counts['PROSE']}",
            flush=True,
        )

        findings = gates.deterministic_floors(draft["body"], card)
        for item in unsupported:
            findings.append({"gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")})

        print("\n-- uwagi (nic nie blokuje) --", flush=True)
        if findings:
            for f in findings:
                print(f"   [{f['gate']}] {f['detail'][:160]}", flush=True)
        else:
            print("   czysto — żadna uwaga", flush=True)

        status, blocked_by = gates.verdict(findings)
        notes = [*findings,
                 {"gate": "DLUGOSC", "detail": f"{len(draft['body'].split())} słów"},
                 {"gate": "RECENZJA", "detail": report.get("summary", "")}]
        # Fragmenty, których artykuł nie zużył, zostają zapisane razem z kartą.
        # Każdy przebieg zbiera ich kilkadziesiąt, a tekst bierze kilka — reszta
        # to gotowe, ocytowane fakty na notki w dni bez artykułu.
        card["unused_evidence"] = [
            {"url": s["url"], "publisher": s.get("publisher"), "excerpts": s["excerpts"],
             "numbers": s["numbers"]}
            for s in evidence
        ]
        path = stages.save(conn, run_id, topic, card, draft, status, blocked_by, notes)

        print(f"\n>> {status}" + (f" ({blocked_by})" if blocked_by else ""), flush=True)
        print(f">> zapisano: {path}", flush=True)
        return _done(conn, run_id, stage)

    except Exception as exc:
        db.finish_run(conn, run_id, "FAILED", stage, f"{type(exc).__name__}: {exc}"[:500])
        print(f"\n!! stanęło na etapie {stage}: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        _summary(conn, run_id)
        return 1
    finally:
        conn.close()


def _done(conn, run_id: int, stage: str) -> int:
    db.finish_run(conn, run_id, "DONE", stage, f"zatrzymany po etapie {stage}")
    _summary(conn, run_id)
    return 0


def _summary(conn, run_id: int) -> None:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total, COUNT(*) AS n FROM calls WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    print(f"\n== koszt przebiegu: ${row['total']:.4f} w {row['n']} wywołaniach ==", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
