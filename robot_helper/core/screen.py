"""Mapping between model screenshot pixels and real screen pixels."""


def fit_scale(width: int, height: int, max_long_edge: int = 1568) -> float:
    return min(1.0, max_long_edge / max(width, height))


def to_screen(x: int, y: int, scale: float) -> tuple[int, int]:
    return round(x / scale), round(y / scale)
