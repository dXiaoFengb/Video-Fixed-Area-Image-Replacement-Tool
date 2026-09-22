from __future__ import annotations

import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from PIL import Image

from video_image_overlay.app import VideoImageOverlayApp


class GuiSmokeTests(unittest.TestCase):
    def test_gui_constructs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw:
            marker = Path(raw) / "gui-smoke.log"
            result = subprocess.run([sys.executable, "main.py", "--smoke-gui", "--smoke-log", str(marker)], cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "GUI destroyed\n")

    def test_preview_window_zoom_fullscreen_and_close(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (320, 240), "blue")
        try:
            root.update()
            app.open_preview()
            root.update()
            self.assertIsNotNone(app.preview_window)
            self.assertIsNotNone(app.preview_surface)
            app.preview_zoom_var.set("150%")
            app._render_large()
            app.toggle_fullscreen()
            root.update()
            self.assertTrue(app.preview_fullscreen)
            app.exit_fullscreen()
            root.update()
            self.assertFalse(app.preview_fullscreen)
            app.close_preview()
            self.assertIsNone(app.preview_window)
        finally:
            if root.winfo_exists():
                root.destroy()


if __name__ == "__main__":
    unittest.main()
