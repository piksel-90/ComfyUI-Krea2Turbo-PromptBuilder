"""Regression tests for real-world llama-cli echo/thinking failures and scene text gates.

Never commit a user's raw result.txt, image, or prompt. All fixtures below are synthetic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from krea_prompt_builder.contract import evaluate_text_contract, parse_phrases
from krea_prompt_builder.prompting import build_instruction, parse_result
from krea_prompt_builder.runner import parse_gpu_offload, run_once


GOOD = """[ANALYSIS]
A small green frog in a yellow circle with text.
[KEEP]
Keep the green frog, the yellow circle, and the text.
[IMPROVE]
Increase clarity of the character edges.
[PROMPT]
A clear green frog centered inside a yellow circle with bold red lettering.
"""
DRAFT = """[ANALYSIS]
Wrong draft describing a desert.
[KEEP]
Keep the desert.
[IMPROVE]
Add sand.
[PROMPT]
A frog standing in a desert instead of a room.
"""


class ParsingRegressionTests(unittest.TestCase):
    def test_echoed_user_instruction_is_not_the_answer(self):
        instruction = build_instruction("improve", "zachowaj pokój", "frog")
        raw = "User:\n" + instruction + "\n\nAssistant:\n" + GOOD
        parsed = parse_result(raw)
        self.assertTrue(parsed["prompt_en_us"].startswith("A clear green frog"))
        self.assertNotIn("only four", parsed["prompt_en_us"].lower())

    def test_echo_only_is_rejected(self):
        raw = "User:\n" + build_instruction("improve", "", "frog")
        with self.assertRaisesRegex(ValueError, "echoed user request"):
            parse_result(raw)

    def test_unclosed_reasoning_is_not_a_valid_result(self):
        raw = "User:\n" + build_instruction("improve", "", "frog") + "\nAssistant:\n[Start thinking]\n" + GOOD
        with self.assertRaisesRegex(ValueError, "unfinished thinking"):
            parse_result(raw)

    def test_closed_reasoning_without_final_is_rejected(self):
        raw = "User:\nplaceholder\nAssistant:\n[Start thinking]\n" + GOOD + "[End thinking]"
        with self.assertRaisesRegex(ValueError, "no final answer"):
            parse_result(raw)

    def test_final_after_thinking_is_accepted(self):
        raw = "User:\nrequest\nAssistant:\n[Start thinking]\n" + DRAFT + "[End thinking]\n" + GOOD
        parsed = parse_result(raw)
        self.assertIn("yellow circle", parsed["prompt_en_us"])
        self.assertNotIn("desert", parsed["prompt_en_us"])

    def test_qwen_thought_channel_is_ignored(self):
        raw = "<|channel>thought\n" + DRAFT + "<channel|>\n" + GOOD
        self.assertIn("green frog", parse_result(raw)["prompt_en_us"])

    def test_last_complete_section_set_wins(self):
        parsed = parse_result(DRAFT + "\n" + GOOD)
        self.assertTrue(parsed["prompt_en_us"].startswith("A clear green frog"))

    def test_template_echo_without_assistant_marker_is_rejected(self):
        raw = """[ANALYSIS]
1-3 sentences describing what is visibly present.
[KEEP]
What must be preserved.
[IMPROVE]
Concrete changes worth making.
[PROMPT]
One self-contained, detailed en-US image-generation prompt.
"""
        with self.assertRaises(ValueError):
            parse_result(raw)

    def test_last_complete_json_wins(self):
        a = {"analysis_en": "an orange sunset", "keep": "sky", "improve": "sun", "prompt_en_us": "An orange sky."}
        b = {"analysis_en": "a blue dusk", "keep": "water", "improve": "contrast", "prompt_en_us": "A blue dusk over water."}
        self.assertEqual(parse_result(json.dumps(a) + "\n" + json.dumps(b))["prompt_en_us"], b["prompt_en_us"])

    def test_scene_contract_instruction_is_not_truth_claim(self):
        instruction = build_instruction("improve", "make colors warmer", "", scene_contract="Stay indoors in a living room")
        self.assertIn("SCENE CONTRACT", instruction)
        self.assertIn("Stay indoors", instruction)
        self.assertIn("not automatically a verified fact", instruction)


class ContractTests(unittest.TestCase):
    def test_no_contract_is_not_visual_certification(self):
        outcome = evaluate_text_contract("A scene in a living room")
        self.assertTrue(outcome.ok)
        self.assertIn("nie ma niezależnego", outcome.report_pl)

    def test_exact_requirements_present(self):
        result = evaluate_text_contract("A European child with a laptop in a living room",
                                        "living room\nlaptop", "rice field\nmeadow")
        self.assertTrue(result.ok)
        self.assertIn("NIE zostały zweryfikowane", result.report_pl)

    def test_missing_required_phrase_blocks(self):
        result = evaluate_text_contract("Child holding a laptop in a rice field",
                                        "living room\nlaptop")
        self.assertFalse(result.ok)
        self.assertIn("living room", result.report_pl)

    def test_forbidden_phrase_blocks_even_if_required_present(self):
        result = evaluate_text_contract("A laptop in a living room next to a rice field",
                                        "living room", "rice field")
        self.assertFalse(result.ok)
        self.assertIn("rice field", result.report_pl)

    def test_whitespace_case_normalization(self):
        self.assertTrue(evaluate_text_contract("A QUIET  Living\nROOM with a laptop", "living room").ok)

    def test_duplicate_lines_ignored(self):
        self.assertEqual(parse_phrases("laptop\nLAPTOP\n\n living room"), ("laptop", "living room"))


class OffloadTests(unittest.TestCase):
    def test_llama_cpp_reported_offload(self):
        stderr = "llm_load_tensors: offloaded 16/49 layers to GPU\n"
        self.assertEqual(parse_gpu_offload(stderr), "16/49 language-model layers reported on GPU")

    def test_unknown_offload_not_faked(self):
        self.assertIn("not reported", parse_gpu_offload("GPU memory used 4500 MiB"))

    @unittest.skipIf(os.name == "nt", "POSIX executable fixture")
    def test_runner_does_not_accept_echoed_instruction_as_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake = folder / "llama-cli"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import sys\n"
                            "output=sys.argv[sys.argv.index('-o')+1]\n"
                            "with open(output, 'w') as f:\n"
                            " f.write('User:\\\\n[ANALYSIS]\\\\n1-3 sentences describing what is visibly present.\\\\n[KEEP]\\\\nWhat must be preserved.\\\\n[IMPROVE]\\\\nConcrete changes worth making.\\\\n[PROMPT]\\\\nOne self-contained, detailed en-US image-generation prompt.')\n")
            fake.chmod(0o755)
            with self.assertRaises(ValueError):
                run_once(fake, folder/'model.gguf', folder/'mmproj.gguf', folder/'image.png',
                         'prompt', 16, 4096, 500, 128, False, 30)


if __name__ == "__main__":
    unittest.main()
