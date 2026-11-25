"""Undo and Redo after another preset is loaded (live sweep 2026-11-24/25, owner-trials/20261124-222512-2717b7e9).

HX Edit 3.82's undo position (editor+0x294) is the index of the last step in a ring of 33 undo records (the editor's
constructor builds its undo manager at +0x270 with 32: the ring is 33 long, +0x290; recording a step sets the index to
(index + 1) % 33, Undo takes it back one, 0x2924f0). A preset load leaves the index as it was (7@3:31, 7@3:32, 10@3:31
in the sweep); HX Edit's history clear (editor vtable+0x20 = 0x504400 -> 0x291b20) empties the records and keeps the
index. The page took "index > 0" for "something to undo", so Undo stayed lit on 031 for 032's steps, and the Levels
scan's 36 steps ran the index 0..32 and round to 3. Now: HX Edit's own Edit-menu question for Undo (0x504630 with 0,
as Redo already asked it with 1), and only for steps made on this preset (workbenchOwnSteps). No editor, no device."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import NODE, run_js  # noqa: E402


@unittest.skipUnless(NODE, 'node is not installed')
class OwnStepsTests(unittest.TestCase):

    @staticmethod
    def steps(readings, size=33):
        code = '''(() => { let t = null; const out = [];
          for (const [at, preset] of %s) { t = workbenchOwnSteps(t, at, preset, %s); out.push(t.steps); }
          return out; })()''' % (json.dumps(readings), json.dumps(size))
        return run_js(['workbench_layout.js'], code)

    def test_the_sweeps_positions(self):
        # 032 from a fresh launch: the Levels scan 0 -> 32 -> 0..3, Apply and Undo last Apply to 7 (as the trace)
        scan = [[n, '3:32'] for n in range(0, 33)] + [[n, '3:32'] for n in range(0, 4)] + [[n, '3:32'] for n in (4, 5, 6, 7)]
        out = self.steps(scan)
        self.assertEqual(out[0], 0)
        self.assertEqual(out[32], 32)
        self.assertEqual(out[33], 33)                       # 32 -> 0 is one more step round the ring, not 32 undone
        self.assertEqual(out[-1], 40)
        # "Don't save", load 031, load 032: the index stays at 7, and each preset starts with no step of its own
        self.assertEqual(self.steps([[7, '3:32'], [7, '3:31'], [7, '3:32']]), [0, 0, 0])
        # 032's later edits (8, 9, 10), then 031 loaded at 10: nothing of 031's to undo
        self.assertEqual(self.steps([[7, '3:32'], [8, '3:32'], [9, '3:32'], [10, '3:32'], [10, '3:31']]), [0, 1, 2, 3, 0])

    def test_undo_and_redo_on_the_preset_itself(self):
        self.assertEqual(self.steps([[10, 'a'], [11, 'a'], [12, 'a'], [11, 'a'], [10, 'a'], [10, 'a']]), [0, 1, 2, 1, 0, 0])
        self.assertEqual(self.steps([[32, 'a'], [0, 'a'], [32, 'a']]), [0, 1, 0])          # round the ring both ways
        self.assertEqual(self.steps([[5, 'a'], [3, 'a']]), [0, 0])                          # never below 0
        self.assertEqual(self.steps([[5, 'a'], [None, 'a'], [6, 'a']]), [0, None, 0])        # unreadable: starts afresh
        self.assertEqual(self.steps([[5, 'a'], [6, ''], [7, 'a']]), [0, 1, 2])              # no header: the same preset
        self.assertEqual(self.steps([[5, 'a'], [7, 'a']], size=None), [0, 2])               # ring size not read

    def test_redo_follows_the_steps_made_here(self):
        code = '''(() => { let s = null, r = null; const out = [];
          for (const [at, preset] of %s) { s = workbenchOwnSteps(s, at, preset, 33); r = workbenchRedo(r, s.steps, s.preset, false); out.push(r.redo); }
          return out; })()'''
        run = lambda seq: run_js(['workbench_layout.js'], code % json.dumps(seq))
        # an undo on 032, then 031 loaded: no redo of 032's step offered on 031
        self.assertEqual(run([[7, '3:32'], [8, '3:32'], [7, '3:32'], [7, '3:31']]), [False, False, True, False])
        # the ring's wrap is not an undo
        self.assertEqual(run([[31, 'a'], [32, 'a'], [0, 'a'], [1, 'a']]), [False, False, False, False])

    def test_the_page_and_the_script_use_them(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("$('undo').disabled = state.undo === false || (!!ownSteps && ownSteps.steps === 0);", page)
        self.assertIn("$('redo').disabled = !((typeof state.redo === 'boolean' ? state.redo : true) && redoTrack.redo);", page)
        self.assertIn('ownSteps = workbenchOwnSteps(ownSteps, state.undoAt, preset, state.undoSize);', page)
        self.assertIn('redoTrack = workbenchRedo(redoTrack, ownSteps.steps, ownSteps.preset,', page)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertNotIn('state.undo = state.undoAt > 0', script)
        self.assertIn('state.undo = targetBinding.canUndo ? targetBinding.canUndo(editor) : null;', script)
        self.assertIn("const size = editor.add(0x290).readS32();", script)
        self.assertIn("stage: 'undo-can', undo: state.undo, redo: state.redo, at: undoWord", script)
        # (a capture add traces HX Edit's undo index before it, after it and after the refresh write: one live add made
        # two records once, 2026-11-25 00:47:20)
        self.assertIn("stage: 'add-capture-one-step', slot: command.slot, undo: [before, added, undoIndex()]", script)
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        self.assertIn("return !entry(editor, 0).isNull();", binding)
        self.assertIn('canRedo, canUndo,', binding)


if __name__ == '__main__':
    unittest.main()
