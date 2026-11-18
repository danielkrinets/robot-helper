"""Test doubles shared by tests."""
import io

from PIL import Image


def png(w=100, h=50) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


class FakeGui:
    """Stands in for the pyautogui module and records calls."""

    def __init__(self, logical=(1440, 900), image=(1440, 900)):
        self.logical, self.image = logical, image
        self.calls: list[tuple] = []
        self.pos = (0, 0)

    def size(self):
        return self.logical

    def screenshot(self):
        return Image.new("RGB", self.image, "white")

    def position(self):
        return self.pos

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name in ("moveTo", "dragTo"):
                self.pos = (args[0], args[1])

        return record


class FakeExecutor:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.intervened = False

    def screenshot(self) -> bytes:
        return png()

    def perform(self, name, args):
        self.calls.append((name, args))
        if name in ("screenshot", "zoom"):
            return png()
        if name == "cursor_position":
            return "[0, 0]"
        return None

    def user_intervened(self) -> bool:
        return self.intervened

    def pointer(self):
        return None
