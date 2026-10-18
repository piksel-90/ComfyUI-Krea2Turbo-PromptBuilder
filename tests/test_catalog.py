"""Regression: 0.1 showed [select local GGUF] even with GGUF in llama_cpp."""
from pathlib import Path
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from krea_prompt_builder.models import (
    catalog, select_gguf, resolve_projector, match_projector, AUTO_MMPROJ, UNSET,
)


class CatalogTests(unittest.TestCase):
    def test_models_in_existing_folders_and_projector_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            llama = root / "llama_cpp"
            llama.mkdir()
            model = llama / "gemma-4-12B-it-abliterated-uncensored.Q5_K_M.gguf"
            proj = llama / "gemma-4-12B-it-abliterated-uncensored.mmproj-f16.gguf"
            model.write_bytes(b"model")
            proj.write_bytes(b"proj")
            (root / "LLM").mkdir()
            other = root / "LLM" / "qwen.gguf"
            other.write_bytes(b"other")
            models, projs, paths = catalog(root)
            self.assertIn("llama_cpp :: " + model.name, models)
            self.assertIn("LLM :: qwen.gguf", models)
            self.assertIn("llama_cpp :: " + proj.name, projs)
            selected = select_gguf("llama_cpp :: " + model.name, paths)
            self.assertEqual(selected, model)
            self.assertEqual(resolve_projector(AUTO_MMPROJ, selected, paths), proj)

    def test_extra_registered_folder_is_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "models"
            root.mkdir()
            ext = Path(tmp) / "external"
            ext.mkdir()
            (ext / "external.gguf").write_bytes(b"x")
            stub = types.SimpleNamespace(get_folder_paths=lambda name: [str(ext)] if name == "llama_cpp" else [])
            models, _, paths = catalog(root, stub)
            self.assertIn("llama_cpp :: external.gguf", models)
            self.assertEqual(select_gguf("llama_cpp :: external.gguf", paths), ext / "external.gguf")

    def test_absolute_override_outside_comfyui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "external.gguf"
            projector = root / "mmproj-f16.gguf"
            model.write_bytes(b"weights")
            projector.write_bytes(b"weights")
            self.assertEqual(select_gguf(UNSET, {}, str(model)), model)
            self.assertEqual(resolve_projector(AUTO_MMPROJ, model, {}), projector)

    def test_multiple_projectors_must_not_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "generic.gguf"
            model.write_bytes(b"x")
            (root / "mmproj-a.gguf").write_bytes(b"x")
            (root / "mmproj-b.gguf").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "Could not uniquely"):
                match_projector(model, {})

    def test_symlink_duplicate_root_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "llama_cpp"
            a.mkdir()
            (a / "m.gguf").write_bytes(b"x")
            fake = types.SimpleNamespace(get_folder_paths=lambda _: [str(a)])
            models, _, _ = catalog(root, fake)
            self.assertEqual(models.count("llama_cpp :: m.gguf"), 1)

    def test_relative_override_rejected(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            select_gguf(UNSET, {}, "not/absolute.gguf")

    def test_wrong_override_extension_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "bad.txt"
            wrong.write_bytes(b"bad")
            with self.assertRaises(FileNotFoundError):
                select_gguf(UNSET, {}, str(wrong))
