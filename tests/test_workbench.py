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
        self.assertIn("const oneLane = item => item.dataset.lane === '0' && !item.closest('.grid8').dataset.two;", lift)
        # an empty place of a one-lane path, or a block of its lane A (the dragged one too) where its model fits
        self.assertIn("laneBranch(near ? (oneLane(near) ? near : null) : over && oneLane(over) && fitsOn(block, Number(over.dataset.dsp)) ? over : null);", lift)
        self.assertIn("button.dataset.dsp = p.dsp; button.dataset.lane = y === YA ? 0 : 1; button.dataset.place = place;", page)
        branch = page[page.index('function laneBranch('):page.index('function splitFormat(')]
        self.assertIn("y = parseFloat(spot.style.top) + (tile ? 52 : 0), d = tile ? 52 : BRANCH_DROP", branch)   # on its bottom edge
        self.assertIn("svg.classList.add('behind')", branch)                     # the branch passes behind the block
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
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=factory, exe='FocusView.exe', costs_file=None,
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


class SplitMoveTests(unittest.TestCase):
    """Stage 2: the split or the mixer moved along lane A (HX Edit's own move with "split" / "join")."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'topology': ['SABJ', 'A'],
                           'blocks': [{'dsp': 0, 'id': 'split', 'model': 'HD2_AppDSPFlowSplitY', 'position': 2},
                                      {'dsp': 0, 'id': 'join', 'model': 'HD2_AppDSPFlowJoin', 'position': 6},
                                      {'dsp': 0, 'id': 'block0', 'model': 'HD2_DelayTest', 'position': 3, 'path': 1, 'enabled': True},
                                      {'dsp': 0, 'id': 'block1', 'model': 'HD2_DelayTest', 'position': 4, 'path': 1, 'enabled': True},
                                      {'dsp': 1, 'id': 'split', 'model': 'HD2_AppDSPFlowSplitY', 'position': 0},
                                      {'dsp': 1, 'id': 'join', 'model': 'HD2_AppDSPFlowJoin', 'position': 8}]}

    def test_the_split_and_the_mixer_keep_lane_b_between_them(self):
        split = lambda dsp, which, place: self.view.checked_split({'dsp': dsp, 'id': which, 'place': place})
        self.assertEqual(split(0, 'split', 0), {'action': 'moveSplit', 'dsp': 0, 'id': 'split', 'place': 0})
        self.assertEqual(split(0, 'split', 3), {'action': 'moveSplit', 'dsp': 0, 'id': 'split', 'place': 3})
        self.assertEqual(split(0, 'join', 5), {'action': 'moveSplit', 'dsp': 0, 'id': 'join', 'place': 5})
        self.assertEqual(split(0, 'join', 8)['place'], 8)
        for refused in ((0, 'split', 4), (0, 'join', 4), (0, 'split', 2), (0, 'join', 9), (0, 'split', -1),
                        (0, 'block0', 1), (0, 'split', True), (1, 'split', 3)):          # past lane B, where it is, a block, one lane
            self.assertIsNone(split(*refused), refused)

    def test_the_page_offers_the_same_gaps(self):
        chain = self.view.state['blocks'] + [{'dsp': 0, 'id': 'outputA', 'model': 'HD2_Out', 'output': 1}]
        gaps = lambda which: run_js(['workbench_layout.js'], f'workbenchNodeGaps(workbenchPaths({json.dumps(chain)}, {{}}, ["SABJ", "A"])[0], "{which}")')
        self.assertEqual(gaps('split'), [0, 1, 2, 3])
        self.assertEqual(gaps('join'), [5, 6, 7, 8])
        self.assertEqual(run_js(['workbench_layout.js'], f'workbenchNodeGaps(workbenchPaths({json.dumps(chain)}, {{}}, ["SABJ", "A"])[1], "split")'), [])

    def test_the_wiring_uses_hx_edits_own_move_for_the_split(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function moveSplit('):binding.index('function blockCells(')]
        self.assertIn("editorEntry(editor, 0xa0, 0x5123c0, 'move-block')", body)
        self.assertIn("!['split', 'join'].includes(which)", body)
        self.assertIn('cell.writeU32(5); cell.add(8).writeU32(gap >>> 0);', body)
        self.assertIn('move(editor, dsp, name, cell, 0x80000000)', body)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'moveSplit' && [0, 1].includes(value.dsp) && ['split', 'join'].includes(value.id)", script)
        self.assertIn('targetBinding.moveSplit(editor, command.dsp, command.id, command.place);', script)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'moveSplit': view.checked_split", launcher)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("node.onpointerdown = event => liftNode(event, p, 'split', node, g);", page)
        self.assertIn("node.onpointerdown = event => liftNode(event, p, 'join', node, g);", page)
        self.assertIn("ask('moveSplit', {dsp: p.dsp, id: which, place: over})", page)

    def test_lane_b_gets_its_own_input_or_output_and_back_by_the_paths_shape(self):
        route = lambda dsp, which: self.view.checked_route({'dsp': dsp, 'id': which})
        self.assertEqual(route(0, 'split'), {'action': 'route', 'dsp': 0, 'id': 'split'})     # "SABJ": both nodes
        self.assertEqual(route(0, 'join'), {'action': 'route', 'dsp': 0, 'id': 'join'})
        self.view.state['blocks'] += [{'dsp': 0, 'id': 'inputB', 'model': 'HD2_In'}, {'dsp': 0, 'id': 'outputB', 'model': 'HD2_Out'},
                                      {'dsp': 1, 'id': 'inputB', 'model': 'HD2_In'}]
        self.assertIsNone(route(0, 'inputB')); self.assertIsNone(route(0, 'outputB'))         # not there in "SABJ"
        self.assertIsNone(route(1, 'split')); self.assertIsNone(route(1, 'inputB'))           # "A": no lane B
        self.assertIsNone(route(0, 'block0'))
        for word, there in (('ABJ', {'inputB', 'join'}), ('SAB', {'split', 'outputB'}), ('AB', {'inputB', 'outputB'})):
            self.view.state['topology'] = [word, 'A']
            self.assertEqual({w for w in ('split', 'join', 'inputB', 'outputB') if route(0, w)}, there, word)
            for w in there:                                                                    # the way back: the node again
                self.assertEqual(route(0, w)['id'], {'inputB': 'split', 'outputB': 'join'}.get(w, w))
                self.assertEqual(route(0, w).get('back', False), w in ('inputB', 'outputB'))       # put back: an add
        self.view.state['topology'] = None
        self.assertIsNone(route(0, 'split'))                                                   # no shape read: nothing
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function removeNode('):binding.index('function selectNode(')]
        self.assertIn("editorEntry(editor, 0xb0, 0x514bc0, 'remove-block')", body)
        self.assertIn("!['split', 'join'].includes(which)", body)
        self.assertIn('remove(editor, dsp, name, 0x80000000)', body)
        back = binding[binding.index('function restoreNode('):binding.index('function selectNode(')]
        self.assertIn("editorEntry(editor, 0xa8, 0x4ff300, 'add-block')", back)
        self.assertIn("cell.writeU32(5); cell.add(8).writeU32(which === 'split' ? 0 : 8);", back)
        self.assertIn('add(editor, dsp, name, cell, 0x80000000)', back)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'route' && [0, 1].includes(value.dsp) && ['split', 'join'].includes(value.id)", script)
        self.assertIn('if (command.back) targetBinding.restoreNode(editor, command.dsp, command.id);', script)
        self.assertIn('else targetBinding.removeNode(editor, command.dsp, command.id);', script)
        self.assertIn("'route': view.checked_route", (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8'))
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("turn.onclick = () => ask('route', {dsp: block.dsp, id: block.id});", page)
        for label in ('Give lane B its own input', 'Give lane B its own output', 'Put the split back', 'Put the mixer back'):
            self.assertIn(label, page)

    def test_a_click_selects_the_split_or_the_mixer_as_hx_edits_own_drop_does(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function selectNode('):binding.index('function moveSplit(')]
        self.assertLess(body.index("string('@cursor_dsp')"), body.index("string('@cursor_group')"))   # the path first
        self.assertEqual(body.count('writeValue(editor, -1, group, key, '), 2)
        self.assertIn('number, 0)', body); self.assertIn('name, 0)', body)                          # no undo step
        self.assertNotIn('0x8000', body)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        select = script[script.index('function select(target)'):script.index('function publish(')]
        self.assertLess(select.index('targetBinding.selectNode(editor, block.dsp, block.id);'), select.index('focusChainPoint('))
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        for which in ('split', 'join'):
            self.assertIn(f"node.onclick = () => {{ if (!dragDone) ask('select', {{dsp: p.dsp, id: '{which}'}}); }};", page)
            self.assertIn(f"el('span', 'node movable' + (same(p.{which}, now) ? ' on' : ''))", page)

class DspCostTests(unittest.TestCase):
    """A block's DSP, measured from the path's meter when exactly one block comes or goes (dsp_costs.py)."""

    def setUp(self):
        import tempfile
        import dsp_costs
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / 'dsp-costs.json'
        self.costs = dsp_costs.DspCosts(self.file)

    @staticmethod
    def state(*models, preset=5):
        return {'preset': {'setlist': 0, 'number': preset}, 'blocks': [{'dsp': 0, 'id': 'block%d' % k, 'model': m} for k, m in enumerate(models)]}

    @staticmethod
    def meter(used):
        return [{'used': used, 'budget': 75}, None]

    def settle(self, state, used, at):
        found = []
        for step in range(0, 13):                               # readings every half second for six seconds
            found += self.costs.observe(state, self.meter(used), at + step / 2)
        return found

    def test_a_block_that_comes_or_goes_is_measured_and_kept(self):
        self.assertEqual(self.settle(self.state('Boost'), 10.0, 0), [])
        self.assertEqual(self.settle(self.state('Boost', 'NAM'), 10.0, 10), [])        # the meter has not followed yet
        self.assertEqual(self.settle(self.state('Boost', 'NAM'), 32.5, 20), [('NAM', 22.5)])
        self.assertEqual(self.settle(self.state('Boost'), 10.0, 30), [('NAM', 22.5)])  # and again as it goes
        import dsp_costs
        self.assertEqual(dsp_costs.DspCosts(self.file).costs, {'NAM': 22.5})

    def test_a_swap_counts_once_the_old_model_is_known_and_nothing_else_is_measured(self):
        self.settle(self.state('Boost'), 10.0, 0)
        self.assertEqual(self.settle(self.state('Drive'), 14.0, 10), [])               # Boost's cost is not known
        self.costs.costs['Drive'] = 6.0
        self.assertEqual(self.settle(self.state('Fuzz'), 12.0, 20), [('Fuzz', 4.0)])
        self.assertEqual(self.settle(self.state('Fuzz', 'A', 'B'), 30.0, 30), [])     # two blocks at once
        self.assertEqual(self.settle(self.state('Fuzz', preset=6), 5.0, 40), [])       # another preset
        self.assertEqual(self.settle(self.state('Fuzz', 'A', preset=6), 5.0, 50), [])  # meter never moved
        self.assertEqual(self.settle(self.state('Fuzz', 'A', preset=6), None, 90), [])  # no meter (Floor off)

    def test_a_remove_and_a_quick_undo_are_both_measured(self):
        self.settle(self.state('Boost', 'NAM'), 32.0, 0)
        observe = lambda models, used, at: self.costs.observe(self.state(*models), self.meter(used), at)
        self.assertEqual(observe(('Boost',), 32.0, 10), [])                 # removed; the meter follows a poll later
        self.assertEqual(observe(('Boost',), 10.0, 11.5), [('NAM', 22.0)])
        self.assertEqual(observe(('Boost', 'NAM'), 10.0, 13), [])           # Undo two seconds later
        self.assertEqual(observe(('Boost', 'NAM'), 32.0, 14.5), [('NAM', 22.0)])
        self.assertEqual(observe(('Boost', 'NAM'), 32.0, 30), [])           # and nothing more from it
        self.assertEqual(observe(('Boost',), 32.0, 40), [])                 # removed and put back before the meter
        self.assertEqual(observe(('Boost', 'NAM'), 32.0, 41), [])           # moved: nothing to measure
        self.assertEqual(observe(('Boost', 'NAM'), 33.0, 50), [])           # the meter alone moving is no block's

    def test_the_page_shows_the_measured_figure_or_says_it_is_not_measured_yet(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("message.type === 'dspCosts'", page)
        self.assertIn("'% of DSP ' + (block.dsp + 1) + ' (measured)'", page)
        self.assertIn('Not measured yet', page)

    def test_measured_costs_replace_the_estimates_in_the_room_checks(self):
        kept = run_js(['focus_view.js'], 'focusMeasured({HD2_AmpNAMLite: 27, "bad name": 3, HD2_Zero: 0, HD2_Huge: 90, HD2_Text: "5"})')
        self.assertEqual(kept, {'HD2_AmpNAMLite': 27})
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertEqual(script.count('], costsNow(), '), 3)                                # swap, add, move across
        self.assertIn("if (value.action === 'costs') measured = focusMeasured(value.costs);", script)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'payload': {'action': 'costs', 'costs': dict(workbench.costs.costs)}", launcher)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertNotIn('catalog.loads ||', page.replace('(catalog && catalog.loads || {})', ''))   # only through costOf
        self.assertIn('namCost = costOf(catalog.nam[0])', page)

    def test_the_pane_sends_what_it_measured(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        clock = [0.0]
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe',
                                       costs_file=self.file, clock=lambda: clock[0])
        self.addCleanup(view.close)
        view.costs.costs['Old'] = 3.0
        shown, acted = [], []
        view.on_action = lambda name, value: acted.append((name, value))
        view._write = lambda prefix, value: shown.append(value)
        view.page_ready = True
        for state, used, start in ((self.state('Boost'), 10.0, 0), (self.state('Boost', 'NAM'), 30.0, 10)):
            view.state, view.dsp = state, self.meter(used)
            for step in range(13):
                clock[0] = start + step / 2
                view._idle()
        self.assertEqual(shown[-1], {'type': 'dspCosts', 'costs': {'Old': 3.0, 'NAM': 20.0}})
        self.assertEqual(acted[-1], ('costs', {'Old': 3.0, 'NAM': 20.0}))           # for focus_view.js's room checks

class ChainChangeTests(unittest.TestCase):
    """Stage 2: a block added on an empty place, removed, or moved to an empty place of its own path."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
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
        change = script[script.index('function change(command)'):script.index('let downFollow = null;')]
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
        # lane B of a one-lane path: pasted on an empty place of lane A; the caller moves it down once the Floor has it
        # (moved down at once, the Floor never got the move)
        self.assertIn('if (result < 0 && row === 1) {', across)
        self.assertIn("if (taken.includes('0:' + place)) continue;", across)
        self.assertIn('return {down: made.name, dsp: toDsp, from: via, lane: 1, place: col};', across)
        self.assertNotIn(' move(editor', across)
        self.assertNotIn("'move-block'", across)
        follow = script[script.index('function followDown('):script.index('function followAdd(')]
        self.assertIn('const arrived = meter && follow.used !== null && meter.used !== follow.used;', follow)
        self.assertIn('if (now - follow.at < DOWN_SETTLE_MS || (!arrived && now - follow.at < DOWN_LATEST_MS)) return;', follow)
        self.assertIn('targetBinding.moveBlock(editor, follow.dsp, follow.down, follow.lane, follow.place);', follow)
        self.assertIn('if (moved && moved.down) downFollow = ', script)
        self.assertIn('downFollow = null;', script[script.index('function set('):])
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
        for name in ('workbench.py', 'workbench.html', 'workbench_layout.js', 'pane_controls.js', 'dsp_costs.py'):
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
        self.assertEqual(asked, {'select', 'set', 'model', 'capture', 'snapshot', 'preset', 'undo', 'redo', 'save', 'menu', 'add', 'remove', 'move', 'moveSplit', 'route'})


if __name__ == '__main__':
    unittest.main()
