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
        self.place = (-8, -8, 1936, 1048)         # as a screen-filling window that is not maximized
        self.zoomed = False
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

    def rect(self, window):
        return self.place

    def is_zoomed(self, window):
        return self.zoomed

    def menu_height(self):
        return 20

    def resize(self, window, width, height):
        self.calls.append(('resize', window, width, height))
        self.place = (self.place[0], self.place[1], width, height)
        return True


class WindowFrameTests(unittest.TestCase):
    def frame(self, menu_ok=True, size=None, **options):
        self.api = FakeWindows(**options)
        self.traced, self.kept, self.darkened = [], [], []

        def kept(handle):                         # (what menu_row.js is told, with the window's menu at that moment)
            self.kept.append((handle, self.api.menu_of[100]))
        def dark(window, on):                     # (what menu_dark.js is told, and what the frame had been asked by then)
            self.darkened.append((window, on, len(self.api.calls)))
        self.now, self.sizes = [0.0], []
        frame = WindowFrame(api=self.api, trace=self.traced.append, on_kept=kept, on_dark=dark,
                            size=size, on_size=self.sizes.append, clock=lambda: self.now[0])
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

    def test_a_window_that_came_back_one_menu_row_taller_gets_its_height_back(self):
        # Seen live 2026-11-23: HX Edit saved its inside height with the row away and made the next launch's window
        # that much plus a row: 1068 where it had been 1048, over the taskbar.
        frame = self.frame(size=[-8, -8, 1936, 1048])
        self.api.place = (-8, -8, 1936, 1068)
        frame.apply(True, False)
        self.assertEqual(self.api.place, (-8, -8, 1936, 1048))
        self.assertIn({'type': 'windowFrame', 'event': 'height-back', 'took': True, 'from': 1068, 'to': 1048}, self.traced)
        self.assertEqual(self.sizes, [])                           # nothing new to keep
        self.now[0] = 60
        frame.apply(True, False)
        self.assertEqual(self.sizes, [])

    def test_only_that_one_case_is_touched(self):
        for place, zoomed in (((-8, -8, 1936, 1048), False),     # as it was
                              ((-8, -8, 1936, 1088), False),     # two rows taller: the user's own doing
                              ((-8, -8, 1900, 1068), False),     # another width
                              ((0, -8, 1936, 1068), False),      # another place
                              ((-8, -8, 1936, 1068), True)):     # maximized
            frame = self.frame(size=[-8, -8, 1936, 1048])
            self.api.place, self.api.zoomed = place, zoomed
            frame.apply(True, False)
            self.assertEqual(self.api.place, place)
            self.assertFalse([call for call in self.api.calls if call[0] == 'resize'])
        frame = self.frame()                                       # nothing kept yet: nothing to compare with
        self.api.place = (-8, -8, 1936, 1068)
        frame.apply(True, False)
        self.assertEqual(self.api.place, (-8, -8, 1936, 1068))

    def test_the_windows_size_is_kept_once_the_launch_has_settled(self):
        frame = self.frame(size=[-8, -8, 1936, 1048])
        self.api.place = (100, 80, 1400, 900)                      # the user's own size, from HX Edit's prefs
        frame.apply(True, False)
        self.assertEqual(self.sizes, [])                           # the first seconds: only the one-row check
        self.now[0] = 11
        frame.apply(True, False)
        self.assertEqual(self.sizes, [[100, 80, 1400, 900]])
        self.api.place = (100, 80, 1400, 920)                      # resized later by 20: kept, never undone
        frame.apply(True, False)
        self.assertEqual(self.sizes[-1], [100, 80, 1400, 920])
        self.assertFalse([call for call in self.api.calls if call[0] == 'resize'])
        self.api.zoomed = True
        self.api.place = (-8, -8, 1936, 1048)
        frame.apply(True, False)
        self.assertEqual(len(self.sizes), 2)                       # maximized: not kept

    def test_a_kept_size_that_is_not_one_is_ignored(self):
        for bad in (None, 'x', [1, 2, 3], [-8, -8, 1936.0, 1048], [-8, -8, 10, 10], [True, 0, 1936, 1048]):
            self.assertIsNone(WindowFrame.checked_size(bad))
        self.assertEqual(WindowFrame.checked_size([-8, -8, 1936, 1048]), (-8, -8, 1936, 1048))

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
