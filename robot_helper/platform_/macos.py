"""macOS: permission checks via ctypes, `say` speech, user-started dictation."""
from __future__ import annotations

import ctypes
import subprocess
from typing import Callable

from robot_helper.platform_.base import watch_escape_with_pynput

AX = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
CG = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"


class MacServices:
    def prepare(self) -> None:
        pass

    def _accessibility_ok(self) -> bool:
        return bool(ctypes.cdll.LoadLibrary(AX).AXIsProcessTrusted())

    def _screen_ok(self) -> bool:
        return bool(ctypes.cdll.LoadLibrary(CG).CGPreflightScreenCaptureAccess())

    def missing_permissions(self) -> list[str]:
        missing = []
        if not self._accessibility_ok():
            missing.append("Системные настройки → Конфиденциальность и безопасность → Универсальный доступ")
        if not self._screen_ok():
            missing.append("Системные настройки → Конфиденциальность и безопасность → Запись экрана")
        return missing

    def speak(self, text: str) -> None:
        subprocess.Popen(["say", "-v", "Milena", text])

    def listen(self) -> str | None:
        return None  # v1: system dictation into the text field (see voice-spike.md)

    def start_dictation(self) -> None:
        pass  # the dictation shortcut is user-configurable on macOS; the hint explains it

    def dictation_hint(self) -> str:
        return "Нажмите два раза клавишу Fn (глобус) и говорите."

    def make_click_through(self, window) -> None:
        pass  # overlay avoids covering targets instead (edge strips + offset badge)

    def watch_escape(self, callback: Callable[[], None]) -> None:
        watch_escape_with_pynput(callback)
