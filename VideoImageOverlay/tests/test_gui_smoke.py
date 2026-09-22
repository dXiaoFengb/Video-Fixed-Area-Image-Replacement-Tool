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
                app.on_close()


    def test_ten_wheel_events_are_coalesced_and_accumulate(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.source_var.set("")
        app.original_frame = Image.new("RGB", (640, 360), "blue")
        try:
            root.update()
            app._settings_ready = False
            app._render_main()
            surface = app.main_surface
            calls = []
            original_render = app._render_main
            app._render_main = lambda: (calls.append(1), original_render())[1]
            event = type("Event", (), {"delta": 120, "x": 320, "y": 214})()
            for _ in range(10):
                app._on_wheel(surface, event)
            root.update_idletasks()
            root.update()
            self.assertAlmostEqual(surface.zoom, 1.06 ** 10, places=5)
            self.assertEqual(len(calls), 1)
        finally:
            if root.winfo_exists():
                app.on_close()

    def test_large_preview_wheel_keeps_mouse_anchor_and_syncs_slider(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.source_var.set("")
        app.original_frame = Image.new("RGB", (1200, 800), "blue")
        try:
            root.update()
            app.open_preview()
            root.update()
            app._set_preview_zoom(2.0, persist=False)
            app._render_large()
            surface = app.preview_surface
            self.assertIsNotNone(surface)
            canvas = surface.canvas
            canvas.xview_moveto(0.35)
            canvas.yview_moveto(0.25)
            root.update_idletasks()
            event = type("Event", (), {"delta": 120, "x": 180, "y": 130})()
            old_width = surface.geometry.canvas_width
            old_height = surface.geometry.canvas_height
            old_source = (canvas.canvasx(event.x) / old_width, canvas.canvasy(event.y) / old_height)
            app._on_wheel(surface, event)
            root.update_idletasks()
            root.update()
            new_source = (canvas.canvasx(event.x) / surface.geometry.canvas_width, canvas.canvasy(event.y) / surface.geometry.canvas_height)
            self.assertAlmostEqual(old_source[0], new_source[0], places=3)
            self.assertAlmostEqual(old_source[1], new_source[1], places=3)
            self.assertAlmostEqual(app.preview_scale_var.get(), 2.12, places=2)
            self.assertIn("缩放", app.preview_zoom_label_var.get())
            app._on_preview_scale("3.0")
            self.assertAlmostEqual(app._zoom_value(), 3.0, places=4)
            self.assertAlmostEqual(app.preview_scale_var.get(), 3.0, places=4)
        finally:
            if root.winfo_exists():
                app.on_close()

    def test_large_preview_fit_is_independent_and_reload_resets(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (640, 360), "blue")
        try:
            root.update()
            app.open_preview()
            root.update()
            app._set_preview_zoom(None, persist=False)
            self.assertIsNone(app._zoom_value())
            self.assertEqual(app.preview_zoom_label_var.get(), "适应窗口")
            app._on_wheel(app.preview_surface, type("Event", (), {"delta": 120, "x": 80, "y": 70})())
            root.update_idletasks()
            self.assertIsNotNone(app._zoom_value())
            self.assertGreaterEqual(app._zoom_value(), 0.5)
            app._set_preview_zoom(2.0, persist=False)
            app.source_var.set("")
            app.load_preview()
            self.assertIsNone(app._zoom_value())
        finally:
            if root.winfo_exists():
                app.on_close()
    def test_large_preview_centers_small_image_and_reuses_quality_timer(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.source_var.set("")
        app.original_frame = Image.new("RGB", (320, 180), "blue")
        try:
            root.update()
            app.open_preview()
            root.update()
            app._set_preview_zoom(0.5, persist=False)
            app._render_large()
            surface = app.preview_surface
            self.assertGreater(surface.content_origin_x, 0)
            self.assertGreater(surface.content_origin_y, 0)
            self.assertEqual(surface.canvas.xview()[0], 0.0)
            self.assertEqual(surface.canvas.yview()[0], 0.0)
            calls = []
            original_render = app._render_large
            app._render_large = lambda *args, **kwargs: (calls.append(kwargs.get("quality")), original_render(*args, **kwargs))[1]
            event = type("Event", (), {"delta": 120, "x": 160, "y": 100})()
            for _ in range(10):
                app._on_wheel(surface, event)
            root.update_idletasks()
            root.update()
            self.assertEqual(calls.count("interactive"), 1)
            root.after(140, root.quit)
            root.mainloop()
            self.assertEqual(calls.count("final"), 1)
        finally:
            if root.winfo_exists():
                app.on_close()

    def test_large_preview_new_wheel_cancels_pending_quality_render(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (1200, 800), "blue")
        try:
            root.update()
            app.open_preview()
            root.update()
            surface = app.preview_surface
            app._on_wheel(surface, type("Event", (), {"delta": 120, "x": 300, "y": 200})())
            root.update_idletasks()
            root.update()
            pending = app._large_quality_after
            self.assertIsNotNone(pending)
            cancelled = []
            original_cancel = root.after_cancel
            root.after_cancel = lambda identifier: (cancelled.append(identifier), original_cancel(identifier))[1]
            app._on_wheel(surface, type("Event", (), {"delta": 120, "x": 320, "y": 220})())
            self.assertIn(pending, cancelled)
        finally:
            if root.winfo_exists():
                app.on_close()

    def test_magnifier_is_four_x_mouse_centered_and_layered(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (640, 360), "blue")
        try:
            root.update()
            app._render_main()
            surface = app.main_surface
            press = type("Event", (), {"x": 250, "y": 180})()
            drag = type("Event", (), {"x": 330, "y": 250})()
            app._on_press(surface, press)
            app._on_drag(surface, drag)
            self.assertIsNotNone(surface.magnifier_source_box)
            left, top, right, bottom = surface.magnifier_source_box
            scale = surface.geometry.scale
            self.assertAlmostEqual(right - left, min(app.original_frame.width, 220 / (4.0 * scale)), places=2)
            source_x = (drag.x - surface.geometry.offset_x) / scale
            source_y = (drag.y - surface.geometry.offset_y) / scale
            self.assertAlmostEqual((left + right) / 2, max(0, min(app.original_frame.width, source_x)), delta=2)
            self.assertAlmostEqual((top + bottom) / 2, max(0, min(app.original_frame.height, source_y)), delta=2)
            self.assertIsNotNone(surface.magnifier_item)
            self.assertIsNotNone(surface.magnifier_border_item)
        finally:
            if root.winfo_exists():
                app.on_close()

    def test_right_pan_wheel_and_magnifier(self) -> None:
        root = tk.Tk()
        root.withdraw()
        app = VideoImageOverlayApp(root)
        app.original_frame = Image.new("RGB", (640, 360), "blue")
        try:
            root.update()
            app._render_main()
            app._settings_ready = False
            if app._save_after:
                root.after_cancel(app._save_after)
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
