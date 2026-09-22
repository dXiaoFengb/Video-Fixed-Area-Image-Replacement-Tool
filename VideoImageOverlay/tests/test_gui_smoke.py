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


    def test_right_pan_wheel_and_magnifier(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (640, 360), "blue")
        try:
            root.update()
            app._render_main()
            app._settings_ready = False
            original = app.region
            surface = app.main_surface
            app._on_pan_press(surface, type("Event", (), {"x": 200, "y": 160})())
            app._on_pan_drag(surface, type("Event", (), {"x": 240, "y": 190})())
            app._on_pan_release(surface, type("Event", (), {"x": 240, "y": 190})())
            self.assertEqual(app.region, original)
            app._on_wheel(surface, type("Event", (), {"delta": 120})())
            self.assertGreater(surface.zoom, 1.0)
            app._on_press(surface, type("Event", (), {"x": 250, "y": 180})())
            app._on_drag(surface, type("Event", (), {"x": 330, "y": 250})())
            self.assertIsNotNone(surface.magnifier_photo)
            app._on_release(surface, type("Event", (), {"x": 330, "y": 250})())
            self.assertIsNone(surface.drag_mode)
        finally:
            if app._save_after:
                try: root.after_cancel(app._save_after)
                except tk.TclError: pass
            if root.winfo_exists():
                app.on_close()

if __name__ == "__main__":
    unittest.main()
