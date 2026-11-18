"""Hand-written agent loop: Claude + computer toolset + our two custom tools."""
from __future__ import annotations

import base64
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import anthropic

from robot_helper.core.prompt import SYSTEM_PROMPT
from robot_helper.core.texts import T
from robot_helper.core.tools import TOOLS

MODEL = "claude-opus-5-5"
MAX_STEPS = 40
HALT_TEXT = "Not executed: an earlier computer action in this turn failed."


class State(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class Hooks:
    on_state: Callable[[State], None]
    on_say: Callable[[str], None]
    ask_permission: Callable[[str], bool]
    hand_over: Callable[[str], None]
    on_pointer: Callable[[int, int], None]


def _image(png: bytes) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}}


class Agent:
    def __init__(self, client, executor, hooks: Hooks, model: str = MODEL, max_steps: int = MAX_STEPS):
        self.client, self.executor, self.hooks = client, executor, hooks
        self.model, self.max_steps = model, max_steps
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _finish(self, state: State, message: str | None = None) -> State:
        if message:
            self.hooks.on_say(message)
        self.hooks.on_state(state)
        return state

    def run(self, task: str) -> State:
        if self.stopped:
            return self._finish(State.STOPPED, T["stopped"])
        messages: list[dict] = [{"role": "user", "content": [
            {"type": "text", "text": task}, _image(self.executor.screenshot())]}]
        for _ in range(self.max_steps):
            if self.stopped:
                return self._finish(State.STOPPED, T["stopped"])
            self.hooks.on_state(State.THINKING)
            try:
                response = self.client.beta.messages.create(
                    model=self.model, max_tokens=16000, system=SYSTEM_PROMPT, tools=TOOLS,
                    messages=messages, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            except anthropic.AuthenticationError:
                return self._finish(State.ERROR, T["bad_key"])
            except anthropic.APIConnectionError:
                return self._finish(State.ERROR, T["no_network"])
            except anthropic.APIStatusError:
                return self._finish(State.ERROR, T["try_again"])

            if response.stop_reason == "refusal":
                return self._finish(State.ERROR, T["refused"])
            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.hooks.on_say(block.text.strip())
            if response.stop_reason == "max_tokens":
                return self._finish(State.ERROR, T["try_again"])

            calls = [b for b in response.content if b.type == "tool_use"]
            if not calls:
                return self._finish(State.DONE)
            results = self._run_calls(calls)
            if self.stopped:
                return self._finish(State.STOPPED, T["stopped"])
            messages.append({"role": "user", "content": results})
        return self._finish(State.STOPPED, T["too_many_steps"])

    def _run_calls(self, calls) -> list[dict]:
        results, halted = [], False
        for block in calls:
            is_computer = getattr(block, "toolset_name", None) == "computer"
            base = {"type": "tool_result", "tool_use_id": block.id}
            if is_computer:
                base["toolset_name"] = "computer"
            if halted or self.stopped:
                results.append({**base, "is_error": True, "content": HALT_TEXT})
                continue
            if is_computer:
                if not self._check_intervention():
                    halted = True
                    results.append({**base, "is_error": True, "content": "Stopped by the person."})
                    continue
                self.hooks.on_state(State.WORKING)
                try:
                    out = self.executor.perform(block.name, dict(block.input))
                except Exception as exc:  # report to the model, skip the rest of the batch
                    halted = True
                    results.append({**base, "is_error": True, "content": f"Action failed: {exc}"})
                    continue
                content = [_image(out)] if isinstance(out, bytes) else [
                    {"type": "text", "text": out if isinstance(out, str) else "OK"}]
                results.append({**base, "content": content})
            elif block.name == "ask_permission":
                self.hooks.on_state(State.WAITING)
                yes = self.hooks.ask_permission(block.input["question"]) and not self.stopped
                results.append({**base, "content": "yes" if yes else "no"})
            elif block.name == "hand_over_to_human":
                self.hooks.on_state(State.WAITING)
                self.hooks.hand_over(block.input["reason"])
                results.append({**base, "content": "done"})
            else:
                results.append({**base, "is_error": True, "content": f"Unknown tool: {block.name}"})
        return results

    def _check_intervention(self) -> bool:
        """True to continue. If the person grabbed the mouse, pause and ask."""
        if not self.executor.user_intervened():
            return True
        self.hooks.on_state(State.WAITING)
        if self.hooks.ask_permission(T["paused_continue"]) and not self.stopped:
            forget = getattr(self.executor, "forget_pointer", None)
            if forget:
                forget()
            return True
        self.stop()
        return False
