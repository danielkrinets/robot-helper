"""Mapping between model screenshot pixels and real screen pixels.

Limits follow the computer-use docs example (1568 px long edge, ~1.15 MP total).
Current models accept more, but smaller screenshots cost fewer tokens per step.
"""
import math

MAX_PIXELS = 1_150_000


def fit_scale(width: int, height: int, max_long_edge: int = 1568) -> float:
    return min(1.0, max_long_edge / max(width, height), math.sqrt(MAX_PIXELS / (width * height)))


def to_screen(x: int, y: int, scale: float) -> tuple[int, int]:
    return round(x / scale), round(y / scale)
