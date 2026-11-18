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


def font(size: int, weight: str = "normal"):
    return (FAMILY, size, weight)


class Pill(tk.Canvas):
    """Rounded, flat button drawn on a canvas (tk.Button ignores colors on macOS)."""

    def __init__(self, parent, text, color, command, w=160, h=52, size=18, fg="white"):
        super().__init__(parent, width=w, height=h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.color, self.command = color, command
        r = h // 2
        self.shape = [
            self.create_oval(0, 0, h, h, fill=color, outline=color),
            self.create_oval(w - h, 0, w, h, fill=color, outline=color),
            self.create_rectangle(r, 0, w - r, h, fill=color, outline=color),
        ]
        self.label = self.create_text(w // 2, h // 2, text=text, fill=fg, font=font(size, "bold"))
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self._tint(0.85))
        self.bind("<Leave>", lambda e: self._tint(1.0))

    def _tint(self, k: float):
        rgb = [int(self.color[i:i + 2], 16) for i in (1, 3, 5)]
        c = "#%02x%02x%02x" % tuple(int(v * k) for v in rgb)
        for item in self.shape:
            self.itemconfig(item, fill=c, outline=c)

    def set_text(self, text: str):
        self.itemconfig(self.label, text=text)


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
        bubble = tk.Label(row, text=text, bg=color, fg=MUTED if who == "note" else FG, font=font(20),
                          wraplength=560, justify="left", padx=16, pady=10)
        bubble.pack(side="right" if mine else "left", anchor="e" if mine else "w")
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

        key_card = tk.Frame(box, bg=CARD, padx=20, pady=16)
        key_card.pack(fill="x", pady=8)
        if config.get_api_key():
            self._label(key_card, "✓  Ключ Claude API сохранён", 18, GREEN).pack(anchor="w")
        else:
            self._label(key_card, "Ключ Claude API", 18, weight="bold").pack(anchor="w")
            entry = tk.Entry(key_card, show="•", font=font(18), bg=FIELD, fg=FG, insertbackground=FG,
                             relief="flat", highlightthickness=0)
            entry.pack(fill="x", pady=10, ipady=8)

            def save():
                if entry.get().strip():
                    config.set_api_key(entry.get())
                    self._after_setup()

            entry.bind("<Return>", lambda e: save())
            Pill(key_card, "Сохранить", BLUE, save, w=150, h=44, size=16).pack(anchor="w")
            entry.focus_set()

        missing = self.services.missing_permissions()
        perm_card = tk.Frame(box, bg=CARD, padx=20, pady=16)
        perm_card.pack(fill="x", pady=8)
        if missing:
            self._label(perm_card, "Нужны разрешения macOS", 18, weight="bold").pack(anchor="w")
            self._label(perm_card, "Откройте «Системные настройки → Конфиденциальность и безопасность» "
                        "и включите эту программу в разделах:", 16, MUTED, wraplength=620).pack(anchor="w", pady=(6, 8))
            for item in missing:
                self._label(perm_card, "•  " + item.split("→")[-1].strip(), 17).pack(anchor="w")
            self._label(perm_card, "А также «Мониторинг ввода» — для клавиши Esc.\n"
                        "После этого закройте программу и откройте снова.", 15, MUTED).pack(anchor="w", pady=(8, 10))
            Pill(perm_card, "Проверить снова", FIELD, self._after_setup, w=200, h=44, size=16).pack(anchor="w")
        else:
            self._label(perm_card, "✓  Разрешения выданы", 18, GREEN).pack(anchor="w")

    def _after_setup(self):
        if config.get_api_key() and not self.services.missing_permissions():
            self.show_main()
        else:
            self.show_setup()

    def show_main(self):
        self._clear()
        header = tk.Frame(self.body, bg=BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        self._label(header, "🤖  Робот-помощник", 22, weight="bold").pack(side="left")
        self.status = self._label(header, "Готов помочь", 15, MUTED)
        self.status.pack(side="right")
        tk.Frame(self.body, bg=CARD, height=1).pack(fill="x")

        self.chat = Chat(self.body)
        self.chat.pack(fill="both", expand=True)
        for text, who in self.history:
            self.chat.add(text, who)
        if not self.history:
            self._post(T["greeting"] + " Напишите, что сделать.", "robot")

        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", padx=20, pady=16)
        field = tk.Frame(bar, bg=CARD, padx=14, pady=8)
        field.pack(side="left", fill="x", expand=True)
        self.entry = tk.Text(field, font=font(20), height=2, bg=CARD, fg=FG, insertbackground=FG,
                             relief="flat", highlightthickness=0, wrap="word")
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", lambda e: (self.submit(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: None)
        Pill(bar, "🎤", FIELD, self.dictate, w=56, h=56, size=22).pack(side="left", padx=(12, 0))
        Pill(bar, "↑", BLUE, self.submit, w=56, h=56, size=24).pack(side="left", padx=(8, 0))
        self.entry.focus_set()

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
        Pill(win, "■  " + T["stop"], RED, self.stop, w=240, h=96, size=28).pack()
        win.withdraw()
        return win

    # --- actions -------------------------------------------------------------------
    def dictate(self):
        self.entry.focus_set()
        self._post(self.services.dictation_hint(), "note")
        self.services.start_dictation()

    def submit(self):
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
        self.status.config(text="Работаю…")
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
            self.root.after(0, lambda: self._post(T["try_again"], "robot"))
        self.root.after(0, lambda: self._finished(state))

    def _finished(self, state: State):
        self._running = False
        self.overlay.hide()
        self.stop_win.withdraw()
        self.root.deiconify()
        self.root.lift()
        self.status.config(text={State.DONE: "Готово", State.STOPPED: "Остановлен"}.get(state, "Готов помочь"))
        if state == State.DONE and (not self.history or self.history[-1][1] != "robot"):
            self._post(T["done"], "robot")
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
        self.root.after(0, lambda: self._post(text, "robot"))
        self.overlay.set_label(text)
        self.services.speak(text)

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
