"""Ctrl+Alt+N summons a small always-on-top Nightmare window (Windows only).

    pythonw -m backend.hotkey        (start_nightmare.ps1 and install_autostart.ps1 start it)

A web page can't hear keys pressed outside the browser, so this tiny helper registers the shortcut with
Windows and opens Chrome as an app window on http://127.0.0.1:<port>/?mini. Each press: open it if
it isn't there, show and focus it if it's hidden, behind or maximized, hide it if it's already in front.

The page asks for a size through its window title, which this helper watches:
"Nightmare Mini" = small, bottom-right, on top; "Nightmare" = maximized, not on top ("home").

It only ever starts Chrome with that fixed local address. It opens no port and reads nothing but
NIGHTMARE_PORT and NIGHTMARE_HOTKEY from backend/.env. Logs go to backend/logs/hotkey.log.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from dotenv import dotenv_values

from .config import BACKEND_DIR

MINI_TITLE, FULL_TITLE = "Nightmare Mini", "Nightmare"
CHROME_CLASS = "Chrome_WidgetWin_1"
MINI_W, MINI_H, MARGIN = 400, 560, 16  # device-independent pixels
LAUNCH_WAIT = 20.0  # seconds to look for the new window after starting Chrome
TICK_MS = 250

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
NAMED_KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "home": 0x24, "end": 0x23, "insert": 0x2D,
              "pause": 0x13, "backquote": 0xC0, "`": 0xC0}

log = logging.getLogger("nightmare.hotkey")


class HotkeyError(ValueError):
    pass


def parse_hotkey(text: str | None) -> tuple[int, int] | None:
    """"ctrl+alt+n" -> (modifier flags, virtual-key code). "off" or empty -> None (helper disabled)."""
    text = (text or "").strip().lower()
    if text in {"", "off", "none", "0", "false"}:
        return None
    parts = [p.strip() for p in text.split("+")]
    if len(parts) < 2 or not all(parts):
        raise HotkeyError(f"“{text}” needs a modifier and a key, like ctrl+alt+n")
    *mods, key = parts
    mask = 0
    for mod in mods:
        if mod not in MODIFIERS:
            raise HotkeyError(f"“{mod}” is not a modifier (use ctrl, alt, shift or win)")
        mask |= MODIFIERS[mod]
    if not mask & (MOD_CONTROL | MOD_ALT | MOD_WIN):  # Shift+letter is just typing
        raise HotkeyError("the shortcut needs Ctrl, Alt or Win")
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif key[:1] == "f" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    elif key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    else:
        raise HotkeyError(f"“{key}” is not a key this helper knows (letters, digits, F1-F24, space…)")
    return mask | MOD_NOREPEAT, vk


def mini_rect(work_area: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
    """Bottom-right corner of the work area (above the taskbar): (x, y, width, height) in pixels."""
    left, top, right, bottom = work_area
    w = min(round(MINI_W * scale), right - left)
    h = min(round(MINI_H * scale), bottom - top)
    margin = round(MARGIN * scale)
    return max(left, right - w - margin), max(top, bottom - h - margin), w, h


@dataclass
class WindowState:
    exists: bool
    minimized: bool = False
    full: bool = False  # maximized, or the page asked for the full view
    foreground: bool = False


def decide(state: WindowState) -> str:
    """What one press of the shortcut does: launch | show (small, on top, focused) | hide."""
    if not state.exists:
        return "launch"
    if state.minimized or state.full or not state.foreground:
        return "show"
    return "hide"


def read_config() -> tuple[int, str]:
    env = {**dotenv_values(BACKEND_DIR / ".env"), **os.environ}
    return int(env.get("NIGHTMARE_PORT") or 8000), env.get("NIGHTMARE_HOTKEY", "ctrl+alt+n")


# ---- Windows ----------------------------------------------------------------------------------

def _chrome_path() -> str | None:
    import winreg

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                path = winreg.QueryValue(key, None)
                if path and os.path.isfile(path):
                    return path
        except OSError:
            continue
    return None


class Helper:
    WM_HOTKEY, WM_TIMER = 0x0312, 0x0113
    SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
    SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x1, 0x2, 0x40

    def __init__(self, port: int, hotkey: tuple[int, int]):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = u = ctypes.WinDLL("user32", use_last_error=True)
        # handles are pointer-sized: declare them, or ctypes would squeeze them into a C int
        HWND, INT, UINT = wintypes.HWND, ctypes.c_int, wintypes.UINT
        u.GetForegroundWindow.restype = HWND
        u.SetWindowPos.argtypes = [HWND, HWND, INT, INT, INT, INT, UINT]
        for name in ("IsWindow", "IsWindowVisible", "IsIconic", "IsZoomed", "SetForegroundWindow"):
            getattr(u, name).argtypes = [HWND]
        u.ShowWindow.argtypes = [HWND, INT]
        u.GetWindowTextW.argtypes = u.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, INT]
        u.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetDpiForWindow.argtypes = [HWND]
        self.url = f"http://127.0.0.1:{port}/?mini"
        self.hotkey = hotkey
        self.hwnd = None
        self.last_title = None
        self.launch_until = 0.0
        self.saved_rect = None  # where the user last left the small window
        try:
            self.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        except (AttributeError, OSError):
            pass

    # -- window helpers --
    def _title(self, hwnd) -> str:
        buf = self.ctypes.create_unicode_buffer(256)
        self.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def _class(self, hwnd) -> str:
        buf = self.ctypes.create_unicode_buffer(64)
        self.user32.GetClassNameW(hwnd, buf, 64)
        return buf.value

    def _find_new_window(self):
        found = []
        proc = self.ctypes.WINFUNCTYPE(self.wintypes.BOOL, self.wintypes.HWND, self.wintypes.LPARAM)

        def visit(hwnd, _):
            if (self.user32.IsWindowVisible(hwnd) and self._class(hwnd) == CHROME_CLASS
                    and self._title(hwnd) == MINI_TITLE):
                found.append(hwnd)
                return False
            return True

        self.user32.EnumWindows(proc(visit), 0)
        return found[0] if found else None

    def _alive(self) -> bool:
        if self.hwnd and not self.user32.IsWindow(self.hwnd):
            log.info("window closed")
            self.hwnd, self.last_title = None, None
        return bool(self.hwnd)

    def _scale(self) -> float:
        try:
            return self.user32.GetDpiForWindow(self.hwnd) / 96 or 1.0
        except (AttributeError, OSError):
            return 1.0

    def _work_area(self):
        rect = self.wintypes.RECT()
        self.user32.SystemParametersInfoW(0x30, 0, self.ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        return rect.left, rect.top, rect.right, rect.bottom

    def _remember_position(self):
        if not self._alive() or self.user32.IsIconic(self.hwnd) or self.user32.IsZoomed(self.hwnd):
            return
        rect = self.wintypes.RECT()
        if self.user32.GetWindowRect(self.hwnd, self.ctypes.byref(rect)):
            self.saved_rect = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def _focus(self):
        self.user32.SetForegroundWindow(self.hwnd)

    # -- the three things a window can be --
    def show_mini(self, focus=True):
        if self.user32.IsIconic(self.hwnd) or self.user32.IsZoomed(self.hwnd):
            self.user32.ShowWindow(self.hwnd, self.SW_RESTORE)
        x, y, w, h = self.saved_rect or mini_rect(self._work_area(), self._scale())
        self.user32.SetWindowPos(self.hwnd, self.HWND_TOPMOST, x, y, w, h, self.SWP_SHOWWINDOW)
        if focus:
            self._focus()

    def show_full(self):
        self._remember_position()
        self.user32.SetWindowPos(self.hwnd, self.HWND_NOTOPMOST, 0, 0, 0, 0, self.SWP_NOMOVE | self.SWP_NOSIZE)
        self.user32.ShowWindow(self.hwnd, self.SW_MAXIMIZE)
        self._focus()

    def hide(self):
        self._remember_position()
        self.user32.ShowWindow(self.hwnd, self.SW_MINIMIZE)

    def launch(self):
        if self.launch_until > time.monotonic():
            return  # already starting
        chrome = _chrome_path()
        if not chrome:
            log.error("Chrome was not found (App Paths)")
            self._message("Google Chrome was not found, so the Nightmare window can't open.")
            return
        x, y, w, h = mini_rect(self._work_area(), 1.0)
        subprocess.Popen([chrome, f"--app={self.url}", f"--window-size={MINI_W},{MINI_H}", f"--window-position={x},{y}"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
        self.launch_until = time.monotonic() + LAUNCH_WAIT
        log.info("launched %s", self.url)

    # -- events --
    def on_hotkey(self):
        if not self._alive() and not self.launch_until:
            # a small window left open by an earlier run of this helper: take it over, don't open another
            self.hwnd = self._find_new_window()
            if self.hwnd:
                self.last_title = MINI_TITLE
                log.info("took over an open window")
        exists = self._alive()
        state = WindowState(exists=exists)
        if exists:
            state.minimized = bool(self.user32.IsIconic(self.hwnd))
            state.full = bool(self.user32.IsZoomed(self.hwnd)) or self._title(self.hwnd) == FULL_TITLE
            state.foreground = self.user32.GetForegroundWindow() == self.hwnd
        action = decide(state)
        log.info("hotkey -> %s", action)
        if action == "launch":
            self.launch()
        elif action == "show":
            self.show_mini()
        else:
            self.hide()

    def on_tick(self):
        if not self.hwnd and self.launch_until:
            hwnd = self._find_new_window()
            if hwnd:
                self.hwnd, self.last_title, self.launch_until = hwnd, MINI_TITLE, 0.0
                log.info("window found")
                self.show_mini()
            elif time.monotonic() > self.launch_until:
                self.launch_until = 0.0
                log.warning("no Nightmare window appeared; is the backend running on %s?", self.url)
            return
        if not self._alive():
            return
        title = self._title(self.hwnd)
        if title == self.last_title or title not in (MINI_TITLE, FULL_TITLE):
            return  # page loading, or nothing changed
        self.last_title = title
        log.info("page asked for %s", "full view" if title == FULL_TITLE else "small window")
        if title == FULL_TITLE:
            self.show_full()
        else:
            self.show_mini()

    def _message(self, text: str):
        self.user32.MessageBoxW(None, text, "Nightmare", 0x30)  # MB_ICONWARNING

    def run(self) -> int:
        mods, vk = self.hotkey
        if not self.user32.RegisterHotKey(None, 1, mods, vk):
            log.error("RegisterHotKey failed (error %s)", self.ctypes.get_last_error())
            self._message("Another app already uses the Nightmare shortcut. Set NIGHTMARE_HOTKEY in "
                          "backend\\.env to a different one (for example ctrl+alt+m) and restart Nightmare.")
            return 1
        self.user32.SetTimer(None, 0, TICK_MS, None)
        log.info("listening (modifiers=%#x, key=%#x) for %s", mods, vk, self.url)
        msg = self.wintypes.MSG()
        while self.user32.GetMessageW(self.ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_HOTKEY:
                self.on_hotkey()
            elif msg.message == self.WM_TIMER:
                self.on_tick()
        return 0


def _single_instance() -> bool:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _single_instance.handle = kernel32.CreateMutexW(None, False, "Local\\ProjectNightmareHotkey")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    log_dir = BACKEND_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "hotkey.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s [%(levelname)s] %(message)s")
    if sys.platform != "win32":
        log.error("the hotkey helper only runs on Windows")
        return 1
    port, text = read_config()
    try:
        hotkey = parse_hotkey(text)
    except HotkeyError as exc:
        log.error("NIGHTMARE_HOTKEY: %s", exc)
        return 1
    if hotkey is None:
        log.info("NIGHTMARE_HOTKEY is off")
        return 0
    if not _single_instance():
        log.info("already running")
        return 0
    return Helper(port, hotkey).run()


if __name__ == "__main__":
    sys.exit(main())
