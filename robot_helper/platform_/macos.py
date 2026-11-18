"""macOS: permission checks via ctypes, `say` speech, user-started dictation."""
from __future__ import annotations

import ctypes
import subprocess
from typing import Callable

from robot_helper.platform_.base import watch_escape_with_pynput

AX = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
CG = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
CF = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_URL = "x-apple.systempreferences:com.apple.preference.security?"
PANES = {
    "Универсальный доступ": _URL + "Privacy_Accessibility",
    "Запись экрана": _URL + "Privacy_ScreenCapture",
    "Мониторинг ввода": _URL + "Privacy_ListenEvent",
}


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

    def open_settings(self, name: str) -> None:
        """Ask macOS to list this app in the pane (so no '+' is needed), then open the pane."""
        self._request(name)
        subprocess.Popen(["open", PANES[name]])

    def _request(self, name: str) -> None:
        try:
            if name == "Запись экрана":
                ctypes.cdll.LoadLibrary(CG).CGRequestScreenCaptureAccess()
            elif name == "Универсальный доступ":
                ax, cf = ctypes.cdll.LoadLibrary(AX), ctypes.cdll.LoadLibrary(CF)
                key = ctypes.c_void_p.in_dll(ax, "kAXTrustedCheckOptionPrompt")
                true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
                keys, vals = (ctypes.c_void_p * 1)(key), (ctypes.c_void_p * 1)(true)
                cf.CFDictionaryCreate.restype = ctypes.c_void_p
                cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                  ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
                opts = cf.CFDictionaryCreate(
                    None, keys, vals, 1,
                    ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")),
                    ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryValueCallBacks")))
                ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
                ax.AXIsProcessTrustedWithOptions(opts)
        except Exception:
            pass  # opening the pane still works

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
