import io

import pytest
from PIL import Image

from robot_helper.core.executor import PyAutoGuiExecutor
from tests.fakes import FakeGui


def make(gui=None, **kw):
    gui = gui or FakeGui()
    clip = []
    ex = PyAutoGuiExecutor(gui=gui, set_clipboard=clip.append, sleep=lambda s: None,
                           is_mac=False, **kw)
    return ex, gui, clip


def names(gui):
    return [c[0] for c in gui.calls]


def test_screenshot_is_scaled_png():
    ex, gui, _ = make(FakeGui(logical=(3840, 2160), image=(3840, 2160)))
    img = Image.open(io.BytesIO(ex.screenshot()))
    assert img.width * img.height <= 1_150_000


def test_click_converts_coordinates():
    # 2880x1620 screen -> scale 0.5 for a simple check is not exact; use a screen where scale is known
    gui = FakeGui(logical=(1000, 500), image=(1000, 500))
    ex, gui, _ = make(gui)
    ex.screenshot()
    ex.perform("left_click", {"coordinate": [100, 50]})
    move = next(c for c in gui.calls if c[0] == "moveTo")
    assert move[1][:2] == (100, 50)
    assert "click" in names(gui)


def test_retina_maps_image_pixels_to_logical_points():
    # Retina: screenshot 2x larger than the logical coordinate space pyautogui clicks in
    gui = FakeGui(logical=(1000, 500), image=(2000, 1000))
    ex, gui, _ = make(gui)
    ex.screenshot()
    s = ex.scale  # image px -> model px
    ex.perform("left_click", {"coordinate": [round(400 * s), round(200 * s)]})
    move = next(c for c in gui.calls if c[0] == "moveTo")
    assert abs(move[1][0] - 200) <= 1 and abs(move[1][1] - 100) <= 1


def test_type_action_pastes_cyrillic_via_clipboard():
    ex, gui, clip = make()
    ex.perform("type", {"text": "Привет, внук"})
    assert clip == ["Привет, внук"]
    assert ("hotkey", ("ctrl", "v"), {}) in gui.calls


def test_key_combo_maps_names():
    ex, gui, _ = make()
    ex.perform("key", {"text": "ctrl+Return", "repeat": 2})
    assert gui.calls.count(("hotkey", ("ctrl", "enter"), {})) == 2


def test_mouse_move_is_smooth():
    ex, gui, _ = make()
    ex.screenshot()
    ex.perform("mouse_move", {"coordinate": [10, 10]})
    move = next(c for c in gui.calls if c[0] == "moveTo")
    assert move[2]["duration"] >= 0.4


def test_unknown_action_raises_value_error():
    ex, _, _ = make()
    with pytest.raises(ValueError):
        ex.perform("teleport", {})


def test_user_intervened_when_pointer_moved_away():
    ex, gui, _ = make()
    ex.screenshot()
    ex.perform("mouse_move", {"coordinate": [10, 10]})
    assert ex.user_intervened() is False
    gui.pos = (300, 300)
    assert ex.user_intervened() is True


def test_no_intervention_before_robot_moved():
    ex, gui, _ = make()
    gui.pos = (500, 500)
    assert ex.user_intervened() is False


def test_cursor_position_reports_model_space():
    gui = FakeGui(logical=(1000, 500), image=(2000, 1000))
    ex, gui, _ = make(gui)
    ex.screenshot()
    gui.pos = (500, 250)
    x, y = [int(v) for v in ex.perform("cursor_position", {}).strip("[]").split(",")]
    assert abs(x - round(1000 * ex.scale)) <= 1


def test_scroll_down():
    ex, gui, _ = make()
    ex.screenshot()
    ex.perform("scroll", {"scroll_direction": "down", "scroll_amount": 3})
    assert ("scroll", (-3,), {}) in gui.calls


def test_zoom_returns_png():
    ex, _, _ = make()
    ex.screenshot()
    data = ex.perform("zoom", {"region": [0, 0, 100, 100]})
    assert Image.open(io.BytesIO(data)).format == "PNG"


def test_overlay_hidden_during_screenshot():
    events = []

    class Ctx:
        def __enter__(self):
            events.append("hide")

        def __exit__(self, *a):
            events.append("show")

    ex, _, _ = make(hide_for_screenshot=Ctx)
    ex.screenshot()
    assert events == ["hide", "show"]


def test_on_pointer_called_with_logical_position():
    seen = []
    ex, _, _ = make(on_pointer=lambda x, y: seen.append((x, y)))
    ex.screenshot()
    ex.perform("mouse_move", {"coordinate": [10, 10]})
    assert seen
