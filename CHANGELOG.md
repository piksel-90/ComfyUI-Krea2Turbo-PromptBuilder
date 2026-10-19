# V0.1.8 (2026-10-19)

**New node type:** `Krea2TurboPromptBuilderV018`, shown as `Krea 2 Turbo | Prompt Builder v0.1.8`.

- Three multiline inputs **`original_prompt`**, **`target`**, **`extra_instruction`** remain visible in every Basic / Advanced / Diagnostics / All panel and in all faithful / improve / creative modes.
- `original_prompt` replaces `source_prompt` as the intended source specification. `target` replaces `user_goal` as the desired outcome. `extra_instruction` is a separate direct command to the local VLM (modeled on Test1's EXTRA field), subordinate to `scene_contract`.
- No `report_language` widget: one local llama.cpp inference always produces EN and PL. No `gpu_offload_info` output: the offload detail remains in local logs / optional diagnostics.
- New output order: `prompt_en_us`, `scene_analysis_en`, `edit_plan_en`, `image`, `contract_report_pl`, `contract_ok`, `scene_analysis_pl`, `edit_plan_pl` (8 outputs).
- **Compatibility:** ComfyUI saves widget values by position and output connections by index. Therefore the original `Krea2TurboPromptBuilderV01` is retained as a separate legacy node to load existing workflows without corrupting links. Add V0.1.8 and reconnect deliberately; do not assume the two schemas are interchangeable.
- The local image/text data are not sent to remote inference services. Model weights and dependencies are still installed separately.

---

## 0.1.7 — 2026-10-19

- Fix Gemma/llama.cpp bilingual responses ending in a standalone `END` instead of `[END]`, while still accepting bracketed endings and both `[HEADER]` / `HEADER:` fields.
- Preserve strict end-of-response checking: missing terminators, trailing generated drafts, echo-only output, unfinished reasoning or incomplete fields are rejected rather than used as a Krea prompt.
- Recognize model contract verdicts with a harmless trailing full stop, e.g. `WYNIK_PROMPTU: ZGODNY.` or `NIEZGODNY.`; negatives still block when applicable.
- Regression tests cover anonymized variants of the failing transcript; the user's original `result.txt` was tested locally and is NOT bundled or committed.
- No changes to model paths, GPU settings, execution mode, nine output ports or widget order; no additional inference passes.
- Automated tests and parser test against the supplied transcript only. RTX 4070 end-to-end inference remains user-side validation.

## 0.1.6 — 2026-10-19

- Treat `source_prompt` as the binding intended scene specification (except explicit higher-priority changes), not mere context; separate *observed image* from *desired output*.
- In the same bilingual local VLM call, request a seventh `CONTRACT_REPORT_PL` field to compare original source, observed image and final EN prompt, and request an explicit `WYNIK_PROMPTU` self-assessment.
- Replace static `contract_report_pl` output with an input-aware Polish report: original/goal/contract, available VLM assessment and deterministic literal checks. Mark missing VLM reports and uncertainty clearly.
- Conservatively block an explicit VLM `WYNIK_PROMPTU: NIEZGODNY` as well as existing literal violations; distinguish this fallible self-verdict from independent image validation. A source/image discrepancy is reported, not automatically treated as a final-prompt failure.
- Keep compatibility with old six-field model replies, all 9 existing output positions and widget order, compact UI, local process/offline behavior. Add synthetic regression cases for source precedence, contradiction blocking, fallbacks and seven-field parsing.
- Unit/mock tests only; no live 12GB RTX 4070 model validation by this release process.

## 0.1.5 — 2026-10-19

- Fix real Gemma 4 bilingual outputs using `ANALYSIS_EN: ...` style rather than bracketed `[ANALYSIS_EN]` headings; both forms and mixed/on-line content are now supported.
- Require all six non-empty fields plus standalone final `[END]`, with intact echo/thinking/truncation safeguards.
- Add synthetic regression cases and exercise the actual private `result.txt` locally without publishing its contents.
- Keep all nine output ports, widget order, one-process local `llama.cpp`, and compact frontend unchanged.
- Unit tests/mock inference only; end-to-end accuracy on the user's RTX 4070 still requires validation.

## 0.1.4 — 2026-10-18

- Generate **English prompt/analysis and Polish scene analysis/edit plan in a single local VLM response**, default `report_language=pl_en` and optional legacy `en_only`.
- Append `scene_analysis_pl` and `edit_plan_pl` after the original seven outputs (no port reordering). `contract_report_pl` remains a separate literal-contract diagnostic.
- Extend the schema parser to require all six fields for bilingual JSON or six labelled bilingual sections ending in `[END]`; fail closed on truncated or thinking-only responses.
- Add **optional** compact ComfyUI frontend `web/compact.js`: Basic, Advanced, Diagnostics, All. Hide widgets visually while preserving values; do not change how inference works if JS is absent.
- Raise default generated-token budget to 1600 for new workflows; existing saved widget values are retained.
- Add regression tests for mixed PL/EN responses, echo and thinking removal, truncation, single-process inference and frontend visibility/state.
- Automated tests/mock backend only; model vision reliability remains unverified. No Ollama, cloud inference or private-data upload.

# Changelog

## 0.1.0 — 2026-10-18

- Initial ComfyUI custom node: `IMAGE` -> `prompt_en_us`, `scene_analysis_en`, `edit_plan_en` + passthrough.
- Per-execution local `llama-cli` process, no Ollama / resident server.
- Select local multimodal GGUF and matching `mmproj` from dropdown lists.
- Three prompt modes, optional source prompt and user goal.
- Configurable GPU layer budget, context, image size, system committed-memory guard, timeout with process-tree termination.
- Unit tests with simulated VLM output. No end-to-end GPU validation yet.

## 0.1.1 — 2026-10-18

- Fix blank GGUF dropdown: scan `models/llama_cpp`, `models/LLM`, `models/text_encoders`, legacy `models/krea_prompt_builder` and ComfyUI registered model paths.
- Add external folder support with `KREA_PROMPT_BUILDER_MODEL_DIRS`; detect duplicate paths without copying models.
- Add automatic `mmproj` selection from model's directory (only when unambiguous), and optional absolute path overrides for GGUF and projector.
- Improve missing `llama-cli.exe` diagnostics. No Ollama service or bundled executable.
- Stop copying raw llama.cpp stderr into general ComfyUI logs, which could expose user input.
- Add regression tests for cross-folder discovery, auto-mmproj, extra paths, overrides and ambiguity.


## 0.1.2 — 2026-10-18

- Choose CPU, hybrid CPU+GPU, or GPU for the language model, with independent projector offload when applicable.
- Default to plain labelled sections and disabled reasoning, avoiding mandatory JSON schema grammar on Gemma 4.
- Robustly parse JSON, list-valued keep/improve and complete labelled sections; check both output file and stdout.
- More precise errors for empty/incomplete responses, nonzero process exits, timeouts.
- Optional local-only private diagnostics (stdout, stderr, model output), disabled by default.
- Add regression tests for new parsing, device flags and diagnostic privacy.

## 0.1.3 — 2026-10-18

- Fix `llama-cli` echoed-User prompt and Gemma thought-channel leakage. Fail closed on unfinished/only-thinking responses and reject format placeholders; choose last valid assistant-only final result.
- Refine image-grounded instructions to preserve users' original scene instead of adding invented people, locations and decorations.
- Add opt-in `scene_contract`, required/forbidden literal phrases, and clear Polish contract report with blocking on violations. No semantic/visual verification is claimed.
- Preserve the first four node output positions and append `contract_report_pl`, `contract_ok`, `gpu_offload_info`.
- Parse actual GPU layer offload information from llama.cpp stderr when available; never infer offload count from the GPU utilization graph.
- Extend automated regressions with synthetic prompt-echo, complete/incomplete thinking and scene-contract failures. Raw personal diagnostic content is not committed.
