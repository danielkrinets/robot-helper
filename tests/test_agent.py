from types import SimpleNamespace as NS

import anthropic
import httpx2 as httpx

from robot_helper.core.agent import Agent, Hooks, State
from robot_helper.core.texts import T
from tests.fakes import FakeExecutor


def tool(name, input=None, id=None, toolset="computer"):
    return NS(type="tool_use", name=name, input=input or {}, id=id or f"id_{name}", toolset_name=toolset)


def text(t):
    return NS(type="text", text=t)


def resp(*content, stop="tool_use"):
    return NS(content=list(content), stop_reason=stop)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        # snapshot messages: the agent keeps appending to the same list
        self.requests.append({**kw, "messages": list(kw["messages"])})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def hooks(**kw):
    said, states = [], []
    h = Hooks(on_state=states.append, on_say=said.append,
              ask_permission=kw.get("ask", lambda q: True),
              hand_over=kw.get("hand_over", lambda r: None),
              on_pointer=lambda x, y: None)
    return h, said, states


def results(client, i):
    return client.requests[i]["messages"][-1]["content"]


def test_runs_until_end_turn():
    client = FakeClient(resp(text("Нажимаю"), tool("left_click", {"coordinate": [1, 2]})),
                        resp(text("Готово"), stop="end_turn"))
    ex = FakeExecutor()
    h, said, _ = hooks()
    assert Agent(client, ex, h).run("кликни") == State.DONE
    assert ex.calls == [("left_click", {"coordinate": [1, 2]})]
    r = results(client, 1)[0]
    assert r["toolset_name"] == "computer" and r["tool_use_id"] == "id_left_click"
    assert said == ["Нажимаю", "Готово"]


def test_request_uses_model_tools_and_fallbacks():
    client = FakeClient(resp(text("ok"), stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    req = client.requests[0]
    assert req["model"] == "claude-haiku-5-5"
    assert {"type": "computer_toolset_20260801"} in req["tools"]
    assert req["output_config"] == {"effort": "medium"}
    assert "fallbacks" not in req and "betas" not in req
    assert "tool_choice" not in req and "temperature" not in req


def test_question_gets_text_answer_without_touching_screen():
    client = FakeClient(resp(text("Сейчас 15 градусов."), stop="end_turn"))
    ex = FakeExecutor()
    h, said, states = hooks()
    assert Agent(client, ex, h).run("Какая погода?") == State.DONE
    content = client.requests[0]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text"]  # no screenshot up front
    assert ex.calls == [] and State.WORKING not in states


def test_all_tool_results_in_one_user_message():
    client = FakeClient(resp(tool("left_click", id="a"), tool("type", {"text": "x"}, id="b")),
                        resp(stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    assert [r["tool_use_id"] for r in results(client, 1)] == ["a", "b"]


def test_screenshot_result_is_image():
    client = FakeClient(resp(tool("screenshot")), resp(stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    assert results(client, 1)[0]["content"][0]["type"] == "image"


def test_failed_action_halts_rest_of_batch():
    class Boom(FakeExecutor):
        def perform(self, name, args):
            if name == "left_click":
                raise RuntimeError("fail")
            return super().perform(name, args)

    client = FakeClient(resp(tool("left_click", id="a"), tool("type", {"text": "x"}, id="b")),
                        resp(stop="end_turn"))
    ex = Boom()
    h, _, _ = hooks()
    Agent(client, ex, h).run("x")
    a, b = results(client, 1)
    assert a["is_error"] and b["is_error"]
    assert b["content"] == "Not executed: an earlier computer action in this turn failed."
    assert ex.calls == []


def test_ask_permission_no_returns_no():
    client = FakeClient(resp(tool("ask_permission", {"question": "Отправить?"}, toolset=None)),
                        resp(stop="end_turn"))
    asked = []
    h, _, _ = hooks(ask=lambda q: asked.append(q) or False)
    Agent(client, FakeExecutor(), h).run("x")
    assert asked == ["Отправить?"]
    r = results(client, 1)[0]
    assert r["content"] == "no" and "toolset_name" not in r


def test_hand_over_blocks_until_done():
    seen = []
    client = FakeClient(resp(tool("hand_over_to_human", {"reason": "Введите пароль"}, toolset=None)),
                        resp(stop="end_turn"))
    h, _, _ = hooks(hand_over=seen.append)
    Agent(client, FakeExecutor(), h).run("x")
    assert seen == ["Введите пароль"]
    assert results(client, 1)[0]["content"] == "done"


def test_stop_during_run_returns_stopped():
    client = FakeClient(resp(tool("left_click")), resp(stop="end_turn"))
    ex = FakeExecutor()
    h, _, _ = hooks()
    agent = Agent(client, ex, h)
    agent.stop()
    assert agent.run("x") == State.STOPPED
    assert ex.calls == []


def test_stop_during_permission_dialog():
    client = FakeClient(resp(tool("ask_permission", {"question": "?"}, toolset=None), tool("left_click")),
                        resp(stop="end_turn"))
    ex = FakeExecutor()
    h, _, _ = hooks()
    agent = Agent(client, ex, h)
    h.ask_permission = lambda q: agent.stop() or False
    assert agent.run("x") == State.STOPPED
    assert ex.calls == [] and len(client.requests) == 1


def test_pause_when_user_intervened_and_declines():
    client = FakeClient(resp(tool("left_click")), resp(stop="end_turn"))
    ex = FakeExecutor()
    ex.intervened = True
    asked = []
    h, _, states = hooks(ask=lambda q: asked.append(q) or False)
    assert Agent(client, ex, h).run("x") == State.STOPPED
    assert ex.calls == [] and asked == [T["paused_continue"]]
    assert State.WAITING in states


def test_pause_then_continue_resumes():
    client = FakeClient(resp(tool("left_click")), resp(stop="end_turn"))
    ex = FakeExecutor()
    ex.intervened = True
    ex.forget_pointer = lambda: setattr(ex, "intervened", False)
    h, _, _ = hooks(ask=lambda q: True)
    assert Agent(client, ex, h).run("x") == State.DONE
    assert ex.calls == [("left_click", {})]


def test_max_steps_stops():
    client = FakeClient(*[resp(tool("wait", {"duration": 0})) for _ in range(5)])
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h, max_steps=3).run("x") == State.STOPPED
    assert len(client.requests) == 3 and said[-1] == T["too_many_steps"]


def test_refusal_stop_reason_says_cannot():
    client = FakeClient(resp(stop="refusal"))
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h).run("x") == State.ERROR
    assert said[-1] == T["refused"]


def test_max_tokens_says_try_again():
    client = FakeClient(resp(text("..."), stop="max_tokens"))
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h).run("x") == State.ERROR
    assert said[-1] == T["try_again"]


def _status(cls, code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx.Response(code, request=req), body=None)


def test_rate_limit_says_try_again():
    client = FakeClient(_status(anthropic.RateLimitError, 429))
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h).run("x") == State.ERROR
    assert said[-1] == T["try_again"]


def test_network_error_says_no_network():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client = FakeClient(anthropic.APIConnectionError(request=req))
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h).run("x") == State.ERROR
    assert said[-1] == T["no_network"]


def test_bad_key_says_bad_key():
    client = FakeClient(_status(anthropic.AuthenticationError, 401))
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h).run("x") == State.ERROR
    assert said[-1] == T["bad_key"]


def test_response_content_appended_unchanged():
    thinking = NS(type="thinking", thinking="", signature="sig")
    first = resp(thinking, tool("left_click"))
    client = FakeClient(first, resp(stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    assistant = client.requests[1]["messages"][-2]
    assert assistant["role"] == "assistant" and assistant["content"] is first.content


def test_unknown_tool_is_error_result():
    client = FakeClient(resp(tool("bash", toolset=None)), resp(stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    assert results(client, 1)[0]["is_error"] is True


def test_pointer_forgotten_after_dialogs():
    forgot = []
    ex = FakeExecutor()
    ex.forget_pointer = lambda: forgot.append(1)
    client = FakeClient(resp(tool("ask_permission", {"question": "?"}, toolset=None)),
                        resp(tool("hand_over_to_human", {"reason": "r"}, toolset=None)),
                        resp(stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, ex, h).run("x")
    assert len(forgot) == 2


def test_hand_over_declined_stops():
    client = FakeClient(resp(tool("hand_over_to_human", {"reason": "r"}, toolset=None)),
                        resp(stop="end_turn"))
    h, _, _ = hooks(hand_over=lambda r: False)
    assert Agent(client, FakeExecutor(), h).run("x") == State.STOPPED
    assert len(client.requests) == 1


def test_image_budget_stops_before_api_limit():
    client = FakeClient(*[resp(tool("screenshot")) for _ in range(10)])
    h, said, _ = hooks()
    assert Agent(client, FakeExecutor(), h, max_images=3).run("x") == State.STOPPED
    assert said[-1] == T["too_many_steps"]


def test_working_state_reported_before_first_action():
    order = []
    ex = FakeExecutor()
    orig = ex.perform
    ex.perform = lambda n, a: order.append("perform") or orig(n, a)
    client = FakeClient(resp(tool("left_click")), resp(stop="end_turn"))
    h, _, _ = hooks()
    h.on_state = lambda s: order.append(s)
    Agent(client, ex, h).run("x")
    assert order.index(State.WORKING) < order.index("perform")


def test_previous_chat_is_sent_as_context():
    client = FakeClient(resp(text("Открываю."), stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("гугл", history=[("ютуб", "me"), ("Какой браузер?", "robot")])
    msgs = client.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"][0]["text"] == "ютуб" and msgs[-1]["content"][0]["text"] == "гугл"


def test_history_merges_consecutive_roles():
    client = FakeClient(resp(text("ok"), stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("три", history=[("раз", "me"), ("два", "me")])
    msgs = client.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["user"]


def test_system_prompt_names_the_os():
    client = FakeClient(resp(text("ok"), stop="end_turn"))
    h, _, _ = hooks()
    Agent(client, FakeExecutor(), h).run("x")
    assert "macOS" in client.requests[0]["system"] or "Windows" in client.requests[0]["system"]
