"""v0.1.5: synthetic regression for Gemma bilingual colon headings.

The original private image/transcript supplied by a user is deliberately NOT
included. The same syntax is exercised with invented non-identifying content.
"""
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from krea_prompt_builder.prompting import parse_result
from krea_prompt_builder.runner import run_once


COLON = '''User:
Instructions (echo). [ANALYSIS_EN], [KEEP_EN], [IMPROVE_EN], [PROMPT_EN_US], [ANALYSIS_PL], [EDIT_PLAN_PL], [END].
Assistant:
ANALYSIS_EN: A white card lies on a wooden table.

KEEP_EN: Preserve the white card and wooden tabletop.

IMPROVE_EN: None.

PROMPT_EN_US: A plain white card resting on a wooden table in soft daylight.

ANALYSIS_PL: Na drewnianym stole leży biała kartka.

EDIT_PLAN_PL:
ZACHOWAĆ: Biała kartka i drewniany stół.
ZMIENIĆ: Brak koniecznych zmian.

[END]
'''


class GemmaColonRegressionTests(unittest.TestCase):
    def test_observed_colon_headers_with_prompt_echo(self):
        result = parse_result(COLON, require_polish=True)
        self.assertEqual(len(result), 6)
        self.assertTrue(result['prompt_en_us'].startswith('A plain white card'))
        self.assertIn('drewnianym stole', result['analysis_pl'])
        self.assertIn('ZMIENIĆ', result['edit_plan_pl'])
        self.assertNotIn('Instructions (echo)', str(result))

    def test_single_line_colon_and_bracket_sections_mixed(self):
        data = '''[ANALYSIS_EN] A white square.
KEEP_EN: Keep the square.
[IMPROVE_EN]
None.
PROMPT_EN_US: A white square on a dark canvas.
[ANALYSIS_PL] Biały kwadrat na tle.
EDIT_PLAN_PL: ZACHOWAĆ: kwadrat. ZMIENIĆ: nic.
[END]'''
        result = parse_result(data, require_polish=True)
        self.assertEqual(result['analysis_en'], 'A white square.')
        self.assertEqual(result['prompt_en_us'], 'A white square on a dark canvas.')

    def test_last_complete_colon_answer_is_used(self):
        first = COLON.replace('white card', 'green card').replace('biała kartka', 'zielona kartka')
        result = parse_result(first + '\n' + COLON, require_polish=True)
        self.assertIn('white card', result['prompt_en_us'])

    def test_missing_end_rejected(self):
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(COLON.replace('[END]', ''), require_polish=True)

    def test_nonstandalone_end_rejected(self):
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(COLON.replace('[END]', '[END] some extra prose'), require_polish=True)

    def test_trailing_unfinished_text_after_end_rejected(self):
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(COLON + '\n[ANALYSIS_EN]\nA new unfinished response.', require_polish=True)

    def test_missing_section_rejected(self):
        cut = COLON.replace('ANALYSIS_PL: Na drewnianym stole leży biała kartka.\n\n', '')
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(cut, require_polish=True)

    def test_empty_field_rejected(self):
        empty = COLON.replace('KEEP_EN: Preserve the white card and wooden tabletop.', 'KEEP_EN:')
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(empty, require_polish=True)

    def test_order_must_be_correct(self):
        wrong = COLON.replace('KEEP_EN:', 'XXX:').replace('IMPROVE_EN:', 'KEEP_EN:').replace('XXX:', 'IMPROVE_EN:')
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(wrong, require_polish=True)

    def test_echo_only_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'echoed user request'):
            parse_result('User:\n' + COLON.split('Assistant:')[0], require_polish=True)

    def test_incomplete_thought_after_echo_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'unfinished thinking'):
            parse_result('User:\nplaceholder\nAssistant:\n[Start thinking]\n' + COLON.split('Assistant:')[1], require_polish=True)

    def test_thought_and_echo_removed_before_final_colon_response(self):
        thought = 'User:\nplaceholder\nAssistant:\n[Start thinking]\n' + COLON.split('Assistant:')[1] + '[End thinking]\n'
        data = thought + COLON.split('Assistant:')[1]
        result = parse_result(data, require_polish=True)
        self.assertEqual(result['prompt_en_us'], 'A plain white card resting on a wooden table in soft daylight.')

    def test_node_unchanged_ports_and_model_run_once_with_colon_result(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            exe = base / 'fake-llama-cli'
            exe.write_text('#!/usr/bin/env python3\n'
                           'import sys\nfrom pathlib import Path\n'
                           'a = sys.argv\n'
                           'Path(a[a.index("-o")+1]).write_text(' + repr(COLON) + ', encoding="utf-8")\n', encoding='utf8')
            exe.chmod(0o755)
            with patch('krea_prompt_builder.runner.subprocess.Popen', wraps=subprocess.Popen) as process:
                parsed = run_once(exe, base/'model.gguf', base/'mmproj.gguf', base/'input.png',
                                  'Describe', 16, 4096, 1600, 128, False, 30, report_language='pl_en')
            self.assertEqual(process.call_count, 1)
            self.assertEqual(parsed['analysis_pl'], 'Na drewnianym stole leży biała kartka.')
            self.assertIn('Requested GPU layers: 16', parsed['_gpu_offload_info'])


if __name__ == '__main__':
    unittest.main()
