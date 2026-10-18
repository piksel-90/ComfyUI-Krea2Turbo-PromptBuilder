"""Short-lived llama.cpp process. No Ollama, no web requests."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

from .prompting import SCHEMA, parse_result
import json

LOG = logging.getLogger("ComfyUI-KreaPromptBuilder")
# Only one VLM runs at a time in this ComfyUI process.
_SEMAPHORE = threading.Lock()


def find_executable(user_value: str) -> Path:
    value = user_value.strip().strip('"') or "llama-cli"
    path = Path(value).expanduser()
    candidate = path if path.is_file() else Path(shutil.which(value) or "")
    if not candidate.is_file():
        raise FileNotFoundError(
            "Missing llama.cpp executable: llama-cli.exe. Download a compatible Windows build "
            "from https://github.com/ggml-org/llama.cpp/releases , unpack it, and set "
            "llama_cli_path to the full path of llama-cli.exe in this node. "
            "GGUF model files are not the executable."
        )
    return candidate.resolve()


def make_command(
    executable: Path, model: Path, mmproj: Path, image: Path, schema_path: Path,
    output_path: Path, instruction: str, gpu_layers: int, context_size: int,
    max_tokens: int, batch_size: int, projector_gpu: bool,
) -> list[str]:
    args = [
        str(executable), "-m", str(model), "--mmproj", str(mmproj),
        "--image", str(image), "-p", instruction,
        "-jf", str(schema_path), "-o", str(output_path),
        "--offline", "--single-turn", "--simple-io",
        "--no-display-prompt", "--no-show-timings", "--no-warmup",
        "--log-verbosity", "1", "--log-colors", "off",
        "--gpu-layers", str(gpu_layers),
        "--ctx-size", str(context_size), "--predict", str(max_tokens),
        "--batch-size", str(batch_size), "--ubatch-size", str(min(256, batch_size)),
        "--cache-ram", "0",
    ]
    if not projector_gpu:
        args.append("--no-mmproj-offload")
    return args


def terminate_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # taskkill /T terminates child processes too, unlike proc.kill().
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            LOG.warning("taskkill failed; falling back to killing direct VLM process")
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def run_once(
    executable: Path, model: Path, mmproj: Path, image: Path,
    instruction: str, gpu_layers: int, context_size: int, max_tokens: int,
    batch_size: int, projector_gpu: bool, timeout_seconds: int,
) -> dict[str, str]:
    with _SEMAPHORE:
        with tempfile.TemporaryDirectory(prefix="krea_cli_") as tmp:
            base = Path(tmp)
            result_path = base / "result.txt"
            schema_path = base / "schema.json"
            schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
            cmd = make_command(executable, model, mmproj, image, schema_path, result_path,
                               instruction, gpu_layers, context_size, max_tokens,
                               batch_size, projector_gpu)
            env = os.environ.copy()
            env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "LLAMA_ARG_OFFLINE": "1"})
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            start_new_session = os.name != "nt"
            LOG.info("Starting transient local VLM process (%s)", executable.name)
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                env=env, cwd=str(base), creationflags=creationflags,
                start_new_session=start_new_session,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                terminate_tree(proc)
                proc.communicate()
                raise TimeoutError(f"VLM timed out after {timeout_seconds}s; process tree terminated") from exc
            except BaseException:
                terminate_tree(proc)
                proc.communicate()
                raise
            if proc.returncode != 0:
                # Avoid logging potentially private prompt/image-derived content from stderr.
                LOG.error("llama.cpp exited with status %s. Check binary version, mmproj "
                          "compatibility, and available VRAM/RAM.", proc.returncode)
                raise RuntimeError(f"Local llama.cpp process failed (exit {proc.returncode}). Check ComfyUI console")
            if result_path.exists():
                payload = result_path.read_text(encoding="utf-8", errors="replace")
            else:
                payload = stdout.decode("utf-8", errors="replace")
            result = parse_result(payload)
            LOG.info("Local VLM process completed; no resident server")
            return result
