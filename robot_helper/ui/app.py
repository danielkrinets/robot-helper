"""Main window: one big input, one big button, a giant STOP while the robot works."""
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

BIG = ("Helvetica", 30, "bold")
TEXT = ("Helvetica", 28)
BLUE, RED, GREEN, GREY = "#1E5AFF", "#E02020", "#1A9E3A", "#F2F2F2"


def big_button(parent, text, color, command, width=14):
    # tk.Label used as a button: macOS ignores bg colors on tk.Button
    btn = tk.Label(parent, text=text, bg=color, fg="white", font=BIG, width=width, height=2,
                   cursor="hand2")
    btn.bind("<Button-1>", lambda e: command())
    return btn


class App:
    def __init__(self, root: tk.Tk, services=None):
        self.root, self.services = root, services or get_platform()
        self.services.prepare()
        self.agent: Agent | None = None
        self.executor: PyAutoGuiExecutor | None = None
        self._pending: tuple[threading.Event, list] | None = None
        root.title("Робот-помощник")
        root.configure(bg="white")
        root.geometry("1000x700")
        root.bind("<Escape>", lambda e: self.stop())
        self.overlay = Overlay(root, self.services)
        self.stop_win = self._make_stop_window()
        self.overlay.windows.append(self.stop_win)  # hidden with the overlay during screenshots
        self.services.watch_escape(self._on_global_escape)
        self.frame = tk.Frame(root, bg="white")
        self.frame.pack(expand=True, fill="both", padx=40, pady=30)
        if config.get_api_key() is None or self.services.missing_permissions():
            self.show_setup()
        else:
            self.show_main()

    # --- screens -------------------------------------------------------------------
    def _clear(self):
        for child in self.frame.winfo_children():
            child.destroy()

    def show_setup(self):
        self._clear()
        tk.Label(self.frame, text="Настройка (делает тот, кто устанавливает)", font=BIG, bg="white").pack(pady=10)
        missing = self.services.missing_permissions()
        if missing:
            tk.Label(self.frame, text="Разрешите программе доступ:\n" + "\n".join(missing),
                     font=("Helvetica", 18), bg="white", justify="left").pack(pady=10)
        if config.get_api_key() is None:
            tk.Label(self.frame, text="Ключ Claude API:", font=TEXT, bg="white").pack()
            entry = tk.Entry(self.frame, show="•", font=TEXT, width=40)
            entry.pack(pady=10)

            def save():
                if entry.get().strip():
                    config.set_api_key(entry.get())
                    self.show_setup() if self.services.missing_permissions() else self.show_main()

            big_button(self.frame, "Сохранить", GREEN, save).pack(pady=10)
        else:
            big_button(self.frame, "Проверить снова", BLUE,
                       lambda: self.show_setup() if self.services.missing_permissions() else self.show_main()).pack(pady=10)

    def show_main(self, status: str | None = None):
        self._clear()
        tk.Label(self.frame, text="🤖", font=("Helvetica", 90), bg="white").pack()
        tk.Label(self.frame, text=status or T["greeting"], font=BIG, bg="white", wraplength=900).pack(pady=8)
        self.hint = tk.Label(self.frame, text=T["write_here"], font=TEXT, bg="white", fg="#555")
        self.hint.pack(pady=(16, 4))
        self.entry = tk.Text(self.frame, font=TEXT, height=3, width=40, bg=GREY, relief="flat", wrap="word")
        self.entry.pack(pady=4)
        self.entry.bind("<Return>", lambda e: (self.submit(), "break")[1])
        row = tk.Frame(self.frame, bg="white")
        row.pack(pady=20)
        big_button(row, "🎤 " + T["press_to_talk"].split(",")[0], BLUE, self.dictate, width=12).pack(side="left", padx=12)
        big_button(row, T["send"], GREEN, self.submit, width=10).pack(side="left", padx=12)
        self.entry.focus_set()

    def _make_stop_window(self) -> tk.Toplevel:
        win = tk.Toplevel(self.root, bg=RED)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"280x150+{w - 310}+{h - 220}")
        big_button(win, T["stop"], RED, self.stop, width=8).pack(expand=True, fill="both")
        win.withdraw()
        return win

    # --- actions -------------------------------------------------------------------
    def dictate(self):
        self.entry.focus_set()
        self.hint.config(text=self.services.dictation_hint())
        self.services.start_dictation()

    def submit(self):
        task = self.entry.get("1.0", "end").strip()
        if not task:
            return
        key = config.get_api_key()
        if not key:
            self.show_setup()
            return
        client = anthropic.Anthropic(api_key=key)
        hooks = Hooks(on_state=lambda s: None, on_say=self.say, ask_permission=self.ask,
                      hand_over=self.hand_over, on_pointer=self.overlay.move_hand)
        self.agent = Agent(client, None, hooks)
        self.executor = PyAutoGuiExecutor(hide_for_screenshot=self.overlay.hidden_for_screenshot,
                                          on_pointer=self.overlay.move_hand, stop_event=self.agent._stop)
        self.agent.executor = self.executor
        self.root.withdraw()
        self.overlay.show(T["working"])
        self.stop_win.deiconify()
        self.last_said = ""
        threading.Thread(target=self._run, args=(task,), daemon=True).start()

    def _run(self, task: str):
        try:
            state = self.agent.run(task)
        except Exception:  # never show a traceback to the person
            state = State.ERROR
            self.last_said = T["try_again"]
        self.root.after(0, lambda: self._finished(state))

    def _finished(self, state: State):
        self.overlay.hide()
        self.stop_win.withdraw()
        self.root.deiconify()
        self.root.lift()
        status = {State.DONE: T["done"], State.STOPPED: T["stopped"]}.get(state, "")
        self.show_main(self.last_said or status)

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
        self.last_said = text
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
            win = tk.Toplevel(self.root, bg="white")
            win.attributes("-topmost", True)
            win.title("Робот-помощник")
            tk.Label(win, text=text, font=BIG, bg="white", wraplength=700).pack(padx=40, pady=30)
            row = tk.Frame(win, bg="white")
            row.pack(pady=(0, 30))
            for label, color, value in buttons:
                big_button(row, label, color, lambda v=value: self._resolve(v), width=8).pack(side="left", padx=20)
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
        self.services.speak(question)
        return bool(self._dialog(question, [(T["ask_yes"], GREEN, True), (T["ask_no"], RED, False)], False))

    def hand_over(self, reason: str) -> bool:
        self.services.speak(reason)
        return bool(self._dialog(T["hand_over"] + "\n" + reason,
                                 [(T["ready_button"], GREEN, True), (T["stop"], RED, False)], True))


def main():
    root = tk.Tk()
    App(root)
    if "--smoke" in sys.argv:  # build the UI and exit: used by CI and manual checks
        root.after(1500, root.destroy)
    root.mainloop()
