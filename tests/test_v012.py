"""Regression tests for Gemma text output, device modes and private diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from krea_prompt_builder.prompting import build_instruction, parse_result
from krea_prompt_builder.runner import device_flags, make_command, run_once


class V012Tests(unittest.TestCase):
    def test_section_format(self):
        raw = """[ANALYSIS]
A well-lit mountain landscape.
[KEEP]
Snowy peaks.
[IMPROVE]
Sharper foreground.
[PROMPT]
A vivid snow-covered mountain scene under warm morning light.
"""
        self.assertIn("mountain", parse_result(raw)["prompt_en_us"])

    def test_sections_must_be_complete(self):
        with self.assertRaises(ValueError):
            parse_result("[ANALYSIS]\nlandscape\n[PROMPT]\nLandscape!")

    def test_json_keep_and_improve_lists(self):
        raw = json.dumps({"analysis_en": "A red cat", "keep": ["fur", "eyes"],
                          "improve": ["lighting"], "prompt_en_us": "Red cat on a sofa"})
        self.assertIn("fur", parse_result(raw)["keep"])

    def test_gemma_channel_thought_ignored(self):
        raw = "<|channel>thought\nI need to analyze this carefully.<channel|>\n" + (
            "[ANALYSIS]\nA face\n[KEEP]\nExpression\n[IMPROVE]\nLight\n[PROMPT]\nA portrait")
        self.assertEqual(parse_result(raw)["prompt_en_us"], "A portrait")

    def test_plain_instruction(self):
        value = build_instruction("improve", "Popraw kadr", "", "plain_sections")
        self.assertIn("[PROMPT]", value)
        self.assertNotIn("one JSON", value)

    def test_device_flags(self):
        self.assertEqual(device_flags("cpu", 25, True), ["--gpu-layers", "0", "--no-mmproj-offload"])
        self.assertEqual(device_flags("hybrid", 12, False), ["--gpu-layers", "12", "--no-mmproj-offload"])
        self.assertEqual(device_flags("gpu", 12, True), ["--gpu-layers", "999"])
        with self.assertRaises(ValueError):
            device_flags("unknown", 12, True)

    def test_plain_disables_schema_and_reasoning(self):
        path = Path("/fake.exe")
        cmd = make_command(path, path, path, path, path, path, "test", 16, 2048, 700, 128,
                           False, "cpu", "plain_sections", "off")
        self.assertNotIn("-jf", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning") + 1], "off")
        self.assertEqual(cmd[cmd.index("--reasoning-budget") + 1], "0")
        self.assertEqual(cmd[cmd.index("--gpu-layers") + 1], "0")

    def test_json_schema_toggle(self):
        path = Path("/fake.exe")
        cmd = make_command(path, path, path, path, path, path, "test", 12, 2048, 700, 128,
                           False, "hybrid", "json_schema", "auto")
        self.assertIn("-jf", cmd)
        self.assertNotIn("--reasoning-budget", cmd)

    @unittest.skipIf(os.name == "nt", "POSIX shebang fixture")
    def test_cli_returns_labelled_plain_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "llama-cli"
            fake.write_text('#!/usr/bin/env python3\nimport sys\n'
                            'assert "-jf" not in sys.argv\n'
                            'print("[ANALYSIS]\\nA garden\\n[KEEP]\\nTrees\\n[IMPROVE]\\nSunlight\\n[PROMPT]\\nSunlit garden")\n')
            fake.chmod(0o755)
            out = run_once(fake, root/"m.gguf", root/"p.gguf", root/"i.png", "instruction",
                           0, 2048, 512, 128, False, 30,
                           execution_device="cpu", output_mode="plain_sections")
            self.assertEqual(out["prompt_en_us"], "Sunlit garden")

    @unittest.skipIf(os.name == "nt", "POSIX shebang fixture")
    def test_no_output_reports_metadata_not_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "llama-cli"
            fake.write_text('#!/usr/bin/env python3\nprint("SECRET PRIVATE USER PROMPT")\n')
            fake.chmod(0o755)
            with self.assertRaises(ValueError) as context:
                run_once(fake, root/"m.gguf", root/"p.gguf", root/"i.png", "private",
                         0, 2048, 512, 128, False, 30)
            self.assertNotIn("SECRET", str(context.exception))
            self.assertIn("response_chars", str(context.exception))
            self.assertIn("Enable save_diagnostics", str(context.exception))

    @unittest.skipIf(os.name == "nt", "POSIX shebang fixture")
    def test_opt_in_private_local_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "llama-cli"
            fake.write_text('#!/usr/bin/env python3\nprint("PRIVATE SCENE")\n')
            fake.chmod(0o755)
            diagnostics = root / "private_diagnostics"
            with self.assertRaises(ValueError) as context:
                run_once(fake, root/"m.gguf", root/"p.gguf", root/"i.png", "private",
                         0, 2048, 512, 128, False, 30, diagnostics_dir=diagnostics)
            folders = list(diagnostics.glob("vlm_*"))
            self.assertEqual(len(folders), 1)
            self.assertIn("PRIVATE SCENE", (folders[0] / "stdout.txt").read_text())
            self.assertIn(str(folders[0]), str(context.exception))


if __name__ == "__main__":
    unittest.main()
