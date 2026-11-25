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

    @staticmethod
    def offered(undo, redo, own, track):
        return run_js(['workbench_layout.js'], 'workbenchUndoRedo(%s, %s, %s, %s)' % tuple(json.dumps(x) for x in (undo, redo, own, track)))

    def test_hx_edits_own_answer_decides_where_it_could_be_read(self):
        # (the review of 1d3675f, PR 8: edits made in Classic, then the Workbench opened for the first time on that
        # preset: the tracker starts at 0 steps, HX Edit can undo; Undo must stay lit)
        first_sight = {'preset': '3:32', 'at': 5, 'steps': 0}
        self.assertEqual(self.offered(True, False, first_sight, {'redo': False}), {'undo': True, 'redo': False})
        # one more edit and its Undo here: HX Edit still has the Classic steps, and the one undone to redo
        self.assertEqual(self.offered(True, True, first_sight, {'redo': True}), {'undo': True, 'redo': True})
        # an edit made in Classic and undone there, the Workbench opened after: Redo is offered as HX Edit offers it
        self.assertEqual(self.offered(False, True, first_sight, {'redo': False}), {'undo': False, 'redo': True})
        # another preset loaded: HX Edit empties its history (live 2026-11-25 00:55, undo-can false/false after
        # `preset 31`); whatever the tracker says, nothing is offered
        self.assertEqual(self.offered(False, False, {'preset': '3:31', 'at': 7, 'steps': 3}, {'redo': True}), {'undo': False, 'redo': False})

    def test_the_tracker_only_where_hx_edit_could_not_be_asked(self):
        self.assertEqual(self.offered(None, None, {'steps': 0}, {'redo': False}), {'undo': False, 'redo': False})
        self.assertEqual(self.offered(None, None, {'steps': 2}, {'redo': True}), {'undo': True, 'redo': True})
        self.assertEqual(self.offered(None, None, {'steps': None}, None), {'undo': True, 'redo': False})
        self.assertEqual(self.offered(None, None, None, None), {'undo': True, 'redo': False})

    def test_the_page_and_the_script_use_them(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn('const can = workbenchUndoRedo(state.undo, state.redo, ownSteps, redoTrack);', page)
        self.assertIn("$('undo').disabled = !can.undo;", page)
        self.assertIn("$('redo').disabled = !can.redo;", page)
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


@unittest.skipUnless(NODE, 'node is not installed')
class OneStepPerChoiceTests(unittest.TestCase):
    """Classic+'s model list (and the picker): a double-click on a row, the replace gesture of Nick's Classic rule,
    asked HX Edit for the same model twice before a reading showed the first, and focus_view.js swap compared with the
    last reading: two "Change Model" steps, so the first Undo seemed to do nothing (Nick, 2026-11-25: "Classic+ feels a
    little buggy right now with undo and clicking things inside of the model picker")."""

    @staticmethod
    def repeat(asked, block, choice, now):
        return run_js(['workbench_layout.js'], 'workbenchSwapRepeat(%s, %s, %s, %s)' % tuple(json.dumps(x) for x in (asked, block, choice, now)))

    def test_the_same_choice_again_at_once_is_not_asked_again(self):
        asked = {'dsp': 0, 'id': 'block2', 'symbol': 'HD2_DistKinkyBoost', 'at': 1000}
        block = {'dsp': 0, 'id': 'block2'}
        self.assertTrue(self.repeat(asked, block, {'symbol': 'HD2_DistKinkyBoost'}, 1200))       # the double-click's second
        self.assertFalse(self.repeat(asked, block, {'symbol': 'HD2_DistMinotaur'}, 1200))        # another model: asked
        self.assertFalse(self.repeat(asked, {'dsp': 1, 'id': 'block2'}, {'symbol': 'HD2_DistKinkyBoost'}, 1200))
        self.assertFalse(self.repeat(asked, block, {'symbol': 'HD2_DistKinkyBoost'}, 2600))       # later: asked again
        self.assertFalse(self.repeat(None, block, {'symbol': 'HD2_DistKinkyBoost'}, 1200))
        cap = {'dsp': 0, 'id': 'block4', 'slot': 21, 'at': 1000}
        self.assertTrue(self.repeat(cap, {'dsp': 0, 'id': 'block4'}, {'slot': 21}, 1100))
        self.assertFalse(self.repeat(cap, {'dsp': 0, 'id': 'block4'}, {'slot': 22}, 1100))

    def test_the_page_and_the_script_ask_once(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("else if (symbol !== block.model && !workbenchSwapRepeat(swapAsked, block, {symbol}, Date.now())) {", page)
        self.assertIn("!workbenchSwapRepeat(swapAsked, block, {slot: c.slot}, Date.now())) {", page)
        # (the row clicked shows as in use at once; a refusal redraws the list as it was)
        self.assertIn("choice.classList.add('on'); choice.querySelector('i').textContent = 'in use';", page)
        self.assertIn("addFollow = null; swapAsked = null; toast(message.text);", page)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('fresh = targetBinding.peekModel(editor, block.dsp, block.id);', script)
        self.assertIn("stage: 'swap-same', action: command.action, to: next", script)


if __name__ == '__main__':
    unittest.main()
