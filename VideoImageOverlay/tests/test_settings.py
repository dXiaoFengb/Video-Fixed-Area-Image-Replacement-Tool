from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_image_overlay.engine import MediaTools, Region, VideoProcessor, probe_video, subprocess_window_options
from video_image_overlay.gui_math import PreviewGeometry
from video_image_overlay.settings import AppSettings, SettingsStore


class SettingsTests(unittest.TestCase):
    def test_round_trip_restores_all_gui_fields_and_uses_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = SettingsStore(Path(raw))
            settings = AppSettings("C:/source", "D:/output", "C:/image.png", (0.1, 0.2, 0.3, 0.4), "normalized", 1234, 876, "zoomed", 1400, 900, "150%")
            with patch("video_image_overlay.settings.os.replace", wraps=os.replace) as replace:
                store.save(settings)
            self.assertEqual(replace.call_count, 1)
            self.assertEqual(store.load(), settings)
            self.assertEqual(list(Path(raw).glob(".settings-*.tmp")), [])
            self.assertEqual(json.loads(store.path.read_text(encoding="utf-8"))["window_width"], 1234)

    def test_missing_or_corrupt_file_uses_defaults_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = SettingsStore(Path(raw))
            self.assertEqual(store.load(), AppSettings())
            store.path.write_text("{broken", encoding="utf-8")
            messages: list[str] = []
            self.assertEqual(store.load(messages.append), AppSettings())
            self.assertTrue(messages)

    def test_development_and_frozen_base_directories(self) -> None:
        expected = Path(__file__).resolve().parents[1]
        with patch("video_image_overlay.settings.sys.frozen", False, create=True):
            self.assertEqual(SettingsStore.default_base_directory(), expected)
        with patch("video_image_overlay.settings.sys.frozen", True, create=True), patch("video_image_overlay.settings.sys.executable", r"D:\\portable\\VideoImageOverlay.exe"):
            self.assertEqual(SettingsStore.default_base_directory(), Path(r"D:\\portable"))

    def test_normalized_region_restores_for_different_preview_sizes(self) -> None:
        region = Region(0.25, 0.2, 0.5, 0.4)
        first = PreviewGeometry(1920, 1080, 960, 540)
        second = PreviewGeometry(1080, 1920, 540, 960)
        first_restored = first.to_region(*first.from_region(region))
        self.assertAlmostEqual(first_restored.x, region.x)
        self.assertAlmostEqual(first_restored.y, region.y)
        self.assertAlmostEqual(first_restored.width, region.width)
        self.assertAlmostEqual(first_restored.height, region.height)
        restored = second.to_region(*second.from_region(region))
        self.assertAlmostEqual(restored.x, region.x)
        self.assertAlmostEqual(restored.y, region.y)
        self.assertAlmostEqual(restored.width, region.width)
        self.assertAlmostEqual(restored.height, region.height)

    def test_media_commands_are_noninteractive_and_hidden_on_windows(self) -> None:
        options = subprocess_window_options()
        if os.name == "nt":
            self.assertEqual(options["creationflags"], __import__("subprocess").CREATE_NO_WINDOW)
            self.assertIn("startupinfo", options)
        else:
            self.assertEqual(options, {})
        tools = MediaTools(Path("ffmpeg.exe"), Path("ffprobe.exe"), "test")
        processor = VideoProcessor(tools)
        with patch("video_image_overlay.engine.probe_video", return_value={"width": 100, "height": 100}):
            command = processor._command(Path("image.png"), Path("video.mp4"), Path("out.mp4"), Region(0, 0, 1, 1), "copy")
        self.assertIn("-nostdin", command)


    def test_ffprobe_receives_devnull_and_hidden_window_options(self) -> None:
        tools = MediaTools(Path("ffmpeg.exe"), Path("ffprobe.exe"), "test")
        completed = type("Completed", (), {"stdout": "{\"streams\":[{\"width\":100,\"height\":100}]}"})()
        with patch("video_image_overlay.engine.subprocess.run", return_value=completed) as run:
            self.assertEqual(probe_video(tools, Path("video.mp4"))["width"], 100)
        self.assertEqual(run.call_args.kwargs["stdin"], __import__("subprocess").DEVNULL)
        if os.name == "nt":
            self.assertEqual(run.call_args.kwargs["creationflags"], __import__("subprocess").CREATE_NO_WINDOW)
if __name__ == "__main__":
    unittest.main()