"""Helper window: a native always-on-top panel (docked or full) plus a tiny bubble while minimized."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

import anthropic

from robot_helper.core import config
from robot_helper.core.agent import Agent, Hooks, State
from robot_helper.core.attachments import to_block
from robot_helper.core.chats import Chats
from robot_helper.core.executor import PyAutoGuiExecutor
from robot_helper.core.texts import T
from robot_helper.platform_.base import get_platform
from robot_helper.ui.overlay import Overlay
from robot_helper.ui.widgets import (BG, BLUE, CARD, FG, FIELD, GREEN, MUTED, ORANGE, RED, Chat, Pill,
                                     card, check_row, edit_menu, font, install_shortcuts, px, set_scale, icon_button, make_floating, make_panel, rounded)

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
DOCKS = ["right", "left", "bottom_left", "top_right", "bottom"]
DOCK_NAMES = {"right": "Справа", "left": "Слева", "bottom_left": "Слева внизу",
              "top_right": "Справа вверху", "bottom": "Снизу"}
SIZES = {"widget": (400, 580), "full": (1000, 720)}
MINI = 64
MARGIN, TOP, BOTTOM = 20, 60, 90  # keep clear of the menu bar / Dock / taskbar
NEED_PERMS = "Чтобы я мог работать на компьютере, нужно один раз дать разрешения."


def place(dock: str, w: int, h: int, sw: int, sh: int) -> tuple[int, int]:
    """Top-left corner of a w x h window docked at `dock` on a sw x sh screen."""
    return {
        "right": (sw - w - px(MARGIN), (sh - h) // 2),
        "left": (px(MARGIN), (sh - h) // 2),
        "bottom_left": (px(MARGIN), sh - h - px(BOTTOM)),
        "top_right": (sw - w - px(MARGIN), px(TOP)),
        "bottom": ((sw - w) // 2, sh - h - px(BOTTOM)),
    }[dock]


def relaunch() -> None:
    """Start a fresh copy of the app (macOS applies screen-recording permission only after a restart)."""
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        bundle = pathlib.Path(sys.executable).parents[2]
        subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open -n "{bundle}"'])
    else:
        subprocess.Popen([sys.executable, "-m", "robot_helper"], cwd=os.getcwd())


class App:
    def __init__(self, root: tk.Tk, services=None):
        self.root, self.services = root, services or get_platform()
        self.services.prepare()
        self.agent: Agent | None = None
        self.executor: PyAutoGuiExecutor | None = None
        self._pending: tuple[threading.Event, list] | None = None
        self._running = self._working = False
        self.last_said = ""
        self.chat = None
        self.chats = Chats()
        self.files: list[str] = []  # attached, waiting to be sent
        self.show_list = False  # widget mode: chat list instead of the conversation
        self.dock = config.get_pref("dock", "right")
        if self.dock not in DOCKS:
            self.dock = "right"
        self.mode = "widget"
        root.title("Робот-помощник")
        make_panel(root)
        root.resizable(True, True)
        root.minsize(px(340), px(420))
        root.protocol("WM_DELETE_WINDOW", self.quit)
        try:
            self.logo_big = tk.PhotoImage(file=str(ASSETS / "icon.png"))
            self.logo = tk.PhotoImage(file=str(ASSETS / "icon-64.png")).subsample(2, 2)
            root.iconphoto(True, self.logo_big)
        except tk.TclError:
            self.logo_big = self.logo = None
        root.bind("<Escape>", lambda e: self.stop())
        install_shortcuts(root)
        self.overlay = Overlay(root, self.services)
        self.stop_win = self._make_stop_window()
        self.mini = self._make_mini()
        self.overlay.windows.append(self.stop_win)
        self.overlay.screenshot_only += [root, self.mini]  # hidden for screenshots, never withdrawn
        self.services.watch_escape(self._on_global_escape)
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=px(14), pady=(px(6), px(14)))
        needs_setup = config.get_api_key() is None
        self.set_mode("full" if needs_setup else "widget", setup=needs_setup)
        pending = config.get_pref("pending_task", "")
        if pending and not needs_setup and not self.services.missing_permissions():
            config.set_pref("pending_task", "")
            root.after(800, lambda: self.submit(pending))  # finish what was asked before the restart

    # --- windows --------------------------------------------------------------------
    def set_mode(self, mode: str, setup: bool = False):
        if mode == "mini":
            self.mode = "mini"
            self.root.withdraw()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y = place(self.dock, px(MINI), px(MINI), sw, sh)
            self.mini.geometry(f"{px(MINI)}x{px(MINI)}+{x}+{y}")
            self._paint_mini()
            self.mini.deiconify()
            return
        self.mini.withdraw()
        self.mode = mode
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(px(SIZES[mode][0]), sw - px(40)), min(px(SIZES[mode][1]), sh - px(TOP + BOTTOM))
        x, y = ((sw - w) // 2, (sh - h) // 2) if mode == "full" else place(self.dock, w, h, sw, sh)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        for child in self.body.winfo_children():
            child.destroy()
        self.chat = None
        self._header(self.body)
        if setup:
            self._build_setup(self.body)
        else:
            self._build_chat(self.body)
        self.root.deiconify()
        self.root.lift()

    def _make_mini(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        make_floating(win)
        self.mini_canvas = tk.Canvas(win, width=px(MINI), height=px(MINI), bg=BG, highlightthickness=0, cursor="hand2")
        self.mini_canvas.pack()
        self.mini_canvas.bind("<ButtonRelease-1>", lambda e: None if self._running else self.set_mode("widget"))
        win.withdraw()
        return win

    def _paint_mini(self):
        c = self.mini_canvas
        c.delete("all")
        m = px(MINI)
        c.create_rectangle(0, 0, m, m, fill=BG, outline=BLUE if self._running else FIELD, width=px(3))
        if self.logo is not None:
            c.create_image(m // 2, m // 2, image=self.logo)

    def _header(self, body):
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", pady=(0, 10))
        if self.logo is not None:
            tk.Label(head, image=self.logo, bg=BG).pack(side="left", padx=(0, 8))
        title = tk.Frame(head, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Помощник", bg=BG, fg=FG, font=font(16, "bold")).pack(anchor="w")
        row = tk.Frame(title, bg=BG)
        row.pack(anchor="w")
        self.dot = tk.Canvas(row, width=px(8), height=px(8), bg=BG, highlightthickness=0)
        self.dot_item = self.dot.create_oval(0, 0, px(8), px(8), fill=GREEN, outline=GREEN)
        self.dot.pack(side="left", padx=(0, 6))
        self.status = tk.Label(row, text="Готов", bg=BG, fg=MUTED, font=font(13))
        self.status.pack(side="left")
        btns = tk.Frame(head, bg=BG)
        btns.pack(side="right")
        if self.mode == "full":
            icon_button(btns, "shrink", lambda: self.set_mode("widget")).pack(side="right", padx=(6, 0))
        else:
            icon_button(btns, "expand", lambda: self.set_mode("full")).pack(side="right", padx=(6, 0))
            icon_button(btns, "dock", self.next_dock).pack(side="right", padx=(6, 0))
        icon_button(btns, "minus", lambda: self.set_mode("mini")).pack(side="right", padx=(6, 0))
        icon_button(btns, "plus", self.new_chat).pack(side="right", padx=(6, 0))
        if self.mode != "full":
            icon_button(btns, "list", self.toggle_list).pack(side="right", padx=(6, 0))

    def set_status(self, text: str, color: str):
        if self.chat is not None and self.status.winfo_exists():
            self.status.config(text=text)
            self.dot.itemconfig(self.dot_item, fill=color, outline=color)

    def next_dock(self):
        self.dock = DOCKS[(DOCKS.index(self.dock) + 1) % len(DOCKS)]
        config.set_pref("dock", self.dock)
        self.set_mode("widget")
        self.set_status(DOCK_NAMES[self.dock], MUTED)

    def quit(self):
        if self.agent:
            self.agent.stop()
        self.root.destroy()

    # --- setup ----------------------------------------------------------------------
    def _build_setup(self, body):
        box = tk.Frame(body, bg=BG)
        box.pack(fill="both", expand=True, padx=16)
        tk.Label(box, text="Настройка", bg=BG, fg=FG, font=font(26, "bold")).pack(anchor="w")
        tk.Label(box, text="Это делает тот, кто устанавливает помощника.", bg=BG, fg=MUTED,
                 font=font(15)).pack(anchor="w", pady=(2, 14))
        key_card = card(box)
        if config.get_api_key() and not getattr(self, "replace_key", False):
            row = tk.Frame(key_card, bg=CARD)
            row.pack(fill="x")
            check_row(row, "Ключ Claude API сохранён").pack(side="left")

            def change():
                self.replace_key = True
                self.set_mode("full", setup=True)

            Pill(row, "Сменить", FIELD, change, w=110, h=34, size=14).pack(side="right")
        else:
            title = "Ключ не подошёл. Вставьте новый" if getattr(self, "bad_key", False) else "Ключ Claude API"
            tk.Label(key_card, text=title, bg=CARD, fg=RED if getattr(self, "bad_key", False) else FG,
                     font=font(16, "bold")).pack(anchor="w")
            field = card(key_card, pad=10, radius=14, color=FIELD)
            entry = tk.Entry(field, show="•", font=font(16), bg=FIELD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0)
            entry.pack(fill="x")

            def save():
                if entry.get().strip():
                    config.set_api_key(entry.get())
                    self.replace_key = self.bad_key = False
                    self._after_setup()

            entry.bind("<Return>", lambda e: save())
            Pill(key_card, "Сохранить", BLUE, save, w=140, h=40, size=15).pack(anchor="w", pady=(4, 0))
            self.root.after(80, entry.focus_force)
        if config.get_api_key() and not self.services.missing_permissions():
            Pill(box, "Назад к чату", FIELD, lambda: (setattr(self, "replace_key", False),
                                                      self.set_mode("widget")), w=150, h=40, size=15).pack(anchor="w")
        missing = self.services.missing_permissions()
        if not missing:
            return
        # ask macOS right away: its own prompt adds RobotHelper to the list, so no "+" is needed
        request = getattr(self.services, "_request", None)
        if request and not getattr(self, "_asked_perms", False):
            self._asked_perms = True
            for name in [m.split("→")[-1].strip() for m in missing]:
                self.root.after(300, lambda n=name: request(n))
        perm_card = card(box)
        tk.Label(perm_card, text="Разрешения macOS", bg=CARD, fg=FG, font=font(16, "bold")).pack(anchor="w")
        tk.Label(perm_card, text="Нажмите «Открыть» и включите RobotHelper в каждом разделе.", bg=CARD,
                 fg=MUTED, font=font(14), wraplength=px(700), justify="left").pack(anchor="w", pady=(4, 8))
        for item in [m.split("→")[-1].strip() for m in missing] + ["Мониторинг ввода"]:
            row = tk.Frame(perm_card, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=item, bg=CARD, fg=FG, font=font(15)).pack(side="left", padx=(4, 0))
            Pill(row, "Открыть", BLUE, lambda n=item: self.services.open_settings(n),
                 w=110, h=34, size=14).pack(side="right")
        tk.Label(perm_card, text="Когда всё включено, нажмите «Перезапустить» — я продолжу с того места.",
                 bg=CARD, fg=MUTED, font=font(14), wraplength=px(700), justify="left").pack(anchor="w", pady=(10, 8))
        row = tk.Frame(perm_card, bg=CARD)
        row.pack(anchor="w")
        Pill(row, "Перезапустить", GREEN, self.restart, w=170, h=40, size=15).pack(side="left")
        Pill(row, "Назад к чату", FIELD, lambda: self.set_mode("widget"), w=150, h=40, size=15).pack(side="left", padx=8)

    def _after_setup(self):
        ready = bool(config.get_api_key())
        self.set_mode("widget" if ready else "full", setup=not ready)

    def restart(self):
        relaunch()
        self.root.after(200, self.root.destroy)

    # --- chat -----------------------------------------------------------------------
    @property
    def history(self) -> list[tuple[str, str]]:
        return self.chats.history

    def new_chat(self):
        if self._running:
            return
        self.chats.new()
        self.show_list = False
        self.files = []
        self.set_mode(self.mode if self.mode in SIZES else "widget")

    def open_chat(self, chat_id: str):
        if self._running:
            return
        self.chats.switch(chat_id)
        self.show_list = False
        self.set_mode(self.mode if self.mode in SIZES else "widget")

    def delete_chat(self, chat_id: str):
        if self._running:
            return
        self.chats.delete(chat_id)
        self.set_mode(self.mode if self.mode in SIZES else "widget")

    def toggle_list(self):
        self.show_list = not self.show_list
        self.set_mode("widget")

    def _chat_list(self, parent, width=None):
        """List of saved chats: tap to open, trash to delete."""
        width = width or px(300)  # real pixels
        box = tk.Frame(parent, bg=BG, width=width)
        Pill(box, "Новый чат", BLUE, self.new_chat, w=(width - px(12)) * 1000 / px(1000), h=40, size=15).pack(
            pady=(0, px(10)))
        holder = tk.Canvas(box, bg=BG, highlightthickness=0, width=width - px(8))
        holder.pack(fill="both", expand=True)
        inner = tk.Frame(holder, bg=BG)
        holder.create_window((0, 0), window=inner, anchor="nw", width=width - px(8))
        inner.bind("<Configure>", lambda e: holder.configure(scrollregion=holder.bbox("all")))
        for chat in self.chats.items:
            active = chat["id"] == self.chats.current_id
            color = FIELD if active else BG
            row = tk.Frame(inner, bg=color, cursor="hand2")
            row.pack(fill="x", pady=2)
            title = chat["title"] or "Новый чат"
            lab = tk.Label(row, text=title, bg=color, fg=FG, font=font(14, "bold" if active else "normal"),
                           anchor="w", justify="left", wraplength=width - px(70))
            lab.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            for wdg in (row, lab):
                wdg.bind("<ButtonRelease-1>", lambda e, i=chat["id"]: self.open_chat(i))
            Pill(row, color=color, command=lambda i=chat["id"]: self.delete_chat(i), w=28, h=28, icon="trash",
                 icon_scale=0.8, fg=MUTED).pack(side="right", padx=6)
        return box

    def _build_chat(self, body):
        full = self.mode == "full"
        if not full and self.show_list:
            self._chat_list(body, width=int(self.root.winfo_width() or px(SIZES["widget"][0])) - px(28)).pack(
                fill="both", expand=True)
            return
        if full:
            side = self._chat_list(body, width=px(240))
            side.pack(side="left", fill="y", padx=(0, 14))
            side.pack_propagate(False)
        size, design_h = (18, 54) if full else (15, 44)
        h = px(design_h)  # real pixels for the field; Pills take design units
        bar = tk.Frame(body, bg=BG)
        bar.pack(side="bottom", fill="x", pady=(8, 0))
        self.files_row = tk.Frame(body, bg=BG)
        self.files_row.pack(side="bottom", fill="x")
        self._paint_files()
        self.chat = Chat(body, wrap=560 if full else 260, text_size=size)
        self.chat.on_copied = lambda: self.set_status("Скопировано", GREEN)
        self.chat.pack(fill="both", expand=True)
        for text, who in self.history:
            self.chat.add(text, who)
        if not self.history:  # shown, not saved: an empty chat stays empty
            self.chat.add(T["greeting"] + " Напишите, что сделать.", "robot")
        Pill(bar, color=BLUE, command=self.submit, w=design_h, h=design_h, icon="send", icon_scale=design_h / 56).pack(side="right", padx=(6, 0))
        Pill(bar, color=FIELD, command=self.dictate, w=design_h, h=design_h, icon="mic", icon_scale=design_h / 56,
             fg=FG).pack(side="right", padx=(6, 0))
        Pill(bar, color=FIELD, command=self.attach, w=design_h, h=design_h, icon="clip", icon_scale=design_h / 56,
             fg=FG).pack(side="left", padx=(0, 6))
        field = tk.Canvas(bar, bg=BG, highlightthickness=0, height=h, width=10)
        field.pack(side="left", fill="x", expand=True)
        self.entry = tk.Text(field, font=font(size), height=1, bg=CARD, fg=FG, insertbackground=BLUE,
                             relief="flat", highlightthickness=0, wrap="word", undo=True)
        holder = field.create_window(h // 2, h // 2, window=self.entry, anchor="w")

        def layout(e):
            field.delete("bg")
            rounded(field, 0, 0, e.width, e.height, e.height / 2, CARD, tags="bg")
            field.tag_lower("bg")
            field.itemconfigure(holder, width=e.width - h)
            field.coords(holder, h // 2, e.height // 2)

        field.bind("<Configure>", layout)
        field.bind("<Button-1>", lambda e: self.entry.focus_force())
        self.entry.bind("<Return>", lambda e: (self.submit(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: None)  # new line
        self.entry.bind("<<Paste>>", self._paste, add="+")
        edit_menu(self.entry)

        def grow(_=None):  # the field grows up to 5 lines as the person types
            lines = int(self.entry.count("1.0", "end", "displaylines")[0] or 1) if self.entry.winfo_exists() else 1
            lines = max(1, min(5, lines))
            self.entry.configure(height=lines)
            field.configure(height=max(h, px(lines * (size + 10) + 18)))

        self.entry.bind("<KeyRelease>", grow, add="+")
        self._placeholder(self.entry, "Напишите, что сделать…" if full else "Что сделать?")

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
        self.chats.add(text, who)
        if self.chat is not None:
            self.chat.add(text, who)

    def _make_stop_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        make_floating(win)
        win.configure(bg=RED)
        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"{px(200)}x{px(64)}+{(w - px(200)) // 2}+{h - px(64 + BOTTOM)}")
        btn = tk.Label(win, text=T["stop"], bg=RED, fg="white", font=font(24, "bold"), cursor="hand2")
        btn.pack(fill="both", expand=True)
        btn.bind("<ButtonRelease-1>", lambda e: self.stop())
        win.withdraw()
        return win

    # --- actions --------------------------------------------------------------------
    def dictate(self):
        self.entry.focus_force()
        self._post(self.services.dictation_hint(), "note")
        self.root.after(150, self.services.start_dictation)  # after the field really has focus

    def attach(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Выберите файл",
                                            filetypes=[("Фото, PDF, текст", "*.png *.jpg *.jpeg *.gif *.webp *.pdf "
                                                        "*.txt *.md *.csv *.json *.rtf"), ("Все файлы", "*")])
        for p in paths or ():
            try:
                to_block(p)
            except ValueError as exc:
                self._post(f"{pathlib.Path(p).name}: {exc}", "note")
                continue
            if p not in self.files:
                self.files.append(p)
        self._paint_files()

    def _paste(self, _=None):
        """Cmd+V with a picture or copied files in the clipboard attaches them; text pastes as usual."""
        try:
            from PIL import ImageGrab
            got = ImageGrab.grabclipboard()
        except Exception:
            got = None
        if got is None:
            if getattr(self.entry, "is_hint", False):  # paste into an empty field replaces the hint
                self.entry.delete("1.0", "end")
                self.entry.config(fg=FG)
                self.entry.is_hint = False
            return None
        if isinstance(got, list):
            paths = [p for p in got if isinstance(p, str) and os.path.isfile(p)]
        else:
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"robot-helper-paste-{os.getpid()}-{id(got)}.png")
            got.save(path)
            paths = [path]
        for p in paths:
            try:
                to_block(p)
            except ValueError as exc:
                self._post(f"{pathlib.Path(p).name}: {exc}", "note")
                continue
            if p not in self.files:
                self.files.append(p)
        self._paint_files()
        return "break"

    def _paint_files(self):
        row = getattr(self, "files_row", None)
        if row is None or not row.winfo_exists():
            return
        for child in row.winfo_children():
            child.destroy()
        for p in self.files:
            chip = tk.Frame(row, bg=FIELD)
            chip.pack(side="left", padx=(0, 6), pady=(6, 0))
            tk.Label(chip, text=pathlib.Path(p).name[:24], bg=FIELD, fg=FG, font=font(13)).pack(side="left", padx=(10, 2), pady=4)
            x = tk.Label(chip, text="✕", bg=FIELD, fg=MUTED, font=font(13), cursor="hand2")
            x.pack(side="left", padx=(2, 8))
            x.bind("<ButtonRelease-1>", lambda e, q=p: (self.files.remove(q), self._paint_files()))

    def submit(self, task: str | None = None):
        if self._running:
            return
        files, blocks = [], []
        if task is None:
            if self.chat is None or getattr(self.entry, "is_hint", False):
                if not self.files:
                    return
                task = ""
            else:
                task = self.entry.get("1.0", "end").strip()
            files = list(self.files)
            if not task and not files:
                return
            for p in files:
                try:
                    blocks.append(to_block(p))
                except ValueError:
                    pass
            if not task:
                task = "Посмотри файл."
            if files:  # the path lets the robot also open the file on the computer if asked
                task += "\n\n" + "\n".join(f"Файл: {p}" for p in files)
            self.entry.delete("1.0", "end")
            self.files = []
            self._paint_files()
        key = config.get_api_key()
        if not key:
            self.set_mode("full", setup=True)
            return
        if self.chat is None:
            self.set_mode("widget")
        self._post(task, "me")
        self._task = task
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
        context = [x for x in self.history[:-1] if x[1] in ("me", "robot")][-20:]
        threading.Thread(target=self._run, args=(task, context, blocks), daemon=True).start()

    def on_state(self, state: State):
        """Agent thread. The first computer action shrinks the helper out of the robot's way."""
        if state != State.WORKING or self._working:
            return
        if self.services.missing_permissions():
            self.agent.stop()  # cannot see or move without macOS permissions; ask for them now
            self.last_said = NEED_PERMS
            config.set_pref("pending_task", self._task)
            self.root.after(0, lambda: self.set_mode("full", setup=True))
            return
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

    def _run(self, task: str, context=None, blocks=None):
        try:
            state = self.agent.run(task, history=context, attachments=blocks or None)
        except Exception as exc:  # never show a traceback to the person; keep it in the log file
            from robot_helper.core.agent import log_error
            log_error(exc)
            state = State.ERROR
            self.last_said = T["try_again"]
        self.root.after(0, lambda: self._finished(state))

    def _finished(self, state: State):
        self._running = False
        if self._working:
            self.overlay.hide()
            self.stop_win.withdraw()
            self.set_mode(self._mode_before if self._mode_before in SIZES else "widget")
        elif self.mode == "mini":
            self.set_mode("widget")
        final = self.last_said or {State.DONE: T["done"], State.STOPPED: T["stopped"]}.get(state, T["try_again"])
        if state == State.STOPPED and self.last_said not in (T["stopped"], T["too_many_steps"], NEED_PERMS):
            final = T["stopped"]
        if self.chat is not None or final != NEED_PERMS:
            self.chats.add(final, "robot")
            if self.chat is not None:
                self.chat.add(final, "robot")
        if self._working:
            self.services.speak(final)
        if final == T["bad_key"]:  # wrong or revoked key: open the key field right away
            self.bad_key = self.replace_key = True
            self.set_mode("full", setup=True)
        self.set_status(*{State.DONE: ("Готов", GREEN), State.STOPPED: ("Остановлен", ORANGE),
                          State.ERROR: ("Не получилось", RED)}.get(state, ("Готов", GREEN)))

    def _on_global_escape(self):
        # the Esc that the robot itself presses must not stop it
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
            make_panel(win)
            win.title("Робот-помощник")
            w, h = px(520), px(210)
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
            tk.Label(win, text=text, bg=BG, fg=FG, font=font(20, "bold"), wraplength=w - px(60),
                     justify="center").pack(pady=(28, 18), padx=30)
            row = tk.Frame(win, bg=BG)
            row.pack()
            for label, color, value in buttons:
                Pill(row, label, color, lambda v=value: self._resolve(v), w=150, h=52, size=18).pack(side="left", padx=8)
            win.protocol("WM_DELETE_WINDOW", lambda: self._resolve(False))
            win.lift()
            win.focus_force()
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
    services = get_platform()
    services.prepare()  # Windows DPI awareness must be on before Tk starts, or 4K screens get half-size windows
    root = tk.Tk()
    set_scale(root)
    App(root, services)
    if "--smoke" in sys.argv:  # build the UI and exit: used by CI and manual checks
        root.after(1500, root.destroy)
    root.mainloop()
