"""HX Edit's window frame while one of our panes covers its screen: a dark title bar, and its menu row put away.

The Workbench and Focus Mode are dark; HX Edit's title bar and its menu row (File, Edit, Snapshots, Window, Help,
Devices) are Windows' own and white. While either pane is shown the launcher asks Windows for a dark title bar in the
pane's colours and takes the menu row off the window. On HX Edit's own screen both are as HX Edit made them.

Two things are asked of Windows, both on HX Edit's main window, both undone by ``apply(False, ...)``:

  DwmSetWindowAttribute   the title bar: dark mode, and on Windows 11 the caption, text and border colours
  SetMenu                 the menu row: the window's own menu handle is kept here and given back as it was;
                          the menu itself is never changed or freed

The menu row is only taken off once HX Edit's script can stand in for it (menu_row.js, ``allow_menu``): HX Edit runs a
menu command only when it finds it in its window's menu, so with the row simply off it ignored its own Save (seen live
2026-11-23: Ctrl+S and File > Save Preset both did nothing). menu_row.js hands HX Edit the kept menu for that one
lookup; ``on_kept`` tells it which menu that is, before the row goes and after it is back.
The Workbench's menu has a switch ("Show HX Edit's menu bar", settings.json "workbenchMenuBar") for the menus
themselves (Preferences, Command Center, Global EQ, Help). Nothing here talks to the device.
"""
import ctypes
from threading import Lock

MENU_BAR = 'workbenchMenuBar'          # settings.json: True keeps HX Edit's menu row while a pane is shown

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
                ('GetMenu', wintypes.HMENU, [wintypes.HWND]), ('SetMenu', wintypes.BOOL, [wintypes.HWND, wintypes.HMENU]),
                ('IsMenu', wintypes.BOOL, [wintypes.HMENU]),
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

    def menu(self, window):
        return self.user.GetMenu(window) or 0

    def is_menu(self, menu):
        return bool(menu) and bool(self.user.IsMenu(menu))

    def set_menu(self, window, menu):
        return bool(self.user.SetMenu(window, menu or None))

    def redraw(self, window):
        self.user.SetWindowPos(window, None, 0, 0, 0, 0, FRAME_CHANGED)


class WindowFrame:
    """The frame of HX Edit's main window, as the launcher wants it: apply(covered, menu_bar).

    covered: one of our panes is shown (a dark title bar; the menu row away unless menu_bar, and only once
    allow_menu(True) said HX Edit's script stands in for it). Asking twice changes nothing. The window is the one
    focus_view.js reports (set_window); until it is known nothing is done.
    on_kept(handle): the menu taken off the window (0: none), for menu_row.js."""

    def __init__(self, api=None, trace=None, on_kept=None):
        self.api = api
        self.trace = trace or (lambda value: None)
        self.on_kept = on_kept or (lambda handle: None)
        self.window = None
        self.dark = False
        self.kept = 0                  # HX Edit's own menu handle while its row is away
        self.menu_ok = False           # menu_row.js is in place: HX Edit finds its commands without the row
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
                self.window, self.dark, self.kept = root, False, 0

    def allow_menu(self, on):
        """Whether the menu row may be taken off: only while menu_row.js stands in for it."""
        with self.lock:
            self.menu_ok = bool(on)

    def apply(self, covered, menu_bar):
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
            now = api.menu(window)
            if covered and not menu_bar and self.menu_ok:
                if now:                # (also a menu HX Edit set again meanwhile: that one is kept from now on)
                    self.kept = now
                    self.on_kept(now)  # menu_row.js first: no command meets a window without its menu
                    if not api.set_menu(window, 0):
                        self.kept = 0
                        self.on_kept(0)
                    self.trace({'type': 'windowFrame', 'event': 'menu-away', 'took': bool(self.kept)})
            elif not now and self.kept:
                took = api.is_menu(self.kept) and api.set_menu(window, self.kept)
                self.trace({'type': 'windowFrame', 'event': 'menu-back', 'took': bool(took)})
                self.kept = 0
                self.on_kept(0)
            return True

    def restore(self):
        """HX Edit's frame as it made it (the launcher is closing)."""
        try:
            return self.apply(False, True)
        except Exception:              # the window has gone with HX Edit
            return False
