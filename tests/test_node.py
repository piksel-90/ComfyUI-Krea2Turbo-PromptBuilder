"""Test ComfyUI-facing integration with mocked VLM, not real model weights."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import torch
except ImportError:
    torch = None


class NodeTests(unittest.TestCase):
    @unittest.skipIf(torch is None, "ComfyUI supplies torch")
    def test_single_frame_full_node_integration_with_fake_runner(self):
        root = Path(__file__).resolve().parents[1]
        module_name = "_ComfyUITestPackage"
        with tempfile.TemporaryDirectory() as tmp:
            stub_folder_paths = types.ModuleType("folder_paths")
            stub_folder_paths.models_dir = tmp
            pkg = types.ModuleType(module_name)
            pkg.__path__ = [str(root)]
            sys.modules[module_name] = pkg
            sys.modules["folder_paths"] = stub_folder_paths
            try:
                spec = importlib.util.spec_from_file_location(f"{module_name}.nodes", root / "nodes.py")
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                chosen = mod.MODEL_ROOT / "llama_cpp" / "demo"
                chosen.mkdir(parents=True)
                (chosen / "demo.gguf").write_bytes(b"test")
                (chosen / "mmproj.gguf").write_bytes(b"test")
                stubbin = Path(tmp) / "llama-cli"
                stubbin.write_bytes(b"test")
                node = mod.KreaPromptBuilder()
                self.assertIn("after_purge", node.INPUT_TYPES()["optional"])
                self.assertIn("llama_cpp :: demo/demo.gguf", node.INPUT_TYPES()["required"]["model_gguf"][0])
                img = torch.zeros((1, 40, 60, 3), dtype=torch.float32)
                with patch.object(mod, "run_once", return_value={
                    "analysis_en": "Red sky", "keep": "sky", "improve": "contrast",
                    "prompt_en_us": "A crimson sunset",
                }) as runner:
                    result = node.build(img, "llama_cpp :: demo/demo.gguf", "[AUTO: projector next to model]", str(stubbin),
                        "improve", "Improve contrast", "", 0, 384, 24, False,
                        4096, 512, 256, 30, 0, after_purge="done", report_language="en_only")
                self.assertEqual(result[0], "A crimson sunset")
                self.assertIn("KEEP:", result[2])
                self.assertIs(result[3], img)
                self.assertEqual(runner.call_count, 1)
                self.assertEqual(len(result), 9)
                self.assertEqual(result[7:], ("", ""))
                self.assertTrue(result[5])
                self.assertIn("nie ma niezależnego", result[4])
                # Bilingual V0.1.4: a single runner invocation supplies EN + PL.
                with patch.object(mod, "run_once", return_value={
                    "analysis_en": "An older woman resting in bed.",
                    "keep": "Two people in a room", "improve": "Clearer hand contours",
                    "prompt_en_us": "An older woman in a softly lit room.",
                    "analysis_pl": "Starsza kobieta leży w łóżku.",
                    "edit_plan_pl": "ZACHOWAĆ: obie osoby. ZMIENIĆ: kontur dłoni.",
                }) as bilingual_runner:
                    bilingual = node.build(img, "llama_cpp :: demo/demo.gguf", "[AUTO: projector next to model]", str(stubbin),
                        "improve", "", "", 0, 384, 16, False, 4096, 1400, 128, 30, 0,
                        report_language="pl_en")
                self.assertEqual(bilingual_runner.call_count, 1)
                self.assertEqual(bilingual[7], "Starsza kobieta leży w łóżku.")
                self.assertIn("ZACHOWAĆ", bilingual[8])
                self.assertEqual(bilingual[0], "An older woman in a softly lit room.")
                self.assertEqual(len(bilingual), 9)
                self.assertEqual(node.INPUT_TYPES()["optional"]["report_language"][1]["default"], "pl_en")
                self.assertEqual(node.RETURN_NAMES[:7], (
                    "prompt_en_us", "scene_analysis_en", "edit_plan_en", "image",
                    "contract_report_pl", "contract_ok", "gpu_offload_info"))
                with patch.object(mod, "run_once", return_value={
                    "analysis_en": "A room", "keep": "scene", "improve": "light", "prompt_en_us": "A room"
                }):
                    with self.assertRaisesRegex(ValueError, "missing Polish report"):
                        node.build(img, "llama_cpp :: demo/demo.gguf", "[AUTO: projector next to model]", str(stubbin),
                            "improve", "", "", 0, 384, 16, False, 4096, 1400, 128, 30, 0,
                            report_language="pl_en")
                with patch.object(mod, "run_once", return_value={
                    "analysis_en": "A scene", "keep": "original room", "improve": "soft light",
                    "prompt_en_us": "A child in a rice field holding a laptop",
                }):
                    blocked = node.build(img, "llama_cpp :: demo/demo.gguf", "[AUTO: projector next to model]", str(stubbin),
                        "improve", "", "", 0, 384, 12, False, 2048, 512, 128, 30, 0,
                        required_exact_phrases="living room\nlaptop",
                        forbidden_exact_phrases="rice field", report_language="en_only")
                    self.assertEqual(blocked[0], "")
                    self.assertFalse(blocked[5])
                    self.assertIn("BLOKADA", blocked[4])
            finally:
                del sys.modules["folder_paths"]
                del sys.modules[module_name]
                del sys.modules[f"{module_name}.nodes"]
