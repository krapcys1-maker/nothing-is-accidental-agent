"""Kontrdowody okresowej taryfy modeli — wyłącznie arytmetyka offline."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import llm  # noqa: E402


class ModelPricingTest(unittest.TestCase):
    def test_sonnet_promo_boundary(self) -> None:
        before = config.stawka_anthropic(
            config.SONNET,
            datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        boundary = config.stawka_anthropic(
            config.SONNET,
            datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        after = config.stawka_anthropic(
            config.SONNET, datetime(2027, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual((before["in"], before["out"]), (2.0, 10.0))
        self.assertEqual((boundary["in"], boundary["out"]), (3.0, 15.0))
        self.assertEqual(boundary, after)

    def test_anthropic_tariff_rejects_naive_time(self) -> None:
        with self.assertRaises(ValueError):
            config.stawka_anthropic(config.SONNET, datetime(2026, 8, 21))

    def test_other_anthropic_models_keep_their_tariff(self) -> None:
        opus = config.stawka_anthropic(
            config.CLAUDE, datetime(2027, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(
            (opus["in"], opus["out"], opus["verified"]),
            (5.0, 25.0, True),
        )

    def test_e007_cost_at_current_official_tariff(self) -> None:
        original = config.stawka_anthropic
        try:
            config.stawka_anthropic = lambda model: {
                "in": 2.0, "out": 10.0, "verified": False,
            }
            cost, verified = llm._cost(
                config.SONNET, tokens_in=17_437, tokens_out=2_173,
                web_searches=0,
            )
        finally:
            config.stawka_anthropic = original
        self.assertEqual(cost, 0.056604)
        self.assertFalse(verified)


if __name__ == "__main__":
    unittest.main(verbosity=2)
