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

    def test_hx_edits_own_topology_word_decides_the_shape(self):
        # global @topology0/1 (as the preset files keep it: "A", "SABJ" in DIR_Relief.hlx; HX Edit.exe also names
        # "SAB" and "ABJ"). With it, an unused outputB or a stray inputB setting changes nothing.
        chain = ends(0, output_b=6, input_b=3, split=2, join=6) + blocks(0, (0, 0), (2, 1), (3, 1))
        cases = {'SABJ': ('split', 'join', None, None), 'SAB': ('split', None, None, 'XLR'),
                 'ABJ': (None, 'join', 'Aux', None), 'AB': (None, None, 'Aux', 'XLR')}
        for word, (split, join, own_in, own_out) in cases.items():
            path = run_js(['workbench_layout.js'], f'workbenchPaths({json.dumps(chain)}, {json.dumps({"inputs": INPUTS, "outputs": OUTPUTS})}, [{json.dumps(word)}, "A"])')[0]
            self.assertEqual((path['split'] or {}).get('id'), split, word)
            self.assertEqual((path['join'] or {}).get('id'), join, word)
            self.assertEqual((path['inputB'] or {}).get('name'), own_in, word)
            self.assertEqual((path['outputB'] or {}).get('name'), own_out, word)
        plain = run_js(['workbench_layout.js'], f'workbenchPaths({json.dumps(ends(0, output_b=1, input_b=3) + blocks(0, (0, 0)))}, {{}}, ["A", "A"])')[0]
        self.assertIsNone(plain['b'])
        for word in ('SABJ', 'SAB', 'ABJ', 'AB', 'A'):
            self.assertIsNotNone(run_js(['workbench_layout.js'], f'workbenchShape({json.dumps(word)})'))
        for word in ('', 'SA', 'AJ', 'X', None, 3):
            self.assertIsNone(run_js(['workbench_layout.js'], f'workbenchShape({json.dumps(word)})'))
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("targetBinding.peekGlobal(editor, 'global', '@topology' + dsp)", script)

    def test_redo_is_offered_only_after_an_undo_until_a_new_change(self):
        steps = '''(() => { let t = null; const out = [];
          for (const [at, preset, redoing] of %s) { t = workbenchRedo(t, at, preset, redoing); out.push(t.redo); }
          return out; })()'''
        run = lambda seq: run_js(['workbench_layout.js'], steps % json.dumps(seq))
        # 3 changes, an undo, a redo asked for, an undo, a new change
        self.assertEqual(run([[3, 'a', False], [2, 'a', False], [3, 'a', True], [2, 'a', False], [3, 'a', False]]),
                         [False, True, False, True, False])
        # two undos and a new change: nothing to redo after it
        self.assertEqual(run([[4, 'a', False], [2, 'a', False], [3, 'a', False]]), [False, True, False])
        # another preset starts afresh; an unknown position leaves the button on
        self.assertEqual(run([[4, 'a', False], [3, 'a', False], [0, 'b', False]]), [False, True, False])
        self.assertEqual(run([[None, 'a', False]]), [True])
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("$('redo').disabled = !redoTrack.redo;", page)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('state.undoAt = editor.add(0x294).readS32();', script)

    def pending(self, chain, change):
        return run_js(['workbench_layout.js'], f'workbenchPending({json.dumps(chain)}, {json.dumps(change)}, "HD2_AmpNAMLite")')

    def test_a_change_asked_for_shows_at_once_until_hx_edits_reading_has_it(self):
        chain = blocks(0, (0, 0), (3, 0))
        # a move: the block stands at its new place, also while HX Edit reads it in neither place
        shown = self.pending(chain, {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 1, 'place': 5})
        self.assertFalse(shown['settled'])
        self.assertEqual([(b['id'], b['position'], b['path']) for b in shown['blocks']], [('block0', 0, 0), ('block1', 5, 1)])
        between = self.pending(chain[:1], {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 1, 'place': 5, 'block': chain[1]})
        self.assertFalse(between['settled'])                                   # HX Edit has it in neither place for a moment
        self.assertEqual([(b['id'], b['position'], b['path']) for b in between['blocks']], [('block0', 0, 0), ('block1', 5, 1)])
        renamed = chain[:1] + [dict(chain[1], id='block7', position=5, path=1)]
        self.assertTrue(self.pending(renamed, {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 1, 'place': 5, 'block': chain[1]})['settled'])
        self.assertTrue(self.pending(chain[:1], {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 1, 'place': 5})['settled'])
        moved = [chain[0], dict(chain[1], position=5, path=1)]
        self.assertTrue(self.pending(moved, {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 1, 'place': 5})['settled'])
        # a move to the other path: shown there at once; settled once a copy is there and the block is gone from its own
        across = {'action': 'move', 'dsp': 0, 'id': 'block1', 'lane': 0, 'place': 2, 'to': 1, 'block': chain[1]}
        shown = self.pending(chain, across)
        self.assertFalse(shown['settled'])
        self.assertEqual([(b['dsp'], b['id'], b['position'], b['path']) for b in shown['blocks']], [(0, 'block0', 0, 0), (1, 'pending', 2, 0)])
        drawn = run_js(['workbench_layout.js'], f'workbenchPaths({json.dumps(shown["blocks"])}, {{}}, ["A", "A"])[1].a[2]')
        self.assertEqual(drawn['id'], 'pending')                                # the chain draws it there
        copy = dict(chain[1], dsp=1, id='block0', position=2, path=0)
        both = self.pending(chain + [copy], across)                           # pasted, not removed yet
        self.assertFalse(both['settled'])
        self.assertEqual([(b['dsp'], b['id']) for b in both['blocks']], [(0, 'block0'), (1, 'pending')])
        self.assertTrue(self.pending(chain[:1] + [copy], across)['settled'])
        # a removal: gone at once
        shown = self.pending(chain, {'action': 'remove', 'dsp': 0, 'id': 'block0'})
        self.assertEqual([b['id'] for b in shown['blocks']], ['block1'])
        self.assertTrue(self.pending(chain[1:], {'action': 'remove', 'dsp': 0, 'id': 'block0'})['settled'])
        # a capture added: shown with its capture, also while HX Edit has the NAM block on IR slot 1
        add = {'action': 'add', 'dsp': 0, 'lane': 0, 'place': 6, 'slot': 17}
        shown = self.pending(chain, add)
        self.assertEqual(shown['blocks'][-1], {'dsp': 0, 'id': 'pending', 'model': 'HD2_AmpNAMLite', 'position': 6, 'path': 0, 'enabled': True, 'slot': 17})
        early = chain + [{'dsp': 0, 'id': 'block2', 'model': 'HD2_AmpNAMLite', 'position': 6, 'path': 0, 'enabled': True, 'slot': 1}]
        shown = self.pending(early, add)
        self.assertFalse(shown['settled'])
        self.assertEqual((shown['blocks'][-1]['id'], shown['blocks'][-1]['slot'], len(shown['blocks'])), ('block2', 17, 3))
        self.assertTrue(self.pending(early[:2] + [dict(early[2], slot=17)], add)['settled'])
        model = {'action': 'add', 'dsp': 0, 'lane': 0, 'place': 6, 'symbol': 'HD2_X'}
        self.assertTrue(self.pending(early[:2] + [dict(early[2], model='HD2_X')], model)['settled'])
        self.assertTrue(self.pending(chain, None)['settled'])

    def test_a_drag_opens_nothing_and_offers_a_parallel_lane_by_a_dotted_branch(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        lift = page[page.index('function liftBlock('):page.index('const BRANCH_DROP')]
        self.assertNotIn("style.height = '218px'", lift)                        # no path opens a second row
        self.assertNotIn("style.visibility = 'visible'", lift)
        self.assertIn("laneBranch(near && near.dataset.lane === '0' && !near.closest('.grid8').dataset.two ? near : null)", lift)
        branch = page[page.index('function laneBranch('):page.index('function splitFormat(')]
        self.assertIn("el('div', 'slot spot lane-drop', '+')", branch)          # its circle is a place like the others
        self.assertIn("drop.dataset.lane = '1'", branch)                         # dropped on: lane B at that place
        self.assertIn('laneBranch(null);', lift)                                 # gone when the drag ends
        self.assertNotIn('lane-tab', page)

    def test_a_redraw_moves_the_pictures_already_showing(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn('reusable = gather(board);', page)
        self.assertIn('reusable = gather(panel);', page)
        self.assertIn("const paths = workbenchPaths(shownBlocks(), catalog, state.topology);", page)
        for action in ('move', 'remove', 'add'):
            self.assertIn(f"chainAsk('{action}', ", page)

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


class ChainChangeTests(unittest.TestCase):
    """Stage 2: a block added on an empty place, removed, or moved to an empty place of its own path."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe')
        self.addCleanup(self.view.close)
        self.view.state = {'blocks': [{'dsp': 0, 'id': 'inputA', 'model': 'HD2_In', 'enabled': True},
                                      {'dsp': 0, 'id': 'block0', 'model': 'HD2_DelayTest', 'position': 0, 'path': 0, 'enabled': True},
                                      {'dsp': 0, 'id': 'block1', 'model': 'HD2_DelayOther', 'position': 3, 'path': 1, 'enabled': True},
                                      {'dsp': 1, 'id': 'block0', 'model': 'HD2_DelayWide', 'position': 0, 'path': 0, 'enabled': True}],
                           'captures': [{'slot': 17, 'name': 'Klon', 'icon': ''}]}

    def test_a_block_is_added_only_on_an_empty_place_with_a_model_of_the_picker_or_a_capture_on_the_floor(self):
        add = self.view.checked_add
        self.assertEqual(add({'dsp': 0, 'lane': 0, 'place': 1, 'symbol': 'HD2_DelayWide'}),
                         {'action': 'add', 'dsp': 0, 'lane': 0, 'place': 1, 'symbol': 'HD2_DelayWide'})
        self.assertEqual(add({'dsp': 1, 'lane': 1, 'place': 7, 'slot': 17}), {'action': 'add', 'dsp': 1, 'lane': 1, 'place': 7, 'slot': 17})
        for refused in ({'dsp': 0, 'lane': 0, 'place': 0, 'symbol': 'HD2_DelayWide'},          # taken
                        {'dsp': 0, 'lane': 1, 'place': 3, 'slot': 17},                          # taken (lane B)
                        {'dsp': 0, 'lane': 0, 'place': 1, 'symbol': 'HD2_In'},                  # not a model of the picker
                        {'dsp': 0, 'lane': 0, 'place': 1, 'symbol': 'HD2_AmpNAMLite'},          # the NAM engine comes with a capture
                        {'dsp': 0, 'lane': 0, 'place': 1, 'slot': 18},                          # not on the Floor
                        {'dsp': 0, 'lane': 0, 'place': 1, 'slot': 17, 'symbol': 'HD2_DelayWide'},
                        {'dsp': 0, 'lane': 2, 'place': 1, 'slot': 17}, {'dsp': 0, 'lane': 0, 'place': 8, 'slot': 17},
                        {'dsp': True, 'lane': 0, 'place': 1, 'slot': 17}, {'dsp': 2, 'lane': 0, 'place': 1, 'slot': 17}, None):
            self.assertIsNone(add(refused), refused)

    def test_only_a_block_of_the_chain_is_removed(self):
        self.assertEqual(self.view.checked_remove({'dsp': 0, 'id': 'block1'}), {'action': 'remove', 'dsp': 0, 'id': 'block1'})
        for refused in ({'dsp': 0, 'id': 'inputA'}, {'dsp': 1, 'id': 'block1'}, {'dsp': 0}, None):
            self.assertIsNone(self.view.checked_remove(refused))

    def test_a_block_moves_only_to_an_empty_place_of_its_own_path(self):
        move = self.view.checked_move
        self.assertEqual(move({'dsp': 0, 'id': 'block0', 'lane': 1, 'place': 0}), {'action': 'move', 'dsp': 0, 'id': 'block0', 'lane': 1, 'place': 0})
        self.assertEqual(move({'dsp': 0, 'id': 'block1', 'lane': 0, 'place': 7})['place'], 7)
        for refused in ({'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 0},     # where it is
                        {'dsp': 0, 'id': 'block0', 'lane': 1, 'place': 3},     # taken
                        {'dsp': 1, 'id': 'block0', 'lane': 0, 'place': 0},     # taken, other path's block
                        {'dsp': 0, 'id': 'inputA', 'lane': 0, 'place': 2},
                        {'dsp': 0, 'id': 'block0', 'lane': 0, 'place': -1}):
            self.assertIsNone(move(refused), refused)
        self.assertIsNone(move({'dsp': 1, 'id': 'block0', 'lane': 0, 'place': 0}))

    def test_a_block_moves_to_an_empty_place_of_the_other_path(self):
        move = self.view.checked_move
        self.assertEqual(move({'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': 1}),
                         {'action': 'move', 'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': 1})
        self.assertEqual(move({'dsp': 1, 'id': 'block0', 'lane': 1, 'place': 0, 'to': 0})['to'], 0)
        # "to" its own path is an ordinary move
        self.assertNotIn('to', move({'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': 0}))
        for refused in ({'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 0, 'to': 1},      # taken on the other path
                        {'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': 2},
                        {'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': True},
                        {'dsp': 0, 'id': 'block0', 'lane': 0, 'place': 4, 'to': '1'},
                        {'dsp': 0, 'id': 'inputA', 'lane': 0, 'place': 4, 'to': 1}):
            self.assertIsNone(move(refused), refused)

    def test_the_native_calls_are_hx_edits_own_entries_and_only_for_a_block_of_the_chain(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        remove = binding[binding.index('function removeBlock'):binding.index('function moveBlock')]
        move = binding[binding.index('function moveBlock'):binding.index('return { capture, read')]
        self.assertIn("editorEntry(editor, 0xb0, 0x514bc0, 'remove-block')", remove)
        self.assertIn("editorEntry(editor, 0xa0, 0x5123c0, 'move-block')", move)
        for body in (remove, move):
            self.assertIn(r'/^block\d{1,2}$/.test(blockName)', body)
            self.assertIn('0x80000000', body)
        self.assertIn('col < 0 || col > 7', move)
        self.assertIn('if (!entry.equals(base.add(rva)))', binding)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        change = script[script.index('function change(command)'):script.index('function followAdd(')]
        self.assertLess(change.index('focusRoom('), change.index('targetBinding.addModel('))          # room checked first
        self.assertLess(change.rindex('occupied('), change.index('targetBinding.moveBlock('))         # still empty
        # the other path: still empty and with room, then HX Edit's own copy, paste and removal as one undo step
        self.assertLess(change.rindex('occupied('), change.index('targetBinding.moveAcross('))
        self.assertLess(change.rindex('focusRoom('), change.index('targetBinding.moveAcross('))
        across = binding[binding.index('function moveAcross'):binding.index('return { capture, read')]
        for entry in ("0xb8, 0x5034b0, 'copy-block'", "0xc8, 0x500320, 'can-paste'", "0xc4, 0x513620, 'paste'",
                      "0xb0, 0x514bc0, 'remove-block'", "0xd4, 0x4ffa80, 'undo-open'", "0xd8, 0x5044b0, 'undo-close'"):
            self.assertIn('editorEntry(editor, ' + entry + ')', across)
        self.assertIn('fromDsp === toDsp', across)
        self.assertIn("copy(editor, 2, fromDsp, name)", across)                    # the drag's store, not the clipboard
        self.assertLess(across.index('canPaste(editor, 2, toDsp, cell, 0)'), across.index('open(editor, 0x80000000)'))
        self.assertLess(across.index('paste(editor, 2, toDsp, cell, 0x100)'), across.index('remove(editor, fromDsp, name, 0)'))
        # the paste takes the block from its own path; removed only if a reading after the paste still has it there
        self.assertIn('const left = result >= 0 ? peekModel(editor, fromDsp, blockName) : null;', across)
        self.assertIn('if (left && model && left.model === model.model) result = remove(editor, fromDsp, name, 0);', across)
        self.assertIn('finally {\n        close(editor, result);', across)        # the undo step is always closed
        # lane B of a one-lane path: pasted on an empty place of lane A, then moved down inside the same undo step
        self.assertIn('if (result < 0 && row === 1) {', across)
        self.assertIn("if (taken.includes('0:' + place)) continue;", across)
        self.assertLess(across.index('open(editor, 0x80000000)'), across.index('result = move(editor, toDsp, madeName, down, 0)'))
        self.assertIn("editorEntry(editor, 0xa0, 0x5123c0, 'move-block')", across)
        self.assertIn("send({type: 'dspNotice', text: 'HX Edit did not make that change.'})", script)   # a refusal is told
        self.assertIn('targetBinding.setIndex(editor, made.dsp, made.id, follow.slot)', script)         # a capture is never left on slot 1
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'add': view.checked_add, 'remove': view.checked_remove, 'move': view.checked_move", launcher)


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
        self.assertEqual((script.count('targetBinding.setModel('), script.count('targetBinding.setIndex(')), (1, 2))   # (a swap; a capture added)


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
        asked = set(re.findall(r"(?:ask|chainAsk)\('([a-zA-Z]+)'", page + (ROOT / 'pane_controls.js').read_text(encoding='utf-8')))
        self.assertEqual(asked, {'select', 'set', 'model', 'capture', 'snapshot', 'preset', 'undo', 'redo', 'save', 'menu', 'add', 'remove', 'move'})


if __name__ == '__main__':
    unittest.main()
