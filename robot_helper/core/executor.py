"""Runs computer_toolset_20260801 member actions on the real screen.

Members (from the computer-use docs): screenshot, zoom{region}, left_click / right_click /
middle_click / double_click / triple_click {coordinate?, text? modifiers}, left_click_drag
{start_coordinate, coordinate, text?}, mouse_move{coordinate}, left_mouse_down, left_mouse_up,
cursor_position, scroll{scroll_direction, scroll_amount, coordinate?, text?}, type{text},
key{text, repeat?}, hold_key{text, duration}, wait{duration}.

Coordinates arrive in the pixel space of the screenshot we returned. Two conversions apply:
model px -> screenshot image px (undo our downscale), then image px -> pyautogui logical
points (Retina screenshots are 2x the logical size).
"""
from __future__ import annotations

import contextlib
import io
import math
import time
from typing import Callable, Protocol

from PIL import Image

from robot_helper.core.screen import fit_scale

MOVE_SECONDS = 0.5
INTERVENTION_PX = 3
KEY_NAMES = {
    "return": "enter", "escape": "esc", "backspace": "backspace", "page_down": "pagedown",
    "page_up": "pageup", "super": "win", "cmd": "command", "control": "ctrl", "option": "alt",
    "delete": "delete", "arrowup": "up", "arrowdown": "down", "arrowleft": "left",
    "arrowright": "right",
}
CLICKS = {"left_click": ("left", 1), "right_click": ("right", 1), "middle_click": ("middle", 1),
          "double_click": ("left", 2), "triple_click": ("left", 3)}


class Executor(Protocol):
    def screenshot(self) -> bytes: ...
    def perform(self, name: str, args: dict) -> bytes | str | None: ...
    def user_intervened(self) -> bool: ...
    def pointer(self) -> tuple[int, int] | None: ...


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class PyAutoGuiExecutor:
    def __init__(self, gui=None, set_clipboard: Callable[[str], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep, is_mac: bool | None = None,
                 hide_for_screenshot: Callable[[], contextlib.AbstractContextManager] | None = None,
                 on_pointer: Callable[[int, int], None] | None = None):
        if gui is None:
            import pyautogui as gui  # imported lazily so tests run without a display

            gui.FAILSAFE = True
        if set_clipboard is None:
            import pyperclip

            set_clipboard = pyperclip.copy
        if is_mac is None:
            import sys

            is_mac = sys.platform == "darwin"
        self.gui, self.set_clipboard, self.sleep, self.is_mac = gui, set_clipboard, sleep, is_mac
        self.hide = hide_for_screenshot or contextlib.nullcontext
        self.on_pointer = on_pointer
        self.scale = 1.0  # model px per image px
        self.ratio = 1.0  # logical points per image px
        self.last: tuple[int, int] | None = None
        self._image: Image.Image | None = None

    # --- capture ---------------------------------------------------------------
    def _capture(self) -> Image.Image:
        with self.hide():
            img = self.gui.screenshot()
        logical_w, _ = self.gui.size()
        self.ratio = logical_w / img.width
        self.scale = fit_scale(img.width, img.height)
        self._image = img
        return img

    def screenshot(self) -> bytes:
        img = self._capture()
        size = (max(1, math.floor(img.width * self.scale)), max(1, math.floor(img.height * self.scale)))
        return _png(img.resize(size) if self.scale < 1 else img)

    def _zoom(self, region: list[int]) -> bytes:
        img = self._capture() if self._image is None else self._image
        x0, y0, x1, y1 = [round(v / self.scale) for v in region]
        crop = img.crop((x0, y0, x1, y1))
        s = fit_scale(crop.width, crop.height)
        if s < 1:
            crop = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))))
        return _png(crop)

    # --- coordinates -----------------------------------------------------------
    def _to_logical(self, xy: list[int]) -> tuple[int, int]:
        x, y = xy
        return round(x / self.scale * self.ratio), round(y / self.scale * self.ratio)

    def _to_model(self, x: int, y: int) -> tuple[int, int]:
        return round(x / self.ratio * self.scale), round(y / self.ratio * self.scale)

    def _move(self, xy: list[int] | None) -> None:
        if xy is None:
            return
        x, y = self._to_logical(xy)
        self.gui.moveTo(x, y, duration=MOVE_SECONDS)
        self._moved(x, y)

    def _moved(self, x: int, y: int) -> None:
        self.last = (x, y)
        if self.on_pointer:
            self.on_pointer(x, y)

    # --- keys ------------------------------------------------------------------
    def _keys(self, combo: str) -> list[str]:
        keys = [KEY_NAMES.get(k.lower(), k.lower()) for k in combo.split("+") if k]
        if self.is_mac:
            keys = ["command" if k == "win" else k for k in keys]
        return keys

    @contextlib.contextmanager
    def _modifiers(self, text: str | None):
        keys = self._keys(text) if text else []
        for k in keys:
            self.gui.keyDown(k)
        try:
            yield
        finally:
            for k in reversed(keys):
                self.gui.keyUp(k)

    # --- dispatch --------------------------------------------------------------
    def perform(self, name: str, args: dict) -> bytes | str | None:
        if name == "screenshot":
            return self.screenshot()
        if name == "zoom":
            return self._zoom(args["region"])
        if name in CLICKS:
            button, clicks = CLICKS[name]
            self._move(args.get("coordinate"))
            with self._modifiers(args.get("text")):
                self.gui.click(button=button, clicks=clicks, interval=0.1)
            return None
        if name == "mouse_move":
            self._move(args["coordinate"])
            return None
        if name == "left_click_drag":
            self._move(args["start_coordinate"])
            x, y = self._to_logical(args["coordinate"])
            with self._modifiers(args.get("text")):
                self.gui.dragTo(x, y, duration=MOVE_SECONDS + 0.3, button="left")
            self._moved(x, y)
            return None
        if name == "left_mouse_down":
            self.gui.mouseDown(button="left")
            return None
        if name == "left_mouse_up":
            self.gui.mouseUp(button="left")
            return None
        if name == "cursor_position":
            x, y = self._to_model(*self.gui.position())
            return f"[{x}, {y}]"
        if name == "scroll":
            self._move(args.get("coordinate"))
            amount = int(args.get("scroll_amount", 3))
            with self._modifiers(args.get("text")):
                direction = args["scroll_direction"]
                if direction in ("up", "down"):
                    self.gui.scroll(amount if direction == "up" else -amount)
                else:
                    self.gui.hscroll(amount if direction == "right" else -amount)
            return None
        if name == "type":
            # pyautogui cannot type non-ASCII (Cyrillic), so paste through the clipboard
            self.set_clipboard(args["text"])
            self.gui.hotkey("command" if self.is_mac else "ctrl", "v")
            return None
        if name == "key":
            for _ in range(int(args.get("repeat", 1))):
                self.gui.hotkey(*self._keys(args["text"]))
            return None
        if name == "hold_key":
            with self._modifiers(args["text"]):
                self.sleep(float(args["duration"]))
            return None
        if name == "wait":
            self.sleep(min(float(args["duration"]), 300))
            return None
        raise ValueError(f"Unknown computer action: {name}")

    # --- human -----------------------------------------------------------------
    def user_intervened(self) -> bool:
        if self.last is None:
            return False
        x, y = self.gui.position()
        return abs(x - self.last[0]) > INTERVENTION_PX or abs(y - self.last[1]) > INTERVENTION_PX

    def pointer(self) -> tuple[int, int] | None:
        return self.last

    def forget_pointer(self) -> None:
        """Call after the person resumes the robot, so their own mouse moves are not re-flagged."""
        self.last = None
