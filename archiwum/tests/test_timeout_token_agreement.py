"""A deadline must allow the answer it asks for.

Topic generation carried a 60 second deadline and a 4,096 token output ceiling.
Nineteen settled generations in the durable ledger streamed at 14-18 ms per
output token (median 16.08, R^2 0.98 against output length with a 0.4 s
intercept, so the interval is streaming and not local work). 4,096 tokens at
that rate needs 65.9 seconds. The pair was unsatisfiable: a full-length answer
could not arrive in time by arithmetic.

Nobody noticed because the two numbers were chosen in different waves of the
build and nothing ever compared them. It failed twice in production, and the
second failure is owner-confirmed from the provider console - 3,746 tokens
produced and billed at 0.124795 USD for a response the client had already
walked away from. The provider is paid for the work whether or not we wait.

So the check is arithmetic, not judgement: for every paid stage, the deadline
must cover its own output ceiling at a conservative streaming rate, with real
margin on top. A timeout is a guard against hanging forever, not a performance
budget, so it belongs far above the observed distribution rather than inside
it.
"""
from __future__ import annotations

import pytest

from app.content import cost_estimate as ce
from app.content.reviewer import REVIEWER_MAX_OUTPUT_TOKENS, REVIEWER_TIMEOUT_SECONDS
from app.llm.anthropic_client import DEFAULT_PROVIDER_TIMEOUT_SECONDS
from app.research.corpus_enqueue import EVIDENCE_SYNTHESIS_TIMEOUT_SECONDS
from app.research.output_contract import RESEARCH_CARD_MAX_TOKENS
from app.topics.durable_intent import TOPIC_GENERATION_TIMEOUT_SECONDS


# Measured 14.11-17.96 ms/token over nineteen settled runs; rounded up so the
# bound stays honest on a slow day rather than on the median one.
CONSERVATIVE_MS_PER_OUTPUT_TOKEN = 20.0

# A deadline that only just covers the ceiling is the same defect one bad day
# later, so it has to clear it with room. 1.5x was chosen after 2.0 turned out
# to be a round number with nothing behind it: measured streaming varies by
# about 12 per cent (14.11-17.96 ms/token), and the rate constant above is
# already rounded up past the slowest run, so 1.5x absorbs the variance twice
# over. The defect this file exists to catch sat at 0.9x.
#
# It also has to be a bound the system can satisfy. The writer and reviewer
# deadlines are pinned in the SCHEMA, not just in code - content_writer_intents
# CHECKs timeout_seconds <= 300.0 and the content_review_resume_executions
# trigger requires exactly 300.0 - so raising those past 300 needs a migration
# and a rewrite of a durable contract. At 300s against a 164s requirement they
# sit at 1.83x, which is genuinely safe; demanding 2.0x here would only have
# forced a schema change for no measured benefit.
REQUIRED_MARGIN = 1.5

STAGES = [
    ("topic generation", TOPIC_GENERATION_TIMEOUT_SECONDS,
     ce.TOPIC_GENERATION_MAX_OUTPUT_TOKENS),
    ("evidence synthesis", EVIDENCE_SYNTHESIS_TIMEOUT_SECONDS,
     RESEARCH_CARD_MAX_TOKENS),
    ("article reviewer", REVIEWER_TIMEOUT_SECONDS, REVIEWER_MAX_OUTPUT_TOKENS),
    ("article writer", DEFAULT_PROVIDER_TIMEOUT_SECONDS,
     ce.ARTICLE_WRITER_MAX_OUTPUT_TOKENS),
    ("article research", DEFAULT_PROVIDER_TIMEOUT_SECONDS,
     ce.ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS),
]


@pytest.mark.parametrize(
    "stage,timeout_seconds,max_output_tokens",
    STAGES,
    ids=[stage for stage, _, _ in STAGES],
)
def test_deadline_covers_its_own_output_ceiling(
    stage, timeout_seconds, max_output_tokens,
):
    needed = max_output_tokens * CONSERVATIVE_MS_PER_OUTPUT_TOKEN / 1000.0
    assert timeout_seconds >= needed * REQUIRED_MARGIN, (
        f"{stage}: the deadline is {timeout_seconds:.0f}s but a full "
        f"{max_output_tokens}-token answer needs about {needed:.0f}s to stream "
        f"at {CONSERVATIVE_MS_PER_OUTPUT_TOKEN:.0f} ms/token, and {needed * REQUIRED_MARGIN:.0f}s "
        f"with the required {REQUIRED_MARGIN:g}x margin. Raise the deadline or "
        f"lower the ceiling - as written, the provider can be paid for an answer "
        f"this client will abandon."
    )


def test_the_rate_is_the_measured_one_not_a_guess():
    """Guards the constant this whole file rests on.

    If someone lowers it to make a tight stage pass, the arithmetic stops
    describing the system and the next unsatisfiable pair ships silently.
    """
    assert CONSERVATIVE_MS_PER_OUTPUT_TOKEN >= 17.96, (
        "the slowest of nineteen settled runs streamed at 17.96 ms/token; a "
        "bound below that is not conservative, it is optimistic"
    )
