"""Serialize exactly one ComfyUI IMAGE batch item to a transient PNG."""
from __future__ import annotations

from pathlib import Path


def save_one_image(images, index: int, maximum_side: int, destination: Path) -> tuple[int, int]:
    from PIL import Image
    import numpy as np
    import torch

    if len(images.shape) != 4:
        raise ValueError("Expected ComfyUI IMAGE in [B, H, W, C] format")
    count = int(images.shape[0])
    if not 0 <= index < count:
        raise ValueError(f"Image index {index} is outside batch 0..{count - 1}")
    frame = images[index].detach().to(device="cpu", dtype=torch.float32)
    arr = (frame.clamp(0, 1) * 255).round().to(dtype=torch.uint8).numpy()
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    if arr.shape[-1] not in (3, 4):
        raise ValueError("IMAGE must have one, three, or four channels")
    picture = Image.fromarray(arr)
    picture.thumbnail((maximum_side, maximum_side), Image.Resampling.LANCZOS)
    picture.save(destination, format="PNG", optimize=False)
    return picture.size
