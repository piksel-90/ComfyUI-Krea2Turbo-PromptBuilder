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
                        4096, 512, 256, 30, 0, after_purge="done")
                self.assertEqual(result[0], "A crimson sunset")
                self.assertIn("KEEP:", result[2])
                self.assertIs(result[3], img)
                self.assertEqual(runner.call_count, 1)
            finally:
                del sys.modules["folder_paths"]
                del sys.modules[module_name]
                del sys.modules[f"{module_name}.nodes"]
