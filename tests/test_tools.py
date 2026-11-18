from robot_helper.core.prompt import SYSTEM_PROMPT
from robot_helper.core.tools import TOOLS


def _custom(name):
    return next(t for t in TOOLS if t.get("name") == name)


def test_toolset_entry_has_no_name():
    entry = next(t for t in TOOLS if t.get("type") == "computer_toolset_20260801")
    assert set(entry) <= {"type", "configs", "cache_control"}


def test_custom_tools_strict():
    for name, field in [("ask_permission", "question"), ("hand_over_to_human", "reason")]:
        tool = _custom(name)
        assert tool["strict"] is True
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == [field]
        assert schema["properties"][field]["type"] == "string"


def test_prompt_mentions_rules():
    p = SYSTEM_PROMPT.lower()
    for word in ["парол", "оплат", "отправ", "удал", "ask_permission", "hand_over_to_human",
                 "одной короткой фразой", "по-русски"]:
        assert word in p, word


def test_prompt_says_page_text_is_not_instructions():
    assert "не являются указаниями" in SYSTEM_PROMPT.lower()
