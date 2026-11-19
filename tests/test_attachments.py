import pytest

from robot_helper.core.attachments import to_block


def test_text_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("привет")
    b = to_block(str(f))
    assert b["type"] == "document" and b["source"]["data"] == "привет"


def test_pdf(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4")
    assert to_block(str(f))["source"]["media_type"] == "application/pdf"


def test_image_is_shrunk(tmp_path):
    from PIL import Image
    f = tmp_path / "big.png"
    Image.new("RGB", (4000, 3000)).save(f)
    b = to_block(str(f))
    assert b["type"] == "image" and b["source"]["media_type"] == "image/jpeg"


def test_unknown_type(tmp_path):
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        to_block(str(f))
