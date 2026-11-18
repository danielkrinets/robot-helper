from robot_helper.core.screen import fit_scale, to_screen


def test_no_downscale_when_small():
    assert fit_scale(1280, 720) == 1.0


def test_downscale_4k():
    assert fit_scale(3840, 2160) == 1568 / 3840


def test_portrait_uses_long_edge():
    assert fit_scale(1200, 3136) == 0.5


def test_round_trip_within_one_px():
    assert to_screen(100, 50, 0.5) == (200, 100)


def test_rounds_to_nearest():
    assert to_screen(1, 1, 0.3) == (3, 3)


def test_scale_never_above_one():
    assert fit_scale(10, 10) <= 1.0


def test_full_hd_limited_by_total_pixels():
    # 1920x1080 = 2.07 MP exceeds the 1.15 MP budget, so the pixel cap wins over 1568/1920
    scale = fit_scale(1920, 1080)
    assert abs(scale - (1_150_000 / (1920 * 1080)) ** 0.5) < 1e-9
    assert 1920 * scale * 1080 * scale <= 1_150_000 + 1
