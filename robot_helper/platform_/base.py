"""OS-specific services behind one interface. Platform libraries are imported lazily."""
from __future__ import annotations

import sys
from typing import Callable, Protocol


class PlatformServices(Protocol):
    def prepare(self) -> None: ...
    def missing_permissions(self) -> list[str]: ...
    def open_settings(self, name: str) -> None: ...
    def speak(self, text: str) -> None: ...
    def listen(self) -> str | None: ...
    def start_dictation(self) -> None: ...
    def dictation_hint(self) -> str: ...
    def make_click_through(self, window) -> None: ...
    def watch_escape(self, callback: Callable[[], None]) -> None: ...


def watch_escape_with_pynput(callback: Callable[[], None]) -> None:
    from pynput import keyboard

    def on_press(key):
        if key == keyboard.Key.esc:
            callback()

    keyboard.Listener(on_press=on_press, daemon=True).start()


def get_platform() -> PlatformServices:
    if sys.platform == "win32":
        from robot_helper.platform_.windows import WindowsServices

        return WindowsServices()
    from robot_helper.platform_.macos import MacServices

    return MacServices()
