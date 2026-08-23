"""Kontrolowany live replay rdzenia V3 na zamrożonym korpusie.

Nie czyta ani nie importuje Substacka. Etapy scout/feasibility/discovery oraz
publiczny fetch są fixture, aby jednoznacznie zamrozić wejście. Prawdziwe modele
obsługują 4×classify, synthesis, write, review i forma; jeżeli bramki zażądają
rewizji, także revise oraz drugą parę review/forma.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys


AGENT_DIR = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

import config  # noqa: E402
import pipeline_replay  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, required=True)
    parser.add_argument(
        "--max-cost-usd", type=float,
        default=pipeline_replay.LIVE_REPLAY_MAX_USD,
    )
    args = parser.parse_args()

    # Najpierw odmowa bez I/O. Brak klucza, dry-run, override modelu lub zbyt
    # wysoki limit nie mogą nawet utworzyć katalogu wyglądającego jak eksperyment.
    pipeline_replay.validate_live_preflight(args.max_cost_usd)

    workspace = args.workspace.resolve()
    if workspace != AGENT_DIR and AGENT_DIR not in workspace.parents:
        raise SystemExit("workspace live replay must stay inside agent-v3")
    if workspace.exists():
        raise SystemExit("workspace live replay must not exist before dispatch")

    expected = dict(pipeline_replay.EXPECTED_LIVE_ROUTING)
    print("LIVE REPLAY — zero Substack, frozen fetch", flush=True)
    print(
        "models=" + json.dumps(expected, sort_keys=True)
        + " base_dispatches=8 worst_case_dispatches=11"
        + f" max_cost_usd={args.max_cost_usd:.2f}",
        flush=True,
    )

    result = pipeline_replay.run_model_live(
        workspace, max_cost_usd=args.max_cost_usd)
    payload = {
        "experiment": "full-pipeline-live-core@1",
        "models": expected,
        "base_dispatches": 8,
        "worst_case_dispatches": 11,
        "max_cost_usd": args.max_cost_usd,
        "substack": "FORBIDDEN_AND_UNUSED",
        "result": dataclasses.asdict(result),
    }
    artifact = workspace / "result.json"
    artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    exposure = result.known_cost_usd + result.reserved_cost_usd
    print(
        f"exit={result.exit_code} calls={result.call_rows} "
        f"known=${result.known_cost_usd:.6f} "
        f"reserved_or_unknown=${result.reserved_cost_usd:.6f} "
        f"article={result.article_status} unknown_calls={result.unknown_calls}",
        flush=True,
    )
    print(f"artifact={artifact}", flush=True)

    if exposure > args.max_cost_usd + 1e-9:
        print("FAIL: financial exposure exceeded the live replay cap", file=sys.stderr)
        return 5
    if not result.routing_unchanged:
        print("FAIL: model routing changed during replay", file=sys.stderr)
        return 4
    if result.browser_imported or result.remote_mutations:
        print("FAIL: forbidden platform boundary was reached", file=sys.stderr)
        return 6
    if result.unknown_calls:
        print("STOP: provider cost is UNKNOWN; no further dispatch", file=sys.stderr)
        return 3
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
