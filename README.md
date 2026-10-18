# ComfyUI — Krea 2 Turbo Prompt Builder

**v0.1.2 (prototype / alpha)** · One generated image → one improved **en-US** prompt, with an evidence-based scene analysis and keep/change plan.

**Privacy:** No Ollama, remote AI API, or prompt/image upload. VLM inference is run through a **new local `llama-cli` subprocess for every execution**, using pre-downloaded GGUF and `mmproj` files. Model and `llama.cpp` downloads/updates are allowed *outside inference*. The node uses `--offline` during inference and passes only local paths. An OS firewall is still the strongest guarantee against unwanted connections from third-party executables.

[Instrukcja po polsku →](README_PL.md)

## Functionality

- Accepts **`IMAGE` from `Save Image.images`** on current ComfyUI versions; if your Save Image lacks this output, branch from the same upstream IMAGE.
- **Single image** selected by `image_index` from a batch, resized before VLM inference.
- Choose any compatible **vision-capable GGUF + matching `mmproj*.gguf`** from `ComfyUI/models/llama_cpp/`, `LLM/`, `text_encoders/`, or other registered paths (including abliterated checkpoints, provided their vision components actually work with your llama.cpp build).
- Compose **faithful**, **improve** (default) or **creative** prompts with optional source prompt / user goal.
- Outputs `prompt_en_us`, `scene_analysis_en`, `edit_plan_en` and original `IMAGE` (pass-through).
- Choose `execution_device=cpu|hybrid|gpu`, use `gpu_layers` for hybrid and `vision_gpu` independently, or limit context, batch and token budgets. OS commit-headroom guard for Windows/Linux.
- Launches isolated process **once per image** and terminates the process tree on timeout. No resident server or Ollama.

## Workflow ordering

```
Krea generation ── IMAGE ── Save Image ── images ───────────────┐
                                                               ▼
RAM/VRAM Purge ── completion output (if available) ── after_purge ── Prompt Builder
                                                               │
                                                               ├─ prompt_en_us (STRING)
                                                               ├─ scene_analysis_en
                                                               └─ edit_plan_en
```

The **`after_purge` input is an optional ordering dependency**, not a memory purge itself. If your purge node has no output, ComfyUI **cannot guarantee order between independent branches**. Use a purge node with a completion output or an explicit relay/gating step appropriate for your installed nodes. The `IMAGE` input still needs to be available after purging.

## Installation

1. Copy this entire repository into `ComfyUI/custom_nodes/ComfyUI-Krea2Turbo-PromptBuilder`.
2. Use a recent build of `llama.cpp` containing **`llama-cli` with multimodal `--image`, `--mmproj`, `--offline`, `--single-turn`, `--reasoning`, and `--output-file` support**. JSON schema mode additionally needs `-jf`.
3. Download a compatible vision GGUF + matching `mmproj*.gguf` from a trusted source into `ComfyUI/models/llama_cpp/` (or reuse an existing supported directory). **Weights and executables are not included.**
4. Restart ComfyUI. In the node, choose model, projector and executable path.
5. Connect `IMAGE`, optionally `after_purge` and `source_prompt`, and run.

**Dependencies:** uses `torch` and `Pillow` supplied by standard ComfyUI. No separate Python server/LLM stack is installed by this node.

**Important limitations:** tested with unit tests and mock CLI; **not end-to-end validated against a production ComfyUI + Gemma 4/Qwen3.5 model + specific GPU**. Some GGUF multimodal architectures/builds may need a newer `llama.cpp` version or additional flags. A 12B Q5 checkpoint is not guaranteed to fit entirely in 12 GB VRAM; select fewer GPU layers as needed. Using `--offline` is a best-effort CLI-level restriction, not a network sandbox.

## Test

```sh
python -m unittest discover -s tests -v
```

## License

MIT (see `LICENSE`).


### v0.1.1 model discovery fix

The original v0.1 scanned **only** `ComfyUI/models/krea_prompt_builder`, leaving the model widgets empty if GGUFs were in `models/llama_cpp`. This is fixed: the node scans `llama_cpp`, `LLM`, `text_encoders`, `krea_prompt_builder` and registered ComfyUI extra model paths. No duplication is needed. Model labels show the source folder. The projector defaults to automatic same-folder matching (only when unambiguous). Optional `model_path_override` and `mmproj_path_override` accept full absolute `.gguf` paths; alternatively set `KREA_PROMPT_BUILDER_MODEL_DIRS` before ComfyUI startup (OS path separator-delimited). **Restart ComfyUI after changing GGUFs or node code.**

`llama-cli.exe` is NOT bundled or installed by ComfyUI; get a compatible llama.cpp release from https://github.com/ggml-org/llama.cpp/releases and set `llama_cli_path` to its full path (or add it to `PATH`). The selected GGUFs are data, not the executable. The node never downloads or calls an inference server. Real Gemma 4 end-to-end support still requires validation.


### v0.1.2 — Gemma 4 output and device diagnostics

- Defaults to `output_mode=plain_sections` instead of forcing `-jf` JSON schema. Gemma 4 may output thought-channel text or fail to produce JSON on some llama.cpp versions. Plain sections are explicitly labelled `[ANALYSIS]`, `[KEEP]`, `[IMPROVE]`, `[PROMPT]`. The parser accepts both formats. `json_schema` remains opt-in.
- Defaults to `reasoning=off` (`--reasoning off --reasoning-budget 0`) to avoid spending all generated tokens on internal reasoning. Use `auto` for model-default thinking.
- `execution_device=cpu|hybrid|gpu`: `cpu` forces `--gpu-layers 0 --no-mmproj-offload`; `hybrid` uses the `gpu_layers` widget; `gpu` tries `--gpu-layers 999` (will fail with insufficient VRAM). `vision_gpu` is respected in hybrid/GPU modes.
- Parse both output file and stdout; distinguish nonzero exit, timeout, empty reply and wrong response format. By default only *metadata* (not generated text) appears in ComfyUI logs/exceptions.
- Turn on `save_diagnostics` only when troubleshooting to write **private content** to `ComfyUI/output/krea_prompt_builder_diagnostics/vlm_.../{result.txt,stdout.txt,stderr.txt,meta.json}`. Files never leave the local computer; disable afterwards and delete the logs when finished.
- The same ComfyUI node class key is retained, and new widgets are **appended** after old settings, minimizing disruption to saved workflows. Restart ComfyUI, refresh browser, and recreate the node if legacy widget state remains.

**Release status:** automated tests/mock subprocess only; real Gemma 4 b11719 + RTX 4070 inference has not been run by us.
