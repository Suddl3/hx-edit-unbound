"""Before the reveal (Nick's review of the merged build, 2026-11-25; BACKLOG.md "Before the reveal", list A).

Each test names its item. No editor, no device: the page's and the scripts' own text, and their pure parts in node."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import NODE, run_js  # noqa: E402


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def between(whole, start, end):
    at = whole.index(start)
    return whole[at:whole.index(end, at + len(start))]


class ToneStripTests(unittest.TestCase):
    def test_a1_the_strip_under_the_title_has_no_logo_of_its_own(self):
        # (three logos on a diagonal: the window's icon, the layout chooser's logo and the strip's old X logo)
        browser = text('tone_browser.cs')
        bar = between(browser, '// The banner over the site', 'Controls.Add(targetBar);')
        self.assertNotIn('PictureBox', bar)
        self.assertNotIn('Icon.ToBitmap()', browser)
        self.assertIn('targetBar.Controls.Add(targetLabel);', bar)
        # popped out, the window itself still says what it is: its title and HX Edit Unbound's icon
        self.assertIn('floatingHost = new Form { Text = Text, Icon = Icon,', browser)
        self.assertIn('Text = "TONE3000 · HX Edit Unbound";', browser)


if __name__ == '__main__':
    unittest.main()
