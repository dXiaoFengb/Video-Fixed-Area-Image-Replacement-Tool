from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from video_image_overlay.engine import MediaTools, Region, ToolResolver, VideoProcessor, probe_video


class FfmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.tools = ToolResolver.resolve()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_overlay_keeps_source_and_writes_h264_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "input.mp4"
            image = root / "overlay.png"
            output = root / "output.mp4"
            Image.new("RGB", (80, 40), "red").save(image)
            import subprocess
            subprocess.run([str(self.tools.ffmpeg), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25", "-f", "lavfi", "-i", "sine=frequency=1000", "-t", "1", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            VideoProcessor(self.tools).process_one(image, source, output, Region(0.25, 0.25, 0.5, 0.25))
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertTrue(output.is_file())
            metadata = probe_video(self.tools, output)
            self.assertEqual((int(metadata["width"]), int(metadata["height"])), (320, 240))
            codecs = subprocess.run([str(self.tools.ffprobe), "-v", "error", "-show_entries", "stream=codec_name", "-of", "json", str(output)], capture_output=True, text=True, check=True)
            self.assertIn("h264", codecs.stdout)
            frame = root / "result.png"
            subprocess.run([str(self.tools.ffmpeg), "-y", "-v", "error", "-i", str(output), "-frames:v", "1", str(frame)], check=True)
            red, green, blue = Image.open(frame).convert("RGB").getpixel((160, 90))
            self.assertGreater(red, 180)
            self.assertLess(green, 80)
            self.assertLess(blue, 80)



if __name__ == "__main__":
    unittest.main()
