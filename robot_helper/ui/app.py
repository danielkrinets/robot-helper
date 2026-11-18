"""Floating, always-on-top helper with three sizes: mini bubble, docked widget, full window."""
from __future__ import annotations

import pathlib
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
from robot_helper.ui.widgets import (BG, BLUE, CARD, FG, FIELD, GREEN, MUTED, ORANGE, RED, Chat, Pill,
                                     card, check_row, clear_bg, font, icon_button, make_floating, rounded)

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
DOCKS = ["right", "left", "bottom_left", "top_right", "bottom"]
DOCK_NAMES = {"right": "Справа", "left": "Слева", "bottom_left": "Слева внизу",
              "top_right": "Справа вверху", "bottom": "Снизу"}
SIZES = {"widget": (380, 560), "full": (880, 720), "mini": (68, 68)}
RADIUS = 26
MARGIN, TOP, BOTTOM = 20, 44, 90  # keep clear of the menu bar / Dock / taskbar


def place(dock: str, w: int, h: int, sw: int, sh: int) -> tuple[int, int]:
    """Top-left corner of a w x h window docked at `dock` on a sw x sh screen."""
    return {
        "right": (sw - w - MARGIN, (sh - h) // 2),
        "left": (MARGIN, (sh - h) // 2),
        "bottom_left": (MARGIN, sh - h - BOTTOM),
        "top_right": (sw - w - MARGIN, TOP),
        "bottom": ((sw - w) // 2, sh - h - BOTTOM),
    }[dock]


class App:
    def __init__(self, root: tk.Tk, services=None):
        self.root, self.services = root, services or get_platform()
        self.services.prepare()
        self.agent: Agent | None = None
        self.executor: PyAutoGuiExecutor | None = None
        self._pending: tuple[threading.Event, list] | None = None
        self._running = self._working = False
        self.history: list[tuple[str, str]] = []
        self.last_said = ""
        self.chat = None
        self.dock = config.get_pref("dock", "right")
        if self.dock not in DOCKS:
            self.dock = "right"
        self.mode = "widget"
        root.title("Робот-помощник")
        root.withdraw()  # the borderless style only applies to a window that is not mapped yet
        make_floating(root)
        try:
            self.logo_big = tk.PhotoImage(file=str(ASSETS / "icon.png"))
            self.logo = tk.PhotoImage(file=str(ASSETS / "icon-64.png")).subsample(2, 2)
            root.iconphoto(True, self.logo_big)
        except tk.TclError:
            self.logo_big = self.logo = None
        root.bind("<Escape>", lambda e: self.stop())
        self.overlay = Overlay(root, self.services)
        self.stop_win = self._make_stop_window()
        self.overlay.windows += [self.stop_win, root]  # all hidden during screenshots
        self.services.watch_escape(self._on_global_escape)
        self.shell = tk.Canvas(root, bg=clear_bg(), highlightthickness=0)
        self.shell.pack(fill="both", expand=True)
        needs_setup = config.get_api_key() is None or bool(self.services.missing_permissions())
        self.set_mode("full" if needs_setup else "widget", setup=needs_setup)
        root.deiconify()

    # --- window shape and size ------------------------------------------------------
    def set_mode(self, mode: str, setup: bool = False):
        self.mode = mode
        w, h = SIZES[mode]
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = ((sw - w) // 2, (sh - h) // 2) if mode == "full" else place(self.dock, w, h, sw, sh)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.shell.unbind("<ButtonRelease-1>")
        self.shell.delete("all")
        for child in self.shell.winfo_children():
            child.destroy()
        self.chat = None
        if mode == "mini":
            self._build_mini(w, h)
            return
        rounded(self.shell, 1, 1, w - 1, h - 1, RADIUS, BG, outline=FIELD, width=1)
        pad = RADIUS // 2
        body = tk.Frame(self.shell, bg=BG)
        self.shell.create_window(pad, pad, window=body, anchor="nw", width=w - 2 * pad, height=h - 2 * pad)
        self._header(body)
        if setup:
            self._build_setup(body)
        else:
            self._build_chat(body)

    def _build_mini(self, w, h):
        ring = BLUE if self._running else FIELD
        self.shell.create_oval(2, 2, w - 2, h - 2, fill=BG, outline=ring, width=3)
        if self.logo is not None:
            self.shell.create_image(w // 2, h // 2, image=self.logo)
        self.shell.bind("<ButtonRelease-1>", lambda e: None if self._running else self.set_mode("widget"))

    def _drag(self, widget):
        def start(e):
            self._drag_from = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

        def move(e):
            dx, dy = self._drag_from
            self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

        widget.bind("<ButtonPress-1>", start)
        widget.bind("<B1-Motion>", move)

    def _header(self, body):
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", padx=6, pady=(4, 10))
        if self.logo is not None:
            logo = tk.Label(head, image=self.logo, bg=BG)
            logo.pack(side="left", padx=(0, 8))
            self._drag(logo)
        title = tk.Frame(head, bg=BG)
        title.pack(side="left")
        name = tk.Label(title, text="Помощник", bg=BG, fg=FG, font=font(16, "bold"))
        name.pack(anchor="w")
        row = tk.Frame(title, bg=BG)
        row.pack(anchor="w")
        self.dot = tk.Canvas(row, width=8, height=8, bg=BG, highlightthickness=0)
        self.dot_item = self.dot.create_oval(0, 0, 8, 8, fill=GREEN, outline=GREEN)
        self.dot.pack(side="left", padx=(0, 6))
        self.status = tk.Label(row, text="Готов", bg=BG, fg=MUTED, font=font(13))
        self.status.pack(side="left")
        for w in (head, title, name):
            self._drag(w)
        btns = tk.Frame(head, bg=BG)
        btns.pack(side="right")
        icon_button(btns, "close", self.root.destroy).pack(side="right", padx=(6, 0))
        if self.mode == "full":
            icon_button(btns, "shrink", lambda: self.set_mode("widget")).pack(side="right", padx=(6, 0))
        else:
            icon_button(btns, "expand", lambda: self.set_mode("full")).pack(side="right", padx=(6, 0))
            icon_button(btns, "dock", self.next_dock).pack(side="right", padx=(6, 0))
        icon_button(btns, "minus", lambda: self.set_mode("mini")).pack(side="right", padx=(6, 0))

    def set_status(self, text: str, color: str):
        if self.mode != "mini" and self.status.winfo_exists():
            self.status.config(text=text)
            self.dot.itemconfig(self.dot_item, fill=color, outline=color)

    def next_dock(self):
        self.dock = DOCKS[(DOCKS.index(self.dock) + 1) % len(DOCKS)]
        config.set_pref("dock", self.dock)
        self.set_mode("widget")
        self.set_status(DOCK_NAMES[self.dock], MUTED)

    # --- setup ----------------------------------------------------------------------
    def _build_setup(self, body):
        box = tk.Frame(body, bg=BG)
        box.pack(fill="both", expand=True, padx=24, pady=8)
        tk.Label(box, text="Настройка", bg=BG, fg=FG, font=font(28, "bold")).pack(anchor="w")
        tk.Label(box, text="Это делает тот, кто устанавливает помощника.", bg=BG, fg=MUTED,
                 font=font(15)).pack(anchor="w", pady=(2, 16))
        key_card = card(box)
        if config.get_api_key():
            check_row(key_card, "Ключ Claude API сохранён").pack(anchor="w")
        else:
            tk.Label(key_card, text="Ключ Claude API", bg=CARD, fg=FG, font=font(16, "bold")).pack(anchor="w")
            field = card(key_card, pad=10, radius=16, color=FIELD)
            entry = tk.Entry(field, show="•", font=font(16), bg=FIELD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0)
            entry.pack(fill="x")

            def save():
                if entry.get().strip():
                    config.set_api_key(entry.get())
                    self._after_setup()

            entry.bind("<Return>", lambda e: save())
            Pill(key_card, "Сохранить", BLUE, save, w=140, h=40, size=15).pack(anchor="w", pady=(4, 0))
            self.root.after(50, entry.focus_force)
        perm_card = card(box)
        missing = self.services.missing_permissions()
        if missing:
            tk.Label(perm_card, text="Нужны разрешения macOS", bg=CARD, fg=FG, font=font(16, "bold")).pack(anchor="w")
            tk.Label(perm_card, text="Системные настройки, «Конфиденциальность и безопасность». "
                     "Нажмите «Открыть» и включите RobotHelper в каждом разделе:", bg=CARD, fg=MUTED, font=font(14),
                     wraplength=700, justify="left").pack(anchor="w", pady=(4, 6))
            for item in [m.split("→")[-1].strip() for m in missing] + ["Мониторинг ввода"]:
                row = tk.Frame(perm_card, bg=CARD)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=item, bg=CARD, fg=FG, font=font(15)).pack(side="left", padx=(4, 0))
                Pill(row, "Открыть", BLUE, lambda n=item: self.services.open_settings(n),
                     w=110, h=34, size=14).pack(side="right")
            tk.Label(perm_card, text="Потом закройте программу и откройте снова.", bg=CARD, fg=MUTED,
                     font=font(14)).pack(anchor="w", pady=(6, 8))
            Pill(perm_card, "Проверить снова", FIELD, self._after_setup, w=180, h=40, size=15).pack(anchor="w")
        else:
            check_row(perm_card, "Разрешения выданы").pack(anchor="w")

    def _after_setup(self):
        ready = bool(config.get_api_key()) and not self.services.missing_permissions()
        self.set_mode("widget" if ready else "full", setup=not ready)

    # --- chat -----------------------------------------------------------------------
    def _build_chat(self, body):
        full = self.mode == "full"
        size, h = (18, 56) if full else (15, 46)
        bar = tk.Frame(body, bg=BG)
        bar.pack(side="bottom", fill="x", pady=(8, 2))
        self.chat = Chat(body, wrap=560 if full else 250, text_size=size)
        self.chat.pack(fill="both", expand=True)
        for text, who in self.history:
            self.chat.add(text, who)
        if not self.history:
            self._post(T["greeting"] + " Напишите, что сделать.", "robot")
        send = Pill(bar, color=BLUE, command=self.submit, w=h, h=h, icon="send", icon_scale=h / 56)
        send.pack(side="right", padx=(6, 0))
        Pill(bar, color=FIELD, command=self.dictate, w=h, h=h, icon="mic", icon_scale=h / 56,
             fg=FG).pack(side="right", padx=(8, 0))
        field = tk.Canvas(bar, bg=BG, highlightthickness=0, height=h, width=10)
        field.pack(side="left", fill="x", expand=True)
        self.entry = tk.Text(field, font=font(size), height=1, bg=CARD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0, wrap="none")
        holder = field.create_window(h // 2, h // 2, window=self.entry, anchor="w")

        def layout(e):
            field.delete("bg")
            rounded(field, 0, 0, e.width, e.height, e.height / 2, CARD, tags="bg")
            field.tag_lower("bg")
            field.itemconfigure(holder, width=e.width - h)

        field.bind("<Configure>", layout)
        self.entry.bind("<Return>", lambda e: (self.submit(), "break")[1])
        self._placeholder(self.entry, "Что сделать?" if not full else "Напишите, что сделать…")

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
        """Main thread only."""
        self.history.append((text, who))
        if self.chat is not None:
            self.chat.add(text, who)

    def _make_stop_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        make_floating(win)
        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"200x64+{(w - 200) // 2}+{h - 64 - BOTTOM}")
        Pill(win, T["stop"], RED, self.stop, w=200, h=64, size=22).pack()
        win.withdraw()
        return win

    # --- actions --------------------------------------------------------------------
    def dictate(self):
        self.entry.focus_force()
        self._post(self.services.dictation_hint(), "note")
        self.services.start_dictation()

    def submit(self):
        if self._running or getattr(self.entry, "is_hint", False):
            return
        task = self.entry.get("1.0", "end").strip()
        if not task:
            return
        key = config.get_api_key()
        if not key:
            self.set_mode("full", setup=True)
            return
        self.entry.delete("1.0", "end")
        self._post(task, "me")
        client = anthropic.Anthropic(api_key=key)
        hooks = Hooks(on_state=self.on_state, on_say=self.say, ask_permission=self.ask,
                      hand_over=self.hand_over, on_pointer=self.overlay.move_hand)
        self.agent = Agent(client, None, hooks)
        self.executor = PyAutoGuiExecutor(hide_for_screenshot=self.overlay.hidden_for_screenshot,
                                          on_pointer=self.overlay.move_hand, stop_event=self.agent._stop)
        self.agent.executor = self.executor
        self._running, self.last_said, self._working = True, "", False
        self._mode_before = self.mode
        self.set_status("Думаю", BLUE)
        threading.Thread(target=self._run, args=(task,), daemon=True).start()

    def on_state(self, state: State):
        """Agent thread. The first computer action shrinks the helper out of the robot's way."""
        if state == State.WORKING and not self._working:
            self._working = True
            done = threading.Event()

            def enter():
                self.set_mode("mini")
                self.overlay.show(T["working"])
                self.stop_win.deiconify()
                self.root.update_idletasks()
                done.set()

            self.root.after(0, enter)
            done.wait(timeout=2)

    def _run(self, task: str):
        try:
            state = self.agent.run(task)
        except Exception:  # never show a traceback to the person
            state = State.ERROR
            self.last_said = T["try_again"]
        self.root.after(0, lambda: self._finished(state))

    def _finished(self, state: State):
        self._running = False
        if self._working:
            self.overlay.hide()
            self.stop_win.withdraw()
            self.set_mode(self._mode_before if self._mode_before != "mini" else "widget")
        final = self.last_said or {State.DONE: T["done"], State.STOPPED: T["stopped"]}.get(state, T["try_again"])
        if state == State.STOPPED and self.last_said not in (T["stopped"], T["too_many_steps"]):
            final = T["stopped"]
        self._post(final, "robot")
        if self._working:
            self.services.speak(final)
        self.set_status(*{State.DONE: ("Готов", GREEN), State.STOPPED: ("Остановлен", ORANGE),
                          State.ERROR: ("Не получилось", RED)}.get(state, ("Готов", GREEN)))

    def _on_global_escape(self):
        # pynput also sees the Esc that the robot itself presses; ignore those
        if self.executor is not None and self.executor.injecting:
            return
        self.root.after(0, self.stop)

    def stop(self):
        if self.agent and self._running:
            self.agent.stop()
            self.overlay.set_label(T["stopped"])
        self._resolve(False)

    # --- hooks (called from the agent thread) ---------------------------------------
    def say(self, text: str):
        # step narration goes to the overlay caption; the chat gets the final answer only
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
            win = tk.Toplevel(self.root)
            make_floating(win)
            w, h = 520, 230
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
            c = tk.Canvas(win, bg=clear_bg(), highlightthickness=0, width=w, height=h)
            c.pack()
            rounded(c, 1, 1, w - 1, h - 1, RADIUS, BG, outline=FIELD, width=1)
            c.create_text(w // 2, 76, text=text, fill=FG, font=font(20, "bold"), width=w - 60, justify="center")
            row = tk.Frame(c, bg=BG)
            for label, color, value in buttons:
                Pill(row, label, color, lambda v=value: self._resolve(v), w=150, h=52, size=18).pack(side="left", padx=8)
            c.create_window(w // 2, h - 56, window=row)
            self._dialog_win = win

        self.root.after(0, build)
        event.wait()
        self._pending = None
        self.root.after(0, lambda: self._dialog_win.destroy())
        if hide_overlay and not (self.agent and self.agent.stopped):
            self.overlay.show(T["working"])
        return box[0]

    def ask(self, question: str) -> bool:
        self.services.speak(question)
        return bool(self._dialog(question, [(T["ask_yes"], GREEN, True), (T["ask_no"], RED, False)], False))

    def hand_over(self, reason: str) -> bool:
        self.services.speak(reason)
        return bool(self._dialog(T["hand_over"] + " " + reason,
                                 [(T["ready_button"], GREEN, True), (T["stop"], RED, False)], True))


def main():
    root = tk.Tk()
    App(root)
    if "--smoke" in sys.argv:  # build the UI and exit: used by CI and manual checks
        root.after(1500, root.destroy)
    root.mainloop()
