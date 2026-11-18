"""Turn model Markdown into plain text for the chat (the person should never see ** or ##)."""
import re


def clean_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)        # headings
        line = re.sub(r"^\s*[-*•]\s+", "", line)             # bullets
        line = re.sub(r"(\*\*|__)(.+?)\1", r"\2", line)      # bold
        line = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", line)  # italic
        line = line.replace("`", "")
        lines.append(line)
    return "\n".join(lines).strip()
