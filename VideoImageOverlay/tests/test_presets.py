from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from video_image_overlay.presets import PRESET_FILENAMES, app_icon_path, install_presets, preset_directory


class PresetTests(unittest.TestCase):
    def test_assets_are_eight_1280x720_png_files(self) -> None:
        directory = preset_directory()
        self.assertEqual(len(PRESET_FILENAMES), 8)
        for name in PRESET_FILENAMES:
            path = directory / name
            self.assertTrue(path.is_file(), name)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1280, 720))
                self.assertEqual(image.format, "PNG")

    def test_app_icon_contains_all_windows_sizes(self) -> None:
        with Image.open(app_icon_path()) as image:
            self.assertEqual(image.ico.sizes(), {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)})
    def test_frozen_resource_directory_uses_meipass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with patch("video_image_overlay.presets.sys.frozen", True, create=True), patch("video_image_overlay.presets.sys._MEIPASS", raw, create=True):
                self.assertEqual(preset_directory(), Path(raw) / "presets")

    def test_install_skips_existing_files_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            application = Path(raw)
            destination = application / "替换图片" / "常用素材"
            destination.mkdir(parents=True)
            existing = destination / PRESET_FILENAMES[0]
            existing.write_bytes(b"user-file")
            messages: list[str] = []
            result = install_presets(application, messages.append)
            self.assertIn(PRESET_FILENAMES[0], result.skipped)
            self.assertEqual(existing.read_bytes(), b"user-file")
            self.assertEqual(len(result.installed), 7)
            self.assertFalse(result.failed)
            self.assertTrue(any("跳过" in message for message in messages))

    def test_install_failure_is_reported_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            application = Path(raw)
            with patch("video_image_overlay.presets.shutil.copy2", side_effect=OSError("拒绝访问")):
                messages: list[str] = []
                result = install_presets(application, messages.append)
            self.assertEqual(len(result.failed), 8)
            self.assertTrue(all("安装常用素材失败" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
