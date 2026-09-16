from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_REGION = (0.22, 0.23, 0.29, 0.28)


@dataclass(frozen=True)
class AppSettings:
    source_path: str = ""
    destination_path: str = ""
    image_path: str = ""
    region: tuple[float, float, float, float] = DEFAULT_REGION
    position_mode: str = "normalized"
    window_width: int = 920
    window_height: int = 760
    window_state: str = "normal"

    @classmethod
    def from_dict(cls, value: object) -> "AppSettings":
        if not isinstance(value, dict):
            raise ValueError("设置根节点必须是对象")
        region_value = value.get("region", DEFAULT_REGION)
        if not isinstance(region_value, list) or len(region_value) != 4:
            raise ValueError("选区设置无效")
        region = tuple(float(item) for item in region_value)
        if any(item < 0 or item > 1 for item in region) or region[2] <= 0 or region[3] <= 0:
            raise ValueError("选区超出范围")
        width = int(value.get("window_width", 920))
        height = int(value.get("window_height", 760))
        if width < 640 or height < 480:
            raise ValueError("窗口尺寸无效")
        state = value.get("window_state", "normal")
        if state not in {"normal", "zoomed"}:
            state = "normal"
        mode = value.get("position_mode", "normalized")
        if mode != "normalized":
            raise ValueError("位置模式无效")
        return cls(str(value.get("source_path", "")), str(value.get("destination_path", "")), str(value.get("image_path", "")), region, mode, width, height, state)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return {"source_path": self.source_path, "destination_path": self.destination_path, "image_path": self.image_path, "region": list(self.region), "position_mode": self.position_mode, "window_width": self.window_width, "window_height": self.window_height, "window_state": self.window_state}


class SettingsStore:
    def __init__(self, base_directory: Path | None = None) -> None:
        self.base_directory = base_directory or self.default_base_directory()
        self.path = self.base_directory / "settings.json"

    @staticmethod
    def default_base_directory() -> Path:
        if getattr(sys, "frozen", False):
            return Path(os.path.dirname(sys.executable))
        return Path(__file__).resolve().parents[1]

    def load(self, logger: Callable[[str], None] | None = None) -> AppSettings:
        write_log = logger or (lambda _: None)
        if not self.path.exists():
            return AppSettings()
        try:
            return AppSettings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            write_log(f"无法读取 settings.json，已使用默认设置：{error}")
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.base_directory.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.base_directory, prefix=".settings-", suffix=".tmp", delete=False) as temporary:
                temporary_name = temporary.name
                json.dump(settings.to_dict(), temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            raise
