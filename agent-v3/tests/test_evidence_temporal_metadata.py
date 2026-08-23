from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("AGENT_V3_MODE", "fixture")
os.environ.setdefault("AGENT_V3_KILL_SWITCH", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capabilities
import db
import llm
import provenance
import safe_fetch
import stages


META = {
    "published_at": "2019-09-18",
    "evidence_status": "OBSERVED_CURRENT_RECORD",
    "evidence_roles": ["MECHANISM", "COUNTEREVIDENCE_OR_LIMIT"],
}


class TemporalEvidenceMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.temp.name) / "evidence.db")
        self.run_id = db.start_run(self.conn, "test")

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def test_fetch_uses_one_retrieved_at_in_memory_and_db(self) -> None:
        original_require = capabilities.require
        original_get = stages.safe_fetch.get
        requested = "https://example.com/report"
        body = (
            "<html><body><h1>Report</h1><p>"
            + "As of February 2026 the recommendation remains open. " * 40
            + "</p></body></html>"
        ).encode()
        response = safe_fetch.SafeResponse(
            200,
            {"content-type": "text/html; charset=utf-8"},
            body,
            requested,
            (safe_fetch.FetchHop(
                requested, "example.com", ("93.184.216.34",), 200),),
        )
        try:
            capabilities.require = lambda *_args, **_kwargs: None
            stages.safe_fetch.get = lambda *_args, **_kwargs: response
            fetched = stages.fetch(self.conn, self.run_id, [{
                "url": requested,
                "title": "A 2019 report",
                "publisher": "Agency",
                "class": "PRIMARY",
                **META,
            }])
        finally:
            capabilities.require = original_require
            stages.safe_fetch.get = original_get

        self.assertEqual(len(fetched), 1)
        retrieved_at = fetched[0]["retrieved_at"]
        row = self.conn.execute("SELECT at FROM sources").fetchone()
        self.assertEqual(row["at"], retrieved_at)
        self.assertEqual(fetched[0]["published_at"], "2019-09-18")
        self.assertEqual(fetched[0]["evidence_roles"], META["evidence_roles"])

    def test_classify_prompt_sees_time_status_and_roles(self) -> None:
        captured: dict[str, str] = {}
        original_call = llm.call

        def fake_call(_purpose, _system, user, **_kwargs):
            captured["prompt"] = user
            return json.dumps({
                "class": "PRIMARY",
                "relevance": 0.9,
                "excerpts": [
                    "As of February 2026 the recommendation remains open."
                ],
                "note": "Dynamic recommendation page.",
            })

        try:
            llm.call = fake_call
            source = provenance.documentize({
                "url": "https://example.com/report",
                "host": "example.com",
                "title": "A 2019 report",
                "publisher": "Agency",
                "class": "PRIMARY",
                "retrieved_at": "2026-08-21T22:00:00+00:00",
                **META,
                "text": (
                    "A 2019 report. As of February 2026 the recommendation "
                    "remains open."
                ),
            })
            kept = stages.classify(
                self.conn, self.run_id, "Why?", [source])
        finally:
            llm.call = original_call

        self.assertEqual(len(kept), 1)
        prompt = captured["prompt"]
        self.assertIn("Published: 2019-09-18", prompt)
        self.assertIn("Retrieved: 2026-08-21T22:00:00+00:00", prompt)
        self.assertIn("OBSERVED_CURRENT_RECORD", prompt)
        self.assertIn("COUNTEREVIDENCE_OR_LIMIT", prompt)
        self.assertIn("Never replace an excerpt's own", prompt)

    def test_synthesis_and_manifest_keep_temporal_metadata(self) -> None:
        source = provenance.fragments_from_excerpts({
            "url": "https://example.com/report",
            "host": "example.com",
            "title": "A 2019 report",
            "publisher": "Agency",
            "class": "PRIMARY",
            "retrieved_at": "2026-08-21T22:00:00+00:00",
            **META,
            "text": (
                "A 2019 report. As of February 2026 the recommendation "
                "remains open."
            ),
        }, ["As of February 2026 the recommendation remains open."])
        payload = stages._synthesis_source_payload(source)
        self.assertEqual(payload["published_at"], "2019-09-18")
        self.assertEqual(
            payload["retrieved_at"], "2026-08-21T22:00:00+00:00")
        self.assertEqual(payload["evidence_roles"], META["evidence_roles"])

        fragment_id = source["fragments"][0]["fragment_id"]
        card = provenance.bind_card({
            "working_thesis": "Dates differ.",
            "main_mechanism": "Updates persist.",
            "confirmed_claims": [{
                "claim": "The status is current to 2026.",
                "fragment_ids": [fragment_id],
            }],
            "citable_numbers": [],
            "parallel_mechanisms": [],
            "uncertain_claims": [],
            "contradictions": [],
            "not_established": [],
        }, [source])
        document = card["evidence_manifest"]["documents"][0]
        self.assertEqual(document["published_at"], "2019-09-18")
        self.assertEqual(
            document["retrieved_at"], "2026-08-21T22:00:00+00:00")
        self.assertEqual(
            document["evidence_status"], "OBSERVED_CURRENT_RECORD")
        self.assertEqual(document["evidence_roles"], META["evidence_roles"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
