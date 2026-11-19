"""macOS: permission checks via ctypes, `say` speech, user-started dictation."""
from __future__ import annotations

import ctypes
import subprocess
from typing import Callable


AX = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
CG = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
CF = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_URL = "x-apple.systempreferences:com.apple.preference.security?"  # macOS 27 may land on the merged pane
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
        # ask AppKit to start system dictation in the focused text field (same as Edit > Start Dictation)
        try:  # runs on the Tk main thread via after(); a plain call, no Python callbacks involved
            from AppKit import NSApp
            NSApp().sendAction_to_from_("startDictation:", None, None)
        except Exception:
            pass  # the hint still tells the person how to start it by hand

    def dictation_hint(self) -> str:
        return "Говорите. Если не слушает, нажмите два раза клавишу Fn (глобус)."

    def make_click_through(self, window) -> None:
        pass  # overlay avoids covering targets instead (edge strips + offset badge)

    def watch_escape(self, callback: Callable[[], None]) -> None:
        # Poll the Esc key state from a plain thread. Callback-based hooks crash here:
        # pynput calls TSM off the main thread, and an AppKit monitor block running inside
        # Tk's event loop corrupts the Python thread state (fatal GIL error).
        import threading
        import time

        def poll():
            try:
                from Quartz import CGEventSourceKeyState, kCGEventSourceStateCombinedSessionState
            except Exception:
                return  # STOP button and the in-app Esc still work
            was = False
            while True:
                down = bool(CGEventSourceKeyState(kCGEventSourceStateCombinedSessionState, 53))  # Esc
                if down and not was:
                    callback()
                was = down
                time.sleep(0.05)

        threading.Thread(target=poll, daemon=True).start()
