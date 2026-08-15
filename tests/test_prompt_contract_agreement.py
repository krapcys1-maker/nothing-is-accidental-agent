"""Every count a prompt asks for must be a count its validator accepts.

This is the structural fix for a failure that recurred all month and cost real
money each time. A prompt says "4-8 confirmed_claims"; the size contract that
validates the answer stops at 6; a model that obeys the instruction exactly
destroys the whole paid research card. Both numbers were deliberate, chosen in
different waves of the build, and nothing ever compared them.

Three such disagreements were live in one prompt when this test was written:
confirmed_claims (8 vs 6), uncertain_claims (4 vs 3) and contradictions
(4 vs 3). None had fired yet, only because models usually volunteer fewer items
than they are allowed - which is what an unexploded defect looks like.

So the check is deliberately crude and reads the prompt TEXT out of the module
source: production prompts are inline strings inside methods that need a live
SDK client, and a test that could only reach the one prompt with a pure builder
is exactly how the other prompts drifted. Crude and total beats elegant and
partial here.

If this test fails, do not raise the contract to match the prompt without
checking the token profile: the contract ceilings are derived from a frozen
maximum payload size (MAX_CORRECT_PAYLOAD_CHARS) that feeds the cost estimate.
The prompt is almost always the side that should move.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.research import anthropic_client
from app.research import output_contract as oc


PROMPT_SOURCES = {
    "app/research/anthropic_client.py": inspect.getsource(anthropic_client),
}


def _stated_counts(source: str, field: str) -> list[tuple[str, int]]:
    """Every numeric bound a prompt states about one field, with its phrasing.

    Matches the two shapes prompts actually use: "at most N ... field" and
    "N-M field". Prompt text is wrapped across adjacent string literals, so the
    concatenation artefacts ('" "') are flattened first.
    """
    # Comments are stripped first. The fix for one of these disagreements
    # quotes the old numbers to explain itself, and scanning them matched the
    # very text that records the repair - a checker that flags its own
    # changelog teaches people to ignore it.
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    flat = re.sub(r'"\s*\n\s*"', "", body)
    flat = re.sub(r"\s+", " ", flat)
    found: list[tuple[str, int]] = []
    for match in re.finditer(
        rf"at most (\d+)(?:[^.;\"]{{0,40}}?)\b{re.escape(field)}\b", flat
    ):
        found.append((match.group(0)[:70], int(match.group(1))))
    for match in re.finditer(rf"(\d+)-(\d+) {re.escape(field)}\b", flat):
        found.append((match.group(0)[:70], int(match.group(2))))
    return found


# field name as it appears in prompt text -> the ceiling that validates it
FIELD_CEILINGS = {
    "confirmed_claims": oc.MAX_CONFIRMED_CLAIMS,
    "uncertain_claims": oc.MAX_UNCERTAIN_CLAIMS,
    "contradictions": oc.MAX_CONTRADICTIONS,
    "citable_numbers": oc.MAX_CITABLE_NUMBERS,
}


@pytest.mark.parametrize("field,ceiling", sorted(FIELD_CEILINGS.items()))
def test_no_prompt_asks_for_more_than_its_validator_accepts(field, ceiling):
    violations: list[str] = []
    for path, source in PROMPT_SOURCES.items():
        for phrasing, asked in _stated_counts(source, field):
            if asked > ceiling:
                violations.append(
                    f"{path}: prompt asks for {asked} {field} "
                    f"but the contract stops at {ceiling} - {phrasing!r}"
                )
    assert not violations, (
        "A prompt invites more items than its validator will accept, so a model "
        "obeying it destroys a paid artefact:\n  " + "\n  ".join(violations)
    )


def test_the_check_can_actually_see_the_prompts():
    """A total check that matches nothing is worse than no check at all.

    The counts live inside implicitly concatenated string literals, so a small
    change to how the prompt is written could silently make every assertion
    above vacuous. This fails loudly if that happens.
    """
    seen = {
        field: _stated_counts(source, field)
        for field in FIELD_CEILINGS
        for source in PROMPT_SOURCES.values()
    }
    assert any(seen.values()), (
        "no prompt count was found in any source - the extractor has stopped "
        f"matching the prompt text: {seen}"
    )
