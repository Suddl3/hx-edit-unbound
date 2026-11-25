"""Each view shows only its own status (live sweep 2026-11-24): after Levels' "Undone: 1 preset(s) are back as they
were." the same line showed under the NAM library's Put on the Floor / Preview buttons. Levels and the library share
one session (tone_preview), whose status text stays the last one said until another is, and the page showed it in
both. Now a text belongs to the page the session was on when it first came. No editor, no device."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import NODE, run_js  # noqa: E402

UNDONE = 'Undone: 1 preset(s) are back as they were.'


@unittest.skipUnless(NODE, 'node is not installed')
class StatusPerViewTests(unittest.TestCase):

    def shown(self, statuses):
        """statuses: [text, page] as the session sends them; what Levels and the library show after each."""
        code = '''(() => { let t = null; const out = [];
          for (const [text, page] of %s) { t = workbenchStatusOwner(t, text, page); out.push([workbenchStatusFor(t, 'level'), workbenchStatusFor(t, 'library')]); }
          return out; })()''' % json.dumps(statuses)
        return run_js(['workbench_layout.js'], code)

    def test_the_sweep_levels_undo_then_the_library(self):
        out = self.shown([[UNDONE, 'level'],
                          [UNDONE, 'library'],                       # the session moved to the library, same text again
                          [UNDONE, 'library'],
                          ['Loaded into User IR 29; verifying capture content. Preset remains unsaved.', 'library'],
                          ['Loaded into User IR 29; verifying capture content. Preset remains unsaved.', 'level']])
        self.assertEqual(out[0], [UNDONE, ''])
        self.assertEqual(out[1], [UNDONE, ''])                               # Levels' line stays Levels', not the library's
        self.assertEqual(out[2], [UNDONE, ''])
        loaded = 'Loaded into User IR 29; verifying capture content. Preset remains unsaved.'
        self.assertEqual(out[3], ['', loaded])
        self.assertEqual(out[4], ['', loaded])                               # back in Levels: the library's, not shown there
        self.assertEqual(self.shown([[None, 'level'], ['', 'library']]), [['', ''], ['', '']])

    def test_the_page_uses_it(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("statusOwner = workbenchStatusOwner(statusOwner, data.text, typeof data.levelPage === 'boolean' ? (data.levelPage ? 'level' : 'library') : sessionPage);", page)
        self.assertIn("levelText = workbenchStatusFor(statusOwner, 'level');", page)
        self.assertIn("floorStatus = {...data, text: workbenchStatusFor(statusOwner, 'library')};", page)
        self.assertNotIn('levelText = data.text', page)
        self.assertNotIn('floorStatus = data;', page)


if __name__ == '__main__':
    unittest.main()
