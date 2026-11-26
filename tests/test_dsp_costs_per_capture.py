"""One DSP cost per capture (dsp_costs.py): every NAM capture is the one model HD2_AmpNAMLite, and the live sweep of
2026-11-24 measured two captures at different costs on the same Floor (owner-trials/20261124-222512-2717b7e9: at
23:33:31 "dsp-cost-held HD2_AmpNAMLite 36.0, kept 27.0", at 23:33:49 "dsp-cost 36.0"): Jcm800 (User IR 18) 36.0 and
Deluxe Reverb (User IR 127) 27.0. One figure for both made the page show Deluxe Reverb at 48% of DSP 1 instead of
36%. Now a NAM block playing a capture of the library is keyed by that capture's library id. No editor, no device."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dsp_costs  # noqa: E402
import floor_firmware  # noqa: E402
import workbench  # noqa: E402
from test_focus_view import FakePane, resources  # noqa: E402
from test_workbench import NODE, run_js  # noqa: E402

NAM = 'HD2_AmpNAMLite'
JCM, DELUXE = 'a' * 64, 'b' * 64
CAPTURES = [{'slot': 18, 'id': JCM, 'name': 'Jcm800'}, {'slot': 127, 'id': DELUXE, 'name': 'Deluxe Reverb'}]


def chain(path1, path2, captures=CAPTURES, preset=32):
    """path1 / path2: models, or (model, slot) for a NAM block."""
    blocks = []
    for dsp, models in ((0, path1), (1, path2)):
        for k, m in enumerate(models):
            model, slot = m if isinstance(m, tuple) else (m, None)
            blocks.append({'dsp': dsp, 'id': 'block%d' % k, 'model': model, **({'slot': slot} if slot else {})})
    return {'preset': {'setlist': 3, 'number': preset}, 'blocks': blocks, 'captures': captures}


def meter(used1, used2):
    return [{'used': used1, 'budget': 75}, {'used': used2, 'budget': 75}]


class PerCaptureTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / 'dsp-costs.json'

    def walk(self, costs, steps):
        """steps: (from, to, path 1, path 2, meter 1, meter 2[, captures]): readings every half second."""
        found = []
        for start, end, path1, path2, used1, used2, *more in steps:
            at = start
            while at < end:
                found += costs.observe(chain(path1, path2, *more), meter(used1, used2), at)
                at += 0.5
        return found

    def test_the_sweep_two_captures_keep_their_own_costs(self):
        costs = dsp_costs.DspCosts(self.file)
        costs.costs = {NAM: 27.0, NAM + '#' + DELUXE: 27.0, 'HD2_DistKinkyBoost': 5.1}
        kinky = ('HD2_DistKinkyBoost', None)
        path1 = [kinky, (NAM, 127)]
        found = self.walk(costs, [
            (0, 6, path1, ['HD2_Chorus'], 32.1, 3.0),
            (6, 8, path1, ['HD2_Chorus', (NAM, 18)], 32.1, 3.0),          # Jcm800 dragged onto a "+" of Path 2
            (8, 14, path1, ['HD2_Chorus', (NAM, 18)], 32.1, 39.0),
            (14, 16, path1, ['HD2_Chorus'], 32.1, 39.0),                  # Undo
            (16, 22, path1, ['HD2_Chorus'], 32.1, 3.0),
        ])
        self.assertEqual(found, [(NAM + '#' + JCM, 36.0), (NAM + '#' + JCM, 36.0)])
        self.assertEqual(costs.held, [])                                    # a new capture is not held against another's
        self.assertEqual(costs.cost_of(NAM + '#' + DELUXE), 27.0)          # Deluxe Reverb keeps its own 27.0
        self.assertEqual(costs.cost_of(NAM + '#' + JCM), 36.0)
        self.assertEqual(costs.cost_of(NAM + '#' + 'c' * 64), 36.0)         # one not measured: the model's, the newest
        self.assertEqual(costs.cost_of('HD2_Nothing'), None)
        saved = json.loads(self.file.read_text(encoding='utf-8'))['costs']
        self.assertEqual(saved[NAM + '#' + DELUXE], 27.0)
        self.assertEqual(saved[NAM + '#' + JCM], 36.0)
        self.assertEqual(saved[NAM], 36.0)

    def test_the_dead_meter_rules_hold_per_capture(self):
        costs = dsp_costs.DspCosts(self.file)
        costs.costs = {NAM + '#' + JCM: 36.0, NAM: 27.0}
        path2 = ['HD2_Chorus', (NAM, 18)]
        # a far figure for Jcm800 is held until a second agrees, whatever the model's own figure is
        found = self.walk(costs, [
            (0, 6, ['HD2_Boost'], path2, 10.0, 39.0),
            (6, 7, ['HD2_Boost'], ['HD2_Chorus'], 10.0, 39.0),
            (7, 13, ['HD2_Boost'], ['HD2_Chorus'], 10.0, 9.0),             # 30.0: held (kept 36.0)
        ])
        self.assertEqual(found, [])
        self.assertEqual(costs.costs[NAM + '#' + JCM], 36.0)
        found = self.walk(costs, [(13, 14, ['HD2_Boost'], path2, 10.0, 9.0), (14, 20, ['HD2_Boost'], path2, 10.0, 39.0)])
        self.assertEqual(found, [(NAM + '#' + JCM, 30.0)])                  # the second agreed
        # never more than the path's total that had it: a Remove whose meter fell to 0 with a block left is the meter
        costs2 = dsp_costs.DspCosts(None)
        found = self.walk(costs2, [
            (0, 6, [], path2, 0.0, 39.0),
            (6, 7, [], ['HD2_Chorus'], 0.0, 39.0),
            (7, 13, [], ['HD2_Chorus'], 0.0, 0.0),
        ])
        self.assertEqual(found, [])
        # told the device is gone: nothing for LOST_QUIET seconds
        costs3 = dsp_costs.DspCosts(None)
        self.walk(costs3, [(0, 6, [], path2, 0.0, 39.0)])
        costs3.lost(6)
        found = self.walk(costs3, [(6, 7, [], ['HD2_Chorus'], 0.0, 39.0), (7, 20, [], ['HD2_Chorus'], 0.0, 3.0)])
        self.assertEqual(found, [])

    def test_a_capture_known_on_one_reading_only_is_the_same_block(self):
        # (after a chain change HX Edit re-checks the slots: for a moment a NAM block's capture is not known)
        costs = dsp_costs.DspCosts(None)
        costs.costs = {NAM: 27.0, NAM + '#' + JCM: 36.0}
        path2 = ['HD2_Chorus', (NAM, 18)]
        found = self.walk(costs, [
            (0, 6, [], path2, 0.0, 39.0),
            (6, 8, [], path2, 0.0, 39.0, []),                              # the slot list re-read: nothing known
            (8, 9, [], path2, 0.0, 39.0),                                  # known again
            (9, 10, [], ['HD2_Chorus', (NAM, 18), 'HD2_Delay'], 0.0, 39.0, []),   # a delay added while not known
            (10, 16, [], ['HD2_Chorus', (NAM, 18), 'HD2_Delay'], 0.0, 42.3, []),
        ])
        self.assertEqual(found, [('HD2_Delay', 3.3)])
        self.assertEqual(dsp_costs.difference(dsp_costs.Counter({NAM: 1}), dsp_costs.Counter({NAM + '#' + JCM: 1})),
                         (dsp_costs.Counter(), dsp_costs.Counter()))

    def test_another_capture_on_the_same_block_counts_once_the_old_one_is_known(self):
        costs = dsp_costs.DspCosts(None)
        costs.costs = {NAM + '#' + JCM: 36.0}
        found = self.walk(costs, [
            (0, 6, [], [(NAM, 18)], 0.0, 36.0),
            (6, 7, [], [(NAM, 127)], 0.0, 36.0),                          # Change capture: Deluxe Reverb
            (7, 13, [], [(NAM, 127)], 0.0, 27.0),
        ])
        self.assertEqual(found, [(NAM + '#' + DELUXE, 27.0)])
        costs = dsp_costs.DspCosts(None)
        costs.costs = {NAM: 36.0}                                           # only the model's figure: not a measure
        found = self.walk(costs, [(0, 6, [], [(NAM, 18)], 0.0, 36.0), (6, 7, [], [(NAM, 127)], 0.0, 36.0),
                                  (7, 13, [], [(NAM, 127)], 0.0, 27.0)])
        self.assertEqual(found, [])

    def test_keys(self):
        self.assertEqual(dsp_costs.key_of({'model': NAM, 'slot': 18}, CAPTURES), NAM + '#' + JCM)
        self.assertEqual(dsp_costs.key_of({'model': NAM, 'slot': 19}, CAPTURES), NAM)          # not a library capture
        self.assertEqual(dsp_costs.key_of({'model': NAM}, CAPTURES), NAM)
        self.assertEqual(dsp_costs.key_of({'model': NAM, 'slot': 18}, [{'slot': 18, 'id': 'not-hex'}]), NAM)
        self.assertEqual(dsp_costs.base(NAM + '#' + JCM), NAM)

    def test_an_old_file_still_loads_and_bad_keys_are_dropped(self):
        self.file.write_text(json.dumps({'costs': {NAM: 36.0, 'HD2_DelaySimpleDelay': 3.3, NAM + '#' + JCM: 36.0,
                                                   NAM + '#nothex': 3.0, 'x': 2.0}}), encoding='utf-8')
        costs = dsp_costs.DspCosts(self.file)
        self.assertEqual(costs.costs, {NAM: 36.0, 'HD2_DelaySimpleDelay': 3.3, NAM + '#' + JCM: 36.0})
        self.assertFalse(costs.dropped)

    def test_costs_are_dropped_when_the_floor_answers_with_another_firmware(self):
        floor = lambda cost, pedal=False: floor_firmware.FloorFirmware(nam_cost=cost, pedal=pedal, source='floor')
        self.assertIsNone(dsp_costs.firmware_of(None))
        self.assertIsNone(dsp_costs.firmware_of(floor_firmware.FloorFirmware(source='remembered')))   # not asked now
        now = dsp_costs.firmware_of(floor(3600))
        self.assertEqual(now, {'namCost': 3600, 'pedal': False, 'pedalCost': None})
        # an old file has no firmware: kept, and from now on written with this one
        self.file.write_text(json.dumps({'costs': {NAM: 36.0}}), encoding='utf-8')
        costs = dsp_costs.DspCosts(self.file, now)
        self.assertEqual((costs.costs, costs.dropped), ({NAM: 36.0}, False))
        costs.costs['HD2_Delay'] = 3.3
        costs._save()
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8'))['firmware'], now)
        # the Floor did not answer this launch: kept, with the firmware they were measured on
        costs = dsp_costs.DspCosts(self.file, None)
        self.assertEqual((costs.costs, costs.firmware), ({NAM: 36.0, 'HD2_Delay': 3.3}, now))
        # the same firmware: kept
        self.assertFalse(dsp_costs.DspCosts(self.file, dsp_costs.firmware_of(floor(3600))).dropped)
        # another one: dropped, and the file says so at once
        costs = dsp_costs.DspCosts(self.file, dsp_costs.firmware_of(floor(3250, True)))
        self.assertEqual((costs.costs, costs.dropped), ({}, True))
        saved = json.loads(self.file.read_text(encoding='utf-8'))
        self.assertEqual(saved, {'costs': {}, 'firmware': {'namCost': 3250, 'pedal': True, 'pedalCost': 750}})

    def test_the_pane_traces_a_drop_and_the_launcher_passes_the_floors_answer(self):
        self.file.write_text(json.dumps({'costs': {NAM: 36.0}, 'firmware': {'namCost': 3600, 'pedal': False, 'pedalCost': None}}), encoding='utf-8')
        traced = []
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe',
                                       costs_file=self.file, trace=traced.append,
                                       firmware={'namCost': 3250, 'pedal': False, 'pedalCost': None})
        self.addCleanup(view.close)
        self.assertEqual(view.costs.costs, {})
        self.assertIn('dsp-costs-dropped', [t.get('event') for t in traced])
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('firmware=dsp_costs.firmware_of(FLOOR_SEEN))', launcher)


@unittest.skipUnless(NODE, 'node is not installed')
class PerCaptureScriptTests(unittest.TestCase):

    def test_the_room_checks_take_a_captures_own_cost_else_its_models(self):
        kept = run_js(['focus_view.js'], 'focusMeasured(%s)' % json.dumps({NAM: 36, NAM + '#' + JCM: 36, NAM + '#' + DELUXE: 27,
                                                                             NAM + '#xyz': 3, 'bad name#' + JCM: 3}))
        self.assertEqual(kept, {NAM: 36, NAM + '#' + JCM: 36, NAM + '#' + DELUXE: 27})
        captures = json.dumps(CAPTURES)
        self.assertEqual(run_js(['focus_view.js'], f'focusCostKey("{NAM}", 127, {captures})'), NAM + '#' + DELUXE)
        self.assertEqual(run_js(['focus_view.js'], f'focusCostKey("{NAM}", 5, {captures})'), NAM)
        self.assertEqual(run_js(['focus_view.js'], f'focusCostKey("HD2_Chorus", null, {captures})'), 'HD2_Chorus')
        # What a NAM block needs free is HX Edit's own figure (the firmware's 36), whatever the capture uses on the
        # meter (Deluxe Reverb 27): live 2026-11-26 12:53, HX Edit refused it at 42.2 used (-8611). What a NAM block
        # replaced or moved frees is its own measured figure.
        costs = json.dumps({'admit': {NAM: 36, 'HD2_X': 2}, 'real': {NAM: 27, NAM + '#' + DELUXE: 27}})
        view = json.dumps({'used': 42.2, 'budget': 75})
        self.assertEqual(run_js(['focus_view.js'], f'focusRoom({view}, {costs}, null, "{NAM}#{DELUXE}", 0)'),
                         'Not enough room on DSP 1: HX Edit needs 48% of it free for that block, and 44% is free. '
                         'Remove or change a block on Path 1 first.')
        self.assertIsNone(run_js(['focus_view.js'], f'focusRoom({json.dumps({"used": 25.2, "budget": 75})}, {costs}, null, "{NAM}#{DELUXE}", 0)'))
        self.assertIsNone(run_js(['focus_view.js'], f'focusRoom({json.dumps({"used": 70, "budget": 75})}, {costs}, "{NAM}#{DELUXE}", "HD2_X", 0)'))

    def test_the_script_and_the_page_look_costs_up_by_capture(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('focusCostKey(block.model, block.slot, onFloor)', script)
        self.assertIn("command.slot && !command.symbol ? focusCostKey(next, command.slot, onFloor) : next", script)
        self.assertIn("...(typeof capture.id === 'string' ? {id: capture.id} : {})", script)
        nam_view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        self.assertIn("result.push({slot, id: typeof capture.id === 'string' ? capture.id : null,", nam_view)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("cost = Number(costs[costKey(block)]);", page)                   # the panel: its own figure only
        self.assertIn("cost = isNam(block) ? 0 : costOf(captureKey(c)), need = isNam(block) ? 0 : admitOf(catalog.nam[0]);", page)   # the picker's captures
        self.assertIn("left: view.budget - view.used + (costOf(costKey(block)) || 0)", page)   # Room on DSP
        self.assertIn("Number(costs[catalog.nam[0] + '#' + row.id])", page)              # the library's "% of a DSP"
        self.assertNotIn('costs[block.model]', page)
        self.assertNotIn('costOf(block.model)', page)


if __name__ == '__main__':
    unittest.main()
