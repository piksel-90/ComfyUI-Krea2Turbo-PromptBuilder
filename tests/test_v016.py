"""v0.1.6 regression tests. All fixtures synthetic; no personal images/prompts."""
from __future__ import annotations

import importlib.util
import subprocess
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from krea_prompt_builder.contract import evaluate_scene_contract
from krea_prompt_builder.prompting import (
    SCHEMA_BILINGUAL_CONTRACT, build_instruction, parse_result
)
from krea_prompt_builder.runner import run_once


FINAL = '''User:
An echoed prompt with [ANALYSIS_EN] and [CONTRACT_REPORT_PL].
Assistant:
ANALYSIS_EN: A child holding a laptop in an indoor room.
KEEP_EN: Preserve the child, room and laptop.
IMPROVE_EN: Improve finger geometry.
PROMPT_EN_US: A child holding a laptop inside a cozy living room, soft daylight.
ANALYSIS_PL: Dziecko trzyma laptop w pokoju.
EDIT_PLAN_PL: ZACHOWAĆ: dziecko i pokój. ZMIENIĆ: palce.
CONTRACT_REPORT_PL:
ZAŁOŻENIA ŹRÓDŁOWE: Dziecko z laptopem w salonie.
ZGODNOŚĆ OBRAZU: Widać dziecko w pomieszczeniu.
ZGODNOŚĆ PROMPTU: Wymagania o miejscu i przedmiocie zachowane.
WYNIK_PROMPTU: ZGODNY
ROZBIEŻNOŚCI: Brak oczywistych.
UZASADNIENIE: Zachowano salon i laptop.
[END]
'''


class BilingualV016ParserTests(unittest.TestCase):
    def test_colon_and_bracket_contract_headings(self):
        result = parse_result(FINAL, require_polish=True)
        self.assertIn('WYNIK_PROMPTU: ZGODNY', result['contract_report_pl'])
        self.assertEqual(len(result), 7)
        self.assertIn('living room', result['prompt_en_us'])
        self.assertNotIn('echoed prompt', str(result))

    def test_mixed_heading_formats_and_content_after_colon(self):
        data = FINAL.replace('CONTRACT_REPORT_PL:', '[CONTRACT_REPORT_PL]')
        self.assertIn('WYNIK_PROMPTU: ZGODNY', parse_result(data, require_polish=True)['contract_report_pl'])

    def test_missing_or_truncated_contract_section_rejected(self):
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(FINAL.replace('[END]', ''), require_polish=True)
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(FINAL.replace('[END]', 'UNFINISHED'), require_polish=True)
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(FINAL.replace('UZASADNIENIE: Zachowano salon i laptop.\n[END]',
                                       'UZASADNIENIE: Zachowano salon i laptop.\n[END]\nNew draft'),
                         require_polish=True)

    def test_old_six_field_transcript_still_accepted(self):
        legacy = FINAL.split('CONTRACT_REPORT_PL:')[0] + '[END]'
        data = parse_result(legacy, require_polish=True)
        self.assertEqual(len(data), 6)
        self.assertNotIn('contract_report_pl', data)

    def test_json_with_contract_report_and_legacy_json(self):
        example = dict(analysis_en='A child in a room', keep='child', improve='fingers',
                       prompt_en_us='A child with a laptop in a room',
                       analysis_pl='Dziecko w pokoju', edit_plan_pl='ZACHOWAĆ: pokój. ZMIENIĆ: dłoń.',
                       contract_report_pl='WYNIK_PROMPTU: ZGODNY')
        self.assertEqual(len(SCHEMA_BILINGUAL_CONTRACT['required']), 7)
        self.assertEqual(parse_result(json.dumps(example), require_polish=True), example)
        example.pop('contract_report_pl')
        self.assertEqual(len(parse_result(json.dumps(example), require_polish=True)), 6)

    def test_single_llama_cli_process_returns_seventh_field(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            exe = base / 'fake-llama-cli'
            exe.write_text('#!/usr/bin/env python3\n'
                           'import sys\nfrom pathlib import Path\n'
                           'a=sys.argv\nPath(a[a.index("-o")+1]).write_text(' +
                           repr(FINAL) + ', encoding="utf-8")\n', encoding='utf-8')
            exe.chmod(0o755)
            with patch('krea_prompt_builder.runner.subprocess.Popen', wraps=subprocess.Popen) as launch:
                result = run_once(exe, base/'model.gguf', base/'mmproj.gguf', base/'image.png',
                                  'Analyze and compare to the source', 16, 4096, 2000, 128,
                                  False, 30, report_language='pl_en')
            self.assertEqual(launch.call_count, 1)
            self.assertIn('WYNIK_PROMPTU: ZGODNY', result['contract_report_pl'])
            self.assertIn('living room', result['prompt_en_us'])

    def test_instruction_marks_source_binding_not_just_context(self):
        s = build_instruction('improve', 'make lighting warmer',
                              'a child with a laptop in a living room',
                              scene_contract='never change the subject', report_language='pl_en')
        self.assertIn('not just inspiration', s.casefold())
        self.assertIn('binding intended requirements', s)
        self.assertIn('source and image differ', s)
        self.assertIn('CONTRACT_REPORT_PL', s)
        self.assertIn('WYNIK_PROMPTU', s)
        self.assertIn('never change the subject', s)


class ContractV016Tests(unittest.TestCase):
    def test_report_contains_real_source_goal_and_model_assessment(self):
        result = evaluate_scene_contract('A child holding a laptop in a living room',
            source_prompt='a child in a living room', user_goal='change the lighting',
            scene_contract='Keep the laptop', analysis_pl='Dziecko z laptopem.',
            model_report_pl='ZAŁOŻENIA ŹRÓDŁOWE: salon.\nWYNIK_PROMPTU: ZGODNY',
        )
        self.assertTrue(result.ok)
        for text in ('a child in a living room', 'change the lighting', 'Keep the laptop',
                     'WYNIK_PROMPTU: ZGODNY', 'nie ma niezależnego'):
            self.assertIn(text, result.report_pl)

    def test_explicit_vlm_prompts_mismatch_blocks_when_requirements_provided(self):
        result = evaluate_scene_contract('A child in a rice field',
            source_prompt='a child in a living room',
            model_report_pl='ZGODNOŚĆ OBRAZU: pole.\nWYNIK_PROMPTU: NIEZGODNY',
        )
        self.assertFalse(result.ok)
        self.assertIn('BLOKADA WEDŁUG VLM', result.report_pl)

    def test_image_mismatch_but_corrected_prompt_does_not_block(self):
        result = evaluate_scene_contract('A child in a living room',
            source_prompt='a child in a living room',
            model_report_pl='ZGODNOŚĆ OBRAZU: obraz przedstawia pole ryżowe.\n'
                            'ZGODNOŚĆ PROMPTU: wymagania przywrócone.\nWYNIK_PROMPTU: ZGODNY')
        self.assertTrue(result.ok)
        self.assertIn('pole ryżowe', result.report_pl)

    def test_unsure_is_not_silent_certification(self):
        result = evaluate_scene_contract('Child in a room', source_prompt='child in a room',
            model_report_pl='WYNIK_PROMPTU: NIEPEWNY')
        self.assertTrue(result.ok)
        self.assertIn('NIEPEWNOŚĆ', result.report_pl)

    def test_empty_model_report_fallback_is_specific_and_clearly_unverified(self):
        report1 = evaluate_scene_contract('Frog.', source_prompt='Green frog',
                                           analysis_pl='Zielona żabka.')
        report2 = evaluate_scene_contract('Apple.', source_prompt='Red apple',
                                           analysis_pl='Czerwone jabłko.')
        self.assertNotEqual(report1.report_pl, report2.report_pl)
        self.assertIn('Brak osobnej sekcji', report1.report_pl)
        self.assertIn('Green frog', report1.report_pl)
        self.assertTrue(report1.ok)  # ok means no detected violation, NOT visual verification

    def test_en_only_report_is_not_legacy_fixed_string(self):
        result = evaluate_scene_contract('A blue sky', source_prompt='A blue sky',
                                          user_goal='do not change the setting',
                                          analysis_en='Visible blue sky')
        self.assertIn('Visible blue sky', result.report_pl)
        self.assertIn('A blue sky', result.report_pl)
        self.assertNotEqual(result.report_pl,
                            'BRAK REGUŁ LITERALNYCH: wynik nie ma niezależnego potwierdzenia zgodności ze sceną.')

    def test_literal_violation_blocks_regardless_of_vlm_self_assessment(self):
        result = evaluate_scene_contract('A rice field', source_prompt='a living room',
                required_exact_phrases='living room', forbidden_exact_phrases='rice field',
                model_report_pl='WYNIK_PROMPTU: ZGODNY')
        self.assertFalse(result.ok)
        self.assertIn('KONTROLA LITERALNA', result.report_pl)
        self.assertIn('Brak wymaganych', result.report_pl)

    def test_verdict_in_narrative_is_not_a_machine_readable_status(self):
        result = evaluate_scene_contract('Prompt', source_prompt='original',
            model_report_pl='The word NIEZGODNY is mentioned, but no verdict line.')
        self.assertTrue(result.ok)
        self.assertIn('BRAK WERDYKTU', result.report_pl)


class NodeV016Tests(unittest.TestCase):
    def test_node_passes_source_and_contract_to_inference_and_report(self):
        import torch
        root = Path(__file__).resolve().parents[1]
        package = '_ComfyUICases016'
        with tempfile.TemporaryDirectory() as d:
            folder_paths = types.ModuleType('folder_paths')
            folder_paths.models_dir = d
            pkg = types.ModuleType(package)
            pkg.__path__ = [str(root)]
            sys.modules['folder_paths'] = folder_paths
            sys.modules[package] = pkg
            try:
                spec = importlib.util.spec_from_file_location(package+'.nodes', root/'nodes.py')
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                base = Path(d)
                (base/'llama_cpp').mkdir()
                (base/'llama_cpp'/'model.gguf').write_bytes(b'gguf')
                (base/'llama_cpp'/'mmproj-f16.gguf').write_bytes(b'projector')
                (base/'llama-cli').write_bytes(b'exe')
                node = module.KreaPromptBuilder()
                payload = dict(analysis_en='A child in a field.', keep='child', improve='setting',
                               prompt_en_us='A child in a rice field holding a laptop.',
                               analysis_pl='Dziecko na polu.', edit_plan_pl='ZACHOWAĆ: laptop. ZMIENIĆ: miejsce.',
                               contract_report_pl='ZGODNOŚĆ OBRAZU: pole ryżowe.\n'
                                                  'ZGODNOŚĆ PROMPTU: inne miejsce.\n'
                                                  'WYNIK_PROMPTU: NIEZGODNY')
                with patch.object(module,'run_once',return_value=payload) as run:
                    out = node.build(torch.zeros((1,16,16,3)),
                        'llama_cpp :: model.gguf','[AUTO: projector next to model]',str(base/'llama-cli'),
                        'improve','Improve clarity','A child in the living room holding a laptop',
                        0,384,16,False,2048,1200,128,30,0,
                        scene_contract='keep living room',report_language='pl_en')
                instruction = run.call_args.args[4]
                self.assertIn('A child in the living room holding a laptop',instruction)
                self.assertIn('Improve clarity',instruction)
                self.assertIn('keep living room',instruction)
                self.assertFalse(out[5])
                self.assertEqual(out[0],'')
                self.assertIn('ZGODNOŚĆ OBRAZU',out[4])
                self.assertIn('A child in the living room',out[4])
                self.assertEqual(len(out),9)
                self.assertEqual(run.call_count,1)
            finally:
                sys.modules.pop('folder_paths',None)
                sys.modules.pop(package,None)
                sys.modules.pop(package+'.nodes',None)


if __name__ == '__main__':
    unittest.main()
