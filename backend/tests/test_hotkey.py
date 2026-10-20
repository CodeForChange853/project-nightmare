"""The Ctrl+Alt+N helper's decisions (the Windows calls themselves are checked live, see handoff.md)."""
import pytest

from backend.hotkey import (MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, MOD_WIN, HotkeyError, WindowState,
                            decide, mini_rect, parse_hotkey)


def test_parse_default_and_variants():
    assert parse_hotkey("ctrl+alt+n") == (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("N"))
    assert parse_hotkey(" Ctrl + Alt + N ") == parse_hotkey("ctrl+alt+n")
    assert parse_hotkey("win+shift+f9") == (MOD_WIN | MOD_SHIFT | MOD_NOREPEAT, 0x78)
    assert parse_hotkey("ctrl+alt+space")[1] == 0x20
    assert parse_hotkey("alt+1")[1] == ord("1")


@pytest.mark.parametrize("off", ["", "off", "OFF", "none", None])
def test_off_disables_the_helper(off):
    assert parse_hotkey(off) is None


@pytest.mark.parametrize("bad", ["n", "ctrl", "shift+n", "ctrl+alt+", "hyper+n", "ctrl+alt+ñ", "ctrl+alt+f25"])
def test_bad_shortcuts_are_refused(bad):
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


def test_mini_window_sits_bottom_right_above_the_taskbar():
    assert mini_rect((0, 0, 1920, 1040), 1.0) == (1920 - 400 - 16, 1040 - 560 - 16, 400, 560)
    x, y, w, h = mini_rect((0, 0, 1536, 824), 1.25)  # 125% scaling
    assert (w, h) == (500, 700) and x + w == 1536 - 20 and y + h == 824 - 20
    # a tiny screen never pushes the window off its top-left edge
    assert mini_rect((0, 0, 300, 400), 1.0)[:2] == (0, 0)


def test_what_a_press_does():
    assert decide(WindowState(exists=False)) == "launch"
    assert decide(WindowState(exists=True, minimized=True)) == "show"
    assert decide(WindowState(exists=True, full=True, foreground=True)) == "show"  # full view -> back to small
    assert decide(WindowState(exists=True, foreground=False)) == "show"  # behind other windows -> focus it
    assert decide(WindowState(exists=True, foreground=True)) == "hide"
