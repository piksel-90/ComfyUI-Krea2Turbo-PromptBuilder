"""Discover GGUFs already installed in ComfyUI. No network traffic and no model copies."""
from __future__ import annotations

import os
from pathlib import Path
import re

UNSET = "[select local GGUF]"
AUTO_MMPROJ = "[AUTO: projector next to model]"
CATEGORIES = ("llama_cpp", "LLM", "text_encoders", "krea_prompt_builder")
SEPARATOR = " :: "


def discover(root: Path) -> tuple[list[str], list[str]]:
    """Legacy single-directory catalog (kept for existing workflows/tests)."""
    root = Path(root)
    if not root.is_dir():
        return [UNSET], [UNSET]
    models, projectors = [], []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".gguf":
            continue
        relative = path.relative_to(root).as_posix()
        if is_projector(path):
            projectors.append(relative)
        else:
            models.append(relative)
    return [UNSET, *sorted(models, key=str.casefold)], [UNSET, *sorted(projectors, key=str.casefold)]


def is_projector(path: Path) -> bool:
    name = path.name.casefold()
    return "mmproj" in name or "projector" in name


def resolve_local(root: Path, selection: str) -> Path:
    if not selection or selection == UNSET:
        raise ValueError("Select an existing local GGUF in the node (the model list was empty or no model was chosen).")
    root = Path(root).resolve()
    candidate = (root / selection).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.suffix.lower() != ".gguf":
        raise ValueError("GGUF must be an existing file in its selected local models directory")
    return candidate


def _source_roots(models_dir: Path, folder_paths_module=None) -> list[tuple[str, Path]]:
    """Built-in ComfyUI dirs plus paths registered by other nodes/extra_model_paths.yaml."""
    candidates: list[tuple[str, Path]] = []
    for category in CATEGORIES:
        candidates.append((category, models_dir / category))
        if folder_paths_module is not None and hasattr(folder_paths_module, "get_folder_paths"):
            try:
                for path in folder_paths_module.get_folder_paths(category):
                    candidates.append((category, Path(path)))
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
    # Optional advanced configuration; separate paths with OS path separator.
    for index, path in enumerate(filter(None, os.environ.get("KREA_PROMPT_BUILDER_MODEL_DIRS", "").split(os.pathsep)), 1):
        candidates.append((f"custom{index}", Path(path)))
    seen: set[str] = set()
    counts: dict[str, int] = {}
    result: list[tuple[str, Path]] = []
    for label, root in candidates:
        resolved = root.expanduser().resolve()
        normalized = os.path.normcase(str(resolved)).casefold()
        if normalized in seen or not resolved.is_dir():
            continue
        seen.add(normalized)
        counts[label] = counts.get(label, 0) + 1
        display = label if counts[label] == 1 else f"{label} [{counts[label]}]"
        result.append((display, resolved))
    return result


def catalog(models_dir: Path, folder_paths_module=None) -> tuple[list[str], list[str], dict[str, Path]]:
    """Return dropdown options and immutable mappings to already-existing GGUF paths."""
    models, projectors, paths = [], [], {}
    seen_files: set[str] = set()
    for label, root in _source_roots(Path(models_dir), folder_paths_module):
        try:
            files = root.rglob("*")
            for path in files:
                try:
                    if not path.is_file() or path.suffix.lower() != ".gguf":
                        continue
                    actual = path.resolve()
                    unique = os.path.normcase(str(actual)).casefold()
                    if unique in seen_files:
                        continue
                    seen_files.add(unique)
                    key = label + SEPARATOR + path.relative_to(root).as_posix()
                    paths[key] = actual
                    (projectors if is_projector(path) else models).append(key)
                except (OSError, ValueError):
                    continue
        except OSError:
            continue
    return ([UNSET, *sorted(models, key=str.casefold)],
            [AUTO_MMPROJ, *sorted(projectors, key=str.casefold)], paths)


def select_gguf(selection: str, paths: dict[str, Path], override: str = "") -> Path:
    """Choose catalog item or explicit user-supplied absolute path, without copying."""
    if override.strip():
        candidate = Path(override.strip().strip('"')).expanduser()
        if not candidate.is_absolute():
            raise ValueError("Override GGUF path must be absolute (e.g. D:\\Models\\model.gguf)")
        path = candidate.resolve()
    elif selection in paths:
        path = paths[selection]
    else:
        raise ValueError(
            "No model selected. Put GGUF in ComfyUI/models/llama_cpp (or LLM/text_encoders), "
            "restart ComfyUI, select a filename, or paste its full path in model_path_override."
        )
    if path.suffix.lower() != ".gguf" or not path.is_file():
        raise FileNotFoundError(f"Selected local GGUF file does not exist: {path}")
    return path


def match_projector(model: Path, paths: dict[str, Path]) -> Path:
    """Auto-match only unambiguous projectors alongside the selected model."""
    siblings = sorted({p for p in paths.values() if is_projector(p) and p.parent == model.parent})
    # Also handle absolute model override in an unregistered directory.
    if model.parent.is_dir():
        siblings = sorted(set(siblings) | {
            p.resolve() for p in model.parent.glob("*.gguf") if p.is_file() and is_projector(p)
        })
    if len(siblings) == 1:
        return siblings[0]
    if len(siblings) > 1:
        matched = []
        for projector in siblings:
            stem = re.split(r"[._-](?:mmproj|projector)", projector.stem, maxsplit=1, flags=re.I)[0]
            if len(stem) >= 5 and model.stem.casefold().startswith(stem.casefold()):
                matched.append(projector)
        if len(matched) == 1:
            return matched[0]
    raise ValueError(
        "Could not uniquely find matching mmproj alongside model. "
        "Choose mmproj_gguf explicitly or set mmproj_path_override (absolute path)."
    )


def resolve_projector(selection: str, model: Path, paths: dict[str, Path], override: str = "") -> Path:
    if override.strip():
        return select_gguf(UNSET, paths, override)
    if selection == AUTO_MMPROJ:
        return match_projector(model, paths)
    projector = select_gguf(selection, paths)
    if not is_projector(projector):
        raise ValueError("The selected GGUF is not named like a multimodal projector (mmproj).")
    return projector
