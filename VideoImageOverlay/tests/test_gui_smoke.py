from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class GuiSmokeTests(unittest.TestCase):
    def test_gui_constructs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw:
            marker = Path(raw) / "gui-smoke.log"
            result = subprocess.run([sys.executable, "main.py", "--smoke-gui", "--smoke-log", str(marker)], cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "GUI destroyed\n")


if __name__ == "__main__":
    unittest.main()
