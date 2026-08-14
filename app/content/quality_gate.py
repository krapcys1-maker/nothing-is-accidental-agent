"""Independent, text-based assessment of a finished draft.

The writer's own quality flags are telemetry.  They are recorded, they are
compared against this assessment, and they never grant a PASS on their own.
Everything decided here is derived from the draft text plus the frozen
Research Package (brief, confirmed claims, evidence excerpts, Research Card).

This is deliberately not a general fact checker.  It answers five bounded,
deterministic questions and fails closed when it cannot answer one of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Protocol

from app.content.contracts import ArticleBrief, ContentBrief, FakeDraft
from app.content.foundation import FrozenEvidenceItem, canonical_json, sha256_text


DRAFT_QUALITY_ASSESSOR_VERSION = "question_semantic_boundary_assessor_v4"

# Finding codes.
UNSUPPORTED_FACTUAL_CLAIM = "UNSUPPORTED_FACTUAL_CLAIM"
UNATTRIBUTED_SOURCE_APPEAL = "UNATTRIBUTED_SOURCE_APPEAL"
FABRICATED_PERSONAL_EXPERIENCE = "FABRICATED_PERSONAL_EXPERIENCE"
EVIDENCE_ID_NOT_USED = "EVIDENCE_ID_NOT_USED"
EVIDENCE_ID_OUT_OF_BRIEF = "EVIDENCE_ID_OUT_OF_BRIEF"
BRIEF_REQUIRED_FACT_MISSING = "BRIEF_REQUIRED_FACT_MISSING"
BRIEF_FORBIDDEN_CLAIM_PRESENT = "BRIEF_FORBIDDEN_CLAIM_PRESENT"
SELF_REPORT_DIVERGED = "SELF_REPORT_DIVERGED"
CLAIM_ACCOUNTING_REVIEW_MISSING = "CLAIM_ACCOUNTING_REVIEW_MISSING"
CLAIM_ACCOUNTING_REVIEW_FAILED = "CLAIM_ACCOUNTING_REVIEW_FAILED"
CLAIM_ACCOUNTING_ENTRY_MALFORMED = "CLAIM_ACCOUNTING_ENTRY_MALFORMED"
CLAIM_ACCOUNTING_COVERAGE_MISSING = "CLAIM_ACCOUNTING_COVERAGE_MISSING"
CLAIM_ACCOUNTING_COVERAGE_DUPLICATE = "CLAIM_ACCOUNTING_COVERAGE_DUPLICATE"
CLAIM_ACCOUNTING_COVERAGE_EXTRA = "CLAIM_ACCOUNTING_COVERAGE_EXTRA"
CLAIM_ACCOUNTING_IDENTITY_MISMATCH = "CLAIM_ACCOUNTING_IDENTITY_MISMATCH"
CLAIM_CLASSIFICATION_UNKNOWN = "CLAIM_CLASSIFICATION_UNKNOWN"
CLAIM_REVIEW_REASON_MISSING = "CLAIM_REVIEW_REASON_MISSING"
CLAIM_REVIEW_BLOCKED = "CLAIM_REVIEW_BLOCKED"
FACTUAL_CLAIM_EVIDENCE_MISSING = "FACTUAL_CLAIM_EVIDENCE_MISSING"
FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE = "FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE"
FACTUAL_CLAIM_SCOPE_NOT_CONFIRMED = "FACTUAL_CLAIM_SCOPE_NOT_CONFIRMED"
INFERENCE_CONTAINS_EXTERNAL_FACT = "INFERENCE_CONTAINS_EXTERNAL_FACT"
NON_FACTUAL_CLASSIFICATION_INCONSISTENT = "NON_FACTUAL_CLASSIFICATION_INCONSISTENT"
# An inference is reasoning *over* the frozen material, so it never carries its
# own citation.  A cited inference is either a grounded fact that was filed
# under the wrong class, or a new claim wearing an inference label; the first
# live review showed both, so the cardinality is now an explicit invariant.
INFERENCE_EVIDENCE_NOT_EMPTY = "INFERENCE_EVIDENCE_NOT_EMPTY"
DOCUMENT_REVIEW_MISSING = "DOCUMENT_REVIEW_MISSING"
DOCUMENT_REVIEW_FAILED = "DOCUMENT_REVIEW_FAILED"

_STOPWORDS = frozenset("""
a an and are as at be been but by for from had has have how in into is it its
of on or that the their them there these they this to was were what when
which who why will with would about after also because before between could
during more most not only other over should some such than then those through
under until upon very while your you our we us his her him she he i my me
""".split())

# Only *checkable* quantities count as factual claims.  A bare small integer
# is usually enumeration ("the second reason"), so it is not treated as a
# statistic; a percentage, magnitude, currency amount, year, decimal or
# grouped number is.
_QUANTITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%|percent|per cent)", re.IGNORECASE),
    re.compile(
        r"\d[\d,]*(?:\.\d+)?\s*(?:million|billion|trillion|thousand|bn|tn)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)"),
    re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])"),
    re.compile(r"(?<!\d)(?:1[6-9]\d{2}|20\d{2})(?!\d)"),
    re.compile(r"(?<![\d.,])\d{4,}(?![\d.,])"),
)

# Appeals to an outside authority the draft does not actually carry.
_SOURCE_APPEAL = re.compile(
    r"(?i)\b(?:according to|a (?:recent |new )?(?:study|survey|report|paper|"
    r"analysis)\s+(?:found|shows?|showed|says?|said|suggests?)|research (?:shows?|"
    r"suggests?|finds?|found)|data from|statistics from|experts? (?:say|said|agree)|"
    r"scientists? (?:say|said|found)|analysts? (?:say|said|estimate))\b"
)

# First-person lived experience, as opposed to first-person reasoning.
_PERSONAL_EXPERIENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(?:i|we)\s+(?:remember|recall|grew up|used to|once|visited|"
        r"travelled|traveled|went|drove|flew|walked|stayed|lived|worked|met|"
        r"saw|watched|heard|spoke|talked|asked|bought|ordered|tried|noticed|"
        r"stood|sat|waited)\b"
    ),
    re.compile(
        r"(?i)\bmy\s+(?:family|childhood|mother|father|parents|brother|sister|"
        r"friend|colleague|neighbour|neighbor|grandmother|grandfather|wife|"
        r"husband|partner|son|daughter|hometown|school|university|office|"
        r"landlord|doctor|first job)\b"
    ),
    re.compile(
        r"(?i)\b(?:a|my)\s+(?:friend|colleague|neighbour|neighbor|relative)\s+"
        r"(?:of mine\s+)?(?:told|said|showed|mentioned|explained)\b"
    ),
    re.compile(
        r"(?i)\b(?:last|this)\s+(?:week|month|year|summer|winter|spring|autumn|fall)"
        r"\s*,?\s+(?:i|we)\b"
    ),
    re.compile(r"(?i)\bwhen (?:i|we) (?:was|were|visited|lived|worked|arrived)\b"),
    re.compile(r"(?i)\bin my (?:experience|own life|twenties|thirties|forties)\b"),
)

# Explicitly allowed first-person reasoning; never a personal-experience hit.
_OPINION_MARKER = re.compile(
    r"(?i)\b(?:i|we)\s+(?:think|argue|suspect|believe|doubt|suggest|would argue|"
    r"am not sure|cannot|can't|do not|don't|note|read|call)\b"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Claims of established proof, and the negation guard that keeps an explicit
# disclaimer ("that does not prove a universal rule") from reading as one.
_PROOF_ASSERTION = re.compile(
    r"(?i)\b(?:proves?|proven|confirms?|shows conclusively|definitively|"
    r"it is a fact that|studies confirm)\b"
)
_NEGATION = re.compile(
    r"(?i)\b(?:not|n't|never|hardly|scarcely|barely|no|nothing|neither|nor|"
    r"cannot|rarely|seldom)\b"
)


def _is_negated(sentence: str, position: int) -> bool:
    """True when a negation governs the assertion starting at ``position``."""
    window = sentence[max(0, position - 60):position]
    clause = re.split(r"[;:,]", window)[-1]
    return _NEGATION.search(clause) is not None


class QualityCheck(str, Enum):
    """The five bounded questions this assessor answers."""

    FACTUAL_CLAIM_SUPPORT = "FACTUAL_CLAIM_SUPPORT"
    NO_OUT_OF_CORPUS_CLAIMS = "NO_OUT_OF_CORPUS_CLAIMS"
    NO_FABRICATED_EXPERIENCE = "NO_FABRICATED_EXPERIENCE"
    EVIDENCE_ID_CORRESPONDENCE = "EVIDENCE_ID_CORRESPONDENCE"
    BRIEF_COMPLIANCE = "BRIEF_COMPLIANCE"


class ClaimClassification(str, Enum):
    """Provider-agnostic classes required for every ARTICLE segment."""

    EVIDENCE_GROUNDED_FACT = "EVIDENCE_GROUNDED_FACT"
    ARGUMENT_OR_INFERENCE = "ARGUMENT_OR_INFERENCE"
    NON_FACTUAL_PROSE = "NON_FACTUAL_PROSE"
    UNKNOWN = "UNKNOWN"


class ClaimReviewOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class SegmentKind(str, Enum):
    """Which visible part of the article a coverage unit comes from.

    The first live review accounted only for body sentences, so a title could
    promise a mechanism the article never explained and still reach APPROVE.
    Every visible element is now its own reviewable segment.
    """

    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"


@dataclass(frozen=True)
class DraftClaimSegment:
    """One deterministic sentence-sized coverage unit from the actual draft."""

    ordinal: int
    segment_id: str
    fingerprint: str
    text: str
    kind: SegmentKind = SegmentKind.BODY

    def payload(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "segment_id": self.segment_id,
            "fingerprint": self.fingerprint,
            "text": self.text,
            "kind": self.kind.value,
        }


@dataclass(frozen=True)
class ClaimAccountingEntry:
    """Independent reviewer's accounting for exactly one draft segment."""

    segment_id: str
    segment_fingerprint: str
    classification: ClaimClassification
    evidence_ids: tuple[str, ...]
    reason: str
    outcome: ClaimReviewOutcome
    contains_external_fact: bool | None = None


#: The one canonical consistency rule for a claim-accounting entry.
#:
#: ``contains_external_fact`` says the segment asserts a fact about the world.
#: That is only legal for EVIDENCE_GROUNDED_FACT, which must then cite the
#: evidence carrying it.  Reasoning and framing assert no outside fact and cite
#: nothing.  The rule lived only in the shared quality gate, so the REVIEW-ONLY
#: initial path — which reads entry outcomes directly — accepted a PASS entry
#: classified ARGUMENT_OR_INFERENCE or NON_FACTUAL_PROSE while also declaring
#: contains_external_fact=true.  It is now one predicate with one definition,
#: enforced at the parser boundary and by every consumer of a reviewer result.
CLASSIFICATION_CONTRACT_VIOLATION = "CLASSIFICATION_CONTRACT_VIOLATION"


def classification_contract_error(
    *,
    classification: "ClaimClassification",
    evidence_ids: tuple[str, ...],
    contains_external_fact: bool | None,
    outcome: "ClaimReviewOutcome | None" = None,
) -> str | None:
    """Return the exact violation of the canonical entry contract, or ``None``.

    ``outcome`` matters for one case only: an uncited EVIDENCE_GROUNDED_FACT is
    how the reviewer reports a factual claim the evidence does not support.
    That must remain expressible, so it is legal while the outcome is BLOCK and
    illegal as a PASS.
    """
    if classification is ClaimClassification.EVIDENCE_GROUNDED_FACT:
        if not evidence_ids and outcome is not ClaimReviewOutcome.BLOCK:
            return (
                "EVIDENCE_GROUNDED_FACT cannot PASS without at least one evidence "
                "id; report an unsupported factual claim as BLOCK instead."
            )
        # The class is defined as "asserts a fact about the world", so denying
        # the external fact contradicts the classification exactly as much as
        # claiming one on an inference does.  The flag is therefore equivalent
        # to the class, in both directions.
        if contains_external_fact is not True:
            return (
                "EVIDENCE_GROUNDED_FACT requires contains_external_fact=true; "
                "a segment asserting no outside fact is not a grounded fact."
            )
        return None
    if classification in (
        ClaimClassification.ARGUMENT_OR_INFERENCE,
        ClaimClassification.NON_FACTUAL_PROSE,
    ):
        if evidence_ids:
            return f"{classification.value} requires evidence_ids to be exactly []."
        if contains_external_fact is not False:
            return (
                f"{classification.value} requires contains_external_fact=false; "
                "a segment asserting an outside fact is not reasoning or framing."
            )
        # BLOCK is how an UNSUPPORTED FACT is reported. It is not a way of
        # saying "this is not a fact", and the reviewer was using it that way:
        # on a finished draft it correctly classified transitions, framing
        # titles and authorial signposting as NON_FACTUAL_PROSE and then
        # blocked them anyway, with reasons like "Transition". Ten such
        # segments failed an otherwise sound article. Reasoning that does not
        # follow, or framing that smuggles a claim, is not this class at all -
        # it is an EVIDENCE_GROUNDED_FACT without evidence, which is exactly
        # what BLOCK exists for.
        if outcome is ClaimReviewOutcome.BLOCK:
            return (
                f"{classification.value} cannot be BLOCK; BLOCK reports a "
                "factual claim the evidence does not support. If the segment "
                "does assert such a claim, classify it EVIDENCE_GROUNDED_FACT."
            )
        return None
    return "classification is not one of the three supported classes."


class DocumentCheck(str, Enum):
    """Whole-article questions that per-segment accounting cannot answer.

    Segment accounting is local: every sentence can be individually defensible
    while the finished article still promises one mechanism and explains a
    different one.  The first live review produced exactly that, so these are
    now first-class gates rather than editorial advice.
    """

    TITLE_REFLECTS_BODY = "TITLE_REFLECTS_BODY"
    TITLE_PROMISE_FULFILLED = "TITLE_PROMISE_FULFILLED"
    TITLE_MECHANISM_EXPLAINED = "TITLE_MECHANISM_EXPLAINED"
    BRIEF_QUESTION_ANSWERED = "BRIEF_QUESTION_ANSWERED"
    THESIS_CONSISTENT = "THESIS_CONSISTENT"
    CONCLUSIONS_WITHIN_EVIDENCE = "CONCLUSIONS_WITHIN_EVIDENCE"


@dataclass(frozen=True)
class DocumentReview:
    """The reviewer's whole-article verdict plus concrete rewrite instructions."""

    checks: dict[DocumentCheck, bool]
    findings: tuple[str, ...]

    @property
    def failed_checks(self) -> tuple[DocumentCheck, ...]:
        return tuple(check for check in DocumentCheck if not self.checks.get(check, False))

    @property
    def approved(self) -> bool:
        return not self.failed_checks

    def payload(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "checks": {check.value: bool(self.checks.get(check, False))
                       for check in DocumentCheck},
            "failed_checks": [check.value for check in self.failed_checks],
            "findings": list(self.findings),
        }


class ClaimAccountingReviewPort(Protocol):
    """Independent ARTICLE review boundary; the writer cannot implement it."""

    @property
    def reviewer_version(self) -> str: ...

    def review(
        self, *, draft: FakeDraft, brief: ContentBrief,
        evidence: tuple[FrozenEvidenceItem, ...],
        segments: tuple[DraftClaimSegment, ...],
    ) -> tuple[ClaimAccountingEntry | dict[str, Any], ...]: ...


@dataclass(frozen=True)
class DraftQualityAssessment:
    """Independent verdict per check, plus the writer's own claims as telemetry."""

    assessor_version: str
    draft_fingerprint: str
    checks: dict[QualityCheck, bool]
    findings: tuple[dict[str, Any], ...]
    self_report: dict[str, Any]
    self_report_divergences: tuple[str, ...]
    claim_accounting: tuple[dict[str, Any], ...] = ()
    claim_coverage_complete: bool = False
    claim_reviewer_version: str | None = None

    def passed(self, check: QualityCheck) -> bool:
        return bool(self.checks[check])

    def findings_for(self, check: QualityCheck) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self.findings if item.get("check") == check.value)

    def payload(self) -> dict[str, Any]:
        return {
            "assessor_version": self.assessor_version,
            "draft_fingerprint": self.draft_fingerprint,
            "checks": {check.value: self.checks[check] for check in QualityCheck},
            "findings": [dict(item) for item in self.findings],
            "self_report": dict(self.self_report),
            "self_report_divergences": list(self.self_report_divergences),
            "claim_accounting": [dict(item) for item in self.claim_accounting],
            "claim_coverage_complete": self.claim_coverage_complete,
            "claim_reviewer_version": self.claim_reviewer_version,
        }

    def fingerprint(self) -> str:
        return sha256_text(canonical_json(self.payload()))


def _content_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9'\-]*", text.lower())
    return {token for token in tokens if len(token) >= 4 and token not in _STOPWORDS}


def _numeric_tokens(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in _QUANTITY_PATTERNS:
        for match in pattern.finditer(text):
            normalized = re.sub(r"[\s,]", "", match.group(0)).lower().rstrip(".")
            if normalized and any(ch.isdigit() for ch in normalized):
                found.add(normalized)
    return found


def _digit_runs(text: str) -> set[str]:
    """Bare digit sequences, so ``$4.2m`` still matches ``4.2`` in a source."""
    return {run for run in re.findall(r"\d[\d.]*", text) if run.strip(".")}


def _sentences(body: str) -> list[str]:
    parts: list[str] = []
    for block in body.split("\n"):
        for sentence in _SENTENCE_SPLIT.split(block):
            cleaned = sentence.strip()
            if cleaned:
                parts.append(cleaned)
    return parts


_SEGMENT_ID_PREFIX = {
    SegmentKind.TITLE: "title",
    SegmentKind.SUBTITLE: "subtitle",
    SegmentKind.BODY: "sentence",
}


def _visible_elements(draft: FakeDraft) -> list[tuple[SegmentKind, str]]:
    """Every reader-visible element of the draft, in reading order.

    Title and subtitle are single units; the body is split into sentences.
    ``subtitle`` is read defensively because the current draft contract does
    not define one — when that field is added, it is covered without a second
    change here.
    """
    elements: list[tuple[SegmentKind, str]] = []
    title = (draft.title or "").strip()
    if title:
        elements.append((SegmentKind.TITLE, title))
    subtitle = (getattr(draft, "subtitle", None) or "").strip()
    if subtitle:
        elements.append((SegmentKind.SUBTITLE, subtitle))
    elements.extend(
        (SegmentKind.BODY, sentence) for sentence in _sentences(draft.body or "")
    )
    return elements


def build_claim_segments(draft: FakeDraft) -> tuple[DraftClaimSegment, ...]:
    """Build the complete deterministic ARTICLE coverage surface.

    ``kind`` is part of the fingerprint preimage, so a title can never be
    silently replayed as a body sentence and an accounting produced against
    the older body-only surface cannot be reused.
    """
    segments: list[DraftClaimSegment] = []
    per_kind: dict[SegmentKind, int] = {}
    draft_fingerprint = draft.fingerprint()
    for ordinal, (kind, raw) in enumerate(_visible_elements(draft)):
        normalized = " ".join(raw.split())
        local = per_kind.get(kind, 0)
        per_kind[kind] = local + 1
        fingerprint = sha256_text(canonical_json({
            "draft_fingerprint": draft_fingerprint,
            "kind": kind.value,
            "ordinal": ordinal,
            "text": normalized,
        }))
        segments.append(DraftClaimSegment(
            ordinal=ordinal,
            segment_id=f"{_SEGMENT_ID_PREFIX[kind]}:{local}:{fingerprint[:16]}",
            fingerprint=fingerprint,
            text=normalized,
            kind=kind,
        ))
    return tuple(segments)


# NON_FACTUAL_PROSE remains a narrow structural exemption for segments without
# explicit question punctuation.  A supported question marker anywhere in the
# segment makes that shortcut unavailable.  This is a punctuation-presence
# contract only; meaning remains owned by the independent semantic reviewer.
_DECLARATIVE_PREDICATE = re.compile(
    r"(?i)\b(?:am|is|are|was|were|be|been|being|has|have|had|do|does|did|"
    r"can|could|will|would|shall|should|may|might|must|"
    r"[a-z][a-z'\-]{2,}(?:s|ed|ing))\b"
)
_NON_FACTUAL_TRANSITION = re.compile(
    r"(?i)^(?:now|first|next|instead|meanwhile|for now|a step back)\b"
)


def _clearly_non_factual(segment: DraftClaimSegment) -> bool:
    text = segment.text.strip()
    if "?" in text or "？" in text:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    return len(words) <= 1 or (
        _NON_FACTUAL_TRANSITION.search(text) is not None
        and _DECLARATIVE_PREDICATE.search(text) is None
    )


def _claim_finding(code: str, segment: DraftClaimSegment | None, detail: str) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "check": QualityCheck.NO_OUT_OF_CORPUS_CLAIMS.value,
        "code": code,
        "detail": detail,
    }
    if segment is not None:
        finding.update({
            "segment_id": segment.segment_id,
            "segment_fingerprint": segment.fingerprint,
            "sentence": segment.text[:240],
        })
    return finding


def _coerce_claim_entry(raw: object) -> ClaimAccountingEntry:
    if isinstance(raw, ClaimAccountingEntry):
        return raw
    if not isinstance(raw, dict):
        raise TypeError("claim accounting entry must be a mapping")
    evidence_ids_raw = raw.get("evidence_ids", ())
    if not isinstance(evidence_ids_raw, (list, tuple)) or not all(
        isinstance(value, str) for value in evidence_ids_raw
    ):
        raise TypeError("evidence_ids must be a sequence of strings")
    external = raw.get("contains_external_fact")
    if external is not None and not isinstance(external, bool):
        raise TypeError("contains_external_fact must be boolean or null")
    return ClaimAccountingEntry(
        segment_id=str(raw["segment_id"]),
        segment_fingerprint=str(raw["segment_fingerprint"]),
        classification=ClaimClassification(str(raw["classification"])),
        evidence_ids=tuple(evidence_ids_raw),
        reason=str(raw["reason"]),
        outcome=ClaimReviewOutcome(str(raw["outcome"])),
        contains_external_fact=external,
    )


def _account_article_claims(
    *,
    draft: FakeDraft,
    brief: ContentBrief,
    evidence: tuple[FrozenEvidenceItem, ...],
    reviewer: ClaimAccountingReviewPort | None,
    propagate_reviewer_errors: bool = False,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], bool, str | None]:
    """Validate complete independent accounting; every ambiguity is BLOCK."""
    segments = build_claim_segments(draft)
    by_id = {segment.segment_id: segment for segment in segments}
    allowed_evidence = {item.confirmed_claim_id for item in evidence}
    findings: list[dict[str, Any]] = []
    reviewer_version: str | None = None
    parsed: list[ClaimAccountingEntry] = []

    if reviewer is None:
        findings.append(_claim_finding(
            CLAIM_ACCOUNTING_REVIEW_MISSING,
            None,
            "ARTICLE requires an independent claim-accounting reviewer",
        ))
    else:
        try:
            reviewer_version = reviewer.reviewer_version
            if (
                not isinstance(reviewer_version, str)
                or not reviewer_version.strip()
                or reviewer_version != reviewer_version.strip()
            ):
                raise ValueError("reviewer_version must be a non-empty canonical string")
            raw_entries = reviewer.review(
                draft=draft,
                brief=brief,
                evidence=evidence,
                segments=segments,
            )
            if not isinstance(raw_entries, tuple):
                raise TypeError("claim accounting review must return a tuple")
            for raw in raw_entries:
                try:
                    parsed.append(_coerce_claim_entry(raw))
                except (KeyError, TypeError, ValueError) as exc:
                    findings.append(_claim_finding(
                        CLAIM_ACCOUNTING_ENTRY_MALFORMED,
                        None,
                        " ".join(str(exc).split())[:240],
                    ))
        except Exception as exc:
            if propagate_reviewer_errors:
                raise
            findings.append(_claim_finding(
                CLAIM_ACCOUNTING_REVIEW_FAILED,
                None,
                " ".join(str(exc).split())[:240] or "reviewer failed",
            ))
        else:
            # Segment accounting cannot see the article.  A reviewer that also
            # returns a whole-article verdict makes it binding here, so a draft
            # whose title promises an unexplained mechanism fails the gate even
            # when every individual sentence is defensible.
            document_review = getattr(reviewer, "last_document_review", None)
            if isinstance(document_review, DocumentReview):
                if not document_review.approved:
                    findings.append(_claim_finding(
                        DOCUMENT_REVIEW_FAILED,
                        None,
                        "; ".join([
                            ",".join(
                                check.value
                                for check in document_review.failed_checks
                            ),
                            *document_review.findings,
                        ])[:240],
                    ))
            elif document_review is not None:
                findings.append(_claim_finding(
                    DOCUMENT_REVIEW_MISSING,
                    None,
                    "reviewer returned an unusable whole-article verdict",
                ))

    grouped: dict[str, list[ClaimAccountingEntry]] = {}
    for entry in parsed:
        grouped.setdefault(entry.segment_id, []).append(entry)
    for segment_id, entries in grouped.items():
        if segment_id not in by_id:
            findings.append(_claim_finding(
                CLAIM_ACCOUNTING_COVERAGE_EXTRA,
                None,
                f"reviewer returned unknown segment {segment_id[:120]}",
            ))
        elif len(entries) != 1:
            findings.append(_claim_finding(
                CLAIM_ACCOUNTING_COVERAGE_DUPLICATE,
                by_id[segment_id],
                "reviewer returned more than one accounting entry",
            ))

    audit: list[dict[str, Any]] = []
    for segment in segments:
        entries = grouped.get(segment.segment_id, [])
        if len(entries) != 1:
            if not entries:
                findings.append(_claim_finding(
                    CLAIM_ACCOUNTING_COVERAGE_MISSING,
                    segment,
                    "reviewer omitted this draft segment",
                ))
            audit.append({
                **segment.payload(),
                "classification": ClaimClassification.UNKNOWN.value,
                "evidence_ids": [],
                "reviewer_reason": "segment was not uniquely accounted",
                "reviewer_outcome": ClaimReviewOutcome.BLOCK.value,
                "contains_external_fact": None,
                "reviewer_version": reviewer_version,
            })
            continue

        entry = entries[0]
        local_codes: list[str] = []
        # The same tolerance the parser applies, for the same reason: the
        # reviewer echoes a value we supplied and is asked for its first 16
        # characters, because a full 64-character hash per segment does not fit
        # the output budget of an article-length review. segment_id already
        # pins that prefix. Keeping this comparison exact while the parser
        # accepted an abbreviation flagged every segment of a good draft as an
        # identity mismatch - one rule living in two places, disagreeing.
        echoed = entry.segment_fingerprint.strip().rstrip(".…").strip()
        if (
            not echoed
            or len(echoed) < 16
            or not segment.fingerprint.startswith(echoed)
        ):
            local_codes.append(CLAIM_ACCOUNTING_IDENTITY_MISMATCH)
        if not entry.reason.strip():
            local_codes.append(CLAIM_REVIEW_REASON_MISSING)
        outside = sorted(set(entry.evidence_ids) - allowed_evidence)

        # One canonical contract, shared with the parser boundary.  The
        # per-class codes below stay the operator-facing vocabulary.
        contract_error = classification_contract_error(
            classification=entry.classification,
            evidence_ids=entry.evidence_ids,
            contains_external_fact=entry.contains_external_fact,
            outcome=entry.outcome,
        )
        if entry.classification is ClaimClassification.EVIDENCE_GROUNDED_FACT:
            if not entry.evidence_ids:
                local_codes.append(FACTUAL_CLAIM_EVIDENCE_MISSING)
            if outside:
                local_codes.append(FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE)
            if entry.outcome is not ClaimReviewOutcome.PASS:
                local_codes.append(FACTUAL_CLAIM_SCOPE_NOT_CONFIRMED)
        elif entry.classification is ClaimClassification.ARGUMENT_OR_INFERENCE:
            if entry.contains_external_fact is not False:
                local_codes.append(INFERENCE_CONTAINS_EXTERNAL_FACT)
            # An inference reasons over the frozen material and therefore cites
            # nothing of its own.  Citing anything means it actually asserted a
            # fact, which belongs in EVIDENCE_GROUNDED_FACT and must be judged
            # against scope there rather than passing as "reasoning".
            if entry.evidence_ids:
                local_codes.append(INFERENCE_EVIDENCE_NOT_EMPTY)
            if outside:
                local_codes.append(FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE)
        elif entry.classification is ClaimClassification.NON_FACTUAL_PROSE:
            if entry.contains_external_fact is not False or not _clearly_non_factual(segment):
                local_codes.append(NON_FACTUAL_CLASSIFICATION_INCONSISTENT)
            if entry.evidence_ids:
                local_codes.append(NON_FACTUAL_CLASSIFICATION_INCONSISTENT)
        else:
            local_codes.append(CLAIM_CLASSIFICATION_UNKNOWN)
        if contract_error is not None and not local_codes:
            local_codes.append(CLASSIFICATION_CONTRACT_VIOLATION)

        if entry.outcome is ClaimReviewOutcome.BLOCK and not local_codes:
            local_codes.append(CLAIM_REVIEW_BLOCKED)
        for code in dict.fromkeys(local_codes):
            detail = entry.reason.strip() or "claim accounting invariant failed"
            finding = _claim_finding(code, segment, detail)
            if outside:
                finding["outside_evidence_ids"] = outside
            findings.append(finding)
        audit.append({
            **segment.payload(),
            "classification": entry.classification.value,
            "evidence_ids": list(entry.evidence_ids),
            "reviewer_reason": entry.reason,
            "reviewer_outcome": (
                ClaimReviewOutcome.BLOCK.value
                if local_codes else entry.outcome.value
            ),
            "contains_external_fact": entry.contains_external_fact,
            "reviewer_version": reviewer_version,
        })

    complete = (
        reviewer is not None
        and len(audit) == len(segments)
        and not any(
            item["code"] in {
                CLAIM_ACCOUNTING_REVIEW_MISSING,
                CLAIM_ACCOUNTING_REVIEW_FAILED,
                CLAIM_ACCOUNTING_ENTRY_MALFORMED,
                CLAIM_ACCOUNTING_COVERAGE_MISSING,
                CLAIM_ACCOUNTING_COVERAGE_DUPLICATE,
                CLAIM_ACCOUNTING_COVERAGE_EXTRA,
                CLAIM_ACCOUNTING_IDENTITY_MISMATCH,
            }
            for item in findings
        )
    )
    return tuple(audit), tuple(findings), complete, reviewer_version


def _allowed_corpus_text(
    brief: ContentBrief,
    evidence: tuple[FrozenEvidenceItem, ...],
    research_card: dict[str, Any] | None,
) -> str:
    chunks: list[str] = []
    for item in evidence:
        chunks.extend((item.claim_text, item.source_claim_text, item.excerpt_text))
    chunks.extend(brief.evidence_ids)
    if isinstance(brief, ArticleBrief):
        chunks.extend(brief.required_facts)
        chunks.append(brief.central_thesis)
        chunks.append(brief.counterargument_or_limitation)
    if research_card:
        for key in ("confirmed_claims", "citable_numbers", "uncertain_claims"):
            value = research_card.get(key)
            if isinstance(value, list):
                chunks.extend(str(entry) for entry in value)
            elif isinstance(value, str):
                chunks.append(value)
        for key in ("working_thesis", "main_mechanism", "strongest_counterargument"):
            value = research_card.get(key)
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(chunk for chunk in chunks if isinstance(chunk, str))


def assess_draft(
    draft: FakeDraft,
    brief: ContentBrief,
    *,
    evidence: tuple[FrozenEvidenceItem, ...],
    research_card: dict[str, Any] | None = None,
    claim_reviewer: ClaimAccountingReviewPort | None = None,
    min_evidence_overlap: int = 2,
    require_independent_review: bool | None = None,
    propagate_reviewer_errors: bool = False,
) -> DraftQualityAssessment:
    """Assess the actual text against the frozen package; ignore self-praise."""
    body = draft.body or ""
    findings: list[dict[str, Any]] = []
    corpus_text = _allowed_corpus_text(brief, evidence, research_card)
    corpus_numbers = _numeric_tokens(corpus_text) | _digit_runs(corpus_text)
    corpus_tokens = _content_tokens(corpus_text)
    review_required = (
        isinstance(brief, ArticleBrief)
        if require_independent_review is None
        else require_independent_review
    )
    claim_accounting: tuple[dict[str, Any], ...] = ()
    claim_findings: tuple[dict[str, Any], ...] = ()
    claim_coverage_complete = not review_required
    claim_reviewer_version: str | None = None
    if review_required or claim_reviewer is not None:
        (
            claim_accounting,
            claim_findings,
            claim_coverage_complete,
            claim_reviewer_version,
        ) = _account_article_claims(
            draft=draft,
            brief=brief,
            evidence=evidence,
            reviewer=claim_reviewer,
            propagate_reviewer_errors=propagate_reviewer_errors,
        )

    # Deterministic floors below may only add blockers. Complete independent
    # claim accounting above owns ARTICLE semantic classification and coverage;
    # no unrecognised sentence is released as stylistic prose.
    unsupported: list[dict[str, Any]] = []
    appeals: list[dict[str, Any]] = list(claim_findings)

    for sentence in _sentences(body):
        numbers = _numeric_tokens(sentence)
        for number in sorted(numbers):
            bare = re.sub(r"[^\d.]", "", number).strip(".")
            if number in corpus_numbers or (bare and bare in corpus_numbers):
                continue
            unsupported.append({
                "check": QualityCheck.FACTUAL_CLAIM_SUPPORT.value,
                "code": UNSUPPORTED_FACTUAL_CLAIM,
                "token": number,
                "sentence": sentence[:240],
            })
        if _SOURCE_APPEAL.search(sentence):
            salient = _content_tokens(sentence)
            if len(salient & corpus_tokens) < min_evidence_overlap:
                appeals.append({
                    "check": QualityCheck.NO_OUT_OF_CORPUS_CLAIMS.value,
                    "code": UNATTRIBUTED_SOURCE_APPEAL,
                    "sentence": sentence[:240],
                })

    # An assertion framed as established proof, absent from the corpus, is
    # also out-of-corpus material.  A negated form ("does not prove") is the
    # opposite move and must not be flagged.
    for sentence in _sentences(body):
        match = _PROOF_ASSERTION.search(sentence)
        if match is None or _is_negated(sentence, match.start()):
            continue
        salient = _content_tokens(sentence)
        if salient and len(salient & corpus_tokens) < min_evidence_overlap:
            appeals.append({
                "check": QualityCheck.NO_OUT_OF_CORPUS_CLAIMS.value,
                "code": UNATTRIBUTED_SOURCE_APPEAL,
                "sentence": sentence[:240],
            })

    findings.extend(unsupported)
    findings.extend(appeals)

    # 3. Fabricated lived experience, distinguished from opinion.
    experience: list[dict[str, Any]] = []
    for sentence in _sentences(body):
        if _OPINION_MARKER.search(sentence) and not any(
            pattern.search(sentence) for pattern in _PERSONAL_EXPERIENCE_PATTERNS
        ):
            continue
        for pattern in _PERSONAL_EXPERIENCE_PATTERNS:
            match = pattern.search(sentence)
            if match is not None:
                experience.append({
                    "check": QualityCheck.NO_FABRICATED_EXPERIENCE.value,
                    "code": FABRICATED_PERSONAL_EXPERIENCE,
                    "match": match.group(0),
                    "sentence": sentence[:240],
                })
                break
    findings.extend(experience)

    # 4. Declared evidence IDs must correspond to material actually used.
    allowed_ids = set(brief.evidence_ids)
    by_id = {item.confirmed_claim_id: item for item in evidence}
    correspondence: list[dict[str, Any]] = []
    body_tokens = _content_tokens(body)
    for declared in draft.evidence_ids_used:
        if declared not in allowed_ids:
            correspondence.append({
                "check": QualityCheck.EVIDENCE_ID_CORRESPONDENCE.value,
                "code": EVIDENCE_ID_OUT_OF_BRIEF,
                "evidence_id": declared,
            })
            continue
        item = by_id.get(declared)
        if item is None:
            correspondence.append({
                "check": QualityCheck.EVIDENCE_ID_CORRESPONDENCE.value,
                "code": EVIDENCE_ID_NOT_USED,
                "evidence_id": declared,
                "detail": "declared evidence is absent from the frozen manifest",
            })
            continue
        item_tokens = _content_tokens(
            f"{item.claim_text}\n{item.source_claim_text}\n{item.excerpt_text}"
        )
        if len(item_tokens & body_tokens) < min_evidence_overlap:
            correspondence.append({
                "check": QualityCheck.EVIDENCE_ID_CORRESPONDENCE.value,
                "code": EVIDENCE_ID_NOT_USED,
                "evidence_id": declared,
                "overlap": len(item_tokens & body_tokens),
                "required": min_evidence_overlap,
            })
    findings.extend(correspondence)

    # 5. Brief compliance measured against the brief, not against a boolean.
    compliance: list[dict[str, Any]] = []
    for forbidden in brief.forbidden_claims:
        if forbidden and forbidden.lower() in body.lower():
            compliance.append({
                "check": QualityCheck.BRIEF_COMPLIANCE.value,
                "code": BRIEF_FORBIDDEN_CLAIM_PRESENT,
                "claim": forbidden[:160],
            })
    if isinstance(brief, ArticleBrief):
        for required in brief.required_facts:
            required_tokens = _content_tokens(required)
            if not required_tokens:
                continue
            if len(required_tokens & body_tokens) < min(
                min_evidence_overlap, len(required_tokens)
            ):
                compliance.append({
                    "check": QualityCheck.BRIEF_COMPLIANCE.value,
                    "code": BRIEF_REQUIRED_FACT_MISSING,
                    "fact": required[:160],
                })
    findings.extend(compliance)

    checks = {
        QualityCheck.FACTUAL_CLAIM_SUPPORT: not unsupported,
        QualityCheck.NO_OUT_OF_CORPUS_CLAIMS: not appeals,
        QualityCheck.NO_FABRICATED_EXPERIENCE: not experience,
        QualityCheck.EVIDENCE_ID_CORRESPONDENCE: not correspondence,
        QualityCheck.BRIEF_COMPLIANCE: not compliance,
    }
    if review_required and not claim_coverage_complete:
        checks[QualityCheck.NO_OUT_OF_CORPUS_CLAIMS] = False

    self_report = {
        "unsupported_claims": list(draft.unsupported_claims),
        "personal_experience": draft.personal_experience,
        "style_ok": draft.style_ok,
        "brief_compliant": draft.brief_compliant,
        "evidence_ids_used": list(draft.evidence_ids_used),
    }
    divergences: list[str] = []
    if not draft.unsupported_claims and unsupported:
        divergences.append("unsupported_claims")
    if not draft.personal_experience and experience:
        divergences.append("personal_experience")
    if draft.brief_compliant and compliance:
        divergences.append("brief_compliant")
    if divergences:
        findings.append({
            "check": QualityCheck.NO_OUT_OF_CORPUS_CLAIMS.value,
            "code": SELF_REPORT_DIVERGED,
            "fields": list(divergences),
            "detail": "writer self-report contradicts the independent assessment",
        })

    return DraftQualityAssessment(
        assessor_version=DRAFT_QUALITY_ASSESSOR_VERSION,
        draft_fingerprint=draft.fingerprint(),
        checks=checks,
        findings=tuple(findings),
        self_report=self_report,
        self_report_divergences=tuple(divergences),
        claim_accounting=claim_accounting,
        claim_coverage_complete=claim_coverage_complete,
        claim_reviewer_version=claim_reviewer_version,
    )
