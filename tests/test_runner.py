import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from krea_prompt_builder.prompting import SCHEMA
from krea_prompt_builder.runner import make_command, run_once


class RunnerTests(unittest.TestCase):
    def test_command_contains_only_local_paths_and_offline(self):
        p = Path("/temp/test.gguf")
        args = make_command(p, p, p, p, p, p, "test", 24, 4096, 900, 512, False)
        self.assertIn("--offline", args)
        self.assertIn("--no-mmproj-offload", args)
        self.assertNotIn("--model-url", args)
        self.assertNotIn("--hf-repo", args)

    @unittest.skipIf(os.name == "nt", "POSIX fixture uses executable shebang")
    def test_disposable_cli_process_with_json_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake = folder / "llama-cli"
            fake.write_text(
                '#!/usr/bin/env python3\n'
                'import json,sys,os\n'
                'a=sys.argv\n'
                'assert "--offline" in a\n'
                'assert "--image" in a\n'
                'out=a[a.index("-o")+1]\n'
                'print("fake-stderr",file=sys.stderr)\n'
                'open(out,"w",encoding="utf-8").write(json.dumps({"analysis_en":"sky","keep":"clouds","improve":"contrast","prompt_en_us":"A soft cloudscape."}))\n'
            )
            fake.chmod(0o755)
            data = run_once(fake, folder / "model.gguf", folder / "mmproj.gguf",
                            folder / "image.png", "one prompt", 20, 4096, 512, 256, True, 30)
            self.assertEqual(data["prompt_en_us"], "A soft cloudscape.")

    @unittest.skipIf(os.name == "nt", "POSIX fixture uses executable shebang")
    def test_timeout_terminates_isolated_process(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake = folder / "llama-cli"
            fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
            fake.chmod(0o755)
            t0 = time.monotonic()
            with self.assertRaises(TimeoutError):
                run_once(fake, folder / "model.gguf", folder / "mmproj.gguf",
                    folder / "image.png", "test", 20, 4096, 512, 256, True, 1)
            self.assertLess(time.monotonic() - t0, 8)
