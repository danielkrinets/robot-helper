from robot_helper.ui.app import DOCKS, place


def test_every_dock_fits_on_screen():
    for dock in DOCKS:
        x, y = place(dock, 380, 560, 1440, 900)
        assert 0 <= x and x + 380 <= 1440 and 0 <= y and y + 560 <= 900, dock


def test_right_dock_hugs_right_edge():
    x, _ = place("right", 380, 560, 1440, 900)
    assert 1440 - (x + 380) == 20
