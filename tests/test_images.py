import tempfile
import unittest
from pathlib import Path

try:
    import torch
    from PIL import Image
except ImportError:
    torch = None

from krea_prompt_builder.images import save_one_image


@unittest.skipIf(torch is None, "ComfyUI supplies torch / Pillow")
class ImagesTests(unittest.TestCase):
    def test_batch_index_and_downscale(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = torch.zeros((2, 400, 800, 3), dtype=torch.float32)
            img[1, :, :, 0] = 1.0
            output = Path(tmp) / "image.png"
            size = save_one_image(img, 1, 384, output)
            self.assertEqual(size, (384, 192))
            with Image.open(output) as saved:
                self.assertEqual(saved.getpixel((0, 0)), (255, 0, 0))

    def test_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_one_image(torch.zeros((1, 4, 4, 3)), 1, 384, Path(tmp) / "image.png")
