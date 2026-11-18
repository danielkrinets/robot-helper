"""Small drawing toolkit: Apple dark colors, rounded shapes, line icons, pill buttons, chat bubbles."""
from __future__ import annotations

import sys
import tkinter as tk

# Apple dark-mode system colors
BG, CARD, FIELD = "#1C1C1E", "#2C2C2E", "#3A3A3C"
FG, MUTED = "#F2F2F7", "#98989F"
BLUE, RED, GREEN, ORANGE = "#0A84FF", "#FF453A", "#30D158", "#FF9F0A"
FAMILY = ".AppleSystemUIFont" if sys.platform == "darwin" else "Segoe UI"
KEY = "#010203"  # Windows transparent key color


def font(size: int, weight: str = "normal"):
    return (FAMILY, size, weight)


def shade(color: str, k: float) -> str:
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(min(255, int(v * k)) for v in rgb)


def rounded(canvas: tk.Canvas, x0, y0, x1, y1, r, color, outline=None, **kw):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, fill=color, outline=outline or color, **kw)


def clear_bg() -> str:
    """Background that the OS treats as see-through, so windows can have real rounded corners."""
    return "systemTransparent" if sys.platform == "darwin" else KEY


def make_floating(win: tk.Misc) -> None:
    if sys.platform == "darwin":
        # borderless panel without the title bar; overrideredirect alone keeps the frame on Tk 9
        try:
            win.tk.call("::tk::unsupported::MacWindowStyle", "style", win._w, "plain", "none")
        except tk.TclError:
            pass
        win.overrideredirect(True)
    else:
        win.overrideredirect(True)
    win.attributes("-topmost", True)
    if sys.platform == "darwin":
        win.attributes("-transparent", True)
    elif sys.platform == "win32":
        win.attributes("-transparentcolor", KEY)
    win.configure(bg=clear_bg())


def draw_icon(c: tk.Canvas, name: str, cx: float, cy: float, color: str, s: float = 1.0) -> None:
    """Line icons drawn on a canvas (no emoji)."""
    w = 2.4 * s
    line = dict(fill=color, width=w, capstyle="round", joinstyle="round")
    if name == "mic":
        rounded(c, cx - 5 * s, cy - 12 * s, cx + 5 * s, cy + 3 * s, 5 * s, color)
        c.create_arc(cx - 9 * s, cy - 9 * s, cx + 9 * s, cy + 8 * s, start=200, extent=140, style="arc",
                     outline=color, width=w)
        c.create_line(cx, cy + 8 * s, cx, cy + 13 * s, **line)
    elif name == "send":
        c.create_line(cx, cy + 9 * s, cx, cy - 8 * s, **line)
        c.create_line(cx - 7 * s, cy - 1 * s, cx, cy - 9 * s, cx + 7 * s, cy - 1 * s, **line)
    elif name == "check":
        c.create_line(cx - 7 * s, cy, cx - 2 * s, cy + 5 * s, cx + 8 * s, cy - 6 * s, **line)
    elif name == "close":
        d = 5 * s
        c.create_line(cx - d, cy - d, cx + d, cy + d, **line)
        c.create_line(cx - d, cy + d, cx + d, cy - d, **line)
    elif name == "minus":
        c.create_line(cx - 6 * s, cy, cx + 6 * s, cy, **line)
    elif name == "expand":  # two outward corners
        d = 6 * s
        c.create_line(cx + 1 * s, cy - d, cx + d, cy - d, cx + d, cy - 1 * s, **line)
        c.create_line(cx - 1 * s, cy + d, cx - d, cy + d, cx - d, cy + 1 * s, **line)
    elif name == "shrink":  # two inward corners
        d = 6 * s
        c.create_line(cx + d, cy - 1 * s, cx + 1 * s, cy - 1 * s, cx + 1 * s, cy - d, **line)
        c.create_line(cx - d, cy + 1 * s, cx - 1 * s, cy + 1 * s, cx - 1 * s, cy + d, **line)
    elif name == "dock":  # a screen with a panel docked to one side
        rounded(c, cx - 8 * s, cy - 6 * s, cx + 8 * s, cy + 6 * s, 3 * s, "", outline=color, width=w)
        c.create_line(cx + 3 * s, cy - 5 * s, cx + 3 * s, cy + 5 * s, **line)


class Pill(tk.Canvas):
    """Rounded flat button. Darkens on press, fires on release inside (cancel by dragging away)."""

    def __init__(self, parent, text="", color=BLUE, command=None, w=160, h=48, size=17, fg="white",
                 icon=None, icon_scale=1.0):
        super().__init__(parent, width=w, height=h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.color, self.command, self.w, self.h = color, command, w, h
        if not color:
            self.shape = None
        elif w == h:  # round icon button
            self.shape = self.create_oval(0, 0, w - 1, h - 1, fill=color, outline=color)
        else:
            self.shape = rounded(self, 0, 0, w, h, h / 2, color)
        if icon:
            draw_icon(self, icon, w / 2, h / 2, fg, icon_scale)
        else:
            self.create_text(w / 2, h / 2, text=text, fill=fg, font=font(size, "bold"))
        self.bind("<ButtonPress-1>", lambda e: self._tint(0.72))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._tint(1.15))
        self.bind("<Leave>", lambda e: self._tint(1.0))

    def _release(self, e):
        self._tint(1.0)
        if self.command and 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.command()

    def _tint(self, k: float):
        if self.shape:
            c = shade(self.color, k)
            self.itemconfig(self.shape, fill=c, outline=c)


def icon_button(parent, icon, command, size=28) -> Pill:
    return Pill(parent, color=FIELD, command=command, w=size, h=size, icon=icon, icon_scale=size / 34,
                fg=FG)


def card(parent, pad=18, radius=22, color=CARD) -> tk.Frame:
    """Rounded container; returns the inner frame to pack content into."""
    outer = tk.Canvas(parent, bg=parent["bg"], highlightthickness=0, height=10)
    outer.pack(fill="x", pady=6)
    inner = tk.Frame(outer, bg=color)
    win = outer.create_window(pad, pad, window=inner, anchor="nw")

    def layout(_=None):
        w = outer.winfo_width()
        h = inner.winfo_reqheight() + 2 * pad
        outer.configure(height=h)
        outer.itemconfigure(win, width=max(10, w - 2 * pad))
        outer.delete("bg")
        rounded(outer, 0, 0, w, h, radius, color, tags="bg")
        outer.tag_lower("bg")

    outer.bind("<Configure>", layout)
    inner.bind("<Configure>", layout)
    return inner


def check_row(parent, text: str) -> tk.Frame:
    row = tk.Frame(parent, bg=parent["bg"])
    c = tk.Canvas(row, width=22, height=22, bg=parent["bg"], highlightthickness=0)
    draw_icon(c, "check", 11, 11, GREEN, 0.9)
    c.pack(side="left", padx=(0, 8))
    tk.Label(row, text=text, bg=parent["bg"], fg=GREEN, font=font(16)).pack(side="left")
    return row


class Chat(tk.Frame):
    """Scrollable list of rounded message bubbles."""

    def __init__(self, parent, wrap: int, text_size: int):
        super().__init__(parent, bg=BG)
        self.wrap, self.size = wrap, text_size
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _wheel(self, e):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def add(self, text: str, who: str = "robot"):
        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill="x", padx=4, pady=4)
        mine = who == "me"
        color = {"me": BLUE, "robot": CARD, "note": BG}[who]
        c = tk.Canvas(row, bg=BG, highlightthickness=0)
        t = c.create_text(14, 9, text=text, anchor="nw", width=self.wrap, font=font(self.size),
                          fill=MUTED if who == "note" else FG)
        _, _, x1, y1 = c.bbox(t)
        w, h = x1 + 14, y1 + 9
        c.configure(width=w, height=h)
        if who != "note":
            c.tag_lower(rounded(c, 0, 0, w, h, min(20, h / 2), color))
        c.pack(side="right" if mine else "left")
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)
