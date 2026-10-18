"""ComfyUI node interface for a single-image, private Krea prompt builder."""
from __future__ import annotations

from pathlib import Path
import logging
import tempfile

import folder_paths

from .krea_prompt_builder.images import save_one_image
from .krea_prompt_builder.contract import evaluate_scene_contract
from .krea_prompt_builder.memory import enforce_headroom
from .krea_prompt_builder.models import catalog, select_gguf, resolve_projector
from .krea_prompt_builder.prompting import build_instruction, MODES, REPORT_LANGUAGES
from .krea_prompt_builder.runner import find_executable, run_once

LOG = logging.getLogger("ComfyUI-KreaPromptBuilder")
MODEL_ROOT = Path(folder_paths.models_dir)


class AnyType(str):
    """Optional ordering dependency for custom Purge nodes with any output type."""
    def __ne__(self, other):
        return False


ANY = AnyType("*")


class KreaPromptBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        models, mmprojs, _ = catalog(MODEL_ROOT, folder_paths)
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Use Save Image.images, or branch the upstream IMAGE."}),
                "model_gguf": (models,),
                "mmproj_gguf": (mmprojs,),
                "llama_cli_path": ("STRING", {"default": "llama-cli", "tooltip": "Absolute path or executable in PATH; no Ollama."}),
                "mode": (list(MODES), {"default": "improve"}),
                "user_goal": ("STRING", {"default": "", "multiline": True}),
                "source_prompt": ("STRING", {"default": "", "multiline": True,
                    "tooltip": "Original intended scene specification. Preserve its requirements unless user_goal or scene_contract explicitly changes them."}),
                "image_index": ("INT", {"default": 0, "min": 0, "max": 1023}),
                "max_image_side": ("INT", {"default": 1280, "min": 384, "max": 2048, "step": 64}),
                "gpu_layers": ("INT", {"default": 24, "min": 0, "max": 200}),
                "vision_gpu": ("BOOLEAN", {"default": True}),
                "context_size": ("INT", {"default": 4096, "min": 2048, "max": 16384, "step": 1024}),
                "max_tokens": ("INT", {"default": 1600, "min": 256, "max": 4096}),
                "batch_size": ("INT", {"default": 512, "min": 128, "max": 2048, "step": 128}),
                "timeout_seconds": ("INT", {"default": 300, "min": 30, "max": 1800}),
                "commit_headroom_gib": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 48.0, "step": 1.0}),
                "execution_device": (["hybrid", "cpu", "gpu"], {"default": "hybrid", "tooltip": "CPU uses no language/vision GPU layers; hybrid uses gpu_layers; GPU attempts full offload (may OOM)."}),
                "output_mode": (["plain_sections", "json_schema"], {"default": "plain_sections", "tooltip": "Gemma 4: try plain_sections first. json_schema uses llama.cpp -jf."}),
                "reasoning": (["off", "auto"], {"default": "off", "tooltip": "Disable thinking for concise direct output; auto allows model defaults."}),
                "save_diagnostics": ("BOOLEAN", {"default": False, "tooltip": "Opt-in: save PRIVATE raw llama.cpp output/stdout/stderr to ComfyUI/output/krea_prompt_builder_diagnostics. No upload."}),
            },
            "optional": {
                "after_purge": (ANY, {"tooltip": "Connect output of RAM/VRAM Purge to enforce execution ordering. If it has no output, sequencing requires a relay node."}),
                "model_path_override": ("STRING", {"default": "", "tooltip": "Optional absolute GGUF file path. Leave empty to use model dropdown; no copies needed."}),
                "mmproj_path_override": ("STRING", {"default": "", "tooltip": "Optional absolute mmproj GGUF path. Leave empty for auto-detection next to model."}),
                "scene_contract": ("STRING", {"default": "", "multiline": True,
                                  "tooltip": "Highest-priority explicit scene constraints. Conflicts with the image must be reported, not hidden."}),
                "required_exact_phrases": ("STRING", {"default": "", "multiline": True,
                                           "tooltip": "One exact case-insensitive phrase per line that MUST occur in generated prompt."}),
                "forbidden_exact_phrases": ("STRING", {"default": "", "multiline": True,
                                            "tooltip": "One exact case-insensitive phrase per line that must NOT occur in prompt."}),
                "report_language": (list(REPORT_LANGUAGES), {"default": "pl_en", "tooltip": "PL and EN from ONE local VLM inference. en_only retains the previous format."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE", "STRING", "BOOLEAN", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt_en_us", "scene_analysis_en", "edit_plan_en", "image", "contract_report_pl", "contract_ok", "gpu_offload_info", "scene_analysis_pl", "edit_plan_pl")
    FUNCTION = "build"
    CATEGORY = "Krea/Prompt Builder"
    DESCRIPTION = "One IMAGE -> a Krea 2 Turbo prompt via local VLM GGUF in disposable llama.cpp process."

    def build(
        self, image, model_gguf, mmproj_gguf, llama_cli_path, mode, user_goal,
        source_prompt, image_index, max_image_side, gpu_layers, vision_gpu,
        context_size, max_tokens, batch_size, timeout_seconds,
        commit_headroom_gib, after_purge=None, model_path_override="", mmproj_path_override="",
        execution_device="hybrid", output_mode="plain_sections", reasoning="off", save_diagnostics=False,
        scene_contract="", required_exact_phrases="", forbidden_exact_phrases="",
        report_language="pl_en",
    ):
        _, _, known_paths = catalog(MODEL_ROOT, folder_paths)
        model = select_gguf(model_gguf, known_paths, model_path_override)
        mmproj = resolve_projector(mmproj_gguf, model, known_paths, mmproj_path_override)
        executable = find_executable(llama_cli_path)
        instruction = build_instruction(mode, user_goal, source_prompt, output_mode, scene_contract, report_language)
        if save_diagnostics:
            output_dir = (Path(folder_paths.get_output_directory()) if hasattr(folder_paths, "get_output_directory")
                          else MODEL_ROOT.parent / "output")
            diagnostics_dir = output_dir / "krea_prompt_builder_diagnostics"
        else:
            diagnostics_dir = None
        if commit_headroom_gib:
            LOG.info(enforce_headroom(float(commit_headroom_gib)))
        with tempfile.TemporaryDirectory(prefix="krea_input_") as folder:
            image_path = Path(folder) / "frame.png"
            width, height = save_one_image(image, image_index, max_image_side, image_path)
            LOG.info("Analyzing one image: %s x %s; batch index %s", width, height, image_index)
            result = run_once(
                executable, model, mmproj, image_path, instruction,
                gpu_layers, context_size, max_tokens, batch_size,
                vision_gpu, timeout_seconds,
                execution_device=execution_device, output_mode=output_mode,
                reasoning=reasoning, diagnostics_dir=diagnostics_dir, report_language=report_language,
            )
        if report_language == "pl_en" and not (result.get("analysis_pl", "").strip() and result.get("edit_plan_pl", "").strip()):
            raise ValueError("Bilingual VLM response is missing Polish report fields; check private diagnostics")
        plan = f"KEEP:\n{result['keep']}\n\nIMPROVE:\n{result['improve']}"
        status = evaluate_scene_contract(
            result["prompt_en_us"], source_prompt=source_prompt, user_goal=user_goal,
            scene_contract=scene_contract, analysis_pl=result.get("analysis_pl", ""),
            analysis_en=result.get("analysis_en", ""),
            model_report_pl=result.get("contract_report_pl", ""),
            required_exact_phrases=required_exact_phrases,
            forbidden_exact_phrases=forbidden_exact_phrases,
        )
        prompt = result["prompt_en_us"] if status.ok else ""  # fail closed: do not forward a known-violating prompt
        if not status.ok:
            LOG.warning("Prompt blocked by explicit text contract; consult contract_report_pl")
        return (prompt, result["analysis_en"], plan, image, status.report_pl, status.ok,
                result.get("_gpu_offload_info", "GPU offload not reported"),
                result.get("analysis_pl", ""), result.get("edit_plan_pl", ""))


NODE_CLASS_MAPPINGS = {"Krea2TurboPromptBuilderV01": KreaPromptBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {"Krea2TurboPromptBuilderV01": "Krea 2 Turbo | Prompt Builder v0.1.6"}
