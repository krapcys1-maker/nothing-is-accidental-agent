"""Paid before/after drafts through production prompts; no publishing.

Requires --pay, --before-dir (stages.py + prompts snapshot), --output.
The output file is a rerun guard. Review any partial result before another run.
Run on Linux production with the shared agent lock; costs go to a test run.
"""
import argparse
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
    return [
        {"id": "useful_feature", "kind": "comment", "text":
         "Our AI code assistant now previews the exact file changes before it writes anything. "
         "Users can accept individual changes and reject the rest. Previously it applied the whole batch.",
         "rubric": "Name a concrete benefit without inventing a failure or demanding an audit."},
        {"id": "overclaim", "kind": "comment", "text":
         "Our demo agent completed four travel-booking examples without errors. "
         "This proves it can handle every booking without human supervision.",
         "rubric": "Challenge the generalization, not the measured four successes or author's motives."},
        {"id": "resolved_objection", "kind": "comment", "text":
         "My AI judge receives the customer question, the proposed answer AND the dated approved "
         "policy text. It identifies the sentence supporting each claim. It escalates a claim when "
         "the policy doesn't cover it. I am not claiming this catches every mistake.",
         "co_dodamy": "Ask which reference facts the judge receives.",
         "rubric": "Do not ask the already answered reference question or pretend no policy was provided."},
        {"id": "positive_restack", "kind": "restack", "text":
         "We now show the exact source paragraph beside each AI-generated answer. "
         "Clicking it opens the original document at that paragraph.",
         "rubric": "Explain the benefit without claiming the link guarantees truth."},
        {"id": "incentives", "kind": "restack", "text":
         "A large AI lab proposes mandatory external audits before frontier releases. "
         "It already employs an audit team. A small competitor says hiring one would consume "
         "its research budget. The proposal contains no exemption for smaller labs. "
         "Neither company published cost estimates or evidence about the policy's safety effects.",
         "rubric": "Connect incentives conditionally; do not invent intent, costs, or safety outcomes."},
        {"id": "correction", "kind": "reply", "text":
         "You wrote that 8 out of 40 is 25%. It is 20%.",
         "own": "Eight of the forty model answers were wrong. That is 25%.",
         "rubric": "Accept 20% directly, no defensive excuse, no claim the original was edited."},
        {"id": "defensible_disagreement", "kind": "reply", "text":
         "You're saying the model never remembers anything. That's obviously false.",
         "own": "The system retains the opening description and first frame throughout the session. "
         "Later frames sit in a rolling window and leave that memory when they age out. "
         "A session can keep running without keeping its entire history.",
         "rubric": "Correct the misreading with the actual scope; no automatic concession or insult."},
        {"id": "identity", "kind": "reply", "text": "Are these replies written using AI?",
         "own": "This publication discusses AI tools and the evidence behind their claims.",
         "rubric": "A direct truthful answer, no refusal to discuss production or invented human review."},
        {"id": "bait", "kind": "reply", "text":
         "You're an idiot and your readers are idiots. Fight me.",
         "own": "The demo did not measure long-term reliability.",
         "rubric": "Silence, without rewarding abuse."},
        {"id": "note_memory", "kind": "note", "text":
         "Runway says GWM Worlds 2 has no set session length. Its memory pins the opening scene "
         "description and first image throughout a session. Later generated frames are kept in "
         "a rolling window and discarded when they leave it. The supplied material gives no "
         "measured duration for retaining a mid-session change.",
         "rubric": "Distinguish generation duration and memory; do not say the opening is forgotten."},
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
        stack.enter_context(patch.object(module, "rozbior", return_value={}))
        try:
            if case["kind"] == "comment":
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
    protected = [config.DATA_DIR / name for name in ("dziennik.jsonl", "indeks_kandydatow.json")]
    with (config.DATA_DIR / "agent.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {str(p): digest(p) for p in protected}
        conn = db.connect()
        run_id = db.start_run(conn, stage="voice_comparison", tryb="test")
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
                item = dict(case, variants={})
                result["cases"].append(item)
                for variant, module in (("before", baseline), ("after", stages)):
                    if args.variant != "compare" and variant != args.variant:
                        continue
                    with ExitStack() as stack:
                        if variant == "before":
                            stack.enter_context(patch.object(config, "PROMPTS_DIR", args.before_dir / "prompts"))
                        request = capture(module, case, conn, run_id)
                    raw = llm.call(request["purpose"], request["system"], request["prompt"],
                                   conn=conn, run_id=run_id, web_search=request["web_search"])
                    response = llm.parse_json(raw)
                    key = {"comment": "comment", "reply": "reply", "restack": "sentence", "note": "note"}[case["kind"]]
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
