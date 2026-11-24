"""HX Edit's window frame while a pane covers its screen (window_frame.py): a dark title bar, and back.
A made-up Windows: no window is touched."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))

import window_frame  # noqa: E402
from window_frame import BORDER_COLOUR, CAPTION_COLOUR, DARK_MODE, DARK_MODE_OLD, DEFAULT_COLOUR, TEXT_COLOUR, WindowFrame  # noqa: E402


class FakeWindows:
    """A top window (100) with a child (7)."""

    def __init__(self, colours=True, dark=True):
        self.windows = {100}
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

    def redraw(self, window):
        self.calls.append(('redraw', window))


class WindowFrameTests(unittest.TestCase):
    def frame(self, **options):
        self.api = FakeWindows(**options)
        self.traced = []
        frame = WindowFrame(api=self.api, trace=self.traced.append)
        frame.set_window(7)                       # (any window of HX Edit's: the frame is its top one's)
        return frame

    def test_nothing_is_done_until_the_window_is_known(self):
        api = FakeWindows()
        frame = WindowFrame(api=api)
        self.assertFalse(frame.apply(True))
        frame.set_window(None)
        frame.set_window(True)
        frame.set_window(0)
        self.assertFalse(frame.apply(True))
        self.assertEqual(api.calls, [])

    def test_a_pane_shown_gets_a_dark_title_bar_in_its_colours(self):
        frame = self.frame()
        self.assertTrue(frame.apply(True))
        self.assertEqual(self.api.attributes, {DARK_MODE: 1, CAPTION_COLOUR: window_frame.CAPTION, TEXT_COLOUR: window_frame.TEXT,
                                               BORDER_COLOUR: window_frame.BORDER})
        self.assertTrue(all(call[1] == 100 for call in self.api.calls))            # only the top window, never the child
        self.assertEqual(self.traced, [{'type': 'windowFrame', 'event': 'dark', 'took': True, 'colours': True}])

    def test_asking_twice_changes_nothing(self):
        frame = self.frame()
        frame.apply(True)
        done = len(self.api.calls)
        frame.apply(True)
        self.assertEqual(len(self.api.calls), done)

    def test_hx_edits_own_screen_gets_its_title_bar_back(self):
        frame = self.frame()
        frame.apply(True)
        frame.apply(False)
        self.assertEqual(self.api.attributes, {DARK_MODE: 0, CAPTION_COLOUR: DEFAULT_COLOUR, TEXT_COLOUR: DEFAULT_COLOUR, BORDER_COLOUR: DEFAULT_COLOUR})
        self.assertEqual(self.traced[-1]['event'], 'plain')

    def test_the_menu_row_is_never_taken_off_the_window(self):
        # Tried live 2026-11-23: with its menu off the window HX Edit ignores its own Save (Ctrl+S and command 32779).
        source = (ROOT / 'window_frame.py').read_text(encoding='utf-8')
        self.assertNotIn('user.SetMenu', source)
        self.assertNotIn("'SetMenu'", source)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('frame.apply(focus_on[0] or workbench_on[0])', launcher)
        self.assertNotIn('menuBar', launcher)

    def test_an_older_windows_gets_what_it_takes(self):
        frame = self.frame(colours=False, dark=False)
        self.assertTrue(frame.apply(True))
        self.assertEqual(self.api.attributes, {DARK_MODE_OLD: 1})
        self.assertEqual(self.traced[0], {'type': 'windowFrame', 'event': 'dark', 'took': True, 'colours': False})

    def test_the_window_gone_with_hx_edit_is_left_alone(self):
        frame = self.frame()
        frame.apply(True)
        self.api.windows.clear()
        done = len(self.api.calls)
        self.assertFalse(frame.restore())
        self.assertEqual(len(self.api.calls), done)

    def test_another_window_starts_afresh(self):
        frame = self.frame()
        frame.apply(True)
        self.api.windows.add(200)
        frame.set_window(200)
        self.assertEqual((frame.window, frame.dark), (200, False))


if __name__ == '__main__':
    unittest.main()
