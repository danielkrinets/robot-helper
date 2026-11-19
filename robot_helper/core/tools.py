"""Tool definitions sent with every request."""


def _custom(name: str, description: str, field: str, field_desc: str) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {field: {"type": "string", "description": field_desc}},
            "required": [field],
            "additionalProperties": False,
        },
    }


TOOLS: list[dict] = [
    {"type": "computer_toolset_20260801"},
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},  # runs on Anthropic servers
    _custom(
        "ask_permission",
        "Ask the person yes/no before anything that sends, pays, deletes, publishes or cannot be undone. "
        "Returns 'yes' or 'no'.",
        "question",
        "One short, plain Russian question, e.g. 'Отправить письмо Маше?'",
    ),
    _custom(
        "hand_over_to_human",
        "Pause and let the person do a step themselves (passwords, card numbers, codes from SMS, "
        "anything you must not type). Returns when the person presses 'Готово'.",
        "reason",
        "One short, plain Russian sentence explaining what the person should do.",
    ),
]
