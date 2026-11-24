"""HX Edit's window frame while a pane covers its screen (window_frame.py): a dark title bar, the menu row away and
back. A made-up Windows: no window is touched."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))

import window_frame  # noqa: E402
from window_frame import BORDER_COLOUR, CAPTION_COLOUR, DARK_MODE, DARK_MODE_OLD, DEFAULT_COLOUR, TEXT_COLOUR, WindowFrame  # noqa: E402


class FakeWindows:
    """A top window (100) with a child (7) and HX Edit's menu (55)."""

    def __init__(self, colours=True, dark=True):
        self.windows = {100}
        self.menus = {55}
        self.menu_of = {100: 55}
        self.attributes = {}
        self.calls = []
        self.colours, self.dark = colours, dark

    def is_window(self, window):
        return window in self.windows

    def root(self, window):
        return 100 if window == 7 else window

    def attribute(self, window, attribute, value):
        self.calls.append(('attribute', window, attribute, value))
        if attribute in (BORDER_COLOUR, CAPTION_COLOUR, TEXT_COLOUR) and not self.colours:
            return False
        if attribute == DARK_MODE and not self.dark:
            return False
        self.attributes[attribute] = value
        return True

    def menu(self, window):
        return self.menu_of.get(window, 0)

    def is_menu(self, menu):
        return menu in self.menus

    def set_menu(self, window, menu):
        self.calls.append(('menu', window, menu))
        self.menu_of[window] = menu
        return True

    def redraw(self, window):
        self.calls.append(('redraw', window))


class WindowFrameTests(unittest.TestCase):
    def frame(self, menu_ok=True, **options):
        self.api = FakeWindows(**options)
        self.traced, self.kept, self.darkened = [], [], []

        def kept(handle):                         # (what menu_row.js is told, with the window's menu at that moment)
            self.kept.append((handle, self.api.menu_of[100]))
        def dark(window, on):                     # (what menu_dark.js is told, and what the frame had been asked by then)
            self.darkened.append((window, on, len(self.api.calls)))
        frame = WindowFrame(api=self.api, trace=self.traced.append, on_kept=kept, on_dark=dark)
        frame.set_window(7)                       # (any window of HX Edit's: the frame is its top one's)
        frame.allow_menu(menu_ok)
        return frame

    def test_nothing_is_done_until_the_window_is_known(self):
        api = FakeWindows()
        frame = WindowFrame(api=api)
        frame.allow_menu(True)
        self.assertFalse(frame.apply(True, False))
        frame.set_window(None)
        frame.set_window(True)
        frame.set_window(0)
        self.assertFalse(frame.apply(True, False))
        self.assertEqual(api.calls, [])

    def test_a_pane_shown_gets_a_dark_title_bar_and_the_menu_row_away(self):
        frame = self.frame()
        self.assertTrue(frame.apply(True, False))
        self.assertEqual(self.api.attributes, {DARK_MODE: 1, CAPTION_COLOUR: window_frame.CAPTION, TEXT_COLOUR: window_frame.TEXT,
                                               BORDER_COLOUR: window_frame.BORDER})
        self.assertEqual(self.api.menu_of[100], 0)
        self.assertEqual(frame.kept, 55)
        self.assertTrue(all(call[1] == 100 for call in self.api.calls))            # only the top window, never the child

    def test_the_row_stays_until_hx_edits_script_stands_in_for_it(self):
        # Seen live 2026-11-23: with its menu simply off the window HX Edit ignores its own Save (menu_row.js).
        frame = self.frame(menu_ok=False)
        frame.apply(True, False)
        self.assertEqual(self.api.attributes[DARK_MODE], 1)                        # the title bar is dark all the same
        self.assertEqual(self.api.menu_of[100], 55)
        self.assertEqual(self.kept, [])
        frame.allow_menu(True)                                                     # "menuRow" ready
        frame.apply(True, False)
        self.assertEqual(self.api.menu_of[100], 0)

    def test_the_script_hears_which_menu_before_the_row_goes_and_after_it_is_back(self):
        frame = self.frame()
        frame.apply(True, False)
        self.assertEqual(self.kept, [(55, 55)])                                    # told while the menu is still on the window
        frame.apply(False, False)
        self.assertEqual(self.kept, [(55, 55), (0, 55)])                           # and "none" once it is back

    def test_the_menu_rows_own_drawing_hears_first(self):
        # menu_dark.js draws the row dark inside HX Edit: it is told before the frame is asked to redraw, and once
        frame = self.frame()
        frame.apply(True, True)
        frame.apply(True, True)
        self.assertEqual(self.darkened, [(100, True, 0)])
        frame.apply(False, True)
        self.assertEqual([(window, on) for window, on, _ in self.darkened], [(100, True), (100, False)])

    def test_asking_twice_changes_nothing(self):
        frame = self.frame()
        frame.apply(True, False)
        done = len(self.api.calls)
        frame.apply(True, False)
        self.assertEqual(len(self.api.calls), done)
        self.assertEqual(len(self.kept), 1)

    def test_hx_edits_own_screen_gets_both_back_as_they_were(self):
        frame = self.frame()
        frame.apply(True, False)
        frame.apply(False, False)
        self.assertEqual(self.api.attributes, {DARK_MODE: 0, CAPTION_COLOUR: DEFAULT_COLOUR, TEXT_COLOUR: DEFAULT_COLOUR, BORDER_COLOUR: DEFAULT_COLOUR})
        self.assertEqual(self.api.menu_of[100], 55)
        self.assertEqual(frame.kept, 0)

    def test_the_switch_keeps_the_menu_row_under_a_dark_title_bar(self):
        frame = self.frame()
        frame.apply(True, True)
        self.assertEqual(self.api.menu_of[100], 55)
        self.assertEqual(self.api.attributes[DARK_MODE], 1)
        frame.apply(True, False)                   # switched off in the Workbench's menu: away
        self.assertEqual(self.api.menu_of[100], 0)
        frame.apply(True, True)                    # and on again: back, the same menu
        self.assertEqual(self.api.menu_of[100], 55)
        self.assertEqual([call for call in self.api.calls if call[0] == 'menu'], [('menu', 100, 0), ('menu', 100, 55)])

    def test_a_menu_hx_edit_set_meanwhile_is_the_one_kept(self):
        frame = self.frame()
        frame.apply(True, False)
        self.api.menus.add(66)
        self.api.menu_of[100] = 66                 # HX Edit set a menu itself (its Devices menu) while its row was away
        frame.apply(True, False)
        self.assertEqual(self.api.menu_of[100], 0)
        self.assertEqual(self.kept[-1][0], 66)     # menu_row.js hears of the newer one
        frame.apply(False, False)
        self.assertEqual(self.api.menu_of[100], 66)

    def test_a_menu_that_has_gone_is_not_given_back(self):
        frame = self.frame()
        frame.apply(True, False)
        self.api.menus.clear()
        frame.apply(False, False)
        self.assertEqual(self.api.menu_of[100], 0)
        self.assertEqual(frame.kept, 0)
        self.assertEqual(self.traced[-1], {'type': 'windowFrame', 'event': 'menu-back', 'took': False})

    def test_an_older_windows_gets_what_it_takes(self):
        frame = self.frame(colours=False, dark=False)
        self.assertTrue(frame.apply(True, False))
        self.assertEqual(self.api.attributes, {DARK_MODE_OLD: 1})
        self.assertEqual(self.traced[0], {'type': 'windowFrame', 'event': 'dark', 'took': True, 'colours': False})

    def test_the_window_gone_with_hx_edit_is_left_alone(self):
        frame = self.frame()
        frame.apply(True, False)
        self.api.windows.clear()
        done = len(self.api.calls)
        self.assertFalse(frame.restore())
        self.assertEqual(len(self.api.calls), done)

    def test_another_window_starts_afresh(self):
        frame = self.frame()
        frame.apply(True, False)
        self.api.windows.add(200)
        frame.set_window(200)
        self.assertEqual((frame.window, frame.dark, frame.kept), (200, False, 0))


if __name__ == '__main__':
    unittest.main()
