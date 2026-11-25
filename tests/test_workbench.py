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
        # a reading without the preset (HX Edit reloading the preset's contents for the undo) is the same preset
        self.assertEqual(run([[0, 'a', False], [1, 'a', False], [0, '', False], [0, 'a', False]]), [False, False, True, True])
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        # (HX Edit's answer and an undo made on this preset, both: test_undo_after_load)
        self.assertIn("$('redo').disabled = !can.redo;", page)
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
        self.assertIn("y = parseFloat(spot.style.top) + (tile ? TILE_TOP : 0), d = tile ? TILE_H - TILE_TOP : BRANCH_DROP", branch)   # on its bottom edge
        self.assertIn("svg.classList.add('behind')", branch)                     # the branch passes behind the block
        self.assertIn("el('div', 'slot spot lane-drop', '+')", branch)          # its circle is a place like the others
        self.assertIn("drop.dataset.lane = '1'", branch)                         # dropped on: lane B at that place
        self.assertIn('laneBranch(null);', lift)                                 # gone when the drag ends
        self.assertNotIn('lane-tab', page)

    def test_a_redraw_moves_the_pictures_already_showing(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn('reusable = gather(board);', page)
        self.assertIn('reusable = gather(panel);', page)
        self.assertIn("paths = workbenchPaths(shownBlocks(), catalog, state.topology)", page)
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
        self.assertEqual(workbench.route_names(self.res), {'inputs': [], 'outputs': [], 'ledColors': []})

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

    def test_the_page_hears_when_a_tools_window_closed_by_itself(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: self.view.page_ready))
        self.view.tool_closed()
        self.assertTrue(self.wait(lambda: any(m.get('type') == 'toolClosed' for m in self.lines('P'))))

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
class SizeTests(unittest.TestCase):
    """The three sizes Nick approved (research/modern-ui/play.js): a drawer beside the chain, a tool in the lower half,
    a full view; the rail opens each in its first size, an expand button switches sizes."""

    def run_view(self, steps, start=None):
        code = """(() => { let v = %s; const out = [];
          for (const [action, name] of %s) { v = workbenchView(v, action, name); out.push([v.drawer, v.half, v.full]); }
          return out; })()""" % (json.dumps(start), json.dumps(steps))
        return run_js(['workbench_layout.js'], code)

    def test_the_rail_opens_each_thing_in_its_first_size_and_closes_it_again(self):
        self.assertEqual(self.run_view([['rail', 'presets'], ['rail', 'captures'], ['rail', 'captures']]),
                         [['presets', '', ''], ['captures', '', ''], ['', '', '']])
        self.assertEqual(self.run_view([['rail', 'look'], ['rail', 'level'], ['rail', 'level']]),
                         [['', 'look', ''], ['', 'level', ''], ['', '', '']])
        self.assertEqual(self.run_view([['rail', 'tone'], ['rail', 'library'], ['rail', 'library']]),
                         [['', '', 'tone'], ['', '', 'library'], ['', '', '']])
        # one thing at a time beside or under the chain (Nick, 2026-11-23): a tool under the chain closes the side
        # list, a side list closes the tool, and a full view shrinking to either does the same
        self.assertEqual(self.run_view([['rail', 'captures'], ['rail', 'look']])[-1], ['', 'look', ''])
        self.assertEqual(self.run_view([['rail', 'level'], ['rail', 'presets']])[-1], ['presets', '', ''])
        self.assertEqual(self.run_view([['open', 'look']], {'drawer': 'irs'})[-1], ['', 'look', ''])
        self.assertEqual(self.run_view([['rail', 'captures'], ['rail', 'tone'], ['rail', 'look']])[-1], ['', 'look', ''])
        self.assertEqual(self.run_view([['shrink', None]], {'drawer': 'captures', 'half': '', 'full': 'look'})[-1], ['', 'look', ''])
        self.assertEqual(self.run_view([['shrink', None]], {'drawer': '', 'half': 'look', 'full': 'presets'})[-1], ['presets', '', ''])
        # "open" (the Unbound menu, a link) never closes what is open
        self.assertEqual(self.run_view([['open', 'look'], ['open', 'look']])[-1], ['', 'look', ''])

    def test_expand_shrink_back_and_escape(self):
        # Floor look: lower half -> full -> back under the chain; Esc closes the full view, then the lower half
        self.assertEqual(self.run_view([['rail', 'look'], ['expand', 'look'], ['shrink', None]]),
                         [['', 'look', ''], ['', 'look', 'look'], ['', 'look', '']])
        self.assertEqual(self.run_view([['rail', 'level'], ['expand', 'level'], ['escape', None], ['escape', None]]),
                         [['', 'level', ''], ['', 'level', 'level'], ['', 'level', ''], ['', '', '']])
        # Presets: the drawer -> the full grid -> back to the drawer; Back to the chain keeps the drawer
        self.assertEqual(self.run_view([['rail', 'presets'], ['expand', 'presets'], ['shrink', None]]),
                         [['presets', '', ''], ['presets', '', 'presets'], ['presets', '', '']])
        self.assertEqual(self.run_view([['expand', 'presets'], ['back', None]], {'drawer': 'captures'})[-1], ['captures', '', ''])
        # a thing with one size has no other: Captures and IRs never fill the screen, TONE3000 never shrinks
        self.assertEqual(self.run_view([['expand', 'captures'], ['expand', 'irs']]), [['', '', ''], ['', '', '']])
        self.assertEqual(self.run_view([['rail', 'tone'], ['shrink', None]])[-1], ['', '', ''])
        # a rail button while a full view is open: it closes and the thing opens beside or under the chain
        self.assertEqual(self.run_view([['rail', 'tone'], ['rail', 'irs']])[-1], ['irs', '', ''])
        # another tool's full view takes the place of the one under the chain
        self.assertEqual(self.run_view([['rail', 'level'], ['rail', 'tone']])[-1], ['', '', 'tone'])

    def test_a_block_picked_closes_levels_and_keeps_floor_look(self):
        self.assertEqual(self.run_view([['rail', 'level'], ['select', None]])[-1], ['', '', ''])
        self.assertEqual(self.run_view([['rail', 'look'], ['select', None]])[-1], ['', 'look', ''])
        # a small tile in a full view's header: back to the chain, with nothing over it
        self.assertEqual(self.run_view([['expand', 'look'], ['goto', None]], {'drawer': 'irs'})[-1], ['irs', '', ''])
        self.assertEqual(self.run_view([['rail', 'look'], ['expand', 'look'], ['goto', None]], {'drawer': 'irs'})[-1], ['', '', ''])
        # the tool's window closed by itself: its frame closes, wherever it was
        self.assertEqual(self.run_view([['rail', 'look'], ['expand', 'look'], ['close', 'look']])[-1], ['', '', ''])

    def test_the_rail_lights_what_shows(self):
        on = lambda view, name: run_js(['workbench_layout.js'], f'workbenchRailOn({json.dumps(view)}, {json.dumps(name)})')
        self.assertTrue(on({'drawer': 'captures', 'half': 'look', 'full': ''}, 'look'))
        self.assertTrue(on({'drawer': 'captures', 'half': 'look', 'full': ''}, 'captures'))
        self.assertFalse(on({'drawer': 'captures', 'half': 'look', 'full': 'tone'}, 'captures'))
        self.assertTrue(on({'drawer': 'captures', 'half': 'look', 'full': 'tone'}, 'tone'))

    def test_the_page_places_an_old_tools_window_over_its_frame_and_closes_it_with_the_frame(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("const body = view.full ? $('vbody').querySelector('.t3web') || $('vbody') : $('toolBody')", page)
        self.assertIn("if (!name) { if (toolShown && !toolPopped) { toolShown = ''; ask('toolClose'); } return; }", page)
        self.assertIn("else if (message.type === 'toolClosed') { toolClosed(); return; }", page)
        self.assertIn("else if (view.full || view.half) setView('escape');", page)
        self.assertIn("if (view.half === 'level' && !view.full) setView('select');", page)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("preview.close_window('workbench')", launcher)
        self.assertIn('workbench.tool_closed()', launcher)


class PresetTests(unittest.TestCase):
    """Stage 2 of the views: the Presets drawer and the whole setlist; pins kept in the editor's settings.json."""

    def test_pins_are_setlist_and_number_and_only_valid_ones_are_kept(self):
        self.assertEqual(workbench.pinned({'presetPins': ['2:6', '2:6', '0:127', '8:0', '1:128', 'x', 3, '02:007']}), ['2:6', '0:127', '2:7'])
        self.assertEqual(workbench.pinned({}), [])
        self.assertEqual(workbench.pinned(None), [])

    def test_a_pin_from_the_page_is_checked_before_it_is_kept(self):
        settings = {'presetPins': ['2:6']}
        self.assertEqual(workbench.pins_after(settings, {'setlist': 2, 'number': 12, 'on': True}), ['2:6', '2:12'])
        self.assertEqual(workbench.pins_after(settings, {'setlist': 2, 'number': 6, 'on': True}), ['2:6'])
        self.assertEqual(workbench.pins_after(settings, {'setlist': 2, 'number': 6, 'on': False}), [])
        for refused in (None, {'setlist': 2, 'number': 6}, {'setlist': 8, 'number': 0, 'on': True}, {'setlist': 0, 'number': 128, 'on': True},
                        {'setlist': True, 'number': 1, 'on': True}, {'setlist': 0, 'number': 1.0, 'on': True}, {'setlist': 0, 'number': 1, 'on': 1}):
            self.assertIsNone(workbench.pins_after(settings, refused))

    def test_the_launcher_keeps_pins_in_settings_and_the_page_never_in_the_browser(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("pins = pins_after(nam_catalog.load_settings(), value)", launcher)
        self.assertIn("nam_catalog.save_setting(PINS, pins)", launcher)
        self.assertIn("workbench.show_pins(pinned(nam_catalog.load_settings()))", launcher)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertNotIn('localStorage', page)
        self.assertNotIn('sessionStorage', page)
        self.assertIn("ask('pin', {setlist, number, on});", page)                 # (Batch 3: of the setlist shown)
        # a preset is loaded the way the top bar's list loads it: through loadPreset, which asks first when the
        # loaded preset has changes that are not saved
        self.assertEqual(page.count("if (index !== at) loadPreset(presetTarget(index));"), 1)   # the drawer (Batch 3: or another setlist's)
        self.assertIn("if (index !== at) loadPreset(target); };", page)                       # the top bar's list (its target read first)

        self.assertIn("b.onclick = () => { if (number !== at) loadPreset(presetTarget(number)); };", page)   # the grid
        self.assertIn("loadPreset('previous');", page)                                    # the top bar's arrows
        self.assertIn("loadPreset('next');", page)
        self.assertEqual(page.count("ask('preset', target)"), 3)        # nothing unsaved; Don't save; after the Save

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_unsaved_is_hx_edits_undo_position_against_where_it_stood_at_the_load_or_the_save(self):
        # Seen live 2026-11-23 on presets 032/033: HX Edit keeps its undo position through a preset load (1 on 032,
        # still 1 on 033, which then wrongly asked) and through a Save (2 before and after).
        unsaved = lambda *args: run_js(['workbench_layout.js'], 'workbenchUnsaved(%s)' % ', '.join(json.dumps(a) for a in args))
        self.assertFalse(unsaved(0, '3:32', {'key': '3:32', 'at': 0}))             # as loaded
        self.assertTrue(unsaved(1, '3:32', {'key': '3:32', 'at': 0}))              # one change
        self.assertFalse(unsaved(1, '3:33', {'key': '3:33', 'at': 1}))             # the next preset, loaded with the position at 1
        self.assertTrue(unsaved(2, '3:33', {'key': '3:33', 'at': 1}))              # and changed there
        self.assertFalse(unsaved(2, '3:32', {'key': '3:32', 'at': 2}))             # saved right there
        self.assertTrue(unsaved(3, '3:32', {'key': '3:32', 'at': 2}))              # changed again after the Save
        self.assertTrue(unsaved(1, '3:32', {'key': '3:32', 'at': 2}))              # undone to before it
        self.assertFalse(unsaved(2, '3:33', {'key': '3:32', 'at': 0}))             # no mark for this preset yet
        self.assertFalse(unsaved(None, '3:32', {'key': '3:32', 'at': 0}))          # HX Edit's position could not be read
        self.assertFalse(unsaved(4, '3:32', {'key': '3:32', 'at': None}))          # nor where it stood
        self.assertFalse(unsaved(4, '3:32', None))
        self.assertFalse(unsaved(4, '', {'key': '', 'at': 0}))                     # no preset

    def test_leaving_a_changed_preset_asks_and_save_is_hx_edits_own(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        guard = page[page.index('function loadPreset(target) {'):page.index('function openMenu() {')]
        self.assertIn("if (!changedHere()) { ask('preset', target); return; }", guard)     # (Batch 3: a pending name counts)

        for words in ("'Stay here'", "'Save, then load '", "has unsaved changes"):
            self.assertIn(words, guard)
        self.assertIn("if (answer === 'drop') ask('preset', target);", guard)
        # Save, then the preset: HX Edit's own Save (the top bar's), then the load a moment later (HX Edit gives no
        # sign that a Save is done; 1.5 s was enough live); never when another preset was loaded meanwhile
        # (a preview playing is ended first: the load follows the Save, inside savePreset's `then`; Batch 3, 13:09)
        self.assertLess(guard.index('savePreset(() => {'), guard.index("setTimeout(() => { if (presetWord() === from) ask('preset', target); }, SAVE_WAIT_MS);"))
        self.assertIn('const SAVE_WAIT_MS = 2000;', page)
        self.assertEqual(page.count("ask('save')"), 1)                                    # only saveNow asks it (savePreset's gate)
        self.assertIn("$('save').onclick = savePreset;", page)
        self.assertIn("$('edited').hidden = !changedHere();", page)                     # (Batch 3: or a pending name)

        # a preset starts unchanged from where HX Edit's undo position stands when it is loaded; a Save moves the mark
        self.assertIn("if (before !== after || savedMark.key !== after || (typeof savedMark.at !== 'number' && typeof state.undoAt === 'number')) savedMark = {key: after, at: state.undoAt, settle: Date.now() + WORKBENCH_LOAD_SETTLE_MS};", page)
        self.assertIn("savedMark = {key: presetWord(), at: state.undoAt};", page)
        self.assertNotIn('state.undoAt === 0', page)
        # two banks of four a row: a preset's bank (number / 4) alternates between the two columns
        self.assertIn("if (item) sides[Math.floor(number / 4) % 2].append(item);", page)

    def test_export_is_hx_edits_own_file_menu_and_nothing_else(self):
        # HX Edit 3.82's File menu (its menu resource): 32781 Export Preset... (Ctrl+E), 32783 Export Setlist...
        # (Ctrl+Alt+E). The pane posts only those two; import, paste and the rest are not offered.
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('{ { "preset", 32781 }, { "setlist", 32783 } }', pane)
        self.assertIn('if ((string)name == "export") { int command; if (value is string && Exports.TryGetValue((string)value, out command)) MenuInEditor(command); return; }', pane)
        self.assertEqual(pane.count('PostMessage('), 2)                                  # (its declaration and the one call)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("b.onclick = () => ask('export', what);", page)
        self.assertEqual(sorted(set(__import__('re').findall(r"exporter\('([a-z]+)'", page))), ['preset', 'setlist'])

    def test_the_page_gets_the_pins(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        panes = []
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: panes.append(FakePane(a)) or panes[-1],
                                       exe='FocusView.exe', costs_file=None)
        self.addCleanup(view.close)
        view.show_pins(['2:6'])
        view.set_on(True)
        view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        deadline = time.time() + 3
        while time.time() < deadline and not panes:
            time.sleep(.01)
        panes[0].say({'type': 'ready'})
        sent = lambda: [json.loads(line[2:]) for line in panes[0].lines if line.startswith('P ')]
        while time.time() < deadline and not any(m.get('type') == 'pins' for m in sent()):
            time.sleep(.01)
        self.assertIn({'type': 'pins', 'pins': ['2:6']}, sent())


class FloorLookTests(unittest.TestCase):
    """Stage 3 of the views: Floor look in the lower half and full, on Focus Mode's looks (no copy of the old page)."""

    def test_the_page_asks_only_focus_modes_look_changes(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        body = page[page.index('// ---- Floor look:'):page.index('function libraryRow(')]
        asked = __import__('re').findall(r"ask\('look', \{scope: '([a-z]+)'", body)
        self.assertEqual(sorted(set(asked)), ['block', 'default', 'preset'])           # focus_view.look_change's scopes
        self.assertIn("ask('lookSave')", body)
        self.assertNotIn("'look'", page[page.index('const OLD_PAGES'):page.index('const OLD_PAGES') + 80])   # no longer the old page
        # the view follows the block picked in the chain; a NAM block is an amp to the Floor, as focus_view.tidy_looks has it
        self.assertIn("const kindKeyOf = block => isNam(block) ? 'amp' : model(block).key || '';", body)
        # said, not pretended: the Floor cannot read a preset's own look yet
        self.assertIn('The Floor shows the defaults until its firmware can read a look per preset', body)

    def test_floor_look_works_as_focus_modes_change_look_does(self):
        # Batch 2 (Nick, 2026-11-23: the grid of kinds read as confusing next to Focus Mode's Change look): the picked
        # block on its scene, then This block | This preset | Defaults, Background | Picture, the scenes by name.
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        body = page[page.index('// ---- Floor look:'):page.index('// ---- a question before something is done')]
        self.assertIn("for (const [scope, words] of [['block', 'This block'], ['preset', 'This preset'], ['defaults', 'Defaults']]) {", body)
        self.assertIn("let look = null, lookScope = 'block', lookPart = 'scene',", body)
        # each scope asks what Focus Mode's panel asks (focus_view.look_change)
        for asked in ("const change = more => ask('look', {scope: 'block', preset: presetRef(), key: lookBlockKey(block), ...more});",
                      "change({scene: name})", "change({scene: null})", "change({picture: id === ownPictureId(block) ? null : id})",
                      "change({picture: null})",
                      "ask('look', {scope: 'preset', preset: presetRef(), scene: name})",
                      "ask('look', {scope: 'preset', preset: presetRef(), clear: true})",
                      "ask('look', {scope: 'preset', preset: presetRef(), adopt: true})",
                      "ask('look', {scope: 'default', category: lookKind, scene: name})",
                      "ask('look', {scope: 'default', reset: true})"):
            self.assertIn(asked, body)
        # who the look is for, in Focus Mode's own words
        self.assertIn("'. Only this block, only in this preset. Everything else keeps its look.'", body)
        self.assertIn("'. Every block in this preset that has no look of its own.'", body)
        # Save for the Floor belongs to the defaults: the only looks the Floor reads
        defaults = body[body.index("if (lookScope === 'defaults') {"):body.index("} else if (!presetKey()) {")]
        self.assertIn("save.onclick = () => ask('lookSave');", defaults)
        self.assertEqual(body.count("ask('lookSave')"), 1)
        # under the chain the frame's card is the block on its scene; the old grid of kinds and its strip are gone
        self.assertIn("card.replaceChildren(head, lookStage(false),", body)
        self.assertIn("$('tool').classList.toggle('look', half === 'look');", page)
        for gone in ('kindCards', "'lkstrip'", "'lkinds'", ' .lkind', 'Preview and gallery', "from the Floor tool"):
            self.assertNotIn(gone, page)

    def test_the_launcher_checks_and_keeps_a_look_as_focus_mode_does(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        action = launcher[launcher.index('            def workbench_action(name, value):'):launcher.index('            if focus is not None:\n                focus.on_action')]
        self.assertIn('changed = workbench.changed_look(value, nam_catalog.load_settings())', action)
        self.assertIn('Thread(target=focus_look_save, args=(workbench,), daemon=True).start()', action)
        self.assertIn('workbench.show_look(nam_catalog.load_settings())', launcher[launcher.index('def workbench_show():'):launcher.index('def workbench_mode(')])

    def test_a_look_change_from_the_workbench_is_the_same_check(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(view.close)
        view.state = {'preset': {'setlist': 0, 'number': 6, 'name': 'John Mayer Style'}, 'blocks': []}
        scenes = list(view.catalog()['scenes'])
        self.assertEqual(view.changed_look({'scope': 'default', 'category': 'delay', 'scene': 'nope'}, {}), {})
        if scenes:
            changed = view.changed_look({'scope': 'default', 'category': 'delay', 'scene': scenes[0]}, {})
            self.assertEqual(changed['floorLook']['assign']['category']['delay'], scenes[0])


class LevelsTests(unittest.TestCase):
    """Stage 4 of the views: Levels as its own Workbench view, on the library page's own LevelFlow, run in a session
    without a window (tone_preview.WorkbenchSession)."""

    ROWS = [
        {'preset': 6, 'setlist': 3, 'name': 'John Mayer Style', 'snapshot': 1, 'snapshots': [1, 2], 'lufs': -17.8, 'peak': -9.0, 'level': 0.0},
        {'preset': 6, 'setlist': 3, 'name': 'John Mayer Style', 'snapshot': 3, 'lufs': -11.6, 'peak': -3.0, 'level': 1.5},
        {'preset': 7, 'setlist': 3, 'name': 'Strat Work', 'snapshot': 1, 'lufs': -14.2, 'peak': -6.0, 'level': 0.0},
        {'preset': 7, 'setlist': 3, 'name': 'Strat Work', 'snapshot': 2, 'lufs': -30.0, 'peak': -20.0, 'level': 0.0},
        {'preset': 7, 'setlist': 3, 'name': 'Strat Work', 'snapshot': 3, 'lufs': -16.0, 'peak': -0.5, 'level': 0.0}]

    def plan(self, choice):
        return run_js(['workbench_layout.js'], f'(() => {{ const p = workbenchLevelPlan({json.dumps(self.ROWS)}, {json.dumps(choice)}); '
                                               f'return {{target: workbenchLevelTarget({json.dumps(self.ROWS)}, {json.dumps(choice)}), '
                                               f'plan: p.map(r => [r.preset, r.snapshot, r.change, r.held, r.use, r.output]), changes: workbenchLevelChanges(p)}}; }})()')

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_plan_is_the_library_pages_own_sums(self):
        out = self.plan({'metric': 'lufs', 'target': 'middle', 'offsets': {}})
        self.assertEqual(out['target']['value'], -16.0)                 # median of -30, -17.8, -16, -14.2, -11.6
        plan = {(r[0], r[1]): r for r in out['plan']}
        self.assertEqual(plan[(6, 1)][2], 1.8)                         # -16 - -17.8
        self.assertEqual(plan[(6, 1)][5], 1.8)                         # the output Level after Apply
        self.assertEqual(plan[(6, 3)][2], -4.4)
        self.assertEqual(plan[(7, 1)][2], -1.8)
        self.assertIn('more than 12 dB away', plan[(7, 2)][3])          # held: not applied
        self.assertEqual(plan[(7, 3)][2], 0)                           # on target: nothing to do
        # Apply names a group of alike snapshots by its first one (LevelFlow.apply changes the whole group)
        self.assertEqual(out['changes'], {'6': {'1': 1.8, '3': -4.4}, '7': {'1': -1.8}})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_offsets_a_presets_own_level_a_peak_ceiling_and_skips(self):
        key = '3:6:John Mayer Style:3'
        out = self.plan({'metric': 'lufs', 'target': 'custom', 'custom': -14, 'offsets': {key: {'dB': 3}}})
        plan = {(r[0], r[1]): r for r in out['plan']}
        self.assertEqual(plan[(6, 3)][2], 0.6)                         # a lead kept +3: to -11, not to -14
        self.assertEqual(plan[(6, 1)][3], '')                          # +3.8 dB peaks at -5.2: fine
        self.assertEqual(plan[(7, 3)][3], 'would peak at +1.5 dBFS')   # +2 dB on a -0.5 peak: held
        self.assertFalse(plan[(7, 3)][4])
        out = self.plan({'metric': 'lufs', 'target': 'preset:7', 'offsets': {}, 'skipped': [6]})
        self.assertEqual(out['target']['value'], -14.2)                # Strat Work's main sound (the first, all of one size)
        self.assertNotIn('6', out['changes'])

    def test_the_session_without_a_window_runs_the_level_page_and_hands_its_view_on(self):
        import tempfile
        from queue import Queue
        from threading import Event
        from unittest.mock import Mock
        from nam_library import Library
        from tone_preview import TonePreview, WorkbenchSession
        from test_nam_level import FakeHelix
        folder = tempfile.mkdtemp()
        di = Path(folder, 'di.wav')
        di.write_bytes(b'RIFF')
        seen = []
        detached = Event()
        session = WorkbenchSession(detached, lambda kind, data: seen.append((kind, data)))
        preview = TonePreview(Mock(), folder, Path(folder, 'tools', 'nam2ir.py'), detached, Mock(),
                              browser_factory=Mock(), library=Library(Path(folder, 'library')), level=True, level_di=di,
                              level_files={'restore_file': Path(folder, 'r.json'), 'records_file': Path(folder, 'u.json'),
                                           'guitar_file': Path(folder, 'guitar.json')})
        helix = FakeHelix()
        preview.command = lambda session_id, action, **data: helix.command(action, **data)
        preview.initial_level = preview.initial_library = True
        session.actions.put('levelApply:' + json.dumps({'changes': {'30': {'1': -2.0}}, 'target': {'value': -14.0, 'metric': 'lufs'}}))
        session.actions.put({'close': 'workbench'})
        preview.browse(session, 1, '')
        statuses = [data for kind, data in seen if kind == 'status']
        level = [s for s in statuses if s.get('levelPage')]
        self.assertTrue(level)                                         # opened straight on the Level page
        self.assertEqual(level[-1]['level']['current']['preset']['preset'], 30)
        # only what the Workbench draws goes to it, and Apply is checked as from the library page
        self.assertLessEqual(set(statuses[-1]), set(WorkbenchSession.SHOWN))
        self.assertTrue(any('has not been measured' in str(s.get('text', '')) for s in statuses))

    def test_the_workbench_session_is_its_own_and_one_at_a_time(self):
        preview_src = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        self.assertIn("self.workbench = bool(payload.get('workbench')) and self.headless", preview_src)
        self.assertIn('WorkbenchSession(self.detached, self._to_workbench) if self.workbench else', preview_src)
        script = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("if (options.workbench && active) {\n      if (!active.workbench) return false;", script)
        self.assertIn("level: !!options.level || options.workbench === 'level'", script)
        sidebar = (ROOT / 'nam_sidebar.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'workbench' && ['level', 'library'].includes(value.id)", sidebar)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("preview_free(lambda: sidebar_action('workbench', page))", launcher)
        self.assertIn("elif do in LEVEL_COMMANDS and (argument is None or (isinstance(argument, str) and len(argument) <= 20000)):", launcher)
        self.assertIn('preview_free(open_tool)', launcher)        # an old tool's window waits for the Levels session to close
        self.assertEqual(workbench.LEVEL_COMMANDS, ('levelOpen', 'levelScan', 'levelApply', 'levelUndo', 'levelGuitar', 'levelGuitarRemove', 'levelCancel'))
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertNotIn("'level'", page[page.index('const OLD_PAGES'):page.index('const OLD_PAGES') + 60])
        asked = set(__import__('re').findall(r"ask\('levels', \{do: '([a-zA-Z]+)'", page))
        self.assertEqual(asked, {'open', 'close', 'levelScan', 'levelApply', 'levelUndo', 'levelGuitar', 'levelGuitarRemove', 'levelCancel', 'replace',
                                 'listenStop', 'optimizeCancel', 'lightCancel', 'optimize', 'light',
                                 'end'})    # (a Save while the library's preview plays ends it first: Batch 3, 13:09)

        # the NAM library's Floor actions go through the same session (stage 5 part 2)
        floor = set(__import__('re').findall(r"do: (?:verified \? 'use' : 'load'|trial \? \{do: 'end'\} : \{do: '([a-z]+)')", page))
        self.assertIn("ask('levels', {do: verified ? 'use' : 'load', arg: row.id});", page)
        self.assertIn("ask('levels', trial ? {do: 'end'} : {do: 'pick', arg: row.id});", page)
        self.assertIn("ask('levels', {do: 'replace', arg: slot});", page)
        # closing Levels while it scans or applies is asked first (closing puts the presets back)
        self.assertIn("if (levelsIn(view) && !levelsIn(next) && levelRunning()) {", page)

    def test_the_levels_choices_are_kept_in_settings_and_checked(self):
        kept = workbench.prefs({'workbenchPrefs': {'levels': {
            'metric': 'peak', 'target': 'preset:6', 'custom': -14, 'snapshots': '4', 'signal': 'g1',
            'offsets': {'3:6:John Mayer Style:2': {'dB': 3, 'when': 'today'}, 'nope': {'dB': 1}, '3:6:X:1': {'dB': 40}}}}})['levels']
        self.assertEqual((kept['metric'], kept['target'], kept['custom'], kept['snapshots'], kept['signal']), ('peak', 'preset:6', -14.0, '4', 'g1'))
        self.assertEqual(kept['offsets'], {'3:6:John Mayer Style:2': {'dB': 3.0, 'when': 'today'}})
        fallback = workbench.prefs({'workbenchPrefs': {'levels': {'metric': 'x', 'target': 'everything', 'custom': True, 'snapshots': 9}}})['levels']
        self.assertEqual((fallback['metric'], fallback['target'], fallback['custom'], fallback['snapshots']), ('lufs', 'middle', None, 'all'))
        self.assertIsNone(workbench.prefs_after({}, {'levels': 3}))
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('nam_catalog.save_setting(PREFS, prefs)', launcher)


class LibraryTests(unittest.TestCase):
    """Stage 5, part 1: the NAM library as its own Workbench view: the library on this PC, read and changed by the
    launcher (nothing on the Floor), files and folders chosen in the pane's own dialogs."""

    NAM = json.dumps({'version': '0.5.4', 'architecture': 'WaveNet', 'config': {}, 'weights': [0.1, 0.2]}).encode()

    def library(self):
        import tempfile
        from nam_library import Library
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        library = Library(Path(folder.name) / 'library')
        return library, Path(folder.name)

    def test_the_view_is_the_library_pages_own_rows_with_the_uploaded_pictures(self):
        import nam_library
        library, folder = self.library()
        source = folder / 'Brit Gold.nam'
        source.write_bytes(self.NAM)
        try:
            nam_library.check_nam(self.NAM)
        except ValueError:
            self.skipTest('the made-up capture is not a NAM file to this check')
        identity = library.add(source, gear='amp')
        view = workbench.library_view(library)
        self.assertEqual([row['id'] for row in view['rows']], [identity])
        self.assertEqual(view['rows'][0], nam_library.library_row(identity, library.entries()[identity], library.pictures))
        self.assertEqual(view['gears'], nam_library.GEARS)
        self.assertEqual(view['pictures'], {})
        self.assertTrue(view['groups'])

    def test_edits_are_checked_before_the_library_changes(self):
        entries = {'abc': {'source': 'https://www.tone3000.com/tones/12'}, 'def': {'source': 'file'}}
        check = workbench.checked_library
        self.assertEqual(check({'do': 'gear', 'id': 'abc', 'value': 'amp'}, entries), ('gear', 'abc', 'amp'))
        self.assertIsNone(check({'do': 'gear', 'id': 'abc', 'value': 'kazoo'}, entries))
        self.assertIsNone(check({'do': 'gear', 'id': 'nope', 'value': 'amp'}, entries))
        self.assertEqual(check({'do': 'instrument', 'id': 'abc', 'value': None}, entries), ('instrument', 'abc', ''))
        self.assertIsNone(check({'do': 'instrument', 'id': 'abc', 'value': 'kazoo'}, entries))
        self.assertEqual(check({'do': 'remove', 'id': 'def'}, entries), ('remove', 'def', None))
        self.assertEqual(check({'do': 'openSource', 'id': 'abc'}, entries), ('openSource', 'abc', 'https://www.tone3000.com/tones/12'))
        self.assertIsNone(check({'do': 'openSource', 'id': 'def'}, entries))            # only a TONE3000 page opens
        self.assertIsNone(check({'do': 'iconDelete', 'value': 'graphic_eq_head'}, entries))   # only an uploaded one
        self.assertIsNone(check({'do': 'install', 'id': 'abc'}, entries))              # nothing for the Floor here

    def test_only_what_the_panes_dialog_chose_and_only_files_of_that_kind(self):
        library, folder = self.library()
        nam = folder / 'a.nam'; nam.write_bytes(self.NAM)
        txt = folder / 'b.txt'; txt.write_text('x')
        entries = {'abc': {}}
        chosen = workbench.checked_chosen
        self.assertEqual(chosen({'kind': 'nam', 'paths': [str(nam), str(txt)]}, entries, folder), ('nam', None, [nam]))
        self.assertEqual(chosen({'kind': 'namFolder', 'paths': [str(folder)]}, entries, folder), ('namFolder', None, [folder]))
        self.assertIsNone(chosen({'kind': 'export', 'id': 'nope', 'paths': [str(folder)]}, entries, folder))
        picture = folder / 'workbench-picture-1.png'; picture.write_bytes(b'png')
        elsewhere = folder / 'sub'; elsewhere.mkdir(); stray = elsewhere / 'workbench-picture-2.png'; stray.write_bytes(b'png')
        self.assertEqual(chosen({'kind': 'picture', 'id': 'abc', 'paths': [str(picture)]}, entries, folder), ('picture', 'abc', [picture]))
        self.assertIsNone(chosen({'kind': 'picture', 'id': 'abc', 'paths': [str(stray)]}, entries, folder))   # only the pane's own
        self.assertIsNone(chosen({'kind': 'nam', 'paths': [str(txt)]}, entries, folder))

    def test_import_adds_good_files_once_and_names_the_bad_ones(self):
        import nam_library
        try:
            nam_library.check_nam(self.NAM)
        except ValueError:
            self.skipTest('the made-up capture is not a NAM file to this check')
        library, folder = self.library()
        (folder / 'in').mkdir()
        (folder / 'in' / 'one.nam').write_bytes(self.NAM)
        (folder / 'in' / 'deep').mkdir()
        (folder / 'in' / 'deep' / 'bad.nam').write_text('not json')
        stats = workbench.import_files(library, [folder / 'in'])
        self.assertEqual((stats['added'], stats['same'], stats['bad']), (1, 0, ['bad.nam']))
        self.assertEqual(workbench.import_files(library, [folder / 'in' / 'one.nam'])['same'], 1)

    def test_import_stops_walking_at_the_limit_and_reads_no_file_larger_than_a_capture(self):
        # (review of PR #7: the whole tree was walked and sorted before the limit; a huge file was read whole)
        from unittest import mock
        import nam_library
        library, folder = self.library()
        walked = []

        class Endless:                            # a folder whose walk never ends (a drive, a synced cloud folder)
            def is_dir(self):
                return True

            def rglob(self, pattern):
                n = 0
                while True:
                    n += 1
                    walked.append(n)
                    yield folder / ('missing-%06d.nam' % n)

        stats = workbench.import_files(library, [Endless()], limit=3)
        self.assertEqual(len(walked), 4)          # the limit and one more, to know there were more
        self.assertEqual((stats['added'], len(stats['bad']), stats['more']), (0, 3, True))
        (folder / 'two').mkdir()
        for name in ('a.nam', 'b.nam'):
            (folder / 'two' / name).write_text('not json')
        self.assertFalse(workbench.import_files(library, [folder / 'two'], limit=2)['more'])
        big = folder / 'two' / 'big.nam'
        big.write_bytes(b'x' * 64)
        with mock.patch.object(nam_library, 'MAX_NAM_FILE', 32), mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('read')):
            stats = workbench.import_files(library, [big])
        self.assertEqual(stats['bad'], ['big.nam'])

    def test_the_pane_chooses_files_and_the_page_cannot_say_what_was_chosen(self):
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('if ((string)name == "choose") { Choose(value as Dictionary<string, object>); return; }', pane)
        self.assertIn('if ((string)name == "chosen") return;', pane)
        self.assertIn('"workbench-picture-"', pane)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('chosen = checked_chosen(value, library.entries(), tempfile.gettempdir())', launcher)
        self.assertIn('edit = checked_library(value, library.entries())', launcher)
        self.assertIn('library.subscribe(library_changed)', launcher)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("const OLD_PAGES = new Set(['tone']);", page)       # the library no longer opens the old window
        body = page[page.index('// ---- NAM library: every capture'):page.index('function libraryRow(')]
        self.assertEqual(set(__import__('re').findall(r"ask\('choose', \{kind: '([a-zA-Z]+)'", body)), {'picture', 'export'})
        self.assertIn("ask('choose', {kind});", body)                     # the Import menu: nam, namFolder
        self.assertNotIn('localStorage', page)


class LibraryFloorTests(unittest.TestCase):
    """Stage 5 part 2: the library's Floor actions, the library page's own, in the Workbench's session."""

    def test_only_the_library_pages_floor_actions_for_a_capture_of_the_library(self):
        capture = 'a' * 64
        entries = {capture: {}}
        check = workbench.checked_floor
        self.assertEqual(check({'do': 'load', 'arg': capture}, entries), 'load:' + capture)
        self.assertEqual(check({'do': 'use', 'arg': capture}, entries), 'use:' + capture)
        self.assertEqual(check({'do': 'pick', 'arg': capture}, entries), 'pick:' + capture)
        self.assertEqual(check({'do': 'end'}, entries), 'end')
        self.assertEqual(check({'do': 'replace', 'arg': 12}, entries), 'replace:12')
        for refused in ({'do': 'load', 'arg': 'b' * 64}, {'do': 'load', 'arg': 'x'}, {'do': 'replace', 'arg': 0},
                        {'do': 'replace', 'arg': True}, {'do': 'replace', 'arg': '12'}, {'do': 'save', 'arg': capture}, {'do': 'remove', 'arg': capture}):
            self.assertIsNone(check(refused, entries))

    def test_the_versions_are_the_library_pages_own_commands(self):
        capture = 'a' * 64
        entries = {capture: {}}
        check = workbench.checked_floor
        self.assertEqual(check({'do': 'versionDefault', 'arg': capture, 'key': 'pedal'}, entries), f'versionDefault:{capture}:pedal')
        self.assertEqual(check({'do': 'useVersion', 'arg': capture, 'key': 'original'}, entries), f'useVersion:{capture}:original')
        self.assertEqual(check({'do': 'listen', 'arg': capture, 'key': 'light16'}, entries), f'listen:{capture}:light16')
        self.assertEqual(check({'do': 'versionRemove', 'arg': capture, 'key': 'pedal'}, entries), f'versionRemove:{capture}:pedal')
        self.assertEqual(check({'do': 'optimize', 'arg': capture, 'key': 'light16'}, entries), f'optimize:{capture}:light16')
        self.assertEqual(check({'do': 'light', 'arg': capture, 'key': '16:quick'}, entries), f'light:{capture}:16:quick')
        for stop in ('listenStop', 'optimizeCancel', 'lightCancel'):
            self.assertEqual(check({'do': stop}, entries), stop)
        for refused in ({'do': 'versionRemove', 'arg': capture, 'key': 'original'},      # the original is never deleted
                        {'do': 'optimize', 'arg': capture, 'key': 'original'}, {'do': 'versionDefault', 'arg': capture, 'key': 'x'},
                        {'do': 'light', 'arg': capture, 'key': '99:quick'}, {'do': 'light', 'arg': capture, 'key': '16:forever'},
                        {'do': 'listen', 'arg': 'b' * 64, 'key': 'original'}):
            self.assertIsNone(check(refused, entries))
        from tone_preview import WorkbenchSession
        for field in ('light', 'optimize', 'listen', 'listen_source', 'can_train', 'can_optimize', 'pedal_block'):
            self.assertIn(field, WorkbenchSession.SHOWN)

    def test_the_session_opens_on_either_page_and_hands_on_what_the_floor_actions_need(self):
        from tone_preview import WorkbenchSession
        for field in ('can_install', 'can_audition', 'trial', 'free_slots', 'replace', 'text', 'busy'):
            self.assertIn(field, WorkbenchSession.SHOWN)
        sidebar = (ROOT / 'nam_sidebar.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'workbench' && ['level', 'library'].includes(value.id)", sidebar)
        script = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("library: !!options.library || options.workbench === 'library'", script)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("preview.workbench_action('levelOpen' if page == 'level' else 'library')", launcher)
        self.assertIn('elif library is not None and (action := checked_floor(value, library.entries())):', launcher)


class ToneTrayTests(unittest.TestCase):
    """Stage 6: TONE3000's site at full height with the tray of what was chosen on it."""

    def test_only_the_windows_own_keep_load_and_end_reach_it(self):
        from threading import Event
        from unittest.mock import Mock
        from queue import Queue
        from tone_preview import TonePreview
        preview = TonePreview(Mock(), '.', Path('x'), Event(), Mock(), browser_factory=Mock())
        preview.browser = Mock(); preview.browser.actions = Queue()
        self.assertFalse(preview.tone_action('keep:3'))                   # not over the Workbench: nothing
        preview.bounds_override = {'visible': True, 'x': 0, 'y': 0, 'w': 800, 'h': 600}
        for good in ('keep:3', 'save:3:21', 'end'):                       # (end: the window's own End preview)
            self.assertTrue(preview.tone_action(good))
        for bad in ('remove:abc', 'save:3:', 'keep:x', 'finish', 'save:3:21;x', 'end:3', 'close', 'bind'):
            self.assertFalse(preview.tone_action(bad))
        self.assertEqual([preview.browser.actions.get_nowait() for _ in range(3)], ['keep:3', 'save:3:21', 'end'])
        preview.workbench = True                                          # never into the Workbench's own session
        self.assertFalse(preview.tone_action('keep:3'))

    def test_the_tray_follows_the_windows_own_steps(self):
        src = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        for piece in ("'state': 'getting'", "tray_mark(tray_now, state='ready', trial=trial, text='')",
                      "tray_mark(item, state='floor', slot=reply['savedSlot'], kept=True)", "self._to_workbench('tone', {'tray':"):
            self.assertIn(piece, src)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("preview.tone_action(f'keep:{trial}')", launcher)
        self.assertIn("preview.tone_action(f'save:{trial}:{slot}')", launcher)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("$('vbody').querySelector('.t3web') || $('vbody')", page)     # the site's part only, the tray beside
        self.assertIn("ask('tray', {do: 'save', trial: t.trial, slot: free[0]});", page)

    def test_the_one_playing_has_a_card_that_says_where_and_can_stop(self):
        # Batch 2 (Nick, 2026-11-23: opening TONE3000 "still feels kind of confusing"): the tray says what is playing,
        # on which block, that nothing is saved, and has Stop preview beside Load on Floor and Keep on this PC.
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        tray = page[page.index('function drawTray() {'):page.index('function libraryRow(')]
        self.assertIn("const playing = all.find(i => i.state === 'ready' && i.trial === t.trial) || null, items = all.filter(i => i !== playing);", tray)
        for words in ("'Playing on '", "'the NAM block on Path ' + (now.dsp + 1)", "'Stop preview'",
                      "ask('tray', {do: 'end', trial: t.trial});", "ask('tray', {do: 'keep', trial: t.trial});",
                      "Stop puts the block\u2019s own capture back."):
            self.assertIn(words, tray)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("if preview is not None and value.get('do') == 'end':\n                        preview.tone_action('end')", launcher)
        src = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        # once the preview has ended the tray no longer shows it as the one playing
        ended = src[src.index("elif action == 'end':"):src.index("status('Target selected. Choose a profile to audition.')")]
        self.assertIn("tray_now['trial'] = None", ended)

    def test_the_banner_over_the_site_is_in_the_workbenchs_colours_and_plain_words(self):
        window = (ROOT / 'tone_browser.cs').read_text(encoding='utf-8')
        self.assertIn('targetBar.BackColor = Color.FromArgb(20, 22, 27);', window)      # workbench.html --panel
        self.assertNotIn('Color.FromArgb(33, 29, 37)', window)                         # the plum strip
        self.assertIn('return "Preview plays on " + PlainTarget(Convert.ToString(label));', window)
        self.assertIn('return "Select a NAM block to hear a tone";', window)
        self.assertIn('popOut.Text = mode == WindowMode.Floating ? "Dock" : "Pop out";', window)   # Pop out stays


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

    def test_the_drawers_add_or_swap_through_the_checked_requests(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        body = page[page.index('const DRAWERS = {'):page.index('// ---- everything together')]
        # onto an empty place: a block with it (checked_add with a slot; an IR with the IR block's model); onto a
        # block of the drawer's kind: its capture or its IR
        self.assertIn("add: (place, c) => chainAsk('add', {...place, slot: c.slot}),", body)
        self.assertIn("add: (place, i) => chainAsk('add', {...place, symbol: IR_BLOCK, slot: i.slot}),", body)
        self.assertIn("swap: (block, c) => ask('capture', {dsp: block.dsp, id: block.id, slot: c.slot}),", body)
        self.assertIn("swap: (block, i) => ask('ir', {dsp: block.dsp, id: block.id, slot: i.slot}),", body)
        self.assertIn("under.closest('.tile.' + kind.tile)", body)                 # only blocks of its kind take a swap
        self.assertIn('fitsOn(engine, Number(target.dataset.dsp))', body)          # a path without room is greyed
        put = page[page.index('function putLibrary('):page.index('function liftLibrary(')]
        self.assertIn('!kind.fits(block)', put)                                  # a click never changes a block's kind
        self.assertIn("if (isNam(block)) button.classList.add('nam-drop'); if (isIr(block)) button.classList.add('ir-drop');", page)
        for tool in ("button('look', 'Floor look'", "button('level', 'Levels'", "button('library', 'Library'", "button('tone', 'TONE3000'"):
            self.assertIn(tool, page)
        self.assertIn("ask('tool', {name, ...rect});", page)               # a tool's window over its frame (lower half or full view)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ('preview.place_over(place)', 'workbench.set_raise(False)', 'preview.on_browser_closed = workbench_tool_closed',
                      "sidebar_action('catalog', '')", 'preview.place_over(None)'):
            self.assertIn(piece, launcher)
        self.assertIn('if (show && raise) SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0013);', (ROOT / 'focus_view.cs').read_text(encoding='utf-8'))
        self.assertIn("browser_factory(window, self.placed(), self.detached)", (ROOT / 'tone_preview.py').read_text(encoding='utf-8'))
        # the slot a capture or an IR asks for is one the drawer was shown (checked_add / checked_capture / checked_ir)
        self.view.state['captures'] = [{'slot': 21, 'name': 'Brit Gold Crunch'}]
        self.view.state['irs'] = [{'slot': 8, 'name': 'Mesa OS 4x12'}]
        self.view.state['blocks'] += [{'dsp': 0, 'id': 'block2', 'model': 'HD2_DelayTest', 'position': 0, 'path': 0, 'enabled': True},
                                      {'dsp': 1, 'id': 'block3', 'model': 'HD2_ImpulseResponse2048', 'position': 2, 'path': 0, 'enabled': True, 'slot': 3}]
        self.assertIsNone(self.view.checked_capture({'dsp': 0, 'id': 'block2', 'slot': 22}))
        self.assertEqual(self.view.checked_capture({'dsp': 0, 'id': 'block2', 'slot': 21})['slot'], 21)
        self.assertEqual(self.view.checked_ir({'dsp': 1, 'id': 'block3', 'slot': 8}), {'action': 'ir', 'dsp': 1, 'id': 'block3', 'slot': 8})
        for refused in ({'dsp': 1, 'id': 'block3', 'slot': 21}, {'dsp': 0, 'id': 'block2', 'slot': 8}, {'dsp': 1, 'id': 'block3', 'slot': True}):
            self.assertIsNone(self.view.checked_ir(refused), refused)          # a capture's slot, not an IR block
        add = lambda **v: self.view.checked_add({'dsp': 1, 'lane': 0, 'place': 5, **v})
        self.assertEqual(add(symbol='HD2_ImpulseResponse1024', slot=8), {'action': 'add', 'dsp': 1, 'lane': 0, 'place': 5, 'symbol': 'HD2_ImpulseResponse1024', 'slot': 8})
        self.assertIsNone(add(symbol='HD2_ImpulseResponse1024', slot=21))        # a capture's slot is not an IR
        self.assertIsNone(add(symbol='HD2_ImpulseResponse2048', slot=8))        # only the drawer's IR block
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("if (!block || !FOCUS_IR_MODEL.test(block.model) || block.slot === command.slot)", script)
        self.assertIn('plainIrs = readIrs(plainIrs);', script)
        self.assertIn('plainIrs() {', (ROOT / 'nam_view.js').read_text(encoding='utf-8'))
        self.assertIn("'ir': view.checked_ir", (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8'))

    def test_a_capture_is_added_with_its_slot_as_one_undo_step(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function addCapture('):binding.index('// What the block picker itself does')]
        self.assertIn("editorEntry(editor, 0xd4, 0x4ffa80, 'undo-open')", body)
        self.assertIn("editorEntry(editor, 0xd8, 0x5044b0, 'undo-close')", body)
        # inside the opened step: the add and the slot with flags 0 (no step of their own), closed with the outcome
        self.assertLess(body.index('open(editor, 0x80000000);'), body.index('result = add(editor, dsp, value, cell, 0);'))
        self.assertLess(body.index('result = add(editor, dsp, value, cell, 0);'), body.index('setIndex(editor, dsp, made.name, slot, 0);'))
        self.assertIn('close(editor, result);', body)
        self.assertIn('!(engines.has(symbol) || IR_MODEL.test(symbol))', body)   # only a NAM engine or an IR block
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('targetBinding.addCapture(editor, command.dsp, command.lane, command.place, next, command.slot);', script)
        self.assertIn('} else addFollow = {dsp: command.dsp', script)          # (the old way when the block was not found)

    def test_the_splits_type_is_one_of_hx_edits_four(self):
        kind = lambda dsp, which, symbol: self.view.checked_split_type({'dsp': dsp, 'id': which, 'symbol': symbol})
        self.assertEqual(kind(0, 'split', 'HD2_AppDSPFlowSplitAB'), {'action': 'splitType', 'dsp': 0, 'symbol': 'HD2_AppDSPFlowSplitAB'})
        self.assertEqual(kind(1, 'split', 'HD2_AppDSPFlowSplitDyn')['dsp'], 1)
        for refused in ((0, 'split', 'HD2_AppDSPFlowSplitY'), (0, 'join', 'HD2_AppDSPFlowSplitAB'), (0, 'block0', 'HD2_AppDSPFlowSplitAB'),
                        (0, 'split', 'HD2_DelayTest'), (0, 'split', None), (2, 'split', 'HD2_AppDSPFlowSplitAB')):
            self.assertIsNone(kind(*refused), refused)                    # the type it has, not a split, not a split type
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('const SPLIT_MODELS'):binding.index('function setModel(') + 400]
        for symbol in ('HD2_AppDSPFlowSplitY', 'HD2_AppDSPFlowSplitAB', 'HD2_AppDSPFlowSplitXOver', 'HD2_AppDSPFlowSplitDyn'):
            self.assertIn(symbol, body)
        self.assertIn("const split = blockName === 'split' && SPLIT_MODELS.includes(symbol);", body)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("targetBinding.setModel(editor, command.dsp, 'split', command.symbol);", script)
        self.assertIn("/^HD2_AppDSPFlowSplit(Y|AB|XOver|Dyn)$/.test(value.symbol)", script)
        self.assertIn("'splitType': view.checked_split_type", (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8'))
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("ask('splitType', {dsp: block.dsp, id: 'split', symbol})", page)

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
            self.assertIn(f"node.onclick = () => {{ if (!dragDone) pickBlock({{dsp: p.dsp, id: '{which}'}}); }};", page)
            self.assertIn(f"el('span', 'node movable' + (same(p.{which}, now) ? ' on' : ''))", page)

class AssignReadTests(unittest.TestCase):
    """Stage 3 step 1: what HX Edit keeps about a block's controls, read from the preset's tree (read-only)."""

    def test_the_tree_is_read_where_hx_edits_own_controller_view_reads_it(self):
        tree = {('controller', 'dsp0.block1.Gain.@controller'): 2, ('controller', 'dsp0.block1.Gain.@min'): 4.0,
                ('controller', 'dsp0.block1.Gain.@max'): 10.0, ('controller', 'dsp0.block1.Level.@cc'): 11,
                ('footswitch', 'dsp0.block1.@fs_index'): 5, ('footswitch', 'dsp0.block1.@fs_customlabel'): 'Teemah!',
                ('snapshot0', 'blocks.dsp0.block1'): True, ('snapshot3', 'blocks.dsp0.block1'): False,
                ('snapshot2', 'controllers.dsp0.block1.Treble.@value'): 8.0}
        fake = 'const T = ' + json.dumps({f'{g}|{k}': v for (g, k), v in tree.items()}) + '; const tree = (g, k) => T[g + "|" + k];'
        got = run_js(['focus_view.js'], '(() => { ' + fake + ' return focusAssign(tree, {dsp: 0, id: "block1"}, ["Gain", "Treble", "Level"]); })()')
        self.assertEqual(got['controls'], {'Gain': {'controller': 2, 'min': 4.0, 'max': 10.0}, 'Level': {'cc': 11}})
        self.assertEqual(got['footswitch'], {'index': 5, 'label': 'Teemah!'})
        self.assertEqual(len(got['snapshots']), 8)
        self.assertEqual(got['snapshots'][0], {'on': True, 'values': {}})
        self.assertEqual(got['snapshots'][2], {'values': {'Treble': 8.0}})
        self.assertEqual(got['snapshots'][3], {'on': False, 'values': {}})

    def test_reading_only_through_the_tree_reader_and_the_tabs_are_open(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function peekTree('):binding.index('// Recalls a snapshot')]  # (writeTree is elsewhere)
        self.assertIn("parameter({editor, dsp: -1, blockName: group}, key).value", body)
        self.assertNotIn('writeValue', body)
        self.assertIn("const treePattern = /^(?:controller|footswitch|snapshot[0-7])$/", binding)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("assign = focusAssign((group, key) => targetBinding.peekTree(editor, group, key), chosen, parameters[chosen.model] || []);", script)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertNotIn('bypass.disabled = values.disabled = true;', page)
        self.assertIn("ctl.append(tabs, panelTab === 'bypass' ? bypassView(block, list) : snapshotView(block, list));", page)

class AssignWriteTests(unittest.TestCase):
    """Stage 3 step 2: a block's footswitch and its controls' controllers, written as HX Edit's own tab writes them."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'blocks': [{'dsp': 0, 'id': 'block1', 'model': 'HD2_DelayTest', 'position': 1, 'path': 0, 'enabled': True}]}

    def test_only_footswitches_colours_labels_and_the_checked_controllers_are_asked_for(self):
        ask = lambda **v: self.view.checked_assign({'dsp': 0, 'id': 'block1', **v})
        key = self.view.catalog()['models']['HD2_DelayTest']['params'][0]['id']
        self.assertEqual(ask(field='fsIndex', value=5), {'action': 'assign', 'dsp': 0, 'id': 'block1', 'field': 'fsIndex', 'value': 5})
        self.assertEqual(ask(field='fsColor', value=11)['value'], 11)
        self.assertEqual(ask(field='fsLabel', value='Lead boost')['value'], 'Lead boost')
        self.assertEqual(ask(field='fsMomentary', value=True)['value'], True)
        self.assertEqual(ask(field='controller', key=key, value=19), {'action': 'assign', 'dsp': 0, 'id': 'block1', 'field': 'controller', 'key': key, 'value': 19})
        self.assertEqual(ask(field='min', key=key, value=0.25)['value'], 0.25)
        self.assertEqual(ask(field='controller', key=key, value=0)['value'], 0)            # None: the assignment taken away
        self.assertEqual(ask(field='controller', key=key, value=18)['value'], 18)          # MIDI CC
        self.assertEqual(ask(field='controller', key=key, value=16)['value'], 16)          # Footswitch 11 (n + 5)
        self.assertEqual(ask(field='cc', key=key, value=64)['value'], 64)
        self.assertEqual(ask(field='fsCc', value=0)['value'], 0)                           # the bypass's MIDI In: Off
        for refused in (dict(field='fsIndex', value=13), dict(field='fsIndex', value=True), dict(field='fsColor', value=12),
                        dict(field='fsLabel', value='x' * 17), dict(field='fsLabel', value='caf\u00e9'), dict(field='fsMomentary', value=1),
                        dict(field='controller', key=key, value=11), dict(field='controller', key=key, value=17), dict(field='controller', key=key, value=20), dict(field='cc', key=key, value=128), dict(field='fsCc', value=-1), dict(field='controller', key='Nope', value=1),
                        dict(field='max', key=key, value=1.5), dict(field='other', value=1)):
            self.assertIsNone(ask(**refused), refused)
        self.assertIsNone(self.view.checked_assign({'dsp': 1, 'id': 'block1', 'field': 'fsIndex', 'value': 2}))

    def test_the_writes_go_as_hx_edits_own_tab_makes_them(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        body = binding[binding.index('function writeTree('):binding.index("  // Focus Mode: a value of a block written")]
        self.assertIn('const writePattern = /^(?:controller|footswitch)$/;', binding)
        self.assertIn('writeValue(editor, -1, groupName, keyName, variant, 0)', body)                 # dsp -1, flags 0
        self.assertIn("let type = {enum: 1, float: 8, bool: 11, text: 10}[kind];", body)
        self.assertIn("if (kind !== 'enum') {", body)                                                  # @controller / @fs_index: type 1
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        for piece in ("fsIndex: ['footswitch', `${at}.@fs_index`, 'enum']", "controller: ['controller', `${at}.${command.key}.@controller`, 'enum']",
                      "min: ['controller', `${at}.${command.key}.@min`, 'float']", 'targetBinding.writeTree(editor, group, key, command.value, kind);'):
            self.assertIn(piece, script)
        self.assertIn("'assign': view.checked_assign", (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8'))

class SnapshotWriteTests(unittest.TestCase):
    """Stage 3 step 3: a value in another snapshot, changed as HX Edit changes one (recall, write, recall back)."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.key = self.view.catalog()['models']['HD2_DelayTest']['params'][0]['id']
        self.view.state = {'blocks': [{'dsp': 0, 'id': 'block1', 'model': 'HD2_DelayTest', 'position': 1, 'path': 0, 'enabled': True}],
                           'selected': {'dsp': 0, 'id': 'block1'}, 'snapshots': ['A', 'B', 'C'], 'snapshot': 0,
                           'assign': {'dsp': 0, 'id': 'block1', 'controls': {self.key: {'controller': 19}}, 'footswitch': {}, 'snapshots': []}}

    def test_only_snapshot_moved_controls_and_the_on_off_of_the_selected_block_in_a_snapshot_of_the_preset(self):
        ask = lambda **v: self.view.checked_snap_value({'dsp': 0, 'id': 'block1', **v})
        got = ask(snapshot=2, key=self.key, value=0.5)
        self.assertEqual((got['action'], got['snapshot'], got['key']), ('snapValue', 2, self.key))
        self.assertEqual(ask(snapshot=1, key='@enabled', value=False)['value'], False)
        self.assertIsNone(ask(snapshot=3, key=self.key, value=0.5))                         # only 3 snapshots
        self.assertIsNone(ask(snapshot=True, key=self.key, value=0.5))
        self.view.state['assign']['controls'] = {self.key: {'controller': 1}}               # a pedal moves it, not snapshots
        self.assertIsNone(ask(snapshot=1, key=self.key, value=0.5))
        self.view.state['selected'] = {'dsp': 1, 'id': 'block1'}
        self.assertIsNone(ask(snapshot=1, key='@enabled', value=False))                     # not the selected block

    def test_the_snapshot_is_recalled_written_and_recalled_back(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        body = script[script.index("command.action === 'snapValue'"):script.index("command.action === 'route'")]
        self.assertLess(body.index('targetBinding.recallSnapshot(editor, command.snapshot)'), body.index('targetBinding.setValue('))
        self.assertLess(body.index('targetBinding.setValue('), body.index('finally {'))
        self.assertIn('if (away) targetBinding.recallSnapshot(editor, now);', body[body.index('finally {'):])
        self.assertIn("'snapValue': view.checked_snap_value", (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8'))
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("ask('snapValue', {dsp: block.dsp, id: block.id, snapshot: s, key, value});", page)
        self.assertIn('snapHeld.set(held(s, key), value);', page)                       # shown as set until HX Edit agrees
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        self.assertIn("if (![1, 4, 5, 6, 7].includes(current.type)) fail('unexpected snapshot value');", binding)
        self.assertIn("if (s !== state.snapshot) { h.title = 'Switch to ' + (names[s] || 'snapshot ' + (s + 1)); h.onclick = () => ask('snapshot', s); }", page)   # a header switches

class CursorTests(unittest.TestCase):
    """The selected block follows the preset's own cursor (it moves on either of HX Edit's tabs), else the edit panel."""

    def test_the_presets_cursor_wins_and_the_panel_is_the_fallback(self):
        cursor = lambda dsp, group: run_js(['focus_view.js'], f'focusCursor({{dsp: 0, block: "block0", editor: 7}}, {json.dumps(dsp)}, {json.dumps(group)})')
        self.assertEqual(cursor(1, 'block3'), {'dsp': 1, 'block': 'block3', 'editor': 7})
        self.assertEqual(cursor(0, 'split'), {'dsp': 0, 'block': 'split', 'editor': 7})
        for dsp, group in ((None, 'block3'), (2, 'block3'), (0, None), (0, 'global'), (0, '')):
            self.assertEqual(cursor(dsp, group), {'dsp': 0, 'block': 'block0', 'editor': 7}, (dsp, group))
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("focusCursor(panelCursor, targetBinding.peekGlobal(editor, 'global', '@cursor_dsp'), targetBinding.peekGlobal(editor, 'global', '@cursor_group'))", script)

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
        self.assertIn('namCost: costOf(catalog.nam[0])', page)

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
        self.assertEqual(script.count('targetBinding.setValue('), 5)   # (and a value in another snapshot)
        self.assertEqual((script.count('targetBinding.setModel('), script.count('targetBinding.setIndex(')), (2, 3))   # (a swap, the split's type; a capture added, an IR)


class WiringTests(unittest.TestCase):
    @unittest.skipUnless(NODE, 'needs Node')
    def test_the_pages_own_script_parses(self):
        # (a stray character in an edit once left the page "Waiting for HX Edit" with no rail, 2026-11-23)
        import re
        import subprocess
        import tempfile
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        script = re.findall(r'<script>(.*?)</script>', page, re.S)[-1]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'page.js'
            path.write_text(script, encoding='utf-8')
            done = subprocess.run([NODE, '--check', str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[:400])

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
        self.assertEqual(asked, {'select', 'set', 'model', 'capture', 'snapshot', 'preset', 'undo', 'redo', 'save', 'menu', 'add', 'remove', 'move', 'moveSplit', 'route', 'assign', 'snapValue', 'splitType', 'ir', 'tool', 'toolPlace', 'toolClose', 'toolDock', 'pin', 'export', 'look', 'lookSave', 'levels', 'prefs', 'library', 'choose', 'tray', 'menuBar', 'rename', 'setlist', 'clear', 'layout', 'scenePin'})

    def test_the_menu_is_the_logo_and_holds_the_layout_and_hx_edits_menu_bar(self):
        # Batch 1 (Nick, 2026-11-23): the app icon top left opens the menu, the "Unbound" button is gone, and the menu
        # no longer repeats the rail's tools or Focus Mode.
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn('<div class="logo"><button id="menuButton"', page)
        self.assertEqual(page.count('id="menuButton"'), 1)
        self.assertNotIn('chip unbound', page)
        menu = page[page.index('function openMenu() {'):page.index('function closeMenu() {')]
        # (Batch 4: the layouts as four cards, test_workbench_batch4)
        for words in ("el('h6', '', 'Layout')", "card('workbench',", "() => ask('menu', 'classic')", "card('classicplus',", "card('stage',"):
            self.assertIn(words, menu)
        # the switch for HX Edit's menu row: only where the row is taken off at all (menu_row.js in place)
        self.assertIn("...(options.menuRow ? [el('hr'), item(\"Show HX Edit's menu bar\",", menu)
        self.assertIn("() => ask('menuBar', !options.menuBar))] : []));", menu)
        for gone in ("'focus'", "'level'", "'look'", "'library'", "setView("):
            self.assertNotIn(gone, menu[:menu.index('// ---- the layouts (Batch 4)')])
        self.assertIn("$('toFocus').onclick = () => ask('menu', 'focus');", page)      # Focus Mode: the Editor | Focus switch
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ("if name == 'menuBar':", 'nam_catalog.save_setting(MENU_BAR, value)', 'workbench.show_options(menu_options())',
                      "return {'level': bool(preview.level), 'menuRow': frame.menu_ok, 'menuBar': menu_bar_kept(), 'layout': layout_kept(),",
                      "frame.apply(focus_on[0] or workbench_on[0], menu_bar_kept())",
                      # the row stays unless it was switched off: away, HX Edit's window grows from launch to launch
                      "return nam_catalog.load_settings().get(MENU_BAR) is not False",
                      "frame.set_window(payload.get('window'))", 'frame.restore()'):
            self.assertIn(piece, launcher)
        show = launcher[launcher.index('            def workbench_show():'):launcher.index('            def workbench_mode(')]
        self.assertIn('frame_show()', show)                                            # either pane on or off: the frame follows

    def test_the_picker_lists_the_nam_categories_beside_hx_edits_own(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        # (Batch 4: the choices are shared with Classic+'s lists, pickChoices ... pickChoice)
        picker = page[page.index('function pickChoices(block) {'):page.index("// ---- Classic+'s Edit area")]
        # (Reveal B9: one category list, "NAM captures" after the stock ones; its kinds are the head row's tabs:
        # test_reveal_polish)
        self.assertIn("models.append(el('h6', '', 'Models'), ...rows.models, el('hr'), ...rows.caps);", picker)
        self.assertIn("captures.filter(c => !pickedKind || namKind(c) === pickedKind)", picker)
        self.assertIn('cats.append(models);', picker)
        # a NAM block's picker opens on its capture's own NAM category
        opener = page[page.index('function pickHome(block, tab) {'):page.index('function closePicker() {')]
        self.assertIn("pickedKind = taken && 'gear' in taken ? namKind(taken) : '';", opener)
        self.assertIn("pickedTab = tab === 'captures' || isNam(block) ? 'all' : '';", opener)

    def test_the_librarys_delete_says_the_floor_keeps_its_slot(self):
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("'Delete from this PC…'", page)
        self.assertIn("that slot is not cleared.", page)
        self.assertNotIn("'Remove…'", page)


@unittest.skipUnless(NODE, 'node is not installed')
class ReviewFindingTests(unittest.TestCase):
    """The two findings of the automated review of PR #7 (2026-11-23), each as it would have gone wrong."""

    def test_a_snapshots_value_is_the_controls_own_value_even_while_it_follows_the_tempo(self):
        # A delay's Time (0.001..8 s) with tempo sync on in the snapshot that is on: the grid's slider stands at the
        # time's own position; valueAt gave the note number there (13 of 18), which went to HX Edit as the time.
        out = run_js(['pane_controls.js'], """(() => {
          globalThis.catalog = {controls: {sync_note: {format: Array.from({length: 18}, (_, i) => 'note' + i)}}};
          globalThis.state = {values: {TempoSync1: true, SyncSelect1: 5, Time: 1}};
          const p = {id: 'Time', min: 0.001, max: 8, sync: {switch: 'TempoSync1', note: 'SyncSelect1', min: 0}};
          const x = turn(p, 1), dial = valueAt(p, x), own = ownValueAt(p, x);
          state.values.TempoSync1 = false;
          return {dial, own, free: valueAt(p, x), steps: ownValueAt({id: 'Voices', min: 1, max: 5, kind: 'steps'}, 0.5),
                  ends: [ownValueAt(p, -1), ownValueAt(p, 2)]};
        })()""")
        self.assertEqual(out['dial'], 13)                          # the dial itself turns notes while synced: unchanged
        self.assertAlmostEqual(out['own'], 1.0, places=6)          # the snapshot's cell keeps the time
        self.assertAlmostEqual(out['free'], 1.0, places=6)         # and without sync the two agree
        self.assertEqual(out['steps'], 3)
        self.assertAlmostEqual(out['ends'][0], 0.001, places=6)
        self.assertAlmostEqual(out['ends'][1], 8.0, places=6)
        page = (ROOT / 'workbench.html').read_text(encoding='utf-8')
        self.assertIn("slide.onchange = () => change(s, p.id, ownValueAt(p, Number(slide.value)));", page)
        self.assertIn("slide.oninput = () => { label.textContent = shown(p, ownValueAt(p, Number(slide.value))); };", page)
        self.assertIn("const at = (p, n) => shown(p, ownValueAt(p, n));", page)    # a controller's range end, the same

    def test_an_ir_block_that_shows_late_still_gets_the_ir_that_was_dragged(self):
        made = lambda blocks, follow: run_js(['focus_view.js'], 'focusAddMade(%s, %s, ["HD2_AmpNAM", "HD2_AmpNAMPedal"])' % (json.dumps(blocks), json.dumps(follow)))
        chain = [{'dsp': 0, 'id': 'inputA', 'model': 'HD2_AppDSPFlow1Input'},
                 {'dsp': 0, 'id': 'block2', 'model': 'HD2_ImpulseResponse1024', 'position': 3, 'path': 0},
                 {'dsp': 0, 'id': 'block3', 'model': 'HD2_AmpNAMPedal', 'position': 4, 'path': 0},
                 {'dsp': 1, 'id': 'block0', 'model': 'HD2_ImpulseResponse1024', 'position': 3, 'path': 0}]
        ir = {'dsp': 0, 'lane': 0, 'place': 3, 'model': 'HD2_ImpulseResponse1024', 'slot': 9}
        self.assertEqual(made(chain, ir)['id'], 'block2')                                   # the IR block: found now
        self.assertEqual(made(chain, {**ir, 'place': 4, 'model': 'HD2_AmpNAM'})['id'], 'block3')   # a capture: any NAM engine, as before
        self.assertIsNone(made(chain, {**ir, 'place': 4}))                                  # another model at that place
        self.assertIsNone(made(chain, {**ir, 'lane': 1}))                                   # another lane
        self.assertIsNone(made(chain, {**ir, 'model': 'HD2_ImpulseResponse2048'}))          # not the block that was added
        self.assertIsNone(made([], ir))
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("slot: command.slot, model: next, until: Date.now() + ADD_FOLLOW_MS};", script)
        self.assertIn('const made = focusAddMade(blocks, addFollow, namEngines);', script)


if __name__ == '__main__':
    unittest.main()
