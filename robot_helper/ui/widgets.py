"""Small drawing toolkit: Apple dark colors, rounded shapes, line icons, pill buttons, chat bubbles."""
from __future__ import annotations

import contextlib
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


_ids = iter(range(1, 10**9))


def rounded(canvas: tk.Canvas, x0, y0, x1, y1, r, color, outline=None, tags=None, **kw):
    """Rounded rectangle. Filled shapes are built from circles + rectangles: smooth polygons
    leave jagged corners in Tk. Returns a tag naming all parts (usable with itemconfig/tag_lower)."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    tag = f"rr{next(_ids)}"
    all_tags = (tag,) + ((tags,) if isinstance(tags, str) else tuple(tags or ()))
    if not color:  # outline only (icons): smooth polygon is fine at this size
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        canvas.create_polygon(pts, smooth=True, fill="", outline=outline or "", tags=all_tags, **kw)
        return tag
    d = 2 * r
    opts = dict(fill=color, outline=color, tags=all_tags)
    for cx, cy in ((x0, y0), (x1 - d, y0), (x0, y1 - d), (x1 - d, y1 - d)):
        canvas.create_oval(cx, cy, cx + d, cy + d, **opts)
    canvas.create_rectangle(x0 + r, y0, x1 - r, y1, **opts)
    canvas.create_rectangle(x0, y0 + r, x1, y1 - r, **opts)
    return tag


def clear_bg() -> str:
    return BG


def make_floating(win: tk.Misc) -> None:
    if sys.platform == "darwin":
        # borderless panel without the title bar; overrideredirect alone keeps the frame on Tk 9
        # "plain" = borderless window that can still become the key window, so typing works.
        # overrideredirect would also remove the frame, but such windows never get keyboard focus.
        try:
            win.attributes("-stylemask", ())  # borderless NSWindow that can still take typing
        except tk.TclError:
            win.overrideredirect(True)
    else:
        win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=BG)  # solid: see-through corners left artifacts on macOS


def make_panel(win: tk.Misc) -> None:
    """A normal, native window (real rounded corners, keyboard focus) that floats above others."""
    win.attributes("-topmost", True)
    if sys.platform == "darwin":
        try:
            win.attributes("-appearance", "darkaqua")
        except tk.TclError:
            pass
    win.configure(bg=BG)


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
    elif name == "plus":
        d = 7 * s
        c.create_line(cx - d, cy, cx + d, cy, **line)
        c.create_line(cx, cy - d, cx, cy + d, **line)
    elif name == "list":  # chats: three lines
        for dy in (-5, 0, 5):
            c.create_line(cx - 7 * s, cy + dy * s, cx + 7 * s, cy + dy * s, **line)
    elif name == "clip":  # paperclip
        c.create_line(cx + 4 * s, cy - 4 * s, cx + 4 * s, cy + 5 * s, **line)
        c.create_arc(cx - 4 * s, cy + 1 * s, cx + 4 * s, cy + 9 * s, start=180, extent=180, style="arc",
                     outline=color, width=w)
        c.create_line(cx - 4 * s, cy + 5 * s, cx - 4 * s, cy - 7 * s, **line)
        c.create_arc(cx - 4 * s, cy - 11 * s, cx + 4 * s, cy - 3 * s, start=0, extent=180, style="arc",
                     outline=color, width=w)
        c.create_line(cx + 4 * s, cy - 7 * s, cx + 4 * s, cy - 4 * s, **line)
    elif name == "trash":
        c.create_line(cx - 7 * s, cy - 6 * s, cx + 7 * s, cy - 6 * s, **line)
        c.create_line(cx - 5 * s, cy - 6 * s, cx - 4 * s, cy + 7 * s, cx + 4 * s, cy + 7 * s, cx + 5 * s,
                      cy - 6 * s, **line)
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
        self.canvas.configure(yscrollincrement=8)
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self._scroll(-3))  # X11
        self.canvas.bind_all("<Button-5>", lambda e: self._scroll(3))
        with contextlib.suppress(tk.TclError):  # Tk 9 sends trackpad scrolling as its own event
            self.canvas.bind_all("<TouchpadScroll>", self._touchpad)

    def _scroll(self, units: int):
        with contextlib.suppress(tk.TclError):
            if self.canvas.winfo_exists() and units:
                self.canvas.yview_scroll(units, "units")

    def _wheel(self, e):
        step = -e.delta if abs(e.delta) < 20 else -e.delta // 40  # mac: small deltas, Windows: 120s
        self._scroll(int(step) or (-1 if e.delta > 0 else 1))

    def _touchpad(self, e):
        with contextlib.suppress(tk.TclError):
            _, dy = self.canvas.tk.splitlist(self.canvas.tk.call("tk::PreciseScrollDeltas", e.delta))
            self._scroll(-int(float(dy) / 4))

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)

    def copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        if self.on_copied:
            self.on_copied()

    on_copied = None

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
        c.pack(side="right" if mine else "left", anchor="n")
        if who != "note":
            menu = tk.Menu(c, tearoff=0)
            menu.add_command(label="Копировать", command=lambda: self.copy(text))
            for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
                c.bind(seq, lambda e: menu.tk_popup(e.x_root, e.y_root))
            c.configure(cursor="hand2")
            c.bind("<Double-Button-1>", lambda e: self.copy(text))
        if who == "robot":
            link = tk.Label(row, text="Копировать", bg=BG, fg=MUTED, font=font(max(11, self.size - 4)),
                            cursor="hand2")
            link.pack(side="left", anchor="s", padx=8)
            link.bind("<ButtonRelease-1>", lambda e: (self.copy(text), link.config(text="Скопировано", fg=GREEN),
                                                      link.after(1500, lambda: link.winfo_exists() and
                                                                 link.config(text="Копировать", fg=MUTED))))
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)
