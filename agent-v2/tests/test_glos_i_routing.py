"""Wspolny glos dociera do krotkich form, a Fable zachowuje prompt artykulu."""
import pathlib
import string
import sys
import tempfile
import unittest

sys.path.insert(0, "agent-v2")
import config
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
import stages

def fields_for(template):
    return {name: 'source {untrusted_field}' for _, name, _, _
            in string.Formatter().parse(template) if name and name != "marka"}

class VoiceRoutingTest(unittest.TestCase):
    def test_each_short_form_receives_shared_voice_once_before_source(self):
        voice = (config.PROMPTS_DIR / "glos_krotkich.md").read_text(encoding="utf-8")
        for name in ("notka.md", "komentarz.md", "odpowiedz.md", "restack.md", "naprawa.md", "pisarz.md"):
            with self.subTest(name=name):
                template = (config.PROMPTS_DIR / name).read_text(encoding="utf-8")
                prompt = stages._prompt(name, **fields_for(template))
                self.assertTrue(prompt.startswith(voice + "\n\n"))
                self.assertEqual(prompt.count(voice), 1)
                self.assertIn("source {untrusted_field}", prompt)
                if name == "notka.md":
                    self.assertNotIn("Length: vary it, hard", prompt)

    def test_article_uses_original_template_and_fable(self):
        template = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf-8")
        fields = fields_for(template)
        expected = template.format(marka=config.MARKA, **fields)
        self.assertTrue(stages._prompt("pisarz.md", **fields).endswith(expected))
        self.assertEqual(config.MODEL_FOR["write"], config.FABLE)

    def test_other_text_stages_use_flash(self):
        # `przeslania` (sledztwo, 27.09.2026) swiadomie na Opusie — zywe A/B
        # trzech modeli na tym samym sledztwie, patrz config.MODEL_FOR.
        self.assertEqual(config.MODEL_FOR["przeslania"], config.CLAUDE)
        # `notka_przeslania` od 25.10.2026 wieczorem na Flashu z myslenie (wlasciciel: notka ma kosztowac centy).
        self.assertEqual(config.MODEL_FOR["notka_przeslania"], config.DEEPSEEK)
        # `note_mimo` — pisarz ramienia „on" eksperymentu E11 (polecenie
        # wlasciciela 28.09.2026: Xiaomi MiMo pisze polowe notek, tylko NIE).
        self.assertEqual(config.MODEL_FOR["note_mimo"], config.MIMO)
        # `restack_opus` — zdanie restacka w ramieniu „on" eksperymentu E13
        # (decyzja wlasciciela 28.09.2026: lepszy pisarz restackow, 50/50).
        self.assertEqual(config.MODEL_FOR["restack_opus"], config.CLAUDE)
        # `pytania_ciekawosci` — plan sledztwa na Sonnecie (25.10.2026): porownanie
        # trzech modeli na tych samych historiach, Sonnet planowal jak Opus za 1/3 ceny,
        # Flash pytal zbyt technicznie.
        self.assertEqual(config.MODEL_FOR["pytania_ciekawosci"], config.SONNET)
        # `krytyk_sledztwa` — starszy redaktor sledztwa na Sonnecie (spec 25.10 §2 etap 11);
        # `notka_przeslania_fakt` — notka kata faktow od 25.10 wieczorem tez na Flashu z myslenie.
        self.assertEqual(config.MODEL_FOR["krytyk_sledztwa"], config.SONNET)
        self.assertEqual(config.MODEL_FOR["notka_przeslania_fakt"], config.DEEPSEEK)
        for purpose, model in config.MODEL_FOR.items():
            if purpose not in {"write", "obraz", "przeslania", "note_mimo",
                               "restack_opus", "pytania_ciekawosci", "krytyk_sledztwa"}:
                with self.subTest(purpose=purpose):
                    self.assertEqual(model, config.DEEPSEEK)

if __name__ == "__main__":
    unittest.main()
