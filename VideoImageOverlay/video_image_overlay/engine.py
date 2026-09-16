from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"}


def subprocess_window_options() -> dict[str, object]:
    """让 GUI 程序调用的媒体工具不显示控制台窗口。"""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


@dataclass(frozen=True)
class Region:
    """相对于参考画面的归一化选区。"""

    x: float
    y: float
    width: float
    height: float

    def pixels_for(self, video_width: int, video_height: int) -> tuple[int, int, int, int]:
        x = max(0, min(video_width - 1, round(self.x * video_width)))
        y = max(0, min(video_height - 1, round(self.y * video_height)))
        width = max(1, min(video_width - x, round(self.width * video_width)))
        height = max(1, min(video_height - y, round(self.height * video_height)))
        return x, y, width, height


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: Path
    ffprobe: Path
    source: str


class ToolResolver:
    """按可审计的顺序查找媒体工具。"""

    @staticmethod
    def resolve() -> MediaTools:
        executable_directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        bundled_directory = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None
        candidates: list[tuple[str, Path]] = [("程序目录", executable_directory)]
        if not getattr(sys, "frozen", False):
            candidates.append(("项目内置组件", executable_directory / "third_party" / "ffmpeg"))
        if bundled_directory:
            candidates.append(("PyInstaller 内置组件", bundled_directory))
        for source, directory in candidates:
            ffmpeg = directory / "ffmpeg.exe"
            ffprobe = directory / "ffprobe.exe"
            if ffmpeg.is_file() and ffprobe.is_file():
                return MediaTools(ffmpeg, ffprobe, source)
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path and ffprobe_path:
            return MediaTools(Path(ffmpeg_path), Path(ffprobe_path), "系统 PATH")
        raise FileNotFoundError("未找到 ffmpeg.exe 与 ffprobe.exe。请使用内置版程序或将二者加入 PATH。")


def scan_videos(source_directory: Path) -> list[Path]:
    return sorted(
        (item for item in source_directory.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda item: item.name.casefold(),
    )


def next_output_path(output_directory: Path, source_video: Path) -> Path:
    base_name = source_video.stem
    candidate = output_directory / f"{base_name}.mp4"
    ordinal = 1
    while candidate.exists():
        candidate = output_directory / f"{base_name} ({ordinal}).mp4"
        ordinal += 1
    return candidate


def probe_video(tools: MediaTools, video_path: Path) -> dict:
    result = subprocess.run(
        [str(tools.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(video_path)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        **subprocess_window_options(),
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise ValueError("找不到视频流")
    return streams[0]


def extract_first_frame(tools: MediaTools, video_path: Path, destination: Path) -> None:
    result = subprocess.run(
        [str(tools.ffmpeg), "-nostdin", "-y", "-v", "error", "-i", str(video_path), "-frames:v", "1", str(destination)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        **subprocess_window_options(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "无法提取首帧")


class VideoProcessor:
    def __init__(self, tools: MediaTools, logger: Callable[[str], None] | None = None) -> None:
        self.tools = tools
        self.logger = logger or (lambda _: None)
        self._cancelled = threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()

    def _run(self, arguments: list[str]) -> tuple[int, str]:
        if self._cancelled.is_set():
            return -1, "已取消"
        with self._lock:
            self._process = subprocess.Popen(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **subprocess_window_options(),
            )
            process = self._process
        _, stderr = process.communicate()
        with self._lock:
            self._process = None
        if self._cancelled.is_set():
            return -1, "已取消"
        return process.returncode, stderr

    def _command(self, image: Path, video: Path, output: Path, region: Region, audio_codec: str) -> list[str]:
        metadata = probe_video(self.tools, video)
        x, y, width, height = region.pixels_for(int(metadata["width"]), int(metadata["height"]))
        filter_graph = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[overlay];[1:v][overlay]overlay={x}:{y}:format=auto[video]"
        )
        return [
            str(self.tools.ffmpeg), "-nostdin", "-y", "-v", "error", "-loop", "1", "-i", str(image), "-i", str(video),
            "-filter_complex", filter_graph, "-map", "[video]", "-map", "1:a?", "-c:v", "libx264", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", audio_codec, "-shortest", str(output),
        ]

    def process_one(self, image: Path, video: Path, output: Path, region: Region) -> str:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.processing{output.suffix}")
        for candidate in (temporary,):
            if candidate.exists():
                candidate.unlink()
        self.logger(f"处理 {video.name}，先尝试复制音频。")
        code, detail = self._run(self._command(image, video, temporary, region, "copy"))
        audio_mode = "复制原音频"
        if code != 0 and not self._cancelled.is_set():
            self.logger(f"{video.name} 无法直接封装音频，改为 AAC。")
            if temporary.exists():
                temporary.unlink()
            code, detail = self._run(self._command(image, video, temporary, region, "aac"))
            audio_mode = "转 AAC"
        if code != 0:
            if temporary.exists():
                temporary.unlink()
            raise RuntimeError("已取消" if self._cancelled.is_set() else detail.strip() or "FFmpeg 处理失败")
        os.replace(temporary, output)
        return audio_mode

    def process_batch(self, image: Path, videos: list[Path], output_directory: Path, region: Region, progress: Callable[[int, int, Path, str], None]) -> dict[str, list[str]]:
        summary = {"success": [], "failed": [], "cancelled": []}
        for index, video in enumerate(videos, start=1):
            if self._cancelled.is_set():
                summary["cancelled"].extend(item.name for item in videos[index - 1:])
                break
            output = next_output_path(output_directory, video)
            try:
                audio_mode = self.process_one(image, video, output, region)
                summary["success"].append(f"{video.name} -> {output.name}（{audio_mode}）")
                progress(index, len(videos), video, "成功")
            except Exception as error:  # noqa: BLE001
                if self._cancelled.is_set():
                    summary["cancelled"].append(video.name)
                    summary["cancelled"].extend(item.name for item in videos[index:])
                    break
                summary["failed"].append(f"{video.name}: {error}")
                progress(index, len(videos), video, "失败")
        return summary


def temporary_frame_path() -> Path:
    handle, name = tempfile.mkstemp(prefix="video_overlay_preview_", suffix=".png")
    os.close(handle)
    return Path(name)
