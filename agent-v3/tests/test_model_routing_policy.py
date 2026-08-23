"""Routing modeli produkcyjnego potoku jest konfiguracją, nie fallbackiem runtime."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


AGENT = Path(__file__).resolve().parents[1]


class ModelRoutingPolicyTests(unittest.TestCase):
    def test_runtime_modules_do_not_mutate_model_for(self) -> None:
        violations: list[str] = []
        for path in sorted(AGENT.glob("*.py")):
            if path.name == "config.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    )
                    for target in targets:
                        if self._is_model_for_target(target):
                            violations.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if (
                        node.func.attr in {"update", "setdefault", "pop", "clear"}
                        and self._is_model_for_object(node.func.value)
                    ):
                        violations.append(f"{path.name}:{node.lineno}")
        self.assertEqual(violations, [])

    def test_live_provenance_harness_uses_configured_routing(self) -> None:
        path = AGENT / "tests" / "platne" / "test_provenance_live.py"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("MODEL_FOR.update", source)
        self.assertNotIn("config.SONNET for name", source)
        self.assertIn('choices=("configured",)', source)
        self.assertIn('"classify": config.DEEPSEEK', source)
        self.assertIn('"synthesis": config.DEEPSEEK_PRO', source)
        self.assertIn('"review": config.DEEPSEEK_PRO', source)
        self.assertIn("model override is forbidden", source)

    @staticmethod
    def _is_model_for_object(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "MODEL_FOR"
            and isinstance(node.value, ast.Name)
            and node.value.id == "config"
        )

    @classmethod
    def _is_model_for_target(cls, node: ast.AST) -> bool:
        if cls._is_model_for_object(node):
            return True
        return isinstance(node, ast.Subscript) and cls._is_model_for_object(node.value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
