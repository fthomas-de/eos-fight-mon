"""Windows docking: a window let go near another eos-fight-mon window (any instance) or a screen edge lines up with it."""
import ctypes
import sys

DIST = 15  # pixels: closer than this snaps
TITLES = ("eos-fight-mon – ", "Cockpit – ", "Graph – ")


def snap_offset(rect, others, areas, dist=DIST):
    """How far (dx, dy) to move rect (left, top, right, bottom) so its edges meet nearby windows or work areas.
    Pure function, the Windows part below only collects the rectangles."""
    l, t, r, b = rect
    xs, ys = [], []
    for ol, ot, or_, ob in others:
        if t < ob + dist and b > ot - dist:  # side by side: dock left/right, align left/right edges
            xs += [or_ - l, ol - r, ol - l, or_ - r]
        if l < or_ + dist and r > ol - dist:  # stacked: dock top/bottom, align top/bottom edges
            ys += [ob - t, ot - b, ot - t, ob - b]
    for al, at, ar, ab in areas:  # screen edges from the inside
        xs += [al - l, ar - r]
        ys += [at - t, ab - b]
    best = lambda ds: min((d for d in ds if abs(d) < dist), key=abs, default=0)
    return best(xs), best(ys)


if sys.platform == "win32":
    from ctypes import wintypes  # Windows only, older Pythons fail importing it elsewhere

    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    user32.MonitorFromRect.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]

    class _MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    def _rect(hwnd):
        """Visible frame, without the invisible resize border Windows 10/11 puts around windows."""
        rc = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rc), ctypes.sizeof(rc)):  # 9 = extended frame bounds
            user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc))
        return rc.left, rc.top, rc.right, rc.bottom

    def _ours():
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _):
            title, cls = ctypes.create_unicode_buffer(200), ctypes.create_unicode_buffer(40)
            user32.GetWindowTextW(hwnd, title, 200)
            user32.GetClassNameW(hwnd, cls, 40)
            if cls.value == "TkTopLevel" and title.value.startswith(TITLES) \
                    and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                found.append(hwnd)
            return True
        user32.EnumWindows(visit, 0)
        return found

    def _work_area(rect):
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        user32.GetMonitorInfoW(user32.MonitorFromRect(ctypes.byref(wintypes.RECT(*rect)), 2), ctypes.byref(info))
        w = info.rcWork
        return w.left, w.top, w.right, w.bottom

    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]

    def _titles(own):
        """Titles of the other instances' main windows, also minimized ones. `own` is our frame handle."""
        found, hwnd, buf = [], None, ctypes.create_unicode_buffer(500)
        while hwnd := user32.FindWindowExW(None, hwnd, "TkTopLevel", None):
            user32.GetWindowTextW(hwnd, buf, 500)
            if hwnd != own and buf.value.startswith(TITLES[0]):
                found.append(buf.value)
        return found

    def focus(pid):
        """Bring the main window of the process `pid` to the front, restored if minimized."""
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _):
            owner, title = wintypes.DWORD(), ctypes.create_unicode_buffer(500)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            user32.GetWindowTextW(hwnd, title, 500)
            if owner.value == pid and title.value.startswith(TITLES[0]):
                found.append(hwnd)
            return True
        user32.EnumWindows(visit, 0)
        for hwnd in found:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)

    def offset(frame):
        """dx, dy for the Tk window whose frame handle is `frame` (int(top.wm_frame(), 16)); None while still dragging."""
        if user32.GetAsyncKeyState(0x01) & 0x8000:  # left mouse button still down
            return None
        rect = _rect(frame)
        others = [_rect(h) for h in _ours() if h != frame]
        return snap_offset(rect, others, [_work_area(rect)])
else:
    def offset(frame):
        return 0, 0  # the window manager does this on Linux

    def _titles(own):
        return []  # no portable way to list other programs' windows

    def focus(pid):
        pass  # the window manager decides


def tab_names(title):
    """Tab names in a main window title (App._title); "Server" is the server. Also reads titles of
    versions before tabs: "eos-fight-mon – Client – Name" and "eos-fight-mon – Server"."""
    return set(title.removeprefix(TITLES[0]).removeprefix("Client – ").split(" · "))


def open_tabs(own=None):
    """Characters (and "Server") another running instance already shows."""
    return set().union(*map(tab_names, _titles(own)))
