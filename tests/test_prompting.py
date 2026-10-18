import unittest
from krea_prompt_builder.prompting import build_instruction, parse_result


class PromptingTests(unittest.TestCase):
    def test_prompt_is_en_us_instruction_with_user_context(self):
        result = build_instruction("improve", "Popraw kadr", "Red cat")
        self.assertIn("en-US", result)
        self.assertIn("Popraw kadr", result)
        self.assertIn("Red cat", result)

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            build_instruction("wrong", "", "")

    def test_parse_json(self):
        body = '{"analysis_en":"A cat","keep":"fur","improve":"light","prompt_en_us":"A cat in light."}'
        self.assertEqual(parse_result(body)["prompt_en_us"], "A cat in light.")

    def test_parse_fenced_json_with_think(self):
        body = '<think>internal</think>```json\n{"analysis_en":"A","keep":"B","improve":"C","prompt_en_us":"D"}\n```'
        self.assertEqual(parse_result(body)["keep"], "B")

    def test_non_json_rejected(self):
        with self.assertRaises(ValueError):
            parse_result("A cat in a hat. Not JSON")

    def test_empty_prompt_rejected(self):
        with self.assertRaises(ValueError):
            parse_result('{"analysis_en":"A","keep":"B","improve":"C","prompt_en_us":""}')
