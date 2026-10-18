"""v0.1.4: one VLM invocation, bilingual report, legacy outputs, compact frontend."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from krea_prompt_builder.prompting import (
    SCHEMA_BILINGUAL, build_instruction, parse_result
)
from krea_prompt_builder.runner import run_once


FINAL = """[ANALYSIS_EN]
A woman rests in bed while another person leans over her and touches her forehead.
[KEEP_EN]
Preserve both figures, their positions and the room composition.
[IMPROVE_EN]
Make the hand positions more anatomically clear, without changing the action.
[PROMPT_EN_US]
A realistic, softly lit indoor photograph of an older woman lying in bed while a man leans over and carefully touches her forehead, natural proportions, authentic room details.
[ANALYSIS_PL]
Na zdjęciu starsza kobieta leży w łóżku, a mężczyzna pochyla się nad nią i dotyka jej czoła. Nie wiadomo, co dokładnie nakłada na skórę.
[EDIT_PLAN_PL]
ZACHOWAĆ: Obie postacie, pozycje ich rąk, pościel i wnętrze pokoju, ponieważ stanowią istotę sceny.
ZMIENIĆ: Wyostrzyć kontury dłoni bez zmiany gestu; nie dodawać rekwizytów.
[END]
"""


class BilingualTests(unittest.TestCase):
    def test_bilingual_instruction_requests_six_fields_but_one_pass(self):
        text = build_instruction('improve', 'Delikatnie popraw anatomię', 'osoby w pokoju',
                                 scene_contract='Keep the room', report_language='pl_en')
        self.assertIn('[ANALYSIS_PL]', text)
        self.assertIn('[EDIT_PLAN_PL]', text)
        self.assertIn('[END]', text)
        self.assertIn('Polish', text)
        self.assertIn('Keep the room', text)
        self.assertIn('en-US', text)

    def test_one_response_returns_polish_and_english(self):
        parsed = parse_result('User:\n' + build_instruction('improve', '', '',report_language='pl_en')
                              + '\nAssistant:\n' + FINAL, require_polish=True)
        self.assertIn('lying in bed', parsed['prompt_en_us'])
        self.assertIn('starsza kobieta', parsed['analysis_pl'])
        self.assertIn('ZACHOWAĆ', parsed['edit_plan_pl'])
        self.assertEqual(len(parsed), 6)

    def test_bilingual_rejects_missing_end_marker(self):
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(FINAL.replace('[END]', ''), require_polish=True)

    def test_bilingual_rejects_old_four_section_response(self):
        old = '[ANALYSIS]\nA frog.\n[KEEP]\nThe frog.\n[IMPROVE]\nEdges.\n[PROMPT]\nA frog on yellow.'
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(old, require_polish=True)
        self.assertEqual(parse_result(old)['prompt_en_us'], 'A frog on yellow.')

    def test_last_full_bilingual_answer_wins(self):
        first = FINAL.replace('An older woman', 'A young woman').replace('starsza kobieta', 'młoda kobieta')
        parsed = parse_result(first + '\n' + FINAL, require_polish=True)
        self.assertIn('starsza kobieta', parsed['analysis_pl'])

    def test_closed_reasoning_is_skipped_even_if_it_has_bilingual_labels(self):
        draft = FINAL.replace('older woman', 'young woman')
        data = 'User:\nplaceholder\nAssistant:\n[Start thinking]\n' + draft + '[End thinking]\n' + FINAL
        parsed = parse_result(data, require_polish=True)
        self.assertIn('older woman', parsed['prompt_en_us'])
        self.assertNotIn('young woman', parsed['prompt_en_us'])

    def test_incomplete_thinking_is_not_a_report(self):
        with self.assertRaisesRegex(ValueError, 'unfinished thinking'):
            parse_result('Assistant:\n[Start thinking]\n' + FINAL, require_polish=True)

    def test_json_schema_six_fields_required(self):
        self.assertEqual(len(SCHEMA_BILINGUAL['required']), 6)
        good = {
            'analysis_en': 'Visible woman', 'keep': 'Keep room',
            'improve': 'Fix hand', 'prompt_en_us': 'A woman in a room.',
            'analysis_pl': 'Kobieta w pokoju', 'edit_plan_pl': 'ZACHOWAĆ: pokój. ZMIENIĆ: dłoń.'
        }
        self.assertEqual(parse_result(json.dumps(good, ensure_ascii=False), require_polish=True), good)
        del good['analysis_pl']
        with self.assertRaisesRegex(ValueError, 'six bilingual'):
            parse_result(json.dumps(good), require_polish=True)

    def test_legacy_english_parse_unchanged(self):
        parsed = parse_result('[ANALYSIS]\nWhite paper.\n[KEEP]\nWhite.\n[IMPROVE]\nNone.\n[PROMPT]\nA blank white page.')
        self.assertEqual(parsed['prompt_en_us'], 'A blank white page.')
        self.assertNotIn('analysis_pl', parsed)

    def test_parser_preserves_literal_non_english_image_text_in_prompt(self):
        data = FINAL.replace('authentic room details.', 'and the visible lettering "żabka".')
        self.assertIn('żabka', parse_result(data, require_polish=True)['prompt_en_us'])

    def test_runner_calls_single_subprocess_and_reads_bilingual_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe = base / 'fake-llama-cli'
            exe.write_text('#!/usr/bin/env python3\n'
                           'import sys\n'
                           'from pathlib import Path\n'
                           'args=sys.argv\n'
                           'Path(args[args.index("-o")+1]).write_text(' + repr(FINAL) + ', encoding="utf-8")\n', encoding='utf8')
            exe.chmod(0o755)
            with patch('krea_prompt_builder.runner.subprocess.Popen', wraps=subprocess.Popen) as process:
                actual = run_once(exe, base/'model.gguf', base/'mmproj.gguf', base/'image.png',
                                  'Describe', 16, 4096, 1200, 128, False, 30,
                                  report_language='pl_en')
            self.assertEqual(process.call_count, 1)
            self.assertIn('starsza kobieta', actual['analysis_pl'])
            self.assertIn('Requested GPU layers: 16', actual['_gpu_offload_info'])


class FrontendTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Requires Node.js for JS execution test')
    def test_js_preserves_values_when_hiding_and_supports_four_panels(self):
        root = Path(__file__).resolve().parents[1]
        js = root / 'web' / 'compact.js'
        script = r'''
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const src = fs.readFileSync(process.argv[2], 'utf8').replace('import { app } from "../../scripts/app.js";', 'const app = globalThis.mockApp;');
let registered; const mockApp = { registerExtension(extension){ registered=extension; } };
const ctx = {mockApp, globalThis:{mockApp}, queueMicrotask: fn => fn()};
ctx.globalThis = ctx;
vm.runInNewContext(src, ctx);
const proto = {onNodeCreated(){}};
const nodeType = {prototype:proto};
registered.beforeRegisterNodeDef(nodeType, {name:'Krea2TurboPromptBuilderV01'});
const make = name => ({name, type:'combo', value:name+'-value', options:{values:[]}, computeSize:()=>[140,20]});
const node = Object.assign(Object.create(proto), {
  widgets:['model_gguf','llama_cli_path','source_prompt','save_diagnostics','report_language','scene_contract'].map(make),
  properties:{}, inputs:[], size:[400,1000],
  addWidget(type,name,value,callback,options){const w={name,type,value,callback,options};this.widgets.push(w);return w;},
  computeSize(){return [400,this.widgets.filter(w=>!w.hidden).length*26+100];},
  setSize(size){this.size=size;}, setDirtyCanvas(){}
});
node.onNodeCreated();
const get = n=>node.widgets.find(w=>w.name===n);
assert.strictEqual(get('llama_cli_path').hidden,true);
assert.strictEqual(get('model_gguf').hidden,undefined);
assert.strictEqual(get('llama_cli_path').value,'llama_cli_path-value');
const selector=get('⚙ Settings panel');
selector.callback('Advanced');
assert.strictEqual(get('llama_cli_path').hidden,undefined);
assert.strictEqual(get('save_diagnostics').hidden,true);
selector.callback('Diagnostics');
assert.strictEqual(get('save_diagnostics').hidden,undefined);
assert.strictEqual(get('llama_cli_path').hidden,true);
selector.callback('All');
assert.strictEqual(get('llama_cli_path').hidden,undefined);
assert.strictEqual(get('llama_cli_path').value,'llama_cli_path-value');
assert.strictEqual(get('scene_contract').value,'scene_contract-value');
console.log('frontend lifecycle passed');
'''
        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / 'frontend.cjs'
            harness.write_text(script, encoding='utf-8')
            run = subprocess.run(['node', str(harness), str(js)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, f'frontend test failed:\n{run.stdout}\n{run.stderr}')


if __name__ == '__main__':
    unittest.main()
