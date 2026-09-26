"""Paid before/after drafts through production prompts; no publishing.

Requires --pay, --before-dir (stages.py + prompts snapshot), --output.
The output file is a rerun guard. Review any partial result before another run.
Run on Linux production with the shared agent lock; costs go to a test run.
"""
import argparse
import ast
import hashlib
import json
import os
import pathlib
import sys
import types
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def cases():
    # Synthetic supplied evidence: these are comprehension tests, not news claims.
    memory = ("A video generator keeps the opening scene description and first image "
              "throughout a session. Later generated frames are kept in a rolling window "
              "and discarded when they leave it. Sessions have no preset time limit. "
              "The supplied material does not measure how long a mid-session change is retained.")
    audits = ("A large AI laboratory proposes mandatory independent safety audits before "
              "releasing advanced models. It already employs a team preparing evidence for "
              "external auditors. A smaller developer says hiring such a team would strain "
              "its research budget. No cost estimates or measured safety effects were supplied. "
              "The proposed rule would cover models offered in the adopting jurisdiction, "
              "including imports; it would not govern training done abroad for other markets. "
              "The laboratory says the aim is to prevent dangerous releases. The proposal "
              "has not been enacted. The material does not establish either company's motive.")
    claims = [{"claim": x.strip() + ".", "evidence": x.strip() + ".",
               "url": "https://example.org/synthetic-audit-record"}
              for x in audits.split(".") if x.strip()]
    card = {"working_thesis": "What would a safety audit rule change, and for whom?",
            "main_mechanism": "A required audit could change both release checks and the resources needed to offer a model. The effects depend on the rule and its enforcement.",
            "confirmed_claims": claims, "citable_numbers": [], "parallel_mechanisms": [],
            "uncertain_claims": ["Actual safety improvement and compliance costs are unknown."],
            "not_established": ["Private motive", "Effectiveness of import enforcement", "Whether other jurisdictions would adopt the rule"],
            "contradictions": [], "investigation": {"question": "Who benefits, why, and what if other countries do not adopt the rule?"}}
    return [
        {"id": "memory_analysis", "kind": "analysis", "text": memory,
         "rubric": "Explain rolling memory without jargon; no invented retention time or obligatory deflation."},
        {"id": "memory_note", "kind": "note", "text": memory,
         "rubric": "A newcomer understands duration versus memory, without an invented scene or a retention figure."},
        {"id": "reasoning_note", "kind": "note", "text":
         "A model's price sheet charges for generated tokens, including hidden reasoning tokens. "
         "A worked example shows 100 visible output tokens and 900 hidden reasoning tokens, "
         "with 1000 output tokens billed. Input tokens are charged separately. This example "
         "does not establish a typical ratio or any currency amount.",
         "rubric": "Explain tokens as pieces of text and the hidden computation; no invented bill or typical ratio."},
        {"id": "electricity_comment", "kind": "comment", "text":
         "Our factory uses solar electricity directly on site, without selling surplus into "
         "the public grid. The paper says this setup avoids the export connection queue. "
         "A project that sells power into that grid still needs connection approval. "
         "The EPC contractor designs, purchases and builds the installation. The paper gives "
         "no contractor profits or evidence about who earns more.",
         "rubric": "Explain the practical distinction without unexplained EPC jargon, claiming all permits disappear, or inventing margins."},
        {"id": "audit_reply", "kind": "reply", "own": audits,
         "text": "So this proves the lab just wants to block competitors? And if China does not adopt the rule, is it pointless?",
         "rubric": "Reject the proof-of-motive leap, explain possible competitive effect and jurisdiction in plain words. No invented facts about China."},
        {"id": "source_restack", "kind": "restack", "text":
         "We now show the exact source paragraph beside each AI-generated answer. Clicking "
         "it opens that passage in the original document. This does not guarantee that the "
         "document itself is correct.",
         "rubric": "Acknowledge a concrete useful improvement, without manufacturing an objection already answered."},
        {"id": "audit_article", "kind": "article", "card": card, "text": audits,
         "rubric": "Fable explains the proposal, incentives, alternative motives, foreign jurisdiction and unknowns for a non-specialist. No invented sources, costs or promises."},
    ]


class Captured(BaseException):
    pass


def capture(module, case, conn, run_id):
    """Use actual stage assembly, stopping exactly before its first paid call."""
    import config
    import llm
    result = {}

    def intercept(purpose, system, user, **kwargs):
        result.update(purpose=purpose, system=system, prompt=user,
                      web_search=kwargs.get("web_search", False))
        raise Captured()

    with ExitStack() as stack:
        stack.enter_context(patch.object(llm, "call", side_effect=intercept))
        stack.enter_context(patch.object(config, "losowa_dlugosc", return_value=32))
        stack.enter_context(patch.object(config, "losowe_otwarcie", return_value="Start with the specific detail."))
        if case["kind"] != "analysis":
            stack.enter_context(patch.object(module, "rozbior", return_value={}))
        try:
            if case["kind"] == "article":
                module.write(conn, run_id, case["card"], "SINGLE")
            elif case["kind"] == "analysis":
                module.rozbior(conn, run_id, {"fact": case["text"]})
            elif case["kind"] == "comment":
                module.comment_on(conn, run_id, dict(text=case["text"], author="Test fixture",
                                  co_dodamy=case.get("co_dodamy", "")))
            elif case["kind"] == "restack":
                module.ocen_restack(conn, run_id, dict(tekst=case["text"], autor="Test fixture"))
            elif case["kind"] == "reply":
                module.reply_to(conn, run_id, dict(text=case["text"], author="Test fixture", under="note"),
                                {"own_text": case["own"]})
            else:
                module.note(conn, run_id, "CIEKAWOSTKA", {"fact": case["text"]}, note_form="PROSTA")
        except Captured:
            pass
    if not result:
        raise AssertionError("Stage never reached drafting: " + case["id"])
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pay", action="store_true")
    parser.add_argument("--before-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--variant", choices=("compare", "before", "after"), default="compare")
    parser.add_argument("--case", action="append", choices=[c["id"] for c in cases()])
    args = parser.parse_args()
    if not args.pay:
        parser.error("Explicit --pay is required for real API charges")
    if args.output.exists():
        parser.error("Output exists; review it before paying again")
    import fcntl
    import config
    import db
    import llm
    import stages
    baseline = types.ModuleType("voice_baseline")
    baseline.__file__ = str(args.before_dir / "stages.py")
    sys.modules[baseline.__name__] = baseline
    exec(compile(pathlib.Path(baseline.__file__).read_text(encoding="utf-8"), baseline.__file__, "exec"), baseline.__dict__)
    before_config = {}
    for node in ast.parse((args.before_dir / "config.py").read_text(encoding="utf8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {"NOTE_FORMS", "NOTE_TYPES", "KSZTALTY_MYSLI"}:
            before_config[node.targets[0].id] = ast.literal_eval(node.value)
    protected = [config.DATA_DIR / name for name in ("dziennik.jsonl", "indeks_kandydatow.json")]
    with (config.DATA_DIR / "agent.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {str(p): digest(p) for p in protected}
        conn = db.connect()
        run_id = db.start_run(conn, stage="plain_voice_comparison", tryb="test")
        result = {"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
                  "model": config.MODEL_FOR["comment"], "cases": [], "status": "RUNNING",
                  "variant": args.variant,
                  "release_sha256": {str(p.relative_to(ROOT)): digest(p) for p in
                                     [ROOT / "stages.py", *sorted(config.PROMPTS_DIR.glob("*.md"))]}}
        def save():
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        save()
        try:
            for case in cases():
                if args.case and case["id"] not in args.case:
                    continue
                item = dict(case, variants={})
                result["cases"].append(item)
                for variant, module in (("before", baseline), ("after", stages)):
                    if args.variant != "compare" and variant != args.variant:
                        continue
                    with ExitStack() as stack:
                        if variant == "before":
                            stack.enter_context(patch.object(config, "PROMPTS_DIR", args.before_dir / "prompts"))
                            stack.enter_context(patch.object(config, "STYLE_PROFILES_DIR", args.before_dir / "article_profiles"))
                            for name, value in before_config.items():
                                stack.enter_context(patch.object(config, name, value))
                        request = capture(module, case, conn, run_id)
                    raw = llm.call(request["purpose"], request["system"], request["prompt"],
                                   conn=conn, run_id=run_id, web_search=request["web_search"])
                    response = llm.parse_json(raw)
                    key = {"comment": "comment", "reply": "reply", "restack": "sentence", "note": "note", "analysis": "w_prostych_slowach", "article": "body"}[case["kind"]]
                    assert key in response, "Missing output field: " + key
                    assert response[key] is None or isinstance(response[key], str), "Invalid draft type"
                    item["variants"][variant] = {"response": response, "prompt_chars": len(request["prompt"]),
                                                "prompt": request["prompt"], "text": response[key]}
                    save()
                    print(json.dumps({"case": case["id"], "variant": variant, "response": response}, ensure_ascii=False), flush=True)
            assert before == {str(p): digest(p) for p in protected}, "Protected publication state changed"
            result["publication_state_unchanged"] = True
            result["status"] = "DONE"
            db.finish_run(conn, run_id, "DONE", note="Before/after drafts; no publication")
        except BaseException as exc:
            result["status"] = "FAILED"
            result["error"] = type(exc).__name__ + ": " + str(exc)[:500]
            db.finish_run(conn, run_id, "FAILED", note=result["error"])
            raise
        finally:
            result["calls"] = [dict(r) for r in conn.execute(
                "SELECT model,purpose,tokens_in,tokens_out,cache_hit,web_searches,cost_usd,ok,price_verified FROM calls WHERE run_id=?", (run_id,))]
            result["cost_usd"] = sum(c["cost_usd"] for c in result["calls"])
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            save()
            conn.close()


if __name__ == "__main__":
    main()
