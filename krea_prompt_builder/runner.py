"""Disposable local llama.cpp process, explicit device modes, private opt-in diagnostics."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from .prompting import SCHEMA, parse_result

LOG = logging.getLogger("ComfyUI-KreaPromptBuilder")
_SEMAPHORE = threading.Lock()
EXECUTION_DEVICES = ("hybrid", "cpu", "gpu")


def find_executable(user_value: str) -> Path:
    value = user_value.strip().strip('"') or "llama-cli"
    path = Path(value).expanduser()
    candidate = path if path.is_file() else Path(shutil.which(value) or "")
    if not candidate.is_file():
        raise FileNotFoundError(
            "Missing llama-cli.exe. Download a Windows llama.cpp build and specify its full path "
            "in llama_cli_path; GGUF files are not executables."
        )
    return candidate.resolve()


def device_flags(execution_device: str, gpu_layers: int, projector_gpu: bool) -> list[str]:
    if execution_device not in EXECUTION_DEVICES:
        raise ValueError(f"Invalid device: {execution_device}")
    count = 0 if execution_device == "cpu" else 999 if execution_device == "gpu" else gpu_layers
    flags = ["--gpu-layers", str(count)]
    if execution_device == "cpu" or not projector_gpu:
        flags.append("--no-mmproj-offload")
    return flags


def make_command(
    executable: Path, model: Path, mmproj: Path, image: Path, schema_path: Path,
    output_path: Path, instruction: str, gpu_layers: int, context_size: int,
    max_tokens: int, batch_size: int, projector_gpu: bool,
    execution_device: str = "hybrid", output_mode: str = "plain_sections",
    reasoning: str = "off",
) -> list[str]:
    if output_mode not in ("plain_sections", "json_schema"):
        raise ValueError(f"Unknown output mode: {output_mode}")
    if reasoning not in ("off", "auto"):
        raise ValueError(f"Unknown reasoning mode: {reasoning}")
    args = [
        str(executable), "-m", str(model), "--mmproj", str(mmproj),
        "--image", str(image), "-p", instruction,
        "-o", str(output_path),
        "--offline", "--single-turn", "--simple-io",
        "--no-display-prompt", "--no-warmup",
        "--log-verbosity", "1", "--log-colors", "off",
        "--ctx-size", str(context_size), "--predict", str(max_tokens),
        "--batch-size", str(batch_size), "--ubatch-size", str(min(256, batch_size)),
        "--cache-ram", "0", "--temp", "0.2", "--reasoning", reasoning,
    ]
    if reasoning == "off":
        args.extend(("--reasoning-budget", "0"))
    if output_mode == "json_schema":
        args.extend(("-jf", str(schema_path)))
    args.extend(device_flags(execution_device, gpu_layers, projector_gpu))
    return args


def terminate_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            LOG.warning("taskkill failed, killing VLM process directly")
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def parse_gpu_offload(stderr: str) -> str:
    """Extract confirmed layers from llama.cpp stderr; never infer from VRAM graph."""
    patterns = (
        r"(?i)offloaded\s+(\d+)\s*/\s*(\d+)\s+layers?\b",
        r"(?i)offloading\s+(\d+)\s*/\s*(\d+)\s+layers?\b",
    )
    found = []
    for pattern in patterns:
        found.extend((int(a), int(b)) for a, b in re.findall(pattern, stderr))
    if not found:
        return "not reported by llama.cpp; inspect private local stderr if needed"
    done, total = found[-1]
    return f"{done}/{total} language-model layers reported on GPU"


def _diagnostic_summary(payload: str, stdout: str, stderr: str, file_exists: bool) -> str:
    # Do not show or print private content by default.
    if not payload.strip():
        classification = "empty output"
    elif "<think>" in payload or "<|channel>thought" in payload:
        classification = "reasoning or unstructured output"
    elif "{" in payload and "}" not in payload:
        classification = "possibly truncated JSON"
    else:
        classification = "unrecognized response format"
    return (f"{classification}; file_exists={file_exists}; "
            f"response_chars={len(payload)}; stdout_chars={len(stdout)}; stderr_chars={len(stderr)}")


def _store_diagnostics(directory: Path | None, *, model: Path, output_mode: str,
                       execution_device: str, code: int | None, elapsed: float,
                       stdout: str, stderr: str, result: str,
                       gpu_layers: int, offload_summary: str) -> Path | None:
    if directory is None:
        return None
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    run_dir = directory / f"vlm_{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    run_dir.mkdir(mode=0o700)
    (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    (run_dir / "result.txt").write_text(result, encoding="utf-8")
    (run_dir / "meta.json").write_text(json.dumps({
        "model_filename": model.name, "mode": output_mode, "device": execution_device,
        "exit_code": code, "elapsed_seconds": round(elapsed, 2),
        "gpu_layers_requested": gpu_layers, "gpu_offload_reported": offload_summary,
        "WARNING": "LOCAL PRIVATE CONTENT: diagnostics may include image-derived text and prompts",
    }, indent=2), encoding="utf-8")
    return run_dir


def run_once(
    executable: Path, model: Path, mmproj: Path, image: Path,
    instruction: str, gpu_layers: int, context_size: int, max_tokens: int,
    batch_size: int, projector_gpu: bool, timeout_seconds: int,
    execution_device: str = "hybrid", output_mode: str = "plain_sections",
    reasoning: str = "off", diagnostics_dir: Path | None = None,
) -> dict[str, str]:
    with _SEMAPHORE:
        with tempfile.TemporaryDirectory(prefix="krea_cli_") as tmp:
            base = Path(tmp)
            result_path = base / "result.txt"
            schema_path = base / "schema.json"
            schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
            cmd = make_command(executable, model, mmproj, image, schema_path, result_path,
                               instruction, gpu_layers, context_size, max_tokens, batch_size,
                               projector_gpu, execution_device, output_mode, reasoning)
            env = os.environ.copy()
            env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "LLAMA_ARG_OFFLINE": "1"})
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            LOG.info("Starting transient local VLM (%s, %s, %s, thinking=%s)",
                     executable.name, execution_device, output_mode, reasoning)
            start = time.monotonic()
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                env=env, cwd=str(base), creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            timed_out = False
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate_tree(proc)
                stdout_bytes, stderr_bytes = proc.communicate()
            except BaseException:
                terminate_tree(proc)
                proc.communicate()
                raise
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            file_exists = result_path.exists()
            result_text = result_path.read_text(encoding="utf-8", errors="replace") if file_exists else ""
            offload_summary = parse_gpu_offload(stderr)
            requested_gpu_layers = 0 if execution_device == "cpu" else 999 if execution_device == "gpu" else gpu_layers
            LOG.info("llama.cpp GPU layers requested=%s, actual=%s", requested_gpu_layers, offload_summary)
            diag = _store_diagnostics(diagnostics_dir, model=model, output_mode=output_mode,
                                      execution_device=execution_device, code=proc.returncode,
                                      elapsed=time.monotonic()-start, stdout=stdout,
                                      stderr=stderr, result=result_text,
                                      gpu_layers=requested_gpu_layers, offload_summary=offload_summary)
            where = f" Local diagnostics: {diag}" if diag else " Enable save_diagnostics to inspect local raw output."
            if timed_out:
                raise TimeoutError(f"VLM timed out after {timeout_seconds}s; process tree terminated.{where}")
            if proc.returncode != 0:
                raise RuntimeError(f"llama-cli exited with status {proc.returncode}.{where} "
                                   "Check CLI flags, model/mmproj compatibility, RAM and VRAM.")
            # -o may contain only output, while some builds write the real response on stdout.
            candidates = [("output_file", result_text), ("stdout", stdout)]
            errors: list[str] = []
            for origin, payload in candidates:
                if not payload.strip():
                    continue
                try:
                    parsed = parse_result(payload)
                    LOG.info("Local VLM completed; parsed %s; no resident server", origin)
                    parsed["_gpu_offload_info"] = (f"Requested GPU layers: {requested_gpu_layers}. "
                                                    f"llama.cpp reported: {offload_summary}.")
                    return parsed
                except ValueError:
                    errors.append(f"{origin}: {_diagnostic_summary(payload, stdout, stderr, file_exists)}")
            summary = "; ".join(errors) if errors else _diagnostic_summary("", stdout, stderr, file_exists)
            raise ValueError(f"VLM did not return a complete prompt. {summary}.{where}")
