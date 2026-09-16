from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path

from video_image_overlay.app import VideoImageOverlayApp
from video_image_overlay.engine import Region, ToolResolver, VideoProcessor, scan_videos


def main() -> None:
    parser = argparse.ArgumentParser(description="VideoImageOverlay")
    parser.add_argument("--smoke-gui", action="store_true")
    parser.add_argument("--smoke-log")
    parser.add_argument("--batch", action="store_true", help="仅用于自动化验收的无界面批处理入口")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    parser.add_argument("--image")
    parser.add_argument("--region", help="x,y,width,height；均为 0 到 1 的比例坐标")
    parser.add_argument("--log")
    arguments = parser.parse_args()
    if arguments.batch:
        run_batch(arguments, parser)
        return
    root = tk.Tk()
    write_smoke_marker(arguments.smoke_log, "Tk root created")
    app = VideoImageOverlayApp(root)
    write_smoke_marker(arguments.smoke_log, "GUI constructed")
    if arguments.smoke_gui:
        def close_smoke() -> None:
            write_smoke_marker(arguments.smoke_log, "GUI close callback reached")
            root.quit()

        root.after(50, close_smoke)
        root.mainloop()
        write_smoke_marker(arguments.smoke_log, "GUI mainloop exited")
        root.destroy()
        write_smoke_marker(arguments.smoke_log, "GUI destroyed")
        return
    root.mainloop()


def run_batch(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not all((arguments.source, arguments.destination, arguments.image, arguments.region, arguments.log)):
        parser.error("--batch 需要 --source、--destination、--image、--region 和 --log")
    try:
        parts = [float(item) for item in arguments.region.split(",")]
        if len(parts) != 4 or any(value < 0 or value > 1 for value in parts) or parts[2] <= 0 or parts[3] <= 0:
            raise ValueError
    except ValueError:
        parser.error("--region 必须是四个 0 到 1 之间的正数：x,y,width,height")
    source = Path(arguments.source)
    destination = Path(arguments.destination)
    image = Path(arguments.image)
    if source.resolve() == destination.resolve():
        parser.error("目标文件夹必须与源文件夹不同")
    log_path = Path(arguments.log)
    messages: list[str] = []
    try:
        tools = ToolResolver.resolve()
        messages.append(f"FFmpeg 来源：{tools.source}")
        processor = VideoProcessor(tools, messages.append)
        summary = processor.process_batch(image, scan_videos(source), destination, Region(*parts), lambda current, total, video, state: messages.append(f"{state}：{video.name}（{current}/{total}）"))
        messages.append(f"完成：成功 {len(summary['success'])}，失败 {len(summary['failed'])}，取消 {len(summary['cancelled'])}。")
        for category, values in summary.items():
            messages.extend(f"[{category}] {value}" for value in values)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(messages) + "\n", encoding="utf-8")
        if summary["failed"] or not summary["success"]:
            raise SystemExit(1)
    except Exception as error:  # noqa: BLE001
        messages.append(f"失败：{error}")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(messages) + "\n", encoding="utf-8")
        raise SystemExit(1) from error


def write_smoke_marker(location: str | None, message: str) -> None:
    if location:
        Path(location).write_text(message + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
