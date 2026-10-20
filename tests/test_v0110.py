"""V0.1.10 integrated ComfyUI memory handoff tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from krea_prompt_builder import memory


class MemoryHandoffUnitTests(unittest.TestCase):
    def test_handoff_uses_official_unload_without_registry_clear(self):
        calls = []
        fake_mm = types.ModuleType("comfy.model_management")
        fake_mm.unload_all_models = lambda: calls.append("unload")
        fake_mm.soft_empty_cache = lambda: calls.append("soft_empty")
        fake_comfy = types.ModuleType("comfy")
        fake_comfy.__path__ = []
        fake_comfy.model_management = fake_mm
        with patch.dict(sys.modules, {"comfy": fake_comfy, "comfy.model_management": fake_mm}):
            with patch.object(memory, "memory_snapshot", side_effect=[{"python_rss": 1, "python_private": 2, "vram_free": 3, "vram_total": 4},
                                                                      {"python_rss": 5, "python_private": 6, "vram_free": 7, "vram_total": 8}]):
                with patch.object(memory.gc, "collect", side_effect=lambda: calls.append("gc")):
                    before, after = memory.perform_comfy_memory_handoff()
        self.assertEqual(calls, ["unload", "gc", "soft_empty", "gc"])
        self.assertEqual(before["python_private"], 2)
        self.assertEqual(after["vram_free"], 7)
        source = (Path(__file__).resolve().parents[1] / "krea_prompt_builder" / "memory.py").read_text(encoding="utf-8")
        self.assertNotIn("current_loaded_models.clear", source)
        self.assertNotIn("loaded_models().clear", source)

    def test_post_prompt_cleanup_is_queue_flag_not_immediate_executor_reset(self):
        calls = []
        queue = types.SimpleNamespace(set_flag=lambda name, value: calls.append((name, value)))
        fake_server = types.ModuleType("server")
        fake_server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=queue))
        with patch.dict(sys.modules, {"server": fake_server}):
            self.assertTrue(memory.schedule_post_prompt_free())
        self.assertEqual(calls, [("free_memory", True)])


class NodeHandoffOrderTests(unittest.TestCase):
    @staticmethod
    def load_nodes(folder):
        name = "_KreaV0110TestPackage"
        root = Path(__file__).resolve().parents[1]
        fake_folder = types.ModuleType("folder_paths")
        fake_folder.models_dir = folder
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(root)]
        sys.modules[name] = pkg
        sys.modules["folder_paths"] = fake_folder
        spec = importlib.util.spec_from_file_location(f"{name}.nodes", root / "nodes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod, name

    @staticmethod
    def unload_nodes(name):
        for key in (f"{name}.nodes", name, "folder_paths"):
            sys.modules.pop(key, None)

    def test_save_then_unload_then_headroom_then_vlm(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, name = self.load_nodes(directory)
            try:
                model = Path(directory) / "demo.gguf"
                mmproj = Path(directory) / "mmproj.gguf"
                cli = Path(directory) / "llama-cli"
                for p in (model, mmproj, cli):
                    p.write_bytes(b"x")
                events = []
                fake_result = {
                    "analysis_en": "A", "keep": "B", "improve": "C", "prompt_en_us": "D",
                    "analysis_pl": "E", "edit_plan_pl": "F",
                    "contract_report_pl": "WYNIK_PROMPTU: ZGODNY.",
                }
                with patch.object(mod, "select_gguf", return_value=model),                      patch.object(mod, "resolve_projector", return_value=mmproj),                      patch.object(mod, "find_executable", return_value=cli),                      patch.object(mod, "save_one_image", side_effect=lambda *a, **k: (events.append("save") or (432, 768))),                      patch.object(mod, "perform_comfy_memory_handoff", side_effect=lambda: (events.append("handoff") or ({}, {}))),                      patch.object(mod, "format_memory_snapshot", return_value="mem"),                      patch.object(mod, "schedule_post_prompt_free", side_effect=lambda: (events.append("schedule") or True)),                      patch.object(mod, "enforce_headroom", side_effect=lambda *a, **k: (events.append("headroom") or "ok")),                      patch.object(mod, "run_once", side_effect=lambda *a, **k: (events.append("run") or fake_result)):
                    node = mod.KreaPromptBuilderV018()
                    node.build(
                        image=object(), model_gguf="x", mmproj_gguf="x", llama_cli_path=str(cli),
                        mode="improve", original_prompt="", target="", extra_instruction="",
                        image_index=0, max_image_side=768, gpu_layers=16, vision_gpu=False,
                        context_size=4096, max_tokens=900, batch_size=128, timeout_seconds=300,
                        commit_headroom_gib=6, execution_device="gpu", memory_handoff=True,
                    )
                self.assertEqual(events, ["save", "handoff", "schedule", "headroom", "run"])
            finally:
                self.unload_nodes(name)

    def test_legacy_default_does_not_force_handoff(self):
        source = (Path(__file__).resolve().parents[1] / "nodes.py").read_text(encoding="utf-8")
        self.assertIn('extra_instruction="", memory_handoff=False', source)
        self.assertIn('forbidden_exact_phrases="", memory_handoff=True', source)


if __name__ == "__main__":
    unittest.main()
