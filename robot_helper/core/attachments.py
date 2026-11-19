"""Turn a file the person attached into a Claude content block."""
from __future__ import annotations

import base64
import io
import pathlib

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp"}
TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".html", ".xml", ".yaml", ".yml", ".ini",
              ".rtf"}
MAX_TEXT = 200_000  # characters
MAX_IMAGE_SIDE = 1568
MAX_FILE = 30 * 1024 * 1024


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _image_block(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    media = IMAGE_TYPES[path.suffix.lower()]
    try:  # shrink big photos: fewer tokens, and the API caps image size
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if max(img.size) > MAX_IMAGE_SIDE or len(data) > 4 * 1024 * 1024:
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.convert("RGB").save(out, "JPEG", quality=85)
            data, media = out.getvalue(), "image/jpeg"
    except Exception:
        pass
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": _b64(data)}}


def to_block(path_str: str) -> dict:
    """Content block for the file. Raises ValueError with a plain Russian reason if it can't be sent."""
    path = pathlib.Path(path_str)
    if not path.is_file():
        raise ValueError("Файл не найден.")
    if path.stat().st_size > MAX_FILE:
        raise ValueError("Файл слишком большой.")
    ext = path.suffix.lower()
    if ext in IMAGE_TYPES:
        return _image_block(path)
    if ext == ".pdf":
        return {"type": "document", "title": path.name,
                "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(path.read_bytes())}}
    if ext in TEXT_TYPES:
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT]
        return {"type": "document", "title": path.name,
                "source": {"type": "text", "media_type": "text/plain", "data": text}}
    raise ValueError("Такой файл я пока не умею читать. Подойдут фото, PDF и текст.")
