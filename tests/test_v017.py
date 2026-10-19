"""Regression tests for real-world Gemma 4 llama.cpp format variations.

Synthetic content only: no private images, original user prompts, or logs.
"""
import unittest

from krea_prompt_builder.prompting import parse_result, build_instruction
from krea_prompt_builder.contract import evaluate_scene_contract


SYNTHETIC = (
    "User:\nPlease analyze the image and use [END].\n"
    "[ANALYSIS_EN], [KEEP_EN], [IMPROVE_EN], [PROMPT_EN_US], "
    "[ANALYSIS_PL], [EDIT_PLAN_PL], [CONTRACT_REPORT_PL], [END].\n"
    "Assistant:\n"
    "ANALYSIS_EN: A red bicycle in a bright courtyard.\n\n"
    "KEEP_EN: Red frame, wheels, sunny courtyard.\n\n"
    "IMPROVE_EN: None.\n\n"
    "PROMPT_EN_US: A bright photograph of a red bicycle in a courtyard.\n\n"
    "ANALYSIS_PL: Czerwony rower stoi na jasnym dziedzińcu.\n\n"
    "EDIT_PLAN_PL: ZACHOWAĆ: rower. ZMIENIĆ: nic.\n\n"
    "CONTRACT_REPORT_PL: ZAŁOŻENIA ŹRÓDŁOWE: czerwony rower.\n"
    "ZGODNOŚĆ OBRAZU: rower widoczny.\n"
    "ZGODNOŚĆ PROMPTU: prompt zachowuje rower.\n"
    "ROZBIEŻNOŚCI: brak.\n"
    "WYNIK_PROMPTU: ZGODNY.\n\n"
    "END\n"
)


class GemmaTerminatorTests(unittest.TestCase):
    def test_bare_end_real_shape_with_colon_headers(self):
        data = parse_result(SYNTHETIC, require_polish=True)
        self.assertEqual(len(data), 7)
        self.assertEqual(data['analysis_pl'], 'Czerwony rower stoi na jasnym dziedzińcu.')
        self.assertTrue(data['prompt_en_us'].startswith('A bright photograph'))
        self.assertNotIn('Assistant:', data['prompt_en_us'])
        self.assertNotIn('END', data['contract_report_pl'])

    def test_bracket_end_and_bracket_headers(self):
        bracketed = SYNTHETIC.replace('\nEND\n','\n[ END ]\n')
        for tag in ('ANALYSIS_EN','KEEP_EN','IMPROVE_EN','PROMPT_EN_US',
                    'ANALYSIS_PL','EDIT_PLAN_PL','CONTRACT_REPORT_PL'):
            bracketed = bracketed.replace('\n'+tag+': ', '\n['+tag+']\n')
        data = parse_result(bracketed, require_polish=True)
        self.assertEqual(data['prompt_en_us'], 'A bright photograph of a red bicycle in a courtyard.')

    def test_end_only_inside_prompt_is_not_terminal(self):
        text = SYNTHETIC.replace('\nEND\n', '\nEND\nFurther unfinished response')
        with self.assertRaisesRegex(ValueError,'six bilingual'):
            parse_result(text, require_polish=True)

    def test_end_with_payload_is_not_terminal(self):
        text = SYNTHETIC.replace('\nEND\n', '\nEND some unrelated text\n')
        with self.assertRaisesRegex(ValueError,'six bilingual'):
            parse_result(text, require_polish=True)

    def test_end_missing_is_not_terminal(self):
        text = SYNTHETIC.replace('\nEND\n','')
        with self.assertRaisesRegex(ValueError,'six bilingual'):
            parse_result(text, require_polish=True)

    def test_missing_required_section_is_not_accepted(self):
        text = SYNTHETIC.replace('ANALYSIS_PL:', 'OTHER:')
        with self.assertRaisesRegex(ValueError,'six bilingual'):
            parse_result(text, require_polish=True)

    def test_echo_only_rejected(self):
        with self.assertRaisesRegex(ValueError,'echoed user'):
            parse_result('User:\n'+build_instruction('improve','','',report_language='pl_en'), require_polish=True)

    def test_unfinished_thinking_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'unfinished thinking'):
            parse_result('Assistant:\n[Start thinking]\n'+SYNTHETIC.split('Assistant:\n')[-1], require_polish=True)

    def test_legacy_six_fields_still_supported_with_bare_end(self):
        text = SYNTHETIC.replace('CONTRACT_REPORT_PL: ZAŁOŻENIA ŹRÓDŁOWE: czerwony rower.\n'
               'ZGODNOŚĆ OBRAZU: rower widoczny.\n'
               'ZGODNOŚĆ PROMPTU: prompt zachowuje rower.\n'
               'ROZBIEŻNOŚCI: brak.\n'
               'WYNIK_PROMPTU: ZGODNY.\n\n', '')
        data = parse_result(text, require_polish=True)
        self.assertEqual(len(data), 6)
        self.assertNotIn('contract_report_pl', data)


class ContractVerdictPunctuationTests(unittest.TestCase):
    def test_positive_verdict_with_period_is_recognized(self):
        result = evaluate_scene_contract('A red bicycle on a street',
            source_prompt='red bicycle', model_report_pl='ZGODNOŚĆ PROMPTU: zachowany.\nWYNIK_PROMPTU: ZGODNY.')
        self.assertTrue(result.ok)
        self.assertNotIn('BRAK WERDYKTU', result.report_pl)

    def test_negative_verdict_with_period_still_blocks(self):
        result = evaluate_scene_contract('A blue bicycle on a street',
            source_prompt='red bicycle', model_report_pl='WYNIK_PROMPTU: NIEZGODNY.')
        self.assertFalse(result.ok)
        self.assertIn('BLOKADA WEDŁUG VLM', result.report_pl)

    def test_uncertain_verdict_with_period_is_recognized(self):
        result = evaluate_scene_contract('A bicycle',source_prompt='red bicycle',
                                         model_report_pl='WYNIK_PROMPTU: NIEPEWNY.')
        self.assertTrue(result.ok)
        self.assertIn('NIEPEWNOŚĆ', result.report_pl)

    def test_substring_status_is_not_recognized(self):
        result = evaluate_scene_contract('A bicycle',source_prompt='red bicycle',
                                         model_report_pl='WYNIK_PROMPTU: NIEZGODNY z powodu tekstu')
        self.assertTrue(result.ok)
        self.assertIn('BRAK WERDYKTU', result.report_pl)


if __name__ == '__main__':
    unittest.main()
