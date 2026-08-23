"""CLI launcher for provider-isolated E-014 live arms; no Substack."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


AGENT_DIR = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

import editorial_live_continuation as experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=(
        experiment.ARM_ANTHROPIC, experiment.ARM_DEEPSEEK,
    ))
    parser.add_argument("--workspace", required=True, type=pathlib.Path)
    parser.add_argument("--max-cost-usd", required=True, type=float)
    parser.add_argument("--anthropic-artifact", type=pathlib.Path)
    args = parser.parse_args()

    experiment.validate_preflight(
        args.workspace, arm=args.arm, max_cost_usd=args.max_cost_usd,
        anthropic_artifact=args.anthropic_artifact,
    )
    print("E-014 PROVIDER-ISOLATED LIVE — NO SUBSTACK", flush=True)
    print(
        f"arm={args.arm} models="
        + json.dumps(experiment.MAX_CALLS_BY_ARM[args.arm], sort_keys=True)
        + f" max_calls={experiment.MAX_CALLS[args.arm]}"
        + f" max_new_cost_usd={args.max_cost_usd:.2f}"
        + f" complete_program_max_usd={experiment.PROGRAM_MAX_EXPOSURE_USD:.8f}",
        flush=True,
    )
    if args.arm == experiment.ARM_ANTHROPIC:
        print(
            "stages=write-styled(1), write-ablated(1), controlled-revise(1), "
            "note-five-forms(5); verification deferred, never publication",
            flush=True,
        )
    else:
        print(
            "stages=distinct-scout(1), feasibility(1), discovery(1), fetch-public, "
            "classify(<=4), synthesis(1), worth(1), review/form A/B(4), "
            "blind-style-judge(2), revision-evaluation(3), note-factcheck(5)",
            flush=True,
        )
    result = experiment.run_arm(
        args.workspace, arm=args.arm, max_cost_usd=args.max_cost_usd,
        anthropic_artifact=args.anthropic_artifact,
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
