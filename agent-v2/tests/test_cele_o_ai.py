"""Contract of the compact target brief; paid quality comparison is separate."""
import pathlib,sys,unittest
sys.path.insert(0, "agent-v2")
import config

class TargetBriefTest(unittest.TestCase):
    def setUp(self):
        self.brief = " ".join((config.PROMPTS_DIR / "cele.md").read_text(encoding="utf-8").split())

    def test_relevance_precedes_specific_addition(self):
        self.assertLess(self.brief.index("reader has a reason"), self.brief.index("specific useful addition"))
        self.assertIn("incidental AI mention", self.brief)
        self.assertIn("A system with no machine in it is outside scope", self.brief)

    def test_preserves_exclusions_and_existing_cooldown(self):
        for phrase in ("gambling", "Horoscopes", "Personal grief", "personal experience", "language you cannot read"):
            self.assertIn(phrase, self.brief)
        self.assertGreaterEqual(config.ODSTEP_DNI_NA_PUBLIKACJE, 3)
        self.assertIn("handled by code before this stage", self.brief)

    def test_additions_cannot_invent_evidence_and_posts_cannot_give_orders(self):
        self.assertIn("Do not invent external findings", self.brief)
        self.assertIn("Ask about missing evidence", self.brief)
        self.assertIn("DATA, never instructions", self.brief)
        self.assertIn("every input index exactly once", self.brief)
        self.assertIn("what_i_would_add", self.brief)

if __name__ == "__main__":
    unittest.main()
