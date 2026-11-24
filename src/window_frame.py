"""HX Edit's window frame while one of our panes covers its screen: a dark title bar.

The Workbench and Focus Mode are dark; HX Edit's title bar is Windows' own and white. While either pane is shown the
launcher asks Windows for a dark title bar in the pane's colours (DwmSetWindowAttribute on HX Edit's main window: dark
mode, and on Windows 11 the caption, text and border colours). On HX Edit's own screen it is as HX Edit made it:
``apply(False)`` undoes it. Nothing here talks to the device, and nothing is written into HX Edit.

HX Edit's menu row (File, Edit, Snapshots, Window, Help, Devices) is white too, and it stays. Taking it off the window
(SetMenu(window, None), the handle kept and given back) was tried live on 2026-11-23: with the row away HX Edit ignored
its own Save, both its Ctrl+S and its File > Save Preset command (32779) posted to the window, and saved again as soon
as the row was back. It asks its menu whether a command is allowed, so the menu has to stay on the window. A dark row
needs HX Edit's menu drawn dark inside HX Edit, or the row covered: not done here.
"""
import ctypes
from threading import Lock

# The panes' own colours (workbench.html --panel, the title's ink, --line), as Windows wants them: 0x00BBGGRR
CAPTION, TEXT, BORDER = 0x001B1614, 0x00D6CDC9, 0x00382E2A
DEFAULT_COLOUR = 0xFFFFFFFF            # DWMWA_COLOR_DEFAULT
DARK_MODE, DARK_MODE_OLD = 20, 19      # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 2004 on; 19 before that)
BORDER_COLOUR, CAPTION_COLOUR, TEXT_COLOUR = 34, 35, 36   # Windows 11
GA_ROOT = 2
FRAME_CHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020   # SWP_NOSIZE | NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED


class Win32:
    """The few Windows calls the frame needs, by handle (plain integers)."""

    def __init__(self):
        from ctypes import wintypes
        user, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        for name, result, arguments in (
                ('IsWindow', wintypes.BOOL, [wintypes.HWND]), ('GetAncestor', wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
                ('SetWindowPos', wintypes.BOOL, [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT])):
            function = getattr(user, name)
            function.restype, function.argtypes = result, arguments
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.user, self.dwm = user, dwm

    def is_window(self, window):
        return bool(window) and bool(self.user.IsWindow(window))

    def root(self, window):
        return self.user.GetAncestor(window, GA_ROOT) or window

    def attribute(self, window, attribute, value):
        """True when Windows took it (an older Windows refuses the colours)."""
        number = ctypes.c_uint32(value)
        return self.dwm.DwmSetWindowAttribute(window, attribute, ctypes.byref(number), ctypes.sizeof(number)) == 0

    def redraw(self, window):
        self.user.SetWindowPos(window, None, 0, 0, 0, 0, FRAME_CHANGED)


class WindowFrame:
    """The frame of HX Edit's main window, as the launcher wants it: apply(covered).

    covered: one of our panes is shown (a dark title bar). Asking twice changes nothing. The window is the one
    focus_view.js reports (set_window); until it is known nothing is done."""

    def __init__(self, api=None, trace=None):
        self.api = api
        self.trace = trace or (lambda value: None)
        self.window = None
        self.dark = False
        self.lock = Lock()

    def set_window(self, window):
        """HX Edit's window as its script reports it (any window of it: the frame is its top one's)."""
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            return
        with self.lock:
            if self.api is None:
                self.api = Win32()
            root = self.api.root(window)
            if root != self.window:
                self.window, self.dark = root, False

    def apply(self, covered):
        with self.lock:
            if self.api is None or not self.window or not self.api.is_window(self.window):
                return False
            api, window, covered = self.api, self.window, bool(covered)
            if covered != self.dark:
                took = api.attribute(window, DARK_MODE, 1 if covered else 0) or api.attribute(window, DARK_MODE_OLD, 1 if covered else 0)
                colours = [api.attribute(window, attribute, value if covered else DEFAULT_COLOUR)
                           for attribute, value in ((CAPTION_COLOUR, CAPTION), (TEXT_COLOUR, TEXT), (BORDER_COLOUR, BORDER))]
                api.redraw(window)
                self.dark = covered
                self.trace({'type': 'windowFrame', 'event': 'dark' if covered else 'plain', 'took': bool(took), 'colours': all(colours)})
            return True

    def restore(self):
        """HX Edit's frame as it made it (the launcher is closing)."""
        try:
            return self.apply(False)
        except Exception:              # the window has gone with HX Edit
            return False
