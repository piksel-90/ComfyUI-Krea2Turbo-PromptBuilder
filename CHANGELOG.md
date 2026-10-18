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
