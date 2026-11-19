from robot_helper.ui.app import DOCKS, place


def test_every_dock_fits_on_screen():
    for dock in DOCKS:
        x, y = place(dock, 380, 560, 1440, 900)
        assert 0 <= x and x + 380 <= 1440 and 0 <= y and y + 560 <= 900, dock


def test_right_dock_hugs_right_edge():
    x, _ = place("right", 380, 560, 1440, 900)
    assert 1440 - (x + 380) == 20


class _Root:
    def __init__(self, dpi, h):
        self.dpi, self.h, self.tk = dpi, h, self
        self.scaling = None

    def winfo_fpixels(self, _):
        return self.dpi

    def winfo_screenheight(self):
        return self.h

    def call(self, *args):
        self.scaling = args[-1]


def test_scale_follows_windows_4k_at_200_percent(monkeypatch):
    from robot_helper.ui import widgets
    monkeypatch.setattr(widgets, "UI", widgets.UI)  # restored after the test
    monkeypatch.setattr(widgets.sys, "platform", "win32")
    root = _Root(192, 2160)  # 4K, 200%: logical height 1080
    assert widgets.set_scale(root) == 2.16 and root.scaling == 2.16


def test_scale_grows_on_big_logical_screen(monkeypatch):
    from robot_helper.ui import widgets
    monkeypatch.setattr(widgets, "UI", widgets.UI)  # restored after the test
    monkeypatch.setattr(widgets.sys, "platform", "darwin")
    assert widgets.set_scale(_Root(72, 1440)) == 1.44
    assert widgets.set_scale(_Root(72, 900)) == 1.0
