from robot_helper.core.format import clean_text


def test_strips_bold_and_italic_markers():
    assert clean_text("**Готово**, письмо *отправлено*") == "Готово, письмо отправлено"


def test_strips_headings_and_bullets():
    assert clean_text("## Итог\n- первое\n* второе") == "Итог\nпервое\nвторое"


def test_strips_code_ticks():
    assert clean_text("нажмите `Enter`") == "нажмите Enter"


def test_keeps_plain_text():
    assert clean_text("Сейчас 5 * 3 = 15") == "Сейчас 5 * 3 = 15"
