"""Launcher pełnego badania live ról redakcyjnych V3, bez Substacka."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


AGENT_DIR = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

import editorial_live_experiment as experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=pathlib.Path)
    parser.add_argument(
        "--max-cost-usd", type=float, default=experiment.LIVE_EXPERIMENT_MAX_USD
    )
    args = parser.parse_args()

    # Preflight przed jakimkolwiek plikiem eksperymentu.
    experiment.validate_preflight(args.workspace, args.max_cost_usd)
    print("EDITORIAL SYSTEM LIVE — NO SUBSTACK", flush=True)
    print(
        "models=" + json.dumps(experiment.MAX_CALLS_BY_MODEL, sort_keys=True)
        + f" max_ledgered_calls={experiment.MAX_LEDGERED_MODEL_CALLS}"
        + f" max_new_cost_usd={args.max_cost_usd:.2f}"
        + f" max_program_exposure_usd="
          f"{experiment.HISTORICAL_COST_USD + args.max_cost_usd:.8f}",
        flush=True,
    )
    print(
        "stages=scout(2), feasibility(1), discovery(1), classify(<=4), "
        "synthesis(1), warto_pisac(1), write-styled(1), write-ablated(1), "
        "review/forma/style-judge, fault-injected revise, note(5), "
        "factcheck(<=5)",
        flush=True,
    )
    result = experiment.run_experiment(
        args.workspace, max_cost_usd=args.max_cost_usd
    )
    print(
        f"status={result['status']} calls={len(result['call_ledger'])} "
        f"known=${result['cost']['known_usd']:.6f} "
        f"unresolved=${result['cost']['reserved_or_unknown_usd']:.6f}",
        flush=True,
    )
    print(f"artifact={args.workspace.resolve() / 'result.json'}", flush=True)
    return experiment.exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
