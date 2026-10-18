import tempfile
import unittest
from pathlib import Path
from krea_prompt_builder.models import discover, resolve_local, UNSET


class ModelTests(unittest.TestCase):
    def test_discover_and_resolve(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "Gemma").mkdir()
            (root / "Gemma" / "model.gguf").write_text("x")
            (root / "Gemma" / "mmproj.gguf").write_text("x")
            models, projs = discover(root)
            self.assertIn("Gemma/model.gguf", models)
            self.assertIn("Gemma/mmproj.gguf", projs)
            self.assertEqual(resolve_local(root, "Gemma/model.gguf"), (root / "Gemma" / "model.gguf"))

    def test_reject_outside_root(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "models"
            root.mkdir()
            with self.assertRaises(ValueError):
                resolve_local(root, "../other.gguf")
            with self.assertRaises(ValueError):
                resolve_local(root, UNSET)
