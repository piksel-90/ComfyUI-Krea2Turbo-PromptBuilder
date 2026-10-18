import unittest
from krea_prompt_builder.memory import enforce_headroom, GIB


class MemoryTests(unittest.TestCase):
    def test_memory_guards_low_commit(self):
        with self.assertRaises(MemoryError):
            enforce_headroom(6, getter=lambda: 4 * GIB)

    def test_headroom_enough(self):
        self.assertIn("8.0", enforce_headroom(6, getter=lambda: 8 * GIB))

    def test_memory_metric_not_supported(self):
        self.assertIn("unavailable", enforce_headroom(6, getter=lambda: None))
