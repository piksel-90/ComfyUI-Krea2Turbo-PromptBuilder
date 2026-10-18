# ComfyUI — Krea 2 Turbo Prompt Builder

**v0.1.3 (prototype / alpha)** · One generated image → one improved **en-US** prompt, with an evidence-based scene analysis and keep/change plan.

**Privacy:** No Ollama, remote AI API, or prompt/image upload. VLM inference is run through a **new local `llama-cli` subprocess for every execution**, using pre-downloaded GGUF and `mmproj` files. Model and `llama.cpp` downloads/updates are allowed *outside inference*. The node uses `--offline` during inference and passes only local paths. An OS firewall is still the strongest guarantee against unwanted connections from third-party executables.

[Instrukcja po polsku →](README_PL.md)

## v0.1.5 — One local model, bilingual outputs, compact UI

**Default `report_language=pl_en`:** one `llama-cli` process returns the original four English response fields PLUS `analysis_pl` and `edit_plan_pl`, in a single generation. `plain_sections` requires a final `[END]` marker to prevent forwarding truncated reports. `en_only` falls back to legacy response format. No second model or translation API is invoked.

Outputs 0–6 are unchanged, with indices 7 `scene_analysis_pl` and 8 `edit_plan_pl` appended. `contract_report_pl` is an exact-phrase diagnostic, **not** the Polish scene report. The interface now optionally offers `⚙ Settings panel` (`Basic`, `Advanced`, `Diagnostics`, `All`) through `web/compact.js`. Widget values are preserved when hidden; on unsupported frontends the native full node still functions. Choose Advanced/All for `llama_cli_path`.

On Windows ComfyUI portable keep the existing GGUF, matching mmproj and `llama-cli.exe` where they are. New installs may need to set `llama_cli_path` via Advanced. The new default `max_tokens` is 1600 for more room for both languages; saved workflows keep their existing values. An inadequate output budget causes a deliberate error rather than silently returning an incomplete PL report. Tested with mocks and Python/JS unit tests, **not** validated against actual Gemma 4/Qwen on your RTX 4070.

---

## Functionality

- Accepts **`IMAGE` from `Save Image.images`** on current ComfyUI versions; if your Save Image lacks this output, branch from the same upstream IMAGE.
- **Single image** selected by `image_index` from a batch, resized before VLM inference.
- Choose any compatible **vision-capable GGUF + matching `mmproj*.gguf`** from `ComfyUI/models/llama_cpp/`, `LLM/`, `text_encoders/`, or other registered paths (including abliterated checkpoints, provided their vision components actually work with your llama.cpp build).
- Compose **faithful**, **improve** (default) or **creative** prompts with optional source prompt / user goal.
- Outputs `prompt_en_us`, `scene_analysis_en`, `edit_plan_en` and original `IMAGE` (pass-through). **v0.1.3 appends** `contract_report_pl` (STRING), `contract_ok` (BOOLEAN), and `gpu_offload_info` (STRING), keeping the first four output indices unchanged.
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


### v0.1.3 — answer extraction and one-image scene constraints

**Root cause seen in actual Gemma 4 diagnostic output:** `llama-cli` may write the entire `User:` instruction into `result.txt`, followed by `Assistant:` and a `[Start thinking] ... [End thinking]` draft. v0.1.2 could accidentally parse the instructions or the draft as a final answer. The new parser:

- selects the text after the **last** standalone `Assistant:` marker if present, dropping echoed `User:` content;
- strips completed `[Start thinking] ... [End thinking]`, `<think> ... </think>`, or recognized thought channels; rejects unfinished thought or thought-only output;
- selects the **last valid full** `[ANALYSIS]` / `[KEEP]` / `[IMPROVE]` / `[PROMPT]` quartet (or JSON object);
- refuses boilerplate section placeholders and template text instead of outputting them as the generated prompt;
- deliberately **does not attempt to manufacture a completed prompt from a truncated thought**. Use `reasoning=off` and an adequate token budget.

**Source-inspired scene contract:** The [Test1 iteration evaluator](https://github.com/piksel-90/Test1/tree/feature/krea2-iteration-evaluator) judges images against `ORIGINAL PROMPT` + `TARGET`, then proposes `KEEP` / `CHANGE`. We reuse that structure for a single image, but keep user constraints separate from model-suggested improvements, without Ollama or a second-image comparison.

New optional inputs (blank by default):

| Input | Meaning |
|---|---|
| `scene_contract` | Free-text user requirements to be honored during analysis; **not automatically verified** |
| `required_exact_phrases` | One case-insensitive **literal phrase** per line required inside `prompt_en_us` |
| `forbidden_exact_phrases` | One case-insensitive **literal phrase** per line forbidden inside `prompt_en_us` |

For example: `scene_contract=Keep the original room and the child holding a laptop`, required lines `living room` and `laptop`, forbidden lines `rice field` and `meadow`. If a literal test fails, the node outputs an **empty prompt**, `contract_ok=false`, and explains why in `contract_report_pl`. The downstream workflow MUST use `contract_ok` to prevent rendering from an empty prompt. The text check cannot detect synonyms, visual errors, changed faces, ethnicity, or spatial errors; even `contract_ok=true` is **NOT evidence of visual fidelity**. To prevent drift between images, maintain stable source instructions and use a separate visual validation stage if required.

**Offload diagnostics:** the node prints **requested** language GPU layers and an **actual layer count only when reported** by `llama.cpp` stderr. The final text output `gpu_offload_info` is displayable via Show Text. `gpu_layers=16` means partial offload and can be CPU-heavy; CUDA activity cannot be inferred from Windows' "3D" graph alone. `reasoning=off` is default, but old workflow nodes may retain an explicitly saved `auto` value. Clear `source_prompt` when switching to a different test image (e.g. an earlier frog prompt is not appropriate context for a photograph).

**Privacy:** metadata-only logging is default; `save_diagnostics=true` explicitly saves private raw model output to the local output folder. No cloud inference is added. As before, no end-to-end live inference on your RTX 4070 has been performed by this release process.

## V0.1.5 – Gemma bilingual header compatibility

The bilingual `plain_sections` parser now accepts both the instructed
`[ANALYSIS_EN]` / `[PROMPT_EN_US]` headings and observed Gemma-style
`ANALYSIS_EN:` / `PROMPT_EN_US:` headings. Either style can contain its value
on the same line or the next line. The final standalone `[END]` marker and
all six populated fields are still mandatory. Prompt echo, thinking, malformed
ordering and incomplete output remain blocked.

This fixes a real user-provided `llama.cpp` sample that produced complete
English and Polish content but was rejected because it used colon headings.
No private sample text, image, model files, or logs are distributed.
