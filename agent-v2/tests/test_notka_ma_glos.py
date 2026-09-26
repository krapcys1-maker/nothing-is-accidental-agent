"""Every public format receives one voice; raw data is not reformatted as code."""
import pathlib
import string
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config
import stages

class PublicVoiceTest(unittest.TestCase):
    def test_render_all_templates_and_preserve_untrusted_braces(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "DATA_DIR", pathlib.Path(tmp)):
            for path in config.PROMPTS_DIR.glob("*.md"):
                if path.name[0].isupper() or path.name in {"glos_krotkich.md", "po_ludzku.md"}:
                    continue
                with self.subTest(path=path.name):
                    fields = {f: "SOURCE {not_a_template}" for _,f,_,_ in string.Formatter().parse(path.read_text(encoding="utf8")) if f and f != "marka"}
                    rendered = stages._prompt(path.name, **fields)
                    if fields:
                        self.assertIn("SOURCE {not_a_template}", rendered)
                    voice = (config.PROMPTS_DIR / "glos_krotkich.md").read_text(encoding="utf8")
                    self.assertEqual(rendered.count(voice), int(path.name in stages.Z_GLOSEM_KROTKICH))
                    if path.name in stages.Z_GLOSEM_KROTKICH:
                        self.assertTrue(rendered.startswith(voice))
                        self.assertNotIn("Length: vary it, hard", rendered)

if __name__ == "__main__":
    unittest.main()
