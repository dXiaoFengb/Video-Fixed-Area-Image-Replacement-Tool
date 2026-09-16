from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_image_overlay.engine import MediaTools, Region, ToolResolver, VideoProcessor, next_output_path, scan_videos
from video_image_overlay.gui_math import PreviewGeometry


class EngineTests(unittest.TestCase):
    def test_output_name_uses_incrementing_ordinal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = directory / "sample.mkv"
            source.touch()
            (directory / "sample.mp4").touch()
            (directory / "sample (1).mp4").touch()
            self.assertEqual(next_output_path(directory, source).name, "sample (2).mp4")

    def test_scan_reads_only_supported_top_level_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "one.MP4").touch()
            (directory / "note.txt").touch()
            (directory / "child").mkdir()
            (directory / "child" / "nested.mov").touch()
            self.assertEqual([item.name for item in scan_videos(directory)], ["one.MP4"])

    def test_region_scales_and_clamps(self) -> None:
        self.assertEqual(Region(0.25, 0.5, 0.5, 0.25).pixels_for(1920, 1080), (480, 540, 960, 270))
        self.assertEqual(Region(0.99, 0.99, 0.5, 0.5).pixels_for(100, 100), (99, 99, 1, 1))

    def test_preview_geometry_maps_to_normalized_region(self) -> None:
        geometry = PreviewGeometry(1920, 1080, 960, 540)
        self.assertEqual(geometry.to_region(240, 135, 720, 405), Region(0.25, 0.25, 0.5, 0.5))

    def test_tool_resolver_prefers_application_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                (directory / name).touch()
            with patch("video_image_overlay.engine.sys.executable", str(directory / "VideoImageOverlay.exe")), patch("video_image_overlay.engine.sys.frozen", True, create=True), patch("video_image_overlay.engine.shutil.which") as which:
                tools = ToolResolver.resolve()
            self.assertEqual(tools.source, "程序目录")
            which.assert_not_called()

    def test_tool_resolver_falls_back_to_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch("video_image_overlay.engine.sys.executable", str(Path(raw) / "VideoImageOverlay.exe")), patch("video_image_overlay.engine.sys.frozen", True, create=True), patch("video_image_overlay.engine.shutil.which", side_effect=[r"C:\\tools\\ffmpeg.exe", r"C:\\tools\\ffprobe.exe"]):
            tools = ToolResolver.resolve()
        self.assertEqual(tools.source, "系统 PATH")

    def test_tool_resolver_uses_meipass_before_system_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                (directory / name).touch()
            with tempfile.TemporaryDirectory() as application_raw, patch("video_image_overlay.engine.sys.executable", str(Path(application_raw) / "VideoImageOverlay.exe")), patch("video_image_overlay.engine.sys.frozen", True, create=True), patch("video_image_overlay.engine.sys._MEIPASS", str(directory), create=True), patch("video_image_overlay.engine.shutil.which") as which:
                tools = ToolResolver.resolve()
            self.assertEqual(tools.source, "PyInstaller 内置组件")
            which.assert_not_called()

    def test_audio_copy_failure_retries_with_aac(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            image = directory / "image.png"
            video = directory / "source.mkv"
            output = directory / "output.mp4"
            image.touch()
            video.touch()
            messages: list[str] = []
            processor = VideoProcessor(MediaTools(Path("ffmpeg.exe"), Path("ffprobe.exe"), "测试"), messages.append)
            calls: list[list[str]] = []

            def fake_run(arguments: list[str]) -> tuple[int, str]:
                calls.append(arguments)
                if len(calls) == 1:
                    return 1, "MP4 不支持此音频"
                Path(arguments[-1]).touch()
                return 0, ""

            with patch.object(processor, "_command", side_effect=lambda *values: ["ffmpeg", "-c:a", values[-1], str(output.with_name(f".{output.stem}.processing{output.suffix}"))]), patch.object(processor, "_run", side_effect=fake_run):
                self.assertEqual(processor.process_one(image, video, output, Region(0, 0, 1, 1)), "转 AAC")
            self.assertEqual(calls[0][2], "copy")
            self.assertEqual(calls[1][2], "aac")
            self.assertTrue(output.exists())
            self.assertTrue(any("改为 AAC" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
