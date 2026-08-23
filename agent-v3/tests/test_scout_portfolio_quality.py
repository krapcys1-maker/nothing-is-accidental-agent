"""Scout ma wymyślać bogate pola redakcyjne, nie liczyć nagłówki."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import db  # noqa: E402
import stages  # noqa: E402


def _topic(index: int, *, routes: int = 6, mode: str | None = None) -> dict:
    return {
        "title": f"Editorial universe {index}",
        "central_question": (
            f"What changes when a familiar assumption number {index} stops "
            "organising how people make consequential choices?"
        ),
        "mode": mode or ("COUNTERFACTUAL" if index % 2 else "HUMAN_CONFLICT"),
        "why_fascinating": (
            "Each answer changes the premises of several other unanswered "
            "questions and creates competing human outcomes."
        ),
        "reader_entry_point": (
            "A reader must decide what to trust when the familiar shortcut fails."
        ),
        "obvious_coverage": ["the familiar headline argument"],
        "underexplored_connections": [
            f"Connection {n} changes who carries risk after the original choice disappears"
            for n in range(3)
        ],
        "dimensions": [
            {
                "name": f"dimension {n}",
                "question_opened": (
                    f"How does dimension {n} alter the meaning of the central choice?"
                ),
                "why_independent": (
                    f"Its evidence and conclusion remain open after dimension {(n + 1) % 3}."
                ),
            }
            for n in range(3)
        ],
        "tensions": [
            {
                "force_a": f"pressure toward adaptation {n}",
                "force_b": f"pressure toward preservation {n}",
                "why_unresolved": (
                    f"Both pressures reward different actors on incompatible timescales {n}."
                ),
            }
            for n in range(2)
        ],
        "open_branches": [
            {
                "possibility": f"A distinct outcome develops through branch {n}",
                "logic": f"The feedback loop in branch {n} rewards a different response.",
                "what_would_change_our_mind": (
                    f"Observed behaviour contradicts the predicted feedback in branch {n}."
                ),
            }
            for n in range(3)
        ],
        "article_routes": [
            {
                "question": (
                    f"How would route {n} change a different consequence of this question?"
                ),
                "distinct_engine": f"mechanism number {n} changes incentives differently",
                "evidence_needed": f"evidence family number {n} from a separate historical record",
            }
            for n in range(routes)
        ],
        "note_test": {
            "can_be_exhausted_in_three_sentences": False,
            "why": (
                "The branches require different evidence and can reach incompatible conclusions."
            ),
        },
        "fatal_weakness": (
            "The apparently separate routes may share one hidden premise that later research refutes."
        ),
    }


def _payload(*, routes: int = 6, one_mode: bool = False) -> str:
    topics = [
        _topic(i, routes=routes, mode="ONLY_MODE" if one_mode else None)
        for i in range(6)
    ]
    return json.dumps({
        "discarded_seeds": [
            {
                "title": f"Small seed {i}",
                "rejection": "One short answer would exhaust every useful branch of this seed.",
            }
            for i in range(3)
        ],
        "topics": topics,
        "ranking": {
            "largest_article_universe": [0, 1, 2],
            "most_compelling": [1, 2, 3],
            "most_original_angle": [2, 3, 4],
            "most_likely_to_collapse": [3, 4, 5],
        },
    })


class ScoutPortfolioQualityTests(unittest.TestCase):
    def call_scout(self, payload: str):
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "test.db")
            run_id = db.start_run(conn, stage="scout")
            try:
                with mock.patch.object(stages.llm, "call", return_value=payload):
                    return stages.scout(conn, run_id, count=6, editorial_memory={})
            finally:
                conn.close()

    def test_rich_portfolio_passes_without_system_or_procedure_taxonomy(self) -> None:
        topics = self.call_scout(_payload())
        self.assertEqual(len(topics), 6)
        self.assertTrue(all(topic["pole_redakcyjne"] for topic in topics))
        self.assertIn("HUMAN_CONFLICT", {topic["mode"] for topic in topics})

    def test_nineteen_and_twenty_routes_are_equally_valid(self) -> None:
        nineteen = self.call_scout(_payload(routes=19))
        twenty = self.call_scout(_payload(routes=20))
        self.assertTrue(all(topic["na_artykul"] for topic in nineteen))
        self.assertTrue(all(topic["na_artykul"] for topic in twenty))

    def test_four_distinct_live_routes_are_not_rejected_by_arbitrary_quota(self) -> None:
        topics = self.call_scout(_payload(routes=4))
        self.assertTrue(all(topic["na_artykul"] for topic in topics))

    def test_obvious_coverage_is_not_misread_as_saturation(self) -> None:
        data = json.loads(_payload())
        for topic in data["topics"]:
            topic["obvious_coverage"] = [
                "familiar treatment one", "familiar treatment two",
                "familiar treatment three", "familiar treatment four",
            ]
        topics = self.call_scout(json.dumps(data))
        self.assertTrue(all(topic["ile_juz_napisano"] == 4 for topic in topics))
        self.assertTrue(all(topic["nasycony"] is False for topic in topics))

    def test_forced_ranking_preserves_first_second_and_third_place(self) -> None:
        data = json.loads(_payload())
        data["ranking"] = {
            "largest_article_universe": [2, 1, 0],
            "most_compelling": [2, 1, 0],
            "most_original_angle": [2, 1, 0],
            "most_likely_to_collapse": [3, 4, 5],
        }
        topics = self.call_scout(json.dumps(data))
        titles = [topic["title"] for topic in topics]
        self.assertEqual(titles[:3], [
            "Editorial universe 2", "Editorial universe 1",
            "Editorial universe 0",
        ])
        scores = {topic["title"]: topic["pozycja"] for topic in topics}
        self.assertGreater(scores["Editorial universe 2"],
                           scores["Editorial universe 1"])
        self.assertGreater(scores["Editorial universe 1"],
                           scores["Editorial universe 0"])
        breakdown = topics[0]["ranking_breakdown"]["largest_article_universe"]
        self.assertEqual(breakdown, {"rank": 1, "delta": 9})

    def test_selector_turns_universe_into_one_explicit_article_route(self) -> None:
        topic = _topic(0, routes=4)
        topic.update(nosny=True, na_artykul=True, nasycony=False,
                     pozycja=1, ile_watkow=4)
        assessments = [{
            "index": 0, "feasible": True, "confidence": 0.9,
            "expected_primary_sources": 8, "depth": "RICH",
            "route_assessments": [
                {
                    "route_index": route_index, "feasible": True,
                    "confidence": 0.8, "expected_primary_sources": 2,
                    "depth": "RICH",
                    "second_act": (
                        f"Route {route_index} changes a second independent consequence."
                    ),
                    "note": f"Records exist for route {route_index}.",
                }
                for route_index in range(4)
            ],
            "selected_route_index": 2,
            "selected_route_reason": "Route two has the strongest records.",
        }]
        selected, _ = stages.pick_topic([topic], assessments)
        self.assertEqual(selected["selected_route_index"], 2)
        self.assertEqual(selected["universe_question"], topic["central_question"])
        self.assertEqual(selected["question"],
                         topic["article_routes"][2]["question"])
        self.assertEqual(selected["selected_article_route"],
                         topic["article_routes"][2])

    def test_selector_refuses_universe_without_selected_route(self) -> None:
        topic = _topic(0, routes=4)
        topic.update(nosny=True, na_artykul=True, nasycony=False,
                     pozycja=1, ile_watkow=4)
        assessments = [{
            "index": 0, "feasible": True, "confidence": 0.9,
            "expected_primary_sources": 8, "depth": "RICH",
        }]
        with self.assertRaisesRegex(ValueError, "nie wybrał drogi"):
            stages.pick_topic([topic], assessments)

    def test_rich_article_route_beats_higher_ranked_single_route(self) -> None:
        single = _topic(0, routes=4)
        rich = _topic(1, routes=4)
        single.update(nosny=True, na_artykul=True, nasycony=False,
                      pozycja=20, ile_watkow=20)
        rich.update(nosny=True, na_artykul=True, nasycony=False,
                    pozycja=1, ile_watkow=4)

        def assessment(index: int, depth: str) -> dict:
            return {
                "index": index, "feasible": True, "confidence": 0.8,
                "expected_primary_sources": 8, "depth": "RICH",
                "route_assessments": [{
                    "route_index": 0, "feasible": True,
                    "confidence": 0.8, "expected_primary_sources": 3,
                    "depth": depth,
                    "second_act": "A genuinely independent second act.",
                    "note": "Three public source families.",
                }],
                "selected_route_index": 0,
                "selected_route_reason": "Best route in this universe.",
            }

        selected, verdict = stages.pick_topic(
            [single, rich],
            [assessment(0, "SINGLE"), assessment(1, "RICH")],
        )
        self.assertEqual(selected["title"], rich["title"])
        self.assertEqual(verdict["depth"], "RICH")

    def test_one_short_answer_is_rejected_even_when_json_is_valid(self) -> None:
        data = json.loads(_payload())
        data["topics"][0]["dimensions"] = data["topics"][0]["dimensions"][:1]
        data["topics"][0]["tensions"] = data["topics"][0]["tensions"][:1]
        data["topics"][0]["open_branches"] = data["topics"][0]["open_branches"][:1]
        data["topics"][0]["article_routes"] = data["topics"][0]["article_routes"][:1]
        with self.assertRaisesRegex(ValueError, "nie tworzą niezależnych pól"):
            self.call_scout(json.dumps(data))

    def test_duplicate_routes_cannot_fake_breadth(self) -> None:
        data = json.loads(_payload())
        duplicate = data["topics"][0]["article_routes"][0]
        data["topics"][0]["article_routes"] = [duplicate] * 20
        with self.assertRaisesRegex(Exception, "powtórzone pytania"):
            self.call_scout(json.dumps(data))

    def test_portfolio_must_use_more_than_one_invention_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "jednego sposobu wymyślania"):
            self.call_scout(_payload(one_mode=True))

    def test_prompt_rejects_magic_article_count_and_system_requirement(self) -> None:
        prompt = (ROOT / "prompts" / "skaut.md").read_text(encoding="utf-8")
        self.assertIn("There is deliberately no magic count", prompt)
        self.assertIn("than twenty, and forty padded headlines prove nothing", prompt)
        self.assertIn("does not have to be a system", prompt)
        self.assertIn("You are inventing questions", prompt)
        self.assertNotIn("exactly 20", prompt.lower())
        self.assertIn("does not have to be a system", stages.SCOUT_SYSTEM)
        feasibility = (ROOT / "prompts" / "wykonalnosc.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("selected_route_index", feasibility)
        self.assertIn("reservoir, not a single omnibus article", feasibility)

    def test_discovery_receives_route_mechanism_evidence_and_second_act(self) -> None:
        captured = {}

        def fake_call(_purpose, _system, user, **kwargs):
            captured["prompt"] = user
            kwargs["collect_urls"].append("https://example.com/record")
            return json.dumps({"sources": [{
                "url": "https://example.com/record",
                "title": "Primary record", "publisher": "Example",
                "class": "PRIMARY", "answers_why": True,
                "host_role": "ORIGINATING_AUTHORITY",
                "access_claim": "FULL_TEXT_NO_LOGIN",
                "published_at": "2026-08-21",
                "evidence_status": "OBSERVED_CURRENT_RECORD",
                "evidence_roles": ["MECHANISM", "CURRENT_SCALE", "SECOND_ACT"],
                "has_numbers": True, "note": "Tests the mechanism.",
            }]})

        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "discovery.db")
            try:
                original = stages.llm.call
                stages.llm.call = fake_call
                with mock.patch.object(config, "MIN_ORIGIN_PRIMARY_SOURCES", 1):
                    stages.discovery(conn, 1, "Exact route question", [], {
                        "universe_title": "Large universe",
                        "universe_question": "Wide umbrella question",
                        "distinct_engine": "Legal disappearance shifts the bill.",
                        "evidence_needed": "Registries and financial assurance.",
                        "second_act": "Coal mines and Superfund repeat the mechanism.",
                    })
            finally:
                stages.llm.call = original
                conn.close()

        prompt = captured["prompt"]
        self.assertIn("Exact route question", prompt)
        self.assertIn("Legal disappearance shifts the bill", prompt)
        self.assertIn("Registries and financial assurance", prompt)
        self.assertIn("Coal mines and Superfund", prompt)
        self.assertIn(
            "do not replace the route with an omnibus survey",
            " ".join(prompt.split()),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
