"""Always-on-top overlay: orange edge strips, a caption, and a robot badge next to the cursor.

Thread-safe: the agent thread calls these methods; work is marshalled to the Tk main thread.
"""
from __future__ import annotations

import contextlib
import threading
import time
import tkinter as tk

ORANGE = "#FF8A00"
EDGE = 10
BADGE_OFFSET = 28


class Overlay:
    def __init__(self, root: tk.Tk, services=None):
        self.root, self.services = root, services
        self._main = threading.current_thread()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        geoms = [f"{w}x{EDGE}+0+0", f"{w}x{EDGE}+0+{h - EDGE}", f"{EDGE}x{h}+0+0", f"{EDGE}x{h}+{w - EDGE}+0"]
        self.strips = [self._window(g, ORANGE) for g in geoms]
        self.caption = self._window(f"+{w // 2 - 300}+{EDGE}", ORANGE)
        self.caption_label = tk.Label(self.caption, text="", bg=ORANGE, fg="white",
                                      font=(".AppleSystemUIFont" if __import__("sys").platform == "darwin" else "Segoe UI", 24, "bold"), padx=24, pady=8)
        self.caption_label.pack()
        self.badge = self._window("+0+0", ORANGE)
        dot = tk.Canvas(self.badge, width=36, height=36, bg=ORANGE, highlightthickness=0)
        dot.create_oval(4, 4, 32, 32, fill="white", outline="white")
        dot.create_oval(11, 11, 25, 25, fill=ORANGE, outline=ORANGE)
        dot.pack()
        self.windows = [*self.strips, self.caption, self.badge]
        self._visible = False
        self._hide_all()

    def _window(self, geometry: str, bg: str) -> tk.Toplevel:
        win = tk.Toplevel(self.root, bg=bg)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(geometry)
        if self.services:
            win.update_idletasks()
            with contextlib.suppress(Exception):
                self.services.make_click_through(win)
        return win

    def _on_main(self, fn, wait: bool = False) -> None:
        if threading.current_thread() is self._main:
            fn()
            return
        done = threading.Event()

        def run():
            try:
                fn()
            finally:
                done.set()

        self.root.after(0, run)
        if wait:
            done.wait(timeout=2)

    def _hide_all(self) -> None:
        for win in self.windows:
            win.withdraw()

    def _show_all(self) -> None:
        for win in self.windows:
            win.deiconify()
            win.lift()

    # public API -----------------------------------------------------------------
    def show(self, label: str) -> None:
        def fn():
            self._visible = True
            self.caption_label.config(text=label)
            self._show_all()
        self._on_main(fn)

    def set_label(self, text: str) -> None:
        self._on_main(lambda: self.caption_label.config(text=text[:60]))

    def move_hand(self, x: int, y: int) -> None:
        self._on_main(lambda: self.badge.geometry(f"+{x + BADGE_OFFSET}+{y + BADGE_OFFSET}"))

    def hide(self) -> None:
        def fn():
            self._visible = False
            self._hide_all()
        self._on_main(fn)

    @contextlib.contextmanager
    def hidden_for_screenshot(self):
        was_visible = self._visible

        # move windows off-screen instead of withdraw/deiconify: re-showing a window activates it
        # and would steal keyboard focus from the field the robot just clicked
        saved = {}

        def hide():
            for win in self.windows:
                saved[win] = win.geometry()
                win.geometry("+-10000+-10000")
            self.root.update_idletasks()

        if was_visible:
            self._on_main(hide, wait=True)
            time.sleep(0.05)  # let the window server repaint without the overlay
        try:
            yield
        finally:
            if was_visible:
                def restore():
                    for win, geom in saved.items():
                        win.geometry(geom)
                self._on_main(restore)


if __name__ == "__main__":  # manual demo: overlay for 5 seconds
    root = tk.Tk()
    root.withdraw()
    ov = Overlay(root)
    ov.show("Сейчас нажимаю на почту…")
    ov.move_hand(400, 300)
    root.after(5000, root.destroy)
    root.mainloop()
    print("overlay demo ok")
