"""Windows: DPI awareness, SAPI speech via PowerShell, Win+H dictation, click-through windows."""
from __future__ import annotations

import subprocess
from typing import Callable

from robot_helper.platform_.base import watch_escape_with_pynput

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


class WindowsServices:
    def prepare(self) -> None:
        # Without this, 125%/150% display scaling makes clicks land in the wrong place
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()

    def missing_permissions(self) -> list[str]:
        return []

    def speak(self, text: str) -> None:
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "try{$s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'ru-RU')}catch{};"
            f"$s.Speak({ps_quote(text)})"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def listen(self) -> str | None:
        return None  # v1: system dictation into the text field (see voice-spike.md)

    def start_dictation(self) -> None:
        import pyautogui

        pyautogui.hotkey("win", "h")

    def dictation_hint(self) -> str:
        return "Говорите — Windows сама напишет ваши слова."

    def make_click_through(self, window) -> None:
        import ctypes

        # a layered window draws nothing until its alpha is set; Tk sets it via -alpha
        window.attributes("-alpha", 0.99)
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)

    def watch_escape(self, callback: Callable[[], None]) -> None:
        watch_escape_with_pynput(callback)
