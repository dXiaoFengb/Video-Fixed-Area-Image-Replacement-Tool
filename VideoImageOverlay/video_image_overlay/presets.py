from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PRESET_FILENAMES = (
    "01_纯黑.png",
    "02_纯白.png",
    "03_浅灰.png",
    "04_深灰.png",
    "05_红色.png",
    "06_绿色.png",
    "07_蓝色.png",
    "08_马赛克.png",
)


@dataclass(frozen=True)
class PresetInstallResult:
    installed: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]


def preset_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "presets"
    return Path(__file__).resolve().parents[1] / "assets" / "presets"


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "app_icon.ico"
    return Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"


def install_presets(application_directory: Path, logger: Callable[[str], None] | None = None) -> PresetInstallResult:
    write_log = logger or (lambda _: None)
    destination = application_directory / "替换图片" / "常用素材"
    installed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        message = f"无法创建常用素材目录：{error}"
        write_log(message)
        return PresetInstallResult((), (), (message,))
    for name in PRESET_FILENAMES:
        target = destination / name
        if target.exists():
            skipped.append(name)
            write_log(f"常用素材已存在，跳过：{name}")
            continue
        try:
            shutil.copy2(preset_directory() / name, target)
        except OSError as error:
            message = f"安装常用素材失败 {name}：{error}"
            failed.append(message)
            write_log(message)
        else:
            installed.append(name)
            write_log(f"已安装常用素材：{name}")
    return PresetInstallResult(tuple(installed), tuple(skipped), tuple(failed))
