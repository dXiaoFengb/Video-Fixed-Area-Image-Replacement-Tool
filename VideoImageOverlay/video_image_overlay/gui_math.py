from __future__ import annotations

from dataclasses import dataclass

from .engine import Region


@dataclass(frozen=True)
class PreviewGeometry:
    source_width: int
    source_height: int
    canvas_width: int
    canvas_height: int

    @property
    def scale(self) -> float:
        return min(self.canvas_width / self.source_width, self.canvas_height / self.source_height)

    @property
    def offset_x(self) -> float:
        return (self.canvas_width - self.source_width * self.scale) / 2

    @property
    def offset_y(self) -> float:
        return (self.canvas_height - self.source_height * self.scale) / 2

    def to_region(self, left: float, top: float, right: float, bottom: float) -> Region:
        x = max(0, min(1, (left - self.offset_x) / (self.source_width * self.scale)))
        y = max(0, min(1, (top - self.offset_y) / (self.source_height * self.scale)))
        right_value = max(x, min(1, (right - self.offset_x) / (self.source_width * self.scale)))
        bottom_value = max(y, min(1, (bottom - self.offset_y) / (self.source_height * self.scale)))
        return Region(x, y, max(0.01, right_value - x), max(0.01, bottom_value - y))
