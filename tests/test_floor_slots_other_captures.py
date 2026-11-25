"""Put on the Floor chose slot 29 while the Floor slots view listed 21 and 23 as free (live sweep 2026-11-24 23:38).
The chooser is right: it takes the lowest row of HX Edit's own IR list with nothing in it (nam_view freeSlots), and
21 and 23 hold NAM captures, though not ones of this PC's library (floor-memory: "Nobels LG 64 Deluxe 6-6-" content
57effbf1..., "MES DRECF RD Gain2 BAL O" content 4da5e182..., neither a library payload). The Floor slots view listed
only the library's captures (state.captures) and the plain IRs (state.irs, which leaves out every slot holding a
capture), so those two fell through as "free". Now they are listed (state.otherCaptures, nam_view otherCaptures) and
can be cleared like the others. No editor, no device."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import workbench  # noqa: E402
from test_focus_view import FakePane, resources  # noqa: E402
from test_workbench import NODE, run_js  # noqa: E402

CAPTURES = [{'slot': 18, 'name': 'Jcm800'}, {'slot': 127, 'name': 'Deluxe Reverb'}]
IRS = [{'slot': 1, 'name': 'York 4x12'}, {'slot': 20, 'name': 'Room'}]
OTHERS = [{'slot': 21, 'name': 'Nobels LG 64 Deluxe 6-6-'}, {'slot': 23, 'name': 'MES DRECF RD Gain2 BAL O'}]


class OtherCapturesTests(unittest.TestCase):

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_slots_view_lists_them_and_does_not_call_them_free(self):
        rows = run_js(['workbench_layout.js'], f'workbenchSlotRows({json.dumps(CAPTURES)}, {json.dumps(IRS)}, {json.dumps(OTHERS)})')
        self.assertEqual([(r['slot'], r['kind'], r['name']) for r in rows],
                         [(1, 'ir', 'York 4x12'), (18, 'capture', 'Jcm800'), (20, 'ir', 'Room'), (21, 'capture', 'Nobels LG 64 Deluxe 6-6-'),
                          (23, 'capture', 'MES DRECF RD Gain2 BAL O'), (127, 'capture', 'Deluxe Reverb')])
        used = [r['slot'] for r in rows]
        self.assertEqual(run_js(['workbench_layout.js'], f'workbenchFreeRanges({json.dumps(used)})')[:2], [[2, 17], [19, 19]])
        self.assertNotIn([21, 21], run_js(['workbench_layout.js'], f'workbenchFreeRanges({json.dumps(used)})'))
        # (a library capture wins over the same slot listed as another one; an old page without them is as before)
        rows = run_js(['workbench_layout.js'], 'workbenchSlotRows([{slot: 21, name: "Lib"}], [], [{slot: 21, name: "Other"}])')
        self.assertEqual(rows, [{'slot': 21, 'name': 'Lib', 'kind': 'capture', 'icon': '', 'gear': ''}])
        self.assertEqual(len(run_js(['workbench_layout.js'], f'workbenchSlotRows({json.dumps(CAPTURES)}, {json.dumps(IRS)})')), 4)

    def test_they_can_be_cleared(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(view.close)
        view.state = {'preset': {'setlist': 3, 'number': 32}, 'captures': CAPTURES, 'irs': IRS, 'otherCaptures': OTHERS,
                      'blocks': [{'dsp': 0, 'id': 'block0', 'model': 'HD2_AmpNAMLite', 'slot': 127}]}
        self.assertEqual(view.checked_clear({'slots': [23, 21]}), {'action': 'clear', 'slots': [21, 23]})
        self.assertIsNone(view.checked_clear({'slots': [22]}))                 # really free
        view.state['blocks'].append({'dsp': 1, 'id': 'block0', 'model': 'HD2_AmpNAMLite', 'slot': 21})
        self.assertIsNone(view.checked_clear({'slots': [21]}))                 # the loaded preset uses it

    def test_the_scripts_read_and_send_them(self):
        nam_view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        self.assertIn('otherCaptures() {', nam_view)
        self.assertIn("if (listed.has(slot) || !(Object.hasOwn(profiles, slot) || ledger.has(slot))) continue;", nam_view)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('otherCaptures = readOthers(otherCaptures);', script)
        self.assertIn('state.otherCaptures = otherCaptures;', script)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn('workbenchSlotRows(state.captures, state.irs, state.otherCaptures)', page)
        # the chooser itself is unchanged: the lowest empty row of HX Edit's IR list
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn('const slot = namView.freeSlots(AUDITION_SLOT).find(value => value >= 1 && value <= 127);', tone)


if __name__ == '__main__':
    unittest.main()
