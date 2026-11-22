"""The Workbench (Unbound menu > Workbench): the chain drawn from a preset's routing, what the page draws with beyond
Focus Mode's catalog, the pane's driver, and the wiring. No editor process, no device."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus_view  # noqa: E402
import workbench  # noqa: E402
from dsp_meter import DspMeter  # noqa: E402
from test_focus_view import NODE, FakePane, resources, run_js  # noqa: E402


def setUpModule():
    # As Focus Mode's tests: what this PC has unzipped into art/ must not change them.
    from unittest.mock import patch
    local = patch.object(focus_view, 'LOCAL_ART', {})
    local.start()
    unittest.addModuleCleanup(local.stop)


INPUTS = ['None', 'Multi (Guitar, Aux, Variax)', 'Guitar', 'Aux', 'Variax', 'Variax Magnetics', 'Mic']
OUTPUTS = ['None', 'Multi (1/4", XLR, Digital, USB 1/2)', 'Path 2A', 'Path 2B', 'Path 2A+B', '1/4"', 'XLR']


def ends(dsp, input_a=1, output_a=1, input_b=0, output_b=0, split=0, join=8, mix=(0.0, 0.0)):
    """A DSP's inputs, outputs, split and join as focusSnapshot reads them."""
    return [{'dsp': dsp, 'id': 'inputA', 'model': 'HD2_AppDSPFlow1Input', 'enabled': True, 'input': input_a},
            {'dsp': dsp, 'id': 'inputB', 'model': 'HD2_AppDSPFlow2Input', 'enabled': True, 'input': input_b},
            {'dsp': dsp, 'id': 'outputA', 'model': 'HD2_AppDSPFlowOutput', 'enabled': True, 'output': output_a},
            {'dsp': dsp, 'id': 'outputB', 'model': 'HD2_AppDSPFlowOutput', 'enabled': True, 'output': output_b},
            {'dsp': dsp, 'id': 'split', 'model': 'HD2_AppDSPFlowSplitY', 'enabled': True, 'position': split,
             'values': {'BalanceA': .5, 'BalanceB': .5}},
            {'dsp': dsp, 'id': 'join', 'model': 'HD2_AppDSPFlowJoin', 'enabled': True, 'position': join,
             'values': {'A Level': mix[0], 'B Level': mix[1]}}]


def blocks(dsp, *places):
    """Blocks of a chain: (place, lane) pairs, lane 1 = lane B."""
    return [{'dsp': dsp, 'id': f'block{index}', 'model': 'HD2_X', 'position': place, 'path': lane, 'enabled': True}
            for index, (place, lane) in enumerate(places)]


@unittest.skipUnless(NODE, 'node is not installed')
class ChainTests(unittest.TestCase):
    """Every routing of mockup-B-path-shapes.png, and the ones a real preset has (research/modern-ui)."""

    def paths(self, chain):
        return run_js(['workbench_layout.js'], f'workbenchPaths({json.dumps(chain)}, {json.dumps({"inputs": INPUTS, "outputs": OUTPUTS})})')

    @staticmethod
    def lanes(path):
        def ids(lane):
            return None if lane is None else [b['id'] if b else None for b in lane]
        return ids(path['a']), ids(path['b'])

    def test_a_plain_preset_is_one_lane_whatever_its_unused_lane_b_output_says(self):
        # HX Edit's own new preset keeps outputB on Multi with no lane B at all (res/default_preset.hlx).
        first, second = self.paths(ends(0, output_b=1) + blocks(0, (0, 0), (1, 0)) + ends(1, input_a=0, output_b=1))
        self.assertEqual(self.lanes(first), (['block0', 'block1', None, None, None, None, None, None], None))
        self.assertEqual((first['split'], first['join'], first['inputB'], first['outputB']), (None, None, None, None))
        self.assertEqual((first['input']['name'], first['output']['name']), ('Multi', 'Multi'))
        self.assertTrue(second['empty'])
        self.assertEqual(second['input']['name'], 'None')

    def test_a_split_and_a_mixer_bound_lane_b(self):
        # The real preset on this PC with a lane B (DIR_Relief.hlx): split at 1, join at 6, lane B on places 1 to 4.
        chain = ends(0, split=1, join=6, mix=(0.0, -3.0)) + blocks(0, (0, 0), (1, 1), (2, 1), (3, 1), (4, 1), (5, 0))
        path = self.paths(chain)[0]
        self.assertEqual(self.lanes(path), (['block0', None, None, None, None, 'block5', None, None],
                                            [None, 'block1', 'block2', 'block3', 'block4', None, None, None]))
        self.assertEqual((path['from'], path['to']), (1, 6))
        self.assertEqual((path['split']['id'], path['join']['id']), ('split', 'join'))
        self.assertIsNone(path['inputB'])
        self.assertIsNone(path['outputB'])
        self.assertEqual(run_js(['workbench_layout.js'], f'workbenchMixNote({json.dumps(chain[5])}).replace("\u2212", "-")'),
                         'A 0.0 dB, B -3.0 dB')                                  # (a true minus sign in the page)
        self.assertEqual(run_js(['workbench_layout.js'], f'workbenchSplitNote({json.dumps(chain[4])}, () => "?")'), 'evenly to lanes A and B')

    def test_two_outputs_the_mixer_dragged_down(self):
        path = self.paths(ends(0, input_a=2, output_a=5, output_b=6, split=2, join=8) + blocks(0, (0, 0), (1, 0), (2, 0), (2, 1), (3, 1)))[0]
        self.assertEqual((path['from'], path['to']), (2, 8))
        self.assertEqual(path['split']['id'], 'split')
        self.assertIsNone(path['join'])
        self.assertEqual((path['output']['name'], path['outputB']['name']), ('1/4"', 'XLR'))
        self.assertEqual(path['input']['name'], 'Guitar')

    def test_two_inputs_the_split_dragged_down(self):
        path = self.paths(ends(0, input_a=2, input_b=3, join=4) + blocks(0, (0, 0), (1, 0), (4, 0), (0, 1), (1, 1)))[0]
        self.assertEqual((path['from'], path['to']), (0, 4))
        self.assertIsNone(path['split'])
        self.assertEqual(path['join']['id'], 'join')
        self.assertEqual((path['input']['name'], path['inputB']['name']), ('Guitar', 'Aux'))
        self.assertIsNone(path['outputB'])

    def test_two_separate_lanes(self):
        path = self.paths(ends(0, input_a=2, input_b=6, output_a=5, output_b=6) + blocks(0, (0, 0), (1, 0), (0, 1), (3, 1)))[0]
        self.assertEqual((path['from'], path['to']), (0, 8))
        self.assertEqual((path['split'], path['join']), (None, None))
        self.assertEqual((path['inputB']['name'], path['outputB']['name']), ('Mic', 'XLR'))

    def test_a_lane_b_mixed_back_before_the_end_keeps_its_mixer_whatever_outputb_says(self):
        path = self.paths(ends(0, output_b=1, split=0, join=3) + blocks(0, (0, 0), (1, 1)))[0]
        self.assertEqual(path['join']['id'], 'join')
        self.assertIsNone(path['outputB'])

    def test_path_2_fed_by_path_1_says_so(self):
        for output, lanes in ((2, ('Path 1', None)), (3, ('None', 'Path 1')), (4, ('Path 1', 'Path 1'))):
            second = self.paths(ends(0, output_a=output) + blocks(0, (0, 0)) + ends(1, input_a=0) + blocks(1, (0, 0)))[1]
            self.assertEqual(second['input']['name'], lanes[0])
            self.assertEqual(second['inputB']['name'] if second['inputB'] else None, lanes[1])
        first = self.paths(ends(0, output_a=2) + ends(1, input_a=0))[0]
        self.assertEqual(first['output']['name'], 'Path 2A')

    def test_a_lane_b_block_outside_the_split_and_the_mixer_is_still_drawn(self):
        path = self.paths(ends(0, split=3, join=5) + blocks(0, (1, 1), (6, 1)))[0]
        self.assertEqual((path['from'], path['to']), (1, 7))
        self.assertEqual(self.lanes(path)[1][1], 'block0')
        self.assertEqual(self.lanes(path)[1][6], 'block1')

    def test_the_script_reads_where_inputs_and_outputs_go_and_the_split_and_mixer_settings(self):
        reader = '''(() => { const values = {
            "0|inputA|@model": "HD2_AppDSPFlow1Input", "0|inputA|@input": 2, "0|outputB|@model": "HD2_AppDSPFlowOutput", "0|outputB|@output": 6,
            "0|join|@model": "HD2_AppDSPFlowJoin", "0|join|@position": 6, "0|join|A Level": 0, "0|join|B Level": -3,
            "0|split|@model": "HD2_AppDSPFlowSplitY", "0|split|@position": 1, "0|split|BalanceA": 0.5 };
          return (dsp, place, key) => values[dsp + "|" + place + "|" + key]; })()'''
        parameters = {'HD2_AppDSPFlowJoin': ['A Level', 'B Level', 'Level'], 'HD2_AppDSPFlowSplitY': ['BalanceA', 'BalanceB']}
        state = run_js(['focus_view.js'], f'focusSnapshot({reader}, null, {json.dumps(parameters)}, [])')
        found = {b['id']: b for b in state['blocks']}
        self.assertEqual(found['inputA']['input'], 2)
        self.assertEqual(found['outputB']['output'], 6)
        self.assertEqual((found['split']['position'], found['split']['values']), (1, {'BalanceA': .5}))
        self.assertEqual(found['join']['values'], {'A Level': 0, 'B Level': -3})
        self.assertNotIn('values', found['inputA'])


class CatalogTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.res = resources(self.folder.name)
        controls = json.loads((self.res / 'HelixControls.json').read_text(encoding='utf-8'))
        controls.update(input_type={'isDiscrete': True, 'format': INPUTS}, output_type={'isDiscrete': True, 'format': OUTPUTS})
        (self.res / 'HelixControls.json').write_text(json.dumps(controls), encoding='utf-8')

    def test_the_page_gets_each_models_dsp_cost_and_hx_edits_names_for_inputs_and_outputs(self):
        extra = workbench.extras(self.res)
        self.assertEqual(extra['loads']['HD2_DelayOther'], 30.0)
        self.assertEqual((extra['inputs'][2], extra['outputs'][6]), ('Guitar', 'XLR'))
        self.assertEqual(extra['captureTabs']['Amp'], ['NAM Amp', 'NAM Amp + cab'])
        kinds = {kind for kind, _ in focus_view.NAM_KINDS}
        self.assertTrue(all(set(tabs) <= kinds for tabs in extra['captureTabs'].values()))

    def test_the_names_are_empty_lists_when_hx_edits_file_lacks_them(self):
        (self.res / 'HelixControls.json').write_text('{}', encoding='utf-8')
        self.assertEqual(workbench.route_names(self.res), {'inputs': [], 'outputs': []})

    def test_the_workbench_is_shown_at_launch_only_once_it_was_switched_on(self):
        self.assertFalse(workbench.setting_on({}))
        self.assertFalse(workbench.setting_on({'workbench': False}))
        self.assertFalse(workbench.setting_on(None))
        self.assertTrue(workbench.setting_on({'workbench': True}))

    def test_the_menu_offers_only_hx_edits_own_screen_focus_mode_and_the_launchers_tools(self):
        for choice in ('classic', 'focus', 'level', 'look', 'library'):
            self.assertEqual(workbench.WorkbenchView.checked_menu(choice), choice)
        for other in ('chainArt', 'irDots', 'exit', None, 3, 'workbench'):
            self.assertIsNone(workbench.WorkbenchView.checked_menu(other))
        self.assertTrue(set(workbench.TOOLS) <= set(DspMeter.CHOICES))


class PaneDriverTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.panes, self.actions = [], []

        def factory(command, **options):
            self.panes.append(FakePane(command, **options))
            return self.panes[-1]
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=factory, exe='FocusView.exe',
                                            on_action=lambda name, value: self.actions.append((name, value)))
        self.addCleanup(self.view.close)

    def wait(self, test):
        deadline = time.time() + 3
        while time.time() < deadline:
            if test():
                return True
            time.sleep(.01)
        return False

    def lines(self, prefix):
        return [json.loads(line[2:]) for line in self.panes[0].lines if line.startswith(prefix + ' ')]

    def test_it_is_focus_modes_pane_with_its_own_page_and_profile(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.assertTrue(self.wait(lambda: self.panes))
        command = self.panes[0].command
        self.assertEqual(command[3], 'https://app.focus.example/workbench.html')
        self.assertTrue(command[2].endswith('Workbench WebView'))

    def test_the_page_gets_the_catalog_with_the_extras_and_the_menus_state(self):
        self.view.show_options({'level': True})
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: any(m.get('type') == 'options' for m in self.lines('P'))))
        sent = {m['type']: m for m in self.lines('P')}
        self.assertIn('loads', sent['catalog']['catalog'])
        self.assertIn('lists', sent['catalog']['catalog'])                     # Focus Mode's own catalog under it
        self.assertEqual(sent['options']['options'], {'level': True})

    def test_requests_are_checked_as_focus_modes_are(self):
        self.view.receive({'type': 'focusState', 'state': {'blocks': [{'dsp': 0, 'id': 'block0', 'model': 'HD2_DelayTest', 'enabled': True}],
                                                            'selected': {'dsp': 0, 'id': 'block0'}, 'values': {}, 'snapshots': ['A', 'B'],
                                                            'preset': {'setlist': 0, 'number': 5, 'name': 'X'}}})
        self.assertTrue(self.wait(lambda: self.view.state is not None))
        self.assertEqual(self.view.checked_set({'dsp': 0, 'id': 'block0', 'key': 'Mix', 'value': 7, 'phase': 'single'})['value'], 1.0)
        self.assertIsNone(self.view.checked_set({'dsp': 0, 'id': 'block0', 'key': 'Nope', 'value': 1, 'phase': 'single'}))
        self.assertEqual(self.view.checked_snapshot(1), {'action': 'snapshot', 'index': 1})
        self.assertEqual(self.view.checked_model({'dsp': 0, 'id': 'block0', 'symbol': 'HD2_DelayOther'})['symbol'], 'HD2_DelayOther')


@unittest.skipUnless(NODE, 'node is not installed')
class ScriptTests(unittest.TestCase):
    def test_the_script_reads_while_either_pane_is_shown(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        want = script[script.index('function want(pane, value)'):script.index('function listen()')]
        self.assertIn('wants.focus || wants.workbench', want)
        self.assertIn("value.pane === 'workbench' ? 'workbench' : 'focus'", script)   # Focus Mode's own messages carry no pane
        self.assertIn("targetBinding.peekGlobal(editor, 'global', '@tempo')", script)
        # Still only values, a model, a capture, a snapshot and a click on the chain are ever written.
        self.assertEqual(script.count('targetBinding.setValue('), 4)
        self.assertEqual((script.count('targetBinding.setModel('), script.count('targetBinding.setIndex(')), (1, 1))


class WiringTests(unittest.TestCase):
    def test_the_launcher_shows_one_pane_at_a_time_and_keeps_the_choice(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ('from workbench import WorkbenchView, setting_on', 'shown = workbench_on[0] and not focus_on[0]',
                      "script.post({'type': 'focusMode', 'payload': {'pane': 'workbench', 'on': shown}})",
                      "nam_catalog.save_setting('workbench', on)", 'workbench.receive(payload)', 'workbench.close()',
                      "elif name == 'workbench':", 'pane_request(workbench, workbench_on[0] and not focus_on[0], name, value)',
                      "meter.set_chain_option('focusMode', focus_on[0] or workbench_on[0])", 'for step in after_resume:'):
            self.assertIn(piece, launcher)
        # Focus Mode's "Editor" button comes back to the Workbench: focus_mode places it after itself.
        focus_mode = launcher[launcher.index('            def focus_mode(on, notice=None):'):launcher.index('            def focus_load(')]
        self.assertIn('workbench_show()', focus_mode)
        # A tool of the menu opens on HX Edit's own screen: the Workbench steps aside first.
        action = launcher[launcher.index('            def workbench_action(name, value):'):launcher.index('            if focus is not None:\n                focus.on_action')]
        self.assertLess(action.index('workbench_mode(False)\n                        unbound_choice(choice)'), len(action))

    def test_the_classic_screens_menu_has_the_way_back(self):
        self.assertIn('workbench', DspMeter.CHOICES)
        helper = (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8')
        tools = helper[helper.index('public static readonly Tuple<string,string>[] Choices'):helper.index('static readonly string[] Tips')]
        self.assertIn('Tuple.Create("Workbench (the modern screen)", "workbench")', tools)

    def test_save_is_hx_edits_own_key(self):
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('if ((string)name == "save") { PressInEditor(0x53, false); return; }', pane)

    def test_the_package_carries_the_page_its_scripts_and_the_driver(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('build_windows', ROOT / 'build-windows.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('workbench.py', 'workbench.html', 'workbench_layout.js', 'pane_controls.js'):
            self.assertIn(name, module.APP_FILES)
            self.assertTrue((ROOT / name).is_file())

    def test_the_page_is_local_and_asks_only_for_what_the_launcher_checks(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertNotIn('http://', page)
        self.assertEqual(page.count('https://'), 0)
        self.assertNotIn('localStorage', page)
        for script in ('<script src="pane_controls.js"></script>', '<script src="workbench_layout.js"></script>'):
            self.assertIn(script, page)
        import re
        asked = set(re.findall(r"ask\('([a-zA-Z]+)'", page + (ROOT / 'pane_controls.js').read_text(encoding='utf-8')))
        self.assertEqual(asked, {'select', 'set', 'model', 'capture', 'snapshot', 'preset', 'undo', 'redo', 'save', 'menu'})


if __name__ == '__main__':
    unittest.main()
