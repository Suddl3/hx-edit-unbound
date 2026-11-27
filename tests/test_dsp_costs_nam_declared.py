"""A NAM block costs the firmware's declared figure, whatever capture it plays (dsp_costs.py, v0.7.3).

The Floor's DSP meter counts the cost the firmware DECLARES for each block, not measured load (hx-unbound-floor
floor/dsp_meter.py). Nick's Floor on builder firmware 807b4dbb (NAM 3250, NAM Pedal 750), 2026-11-27: preset 032,
DSP 1 at 50% = Kinky Boost 5.1 + Deluxe Reverb 32.4. But the Workbench still showed Deluxe Reverb at "36% of DSP 1
(measured)": dsp-costs.json kept per-capture figures ("HD2_AmpNAMLite#<capture id>": 27.0 and 36.0) measured under
older firmware. Now NAM blocks are never measured, their old figures are dropped when the file is read, and every
screen and room check takes the declared figure (3250 -> 32.5 of 75, 43%; 3600 -> 36, 48%). Stock models keep their
measured figures. No editor, no device."""
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
from test_focus_view import FakePane, resources, run_js_source  # noqa: E402
from test_workbench import NODE, run_js  # noqa: E402

NAM, PEDAL = 'HD2_AmpNAMLite', 'HD2_AmpNAMPedal'
KINKY, CHORUS = 'HD2_DistKinkyBoost', 'HD2_Chorus'
JCM, DELUXE = 'a' * 64, 'b' * 64
CAPTURES = [{'slot': 18, 'id': JCM, 'name': 'Jcm800'}, {'slot': 127, 'id': DELUXE, 'name': 'Deluxe Reverb'}]
# Nick's dsp-costs.json as v0.7.2 left it (older firmware's per-capture figures)
OLD_FILE = {'costs': {NAM: 36.0, NAM + '#' + DELUXE: 27.0, NAM + '#' + JCM: 36.0, PEDAL: 7.5, KINKY: 5.1, CHORUS: 3.0}}
FW3250 = floor_firmware.FloorFirmware(nam_cost=3250, pedal=True, pedal_cost=750, source='floor')
FW3600 = floor_firmware.FloorFirmware(nam_cost=3600, source='floor')


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


class DeclaredCostTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / 'dsp-costs.json'

    def walk(self, costs, steps):
        """steps: (from, to, path 1, path 2, meter 1, meter 2): readings every half second."""
        found = []
        for start, end, path1, path2, used1, used2 in steps:
            at = start
            while at < end:
                found += costs.observe(chain(path1, path2), meter(used1, used2), at)
                at += 0.5
        return found

    def test_the_firmware_declares_what_every_nam_block_costs(self):
        self.assertEqual(FW3250.declared, {NAM: 32.5, PEDAL: 7.5})
        self.assertEqual(FW3600.declared, {NAM: 36.0})                       # (no NAM Pedal block on it)
        self.assertEqual(dsp_costs.declared_of(FW3250), {NAM: 32.5, PEDAL: 7.5})
        self.assertEqual(dsp_costs.declared_of(None), {})
        self.assertEqual(dsp_costs.NAM_ENGINES, ('HD2_AmpNAMLite', 'HD2_AmpNAMPedal'))
        import focus_view
        self.assertEqual(dsp_costs.NAM_ENGINES, tuple(focus_view.NAM_ENGINES))
        self.assertEqual((floor_firmware.NAM_SYMBOL, floor_firmware.PEDAL_SYMBOL), dsp_costs.NAM_ENGINES)

    def test_nicks_old_file_loads_without_its_nam_figures_and_is_rewritten(self):
        self.file.write_text(json.dumps(OLD_FILE), encoding='utf-8')
        costs = dsp_costs.DspCosts(self.file, None, FW3250.declared)
        self.assertEqual(costs.costs, {KINKY: 5.1, CHORUS: 3.0})            # stock models keep their measured figures
        self.assertFalse(costs.dropped)
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8'))['costs'], {KINKY: 5.1, CHORUS: 3.0})
        # every NAM block, whatever its capture: the declared figure (Deluxe Reverb is 32.5, not 27 or 36)
        for key in (NAM, NAM + '#' + DELUXE, NAM + '#' + JCM, NAM + '#' + 'c' * 64):
            self.assertEqual(costs.cost_of(key), 32.5)
        self.assertEqual(costs.cost_of(PEDAL), 7.5)
        self.assertEqual(costs.cost_of(KINKY), 5.1)
        self.assertIsNone(costs.cost_of('HD2_Nothing'))
        # on 3600 firmware the same blocks count 36; without a declared figure a NAM block's is not known
        self.assertEqual(dsp_costs.DspCosts(self.file, None, FW3600.declared).cost_of(NAM + '#' + DELUXE), 36.0)
        self.assertIsNone(dsp_costs.DspCosts(self.file, None, FW3600.declared).cost_of(PEDAL))
        self.assertIsNone(dsp_costs.DspCosts(None).cost_of(NAM))

    def test_a_file_with_nothing_stale_is_not_written(self):
        self.file.write_text(json.dumps({'costs': {KINKY: 5.1}}), encoding='utf-8')
        before = self.file.stat().st_mtime_ns
        dsp_costs.DspCosts(self.file, None, FW3250.declared)
        self.assertEqual(self.file.stat().st_mtime_ns, before)

    def test_a_nam_block_is_never_measured_nor_saved(self):
        costs = dsp_costs.DspCosts(self.file, None, FW3250.declared)
        path1 = [KINKY]
        found = self.walk(costs, [
            (0, 6, path1, [CHORUS], 5.1, 3.0),
            (6, 8, path1 + [(NAM, 127)], [CHORUS], 5.1, 3.0),                # Deluxe Reverb added on Path 1
            (8, 14, path1 + [(NAM, 127)], [CHORUS], 37.6, 3.0),
            (14, 16, path1, [CHORUS], 37.6, 3.0),                             # Undo
            (16, 22, path1, [CHORUS], 5.1, 3.0),
            (22, 24, path1, [CHORUS, (PEDAL, 18)], 5.1, 3.0),                 # a NAM Pedal block on Path 2
            (24, 30, path1, [CHORUS, (PEDAL, 18)], 5.1, 10.5),
        ])
        self.assertEqual(found, [])
        self.assertEqual(costs.costs, {})
        self.assertFalse(self.file.exists())

    def test_a_stock_model_swapped_for_a_nam_block_counts_from_its_declared_cost(self):
        costs = dsp_costs.DspCosts(None, None, FW3250.declared)
        found = self.walk(costs, [
            (0, 6, [KINKY, (NAM, 127)], [], 37.6, 0.0),
            (6, 7, [KINKY, 'HD2_AmpLine6Litigator'], [], 37.6, 0.0),          # the NAM block changed to a Litigator
            (7, 13, [KINKY, 'HD2_AmpLine6Litigator'], [], 22.1, 0.0),
        ])
        self.assertEqual(found, [('HD2_AmpLine6Litigator', 17.0)])           # 32.5 + (22.1 - 37.6)

    def test_keys_are_models(self):
        self.assertEqual(dsp_costs.key_of({'model': NAM, 'slot': 18}, CAPTURES), NAM)
        self.assertEqual(dsp_costs.key_of({'model': NAM}), NAM)
        self.assertEqual(dsp_costs.key_of({'model': CHORUS, 'slot': 18}, CAPTURES), CHORUS)
        self.assertTrue(dsp_costs.is_nam(NAM + '#' + JCM) and dsp_costs.is_nam(PEDAL) and not dsp_costs.is_nam(CHORUS))

    def test_the_pane_takes_the_copys_declared_costs_and_never_sends_nam_figures(self):
        self.file.write_text(json.dumps(OLD_FILE), encoding='utf-8')
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        res = resources(folder.name)
        floor_firmware.record(res, FW3250)                                   # the copy prepared for 3250 firmware
        view = workbench.WorkbenchView(res, process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=self.file)
        self.addCleanup(view.close)
        self.assertEqual(view.costs.declared, {NAM: 32.5, PEDAL: 7.5})
        self.assertEqual(view.costs.cost_of(NAM + '#' + DELUXE), 32.5)
        acted = []
        view.on_action = lambda name, value: acted.append((name, value))
        view._show_costs()
        self.assertEqual(acted[-1], ('costs', {KINKY: 5.1, CHORUS: 3.0}))
        # a copy prepared before records existed: the basic firmware's 36
        self.assertEqual(workbench.declared(resources(tempfile.mkdtemp(dir=folder.name))), {NAM: 36.0})
        broken = Path(tempfile.mkdtemp(dir=folder.name))
        (broken / floor_firmware.RECORD).write_text('{', encoding='utf-8')
        self.assertEqual(workbench.declared(broken), {})

    def test_costs_are_dropped_when_the_floor_answers_with_another_firmware(self):
        floor = lambda cost, pedal=False: floor_firmware.FloorFirmware(nam_cost=cost, pedal=pedal, source='floor')
        self.assertIsNone(dsp_costs.firmware_of(None))
        self.assertIsNone(dsp_costs.firmware_of(floor_firmware.FloorFirmware(source='remembered')))   # not asked now
        now = dsp_costs.firmware_of(floor(3600))
        self.assertEqual(now, {'namCost': 3600, 'pedal': False, 'pedalCost': None})
        # an old file has no firmware: kept, and from now on written with this one
        self.file.write_text(json.dumps({'costs': {KINKY: 5.1}}), encoding='utf-8')
        costs = dsp_costs.DspCosts(self.file, now)
        self.assertEqual((costs.costs, costs.dropped), ({KINKY: 5.1}, False))
        costs.costs['HD2_Delay'] = 3.3
        costs._save()
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8'))['firmware'], now)
        # the Floor did not answer this launch: kept, with the firmware they were measured on
        costs = dsp_costs.DspCosts(self.file, None)
        self.assertEqual((costs.costs, costs.firmware), ({KINKY: 5.1, 'HD2_Delay': 3.3}, now))
        # the same firmware: kept
        self.assertFalse(dsp_costs.DspCosts(self.file, dsp_costs.firmware_of(floor(3600))).dropped)
        # another one: dropped, and the file says so at once
        costs = dsp_costs.DspCosts(self.file, dsp_costs.firmware_of(floor(3250, True)))
        self.assertEqual((costs.costs, costs.dropped), ({}, True))
        saved = json.loads(self.file.read_text(encoding='utf-8'))
        self.assertEqual(saved, {'costs': {}, 'firmware': {'namCost': 3250, 'pedal': True, 'pedalCost': 750}})

    def test_the_pane_traces_a_drop_and_the_launcher_passes_the_floors_answer(self):
        self.file.write_text(json.dumps({'costs': {KINKY: 5.1}, 'firmware': {'namCost': 3600, 'pedal': False, 'pedalCost': None}}), encoding='utf-8')
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
class DeclaredScriptTests(unittest.TestCase):

    def test_the_room_checks_never_take_a_nam_blocks_measured_figure(self):
        kept = run_js(['focus_view.js'], 'focusMeasured(%s, %s)' % (json.dumps(OLD_FILE['costs']), json.dumps([NAM, PEDAL])))
        self.assertEqual(kept, {KINKY: 5.1, CHORUS: 3.0})
        kept = run_js(['focus_view.js'], 'focusMeasured(%s)' % json.dumps(OLD_FILE['costs']))    # (the engines by default)
        self.assertEqual(kept, {KINKY: 5.1, CHORUS: 3.0})
        # What a NAM block needs free and what it frees: its declared figure (3250 firmware: 32.5 of 75), even when an
        # old per-capture figure (Deluxe Reverb 27) reaches the check
        costs = json.dumps({'admit': {NAM: 32.5, 'HD2_X': 2, 'HD2_Big': 40}, 'real': {NAM + '#' + DELUXE: 27, KINKY: 5.1}})
        room = lambda used, now, then: run_js(['focus_view.js'], f'focusRoom({json.dumps({"used": used, "budget": 75})}, {costs}, '
                                                                 f'{json.dumps(now)}, {json.dumps(then)}, 0)')
        self.assertEqual(room(45.0, None, NAM + '#' + DELUXE),
                         'Not enough room on DSP 1: HX Edit needs 43% of it free for that block, and 40% is free. '
                         'Remove or change a block on Path 1 first.')
        self.assertIsNone(room(42.5, None, NAM + '#' + DELUXE))
        # changing the Deluxe Reverb block frees 32.5, not 27: a 40 block fits on a DSP at 67.5 in use
        self.assertIsNone(room(67.5, NAM + '#' + DELUXE, 'HD2_Big'))
        self.assertIsNotNone(room(67.6, NAM + '#' + DELUXE, 'HD2_Big'))

    def page_costs(self, loads, expression):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        at = page.index('const costOf = key => {')
        piece = page[at:page.index('\n// The cost key of a capture', at)]
        return run_js_source(
            'let costs = ' + json.dumps(OLD_FILE['costs']) + ';\n'
            'const catalog = {nam: ["' + NAM + '", "' + PEDAL + '"], loads: ' + json.dumps(loads) + '};\n' + piece, expression)

    def test_the_page_shows_the_declared_figure_for_every_capture(self):
        expression = (f'[costOf("{NAM}#{DELUXE}"), costOf("{NAM}#{JCM}"), costOf("{NAM}"), costOf("{PEDAL}"), costOf("{KINKY}"),'
                      f' admitOf("{NAM}"), declaredCost({{model: "{NAM}"}}), declaredCost({{model: "{KINKY}"}}),'
                      f' Math.round(100 * costOf("{NAM}#{DELUXE}") / 75)]')
        self.assertEqual(self.page_costs({NAM: 32.5, PEDAL: 7.5, KINKY: 5.0}, expression), [32.5, 32.5, 32.5, 7.5, 5.1, 32.5, True, False, 43])
        self.assertEqual(self.page_costs({NAM: 36, PEDAL: 7.5, KINKY: 5.0}, expression), [36, 36, 36, 7.5, 5.1, 36, True, False, 48])

    def test_the_page_says_a_nam_blocks_figure_is_the_same_for_every_capture(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("const cost = nam ? costOf(costKey(block)) : Number(costs[costKey(block)]);", page)       # the capture panel
        self.assertIn("(nam ? ' (the same for every capture)' : ' (measured)')", page)
        self.assertIn("const cost = costOf(costKey(block)), view = dsp && dsp[block.dsp]", page)              # Classic+'s capture line
        self.assertNotIn("costs[catalog.nam[0] + '#' + row.id]", page)                                       # the library's versions
        self.assertNotIn("share1(measured) + ' (measured)'", page)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("measured = focusMeasured(value.costs, namEngines);", script)


if __name__ == '__main__':
    unittest.main()
