"""Main window: dark, Apple-like chat. History stays across tasks; a big STOP while the robot works."""
from __future__ import annotations

import sys
import threading
import tkinter as tk

import anthropic

from robot_helper.core import config
from robot_helper.core.agent import Agent, Hooks, State
from robot_helper.core.executor import PyAutoGuiExecutor
from robot_helper.core.texts import T
from robot_helper.platform_.base import get_platform
from robot_helper.ui.overlay import Overlay

# Apple dark-mode system colors
BG, CARD, FIELD = "#1C1C1E", "#2C2C2E", "#3A3A3C"
FG, MUTED = "#F2F2F7", "#8E8E93"
BLUE, RED, GREEN = "#0A84FF", "#FF453A", "#30D158"
FAMILY = ".AppleSystemUIFont" if sys.platform == "darwin" else "Segoe UI"


ORANGE = "#FF9F0A"


def font(size: int, weight: str = "normal"):
    return (FAMILY, size, weight)


def rounded(canvas: tk.Canvas, x0, y0, x1, y1, r, color):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, fill=color, outline=color)


def draw_icon(c: tk.Canvas, name: str, cx: float, cy: float, color: str) -> None:
    """Simple line icons drawn with the canvas (no emoji)."""
    if name == "mic":
        rounded(c, cx - 6, cy - 14, cx + 6, cy + 4, 6, color)
        c.create_arc(cx - 11, cy - 10, cx + 11, cy + 10, start=200, extent=140, style="arc",
                     outline=color, width=2.5)
        c.create_line(cx, cy + 10, cx, cy + 15, fill=color, width=2.5, capstyle="round")
    elif name == "send":
        c.create_line(cx, cy + 10, cx, cy - 9, fill=color, width=3, capstyle="round")
        c.create_line(cx - 8, cy - 2, cx, cy - 10, cx + 8, cy - 2, fill=color, width=3,
                      capstyle="round", joinstyle="round")
    elif name == "stop":
        rounded(c, cx - 9, cy - 9, cx + 9, cy + 9, 4, color)
    elif name == "check":
        c.create_line(cx - 7, cy, cx - 2, cy + 5, cx + 8, cy - 6, fill=color, width=3,
                      capstyle="round", joinstyle="round")


def shade(color: str, k: float) -> str:
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(min(255, int(v * k)) for v in rgb)


class Pill(tk.Canvas):
    """Rounded, flat button drawn on a canvas (tk.Button ignores colors on macOS)."""

    def __init__(self, parent, text, color, command, w=160, h=52, size=18, fg="white", icon=None):
        super().__init__(parent, width=w, height=h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.color, self.command, self.w, self.h = color, command, w, h
        self.shape = [rounded(self, 0, 0, w, h, h // 2, color)]
        if icon:
            draw_icon(self, icon, w / 2, h / 2, fg)
            self.label = None
        else:
            self.label = self.create_text(w // 2, h // 2, text=text, fill=fg, font=font(size, "bold"))
        # feedback on press (instant), action on release only if the pointer is still inside
        self.bind("<ButtonPress-1>", lambda e: self._tint(0.75))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._tint(1.12))
        self.bind("<Leave>", lambda e: self._tint(1.0))

    def _release(self, e):
        self._tint(1.0)
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.command()

    def _tint(self, k: float):
        c = shade(self.color, k)
        for item in self.shape:
            self.itemconfig(item, fill=c, outline=c)

    def set_text(self, text: str):
        self.itemconfig(self.label, text=text)


def card(parent, pad=20, radius=28, color=None) -> tk.Frame:
    """A rounded container; returns the inner frame to pack content into."""
    color = color or CARD
    outer = tk.Canvas(parent, bg=parent["bg"], highlightthickness=0, height=10)
    outer.pack(fill="x", pady=8)
    inner = tk.Frame(outer, bg=color)
    win = outer.create_window(pad, pad, window=inner, anchor="nw")

    def layout(_=None):
        outer.update_idletasks()
        w = outer.winfo_width()
        h = inner.winfo_reqheight() + 2 * pad
        outer.configure(height=h)
        outer.itemconfigure(win, width=max(10, w - 2 * pad))
        outer.delete("bg")
        item = rounded(outer, 0, 0, w, h, radius, color)
        outer.itemconfigure(item, tags="bg")
        outer.tag_lower("bg")

    outer.bind("<Configure>", layout)
    inner.bind("<Configure>", layout)
    return inner


def check_row(parent, text: str):
    row = tk.Frame(parent, bg=parent["bg"])
    c = tk.Canvas(row, width=24, height=24, bg=parent["bg"], highlightthickness=0)
    draw_icon(c, "check", 12, 12, GREEN)
    c.pack(side="left", padx=(0, 10))
    tk.Label(row, text=text, bg=parent["bg"], fg=GREEN, font=font(18)).pack(side="left")
    return row


class Chat(tk.Frame):
    """Scrollable list of message bubbles."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // abs(e.delta or 1)), "units"))

    def add(self, text: str, who: str = "robot"):
        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill="x", padx=20, pady=6)
        mine = who == "me"
        color = {"me": BLUE, "robot": CARD, "note": BG}[who]
        c = tk.Canvas(row, bg=BG, highlightthickness=0)
        t = c.create_text(16, 10, text=text, anchor="nw", width=540, font=font(19),
                          fill=MUTED if who == "note" else FG)
        x0, y0, x1, y1 = c.bbox(t)
        w, h = x1 + 16, y1 + 10
        c.configure(width=w, height=h)
        if who != "note":
            c.tag_lower(rounded(c, 0, 0, w, h, 24, color))
        c.pack(side="right" if mine else "left")
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


class App:
    def __init__(self, root: tk.Tk, services=None):
        self.root, self.services = root, services or get_platform()
        self.services.prepare()
        self.agent: Agent | None = None
        self.executor: PyAutoGuiExecutor | None = None
        self._pending: tuple[threading.Event, list] | None = None
        self.history: list[tuple[str, str]] = []
        root.title("Робот-помощник")
        root.configure(bg=BG)
        root.geometry("820x760")
        root.minsize(620, 520)
        root.bind("<Escape>", lambda e: self.stop())
        self.overlay = Overlay(root, self.services)
        self.stop_win = self._make_stop_window()
        self.overlay.windows.append(self.stop_win)  # hidden with the overlay during screenshots
        self.services.watch_escape(self._on_global_escape)
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(expand=True, fill="both")
        self.chat: Chat | None = None
        if config.get_api_key() is None or self.services.missing_permissions():
            self.show_setup()
        else:
            self.show_main()

    # --- screens -------------------------------------------------------------------
    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.chat = None

    def _label(self, parent, text, size=18, color=FG, weight="normal", **kw):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color, font=font(size, weight),
                        justify="left", **kw)

    def show_setup(self):
        self._clear()
        box = tk.Frame(self.body, bg=BG)
        box.pack(expand=True, padx=48, pady=40, fill="x")
        self._label(box, "Настройка", 30, weight="bold").pack(anchor="w")
        self._label(box, "Это делает тот, кто устанавливает помощника.", 16, MUTED).pack(anchor="w", pady=(4, 24))

        key_card = card(box)
        if config.get_api_key():
            check_row(key_card, "Ключ Claude API сохранён").pack(anchor="w")
        else:
            self._label(key_card, "Ключ Claude API", 18, weight="bold").pack(anchor="w")
            field = card(key_card, pad=12, radius=20, color=FIELD)
            entry = tk.Entry(field, show="•", font=font(18), bg=FIELD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0)
            entry.pack(fill="x")

            def save():
                if entry.get().strip():
                    config.set_api_key(entry.get())
                    self._after_setup()

            entry.bind("<Return>", lambda e: save())
            Pill(key_card, "Сохранить", BLUE, save, w=150, h=44, size=16).pack(anchor="w")
            entry.focus_set()

        missing = self.services.missing_permissions()
        perm_card = card(box)
        if missing:
            self._label(perm_card, "Нужны разрешения macOS", 18, weight="bold").pack(anchor="w")
            self._label(perm_card, "Откройте Системные настройки, раздел «Конфиденциальность и безопасность», "
                        "и включите эту программу в разделах:", 16, MUTED, wraplength=620).pack(anchor="w", pady=(6, 8))
            for item in missing:
                self._label(perm_card, item.split("→")[-1].strip(), 17).pack(anchor="w", padx=(12, 0))
            self._label(perm_card, "А также «Мониторинг ввода» — для клавиши Esc.\n"
                        "После этого закройте программу и откройте снова.", 15, MUTED).pack(anchor="w", pady=(8, 10))
            Pill(perm_card, "Проверить снова", FIELD, self._after_setup, w=200, h=44, size=16).pack(anchor="w")
        else:
            check_row(perm_card, "Разрешения выданы").pack(anchor="w")

    def _after_setup(self):
        if config.get_api_key() and not self.services.missing_permissions():
            self.show_main()
        else:
            self.show_setup()

    def show_main(self):
        self._clear()
        header = tk.Frame(self.body, bg=BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        self._label(header, "Робот-помощник", 22, weight="bold").pack(side="left")
        status = tk.Frame(header, bg=BG)
        status.pack(side="right")
        self.dot = tk.Canvas(status, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot_item = self.dot.create_oval(1, 1, 9, 9, fill=GREEN, outline=GREEN)
        self.dot.pack(side="left", padx=(0, 8))
        self.status = self._label(status, "Готов", 15, MUTED)
        self.status.pack(side="left")
        tk.Frame(self.body, bg=CARD, height=1).pack(fill="x")

        self.chat = Chat(self.body)
        self.chat.pack(fill="both", expand=True)
        for text, who in self.history:
            self.chat.add(text, who)
        if not self.history:
            self._post(T["greeting"] + " Напишите, что сделать.", "robot")

        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", padx=20, pady=16)
        field = tk.Canvas(bar, bg=BG, highlightthickness=0, height=64)
        field.pack(side="left", fill="x", expand=True)
        self.entry = tk.Text(field, font=font(19), height=2, bg=CARD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0, wrap="word", padx=4, pady=4)
        holder = field.create_window(16, 8, window=self.entry, anchor="nw")

        def layout(e):
            field.delete("bg")
            field.tag_lower(rounded(field, 0, 0, e.width, e.height, e.height // 2, CARD))
            field.addtag_withtag("bg", "all")
            field.dtag(holder, "bg")
            field.itemconfigure(holder, width=e.width - 32, height=e.height - 16)

        field.bind("<Configure>", layout)
        self._placeholder(self.entry, "Напишите, что сделать…")
        self.entry.bind("<Return>", lambda e: (self.submit(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: None)
        Pill(bar, "", FIELD, self.dictate, w=56, h=56, icon="mic").pack(side="left", padx=(12, 0))
        Pill(bar, "", BLUE, self.submit, w=56, h=56, icon="send").pack(side="left", padx=(8, 0))
        self.entry.focus_set()

    @staticmethod
    def _placeholder(entry: tk.Text, hint: str):
        def show(_=None):
            if not entry.get("1.0", "end").strip():
                entry.delete("1.0", "end")
                entry.insert("1.0", hint)
                entry.config(fg=MUTED)
                entry.is_hint = True

        def hide(_=None):
            if getattr(entry, "is_hint", False):
                entry.delete("1.0", "end")
                entry.config(fg=FG)
                entry.is_hint = False

        entry.bind("<FocusIn>", hide, add="+")
        entry.bind("<FocusOut>", show, add="+")
        show()

    def _post(self, text: str, who: str):
        """Add a message to history and to the chat if it is on screen. Main thread only."""
        self.history.append((text, who))
        if self.chat is not None:
            self.chat.add(text, who)

    def _make_stop_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root, bg=BG)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"240x96+{w - 270}+{h - 160}")
        Pill(win, T["stop"], RED, self.stop, w=240, h=96, size=28).pack()
        win.withdraw()
        return win

    # --- actions -------------------------------------------------------------------
    def dictate(self):
        self.entry.focus_set()
        self._post(self.services.dictation_hint(), "note")
        self.services.start_dictation()

    def submit(self):
        if getattr(self.entry, "is_hint", False):
            return
        task = self.entry.get("1.0", "end").strip()
        if not task or (self.agent and not self.agent.stopped and self._running):
            return
        key = config.get_api_key()
        if not key:
            self.show_setup()
            return
        self.entry.delete("1.0", "end")
        self._post(task, "me")
        client = anthropic.Anthropic(api_key=key)
        hooks = Hooks(on_state=lambda s: None, on_say=self.say, ask_permission=self.ask,
                      hand_over=self.hand_over, on_pointer=self.overlay.move_hand)
        self.agent = Agent(client, None, hooks)
        self.executor = PyAutoGuiExecutor(hide_for_screenshot=self.overlay.hidden_for_screenshot,
                                          on_pointer=self.overlay.move_hand, stop_event=self.agent._stop)
        self.agent.executor = self.executor
        self._running = True
        self.last_said = ""
        self.set_status("Работаю", BLUE)
        self.root.update()
        self.root.withdraw()  # the robot needs the screen; the chat comes back when it finishes
        self.overlay.show(T["working"])
        self.stop_win.deiconify()
        threading.Thread(target=self._run, args=(task,), daemon=True).start()

    _running = False

    def _run(self, task: str):
        try:
            state = self.agent.run(task)
        except Exception:  # never show a traceback to the person
            state = State.ERROR
            self.last_said = T["try_again"]
        self.root.after(0, lambda: self._finished(state))

    def _finished(self, state: State):
        self._running = False
        self.overlay.hide()
        self.stop_win.withdraw()
        self.root.deiconify()
        self.root.lift()
        self.set_status(*{State.DONE: ("Готово", GREEN), State.STOPPED: ("Остановлен", ORANGE),
                          State.ERROR: ("Не получилось", RED)}.get(state, ("Готов", GREEN)))
        final = self.last_said or {State.DONE: T["done"], State.STOPPED: T["stopped"]}.get(state, T["try_again"])
        if state == State.STOPPED and self.last_said not in (T["stopped"], T["too_many_steps"]):
            final = T["stopped"]
        self._post(final, "robot")
        self.services.speak(final)
        self.entry.focus_set()

    def _on_global_escape(self):
        # pynput also sees the Esc that the robot itself presses; ignore those
        if self.executor is not None and self.executor.injecting:
            return
        self.root.after(0, self.stop)

    def stop(self):
        if self.agent:
            self.agent.stop()
            self.overlay.set_label(T["stopped"])  # show at once; the thread finishes after
        self._resolve(False)

    # --- hooks (called from the agent thread) --------------------------------------
    def say(self, text: str):
        # step narration only goes to the overlay caption; the chat gets the final answer
        self.last_said = text
        self.overlay.set_label(text)

    def _resolve(self, value):
        if self._pending:
            event, box = self._pending
            box.append(value)
            event.set()

    def _dialog(self, text: str, buttons: list[tuple[str, str, object]], hide_overlay: bool) -> object:
        event, box = threading.Event(), []
        self._pending = (event, box)
        if self.agent is not None and self.agent.stopped:  # STOP raced the dialog
            self._pending = None
            return False

        def build():
            if hide_overlay:
                self.overlay.hide()
                self.stop_win.deiconify()  # keep STOP reachable while the person works
            win = tk.Toplevel(self.root, bg=BG)
            win.attributes("-topmost", True)
            win.title("Робот-помощник")
            tk.Label(win, text=text, font=font(24, "bold"), bg=BG, fg=FG, wraplength=560,
                     justify="center").pack(padx=40, pady=(32, 24))
            row = tk.Frame(win, bg=BG)
            row.pack(pady=(0, 32))
            for label, color, value in buttons:
                Pill(row, label, color, lambda v=value: self._resolve(v), w=170, h=64, size=22).pack(side="left", padx=12)
            win.protocol("WM_DELETE_WINDOW", lambda: self._resolve(False))
            self._dialog_win = win

        self.root.after(0, build)
        event.wait()
        self._pending = None
        self.root.after(0, lambda: self._dialog_win.destroy())
        if hide_overlay and not (self.agent and self.agent.stopped):
            self.overlay.show(T["working"])
        return box[0]

    def ask(self, question: str) -> bool:
        self.root.after(0, lambda: self._post(question, "robot"))
        self.services.speak(question)
        return bool(self._dialog(question, [(T["ask_yes"], GREEN, True), (T["ask_no"], RED, False)], False))

    def hand_over(self, reason: str) -> bool:
        self.root.after(0, lambda: self._post(reason, "robot"))
        self.services.speak(reason)
        return bool(self._dialog(T["hand_over"] + "\n" + reason,
                                 [(T["ready_button"], GREEN, True), (T["stop"], RED, False)], True))


def main():
    root = tk.Tk()
    App(root)
    if "--smoke" in sys.argv:  # build the UI and exit: used by CI and manual checks
        root.after(1500, root.destroy)
    root.mainloop()


def _set_status(self, text: str, color: str) -> None:
    self.status.config(text=text)
    self.dot.itemconfig(self.dot_item, fill=color, outline=color)


App.set_status = _set_status
