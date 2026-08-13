"""Deterministic C2 planner over one authoritative frozen input."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.content.contracts import ArticleBrief, ContentBrief, ContentPlan, NoteBrief, RouteContract
from app.content.foundation import ContentType, FrozenContentInput


class ContentPlanningBlocked(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


_MAIN_BRAND_BLOCKED_TOPIC = re.compile(
    r"(?i)(?:\bai\b|\bllm\b|chatgpt|artificial intelligence|"
    r"nothing is accidental agent|building (?:this|the) (?:agent|project)|"
    r"substack automation)"
)


@dataclass(frozen=True)
class PlannedContent:
    plan: ContentPlan
    brief: ContentBrief


def plan_content(frozen: FrozenContentInput, route: RouteContract) -> PlannedContent:
    """Build a plan without inventing facts, URLs or evidence identities."""
    try:
        card = json.loads(frozen.research_card_snapshot_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ContentPlanningBlocked(
            "CONTENT_CARD_MISSING", "Frozen Research Card snapshot is invalid.",
        ) from exc
    if not isinstance(card, dict):
        raise ContentPlanningBlocked(
            "CONTENT_CARD_MISSING", "Frozen Research Card snapshot must be an object.",
        )
    if card.get("publication_recommendation") != "PROCEED":
        raise ContentPlanningBlocked(
            "CONTENT_CARD_NOT_PROCEED", "Planner accepts only Research Card PROCEED.",
        )
    if not frozen.evidence_items:
        raise ContentPlanningBlocked(
            "CONTENT_EVIDENCE_MISSING", "Planner requires frozen evidence.",
        )
    if route.content_type is not frozen.content_type:
        raise ContentPlanningBlocked(
            "CONTENT_ROUTE_TYPE_MISMATCH", "Route and frozen content type disagree.",
        )
    if int(card.get("id", 0)) != frozen.research_card_id:
        raise ContentPlanningBlocked(
            "CONTENT_CARD_ID_MISMATCH", "Frozen card identity is inconsistent.",
        )
    if any(
        item.account_id != frozen.account_id
        or item.research_card_id != frozen.research_card_id
        or item.topic_id != int(card.get("topic_id", 0))
        for item in frozen.evidence_items
    ):
        raise ContentPlanningBlocked(
            "CONTENT_LINEAGE_MISMATCH", "Frozen evidence lineage is inconsistent.",
        )
    policy_text = " ".join(str(card.get(key) or "") for key in (
        "topic_title", "topic_question", "question", "thesis", "working_thesis",
    ))
    if _MAIN_BRAND_BLOCKED_TOPIC.search(policy_text):
        raise ContentPlanningBlocked(
            "CONTENT_BRAND_TOPIC_BLOCKED",
            "Main-brand content cannot cover AI or construction of this project.",
        )

    thesis = str(card.get("working_thesis") or card.get("thesis") or "").strip()
    question = str(card.get("question") or card.get("topic_question") or "").strip()
    title = str(card.get("topic_title") or question or thesis).strip()
    mechanism = str(card.get("mechanism") or "the mechanism behind the visible outcome").strip()
    counterargument = str(
        card.get("counterargument") or "The evidence supports a bounded mechanism, not a universal rule."
    ).strip()
    if not thesis or not question or not title:
        raise ContentPlanningBlocked(
            "CONTENT_CARD_INCOMPLETE", "Research Card lacks title, question or thesis.",
        )
    evidence_ids = tuple(item.confirmed_claim_id for item in frozen.evidence_items)
    required_facts = tuple(item.claim_text for item in frozen.evidence_items)
    forbidden = tuple(
        dict.fromkeys(
            [
                *(str(value) for value in (card.get("uncertain_claims") or [])),
                *(str(value) for value in (card.get("contradictions") or [])),
                "Any claim not supported by the frozen evidence manifest.",
                "Any invented personal experience or biographical detail.",
            ]
        )
    )
    plan = ContentPlan(
        content_id=frozen.content_id,
        account_id=frozen.account_id,
        research_card_id=frozen.research_card_id,
        content_type=frozen.content_type,
        frozen_input_sha256=frozen.input_sha256,
        evidence_manifest_sha256=frozen.evidence_manifest_sha256,
        route=route,
        central_thesis=thesis,
        answer_question=question,
        narrative_angle=f"Start with a concrete consequence, then reveal {mechanism}.",
        target_reader="A curious general reader interested in hidden everyday systems.",
        evidence_ids=evidence_ids,
        forbidden_claims=forbidden,
    )
    if frozen.content_type is ContentType.ARTICLE:
        brief: ContentBrief = ArticleBrief(
            content_id=frozen.content_id,
            working_title=title,
            central_thesis=thesis,
            answer_question=question,
            narrative_angle=plan.narrative_angle,
            target_reader=plan.target_reader,
            concrete_opening=f"Open with a specific, observable consequence of {title}.",
            argument_structure=(
                "Concrete observation and the question it creates.",
                f"Evidence-led explanation of {mechanism}.",
                "Who benefits, who bears the cost, and which decision made it durable.",
                "Strongest counterargument or limit.",
                "Return to the opening with a changed interpretation.",
            ),
            required_facts=required_facts,
            evidence_ids=evidence_ids,
            counterargument_or_limitation=counterargument,
            ending="End on the practical implication of seeing the hidden mechanism.",
            min_words=240,
            max_words=420,
            forbidden_claims=forbidden,
        )
    elif frozen.content_type is ContentType.NOTE:
        brief = NoteBrief(
            content_id=frozen.content_id,
            main_point=thesis,
            format="CONCRETE_OBSERVATION_TO_ONE_SYSTEM_POINT",
            hook=f"{title}: the visible outcome is only the last step.",
            evidence_ids=evidence_ids,
            min_words=55,
            max_words=140,
            tone="Precise, curious, compact, and free of synthetic intimacy.",
            forbidden_claims=forbidden,
        )
    else:  # Defensive even though ContentType is closed.
        raise ContentPlanningBlocked(
            "CONTENT_TYPE_UNSUPPORTED", "Planner supports only ARTICLE and NOTE.",
        )
    return PlannedContent(plan=plan, brief=brief)
