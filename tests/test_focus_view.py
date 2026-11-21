"""Focus Mode (HX Unbound menu): the catalog built from HX Edit's own files, the pane's driver, the script's
reading of a preset, and the menu wiring. No editor process, no device."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

import msgpack

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))

import focus_view  # noqa: E402
from dsp_meter import DspMeter  # noqa: E402

NODE = shutil.which('node')
CONTROLS = {
    'generic_knob': {'dspToDisplayScale': 10, 'format': '%.1f', 'step': {'fine': .1}},
    'percent': {'dspToDisplayScale': 100, 'format': '%.0f', 'formatUnits': '%.0f %%'},
    'time_ms': {'dspToDisplayScale': 1000.0, 'format': [{'lowerBound': 0, 'upperBound': 99999, 'format': '%.0f', 'formatUnits': '%.0f ms'}]},
    'time_ms_20_1800': {'alias': 'time_ms'},
    'off_on': {'isDiscrete': True, 'controlType': 'segmented', 'format': ['Off', 'On']},
    'polarity': {'isDiscrete': True, 'format': ['Normal', 'Inverted']},
    'bbd_size': {'isDiscrete': True, 'format': ['1024', '2048', '4096', '8192']},
    'sync_note': {'isDiscrete': True, 'format': ['1/1', '1/2']},
    'ir_select': {},
}
DELAY = {'symbolicID': 'HD2_DelayTest', 'name': 'Test Delay', 'category': 9, 'params': [
    {'symbolicID': 'Time', 'name': 'Time', 'min': .02, 'max': 1.8, 'default': .4, 'valueType': 1, 'displayType': 'time_ms_20_1800'},
    {'symbolicID': 'Scale', 'name': 'Scale', 'min': 0.0, 'max': 1.0, 'default': .75, 'valueType': 1, 'displayType': 'percent', 'stereo-only': True},
    {'symbolicID': 'Mix', 'name': 'Mix', 'min': 0.0, 'max': 1.0, 'default': .5, 'valueType': 1, 'displayType': 'percent'},
    {'symbolicID': 'BBD Size', 'name': 'BBD Size', 'min': 0, 'max': 3, 'default': 2, 'valueType': 0, 'displayType': 'bbd_size'},
    {'symbolicID': 'Depth', 'name': 'Depth', 'min': 0.0, 'max': 1.0, 'default': .2, 'valueType': 1, 'displayType': 'generic_knob'},
    {'symbolicID': 'SyncSelect1', 'name': 'Note Sync', 'min': 1, 'max': 2, 'default': 1, 'valueType': 0, 'displayType': 'sync_note'},
    {'symbolicID': 'TempoSync1', 'name': 'Tempo Sync', 'min': False, 'max': True, 'default': False, 'valueType': 2, 'displayType': 'off_on'},
    {'symbolicID': '@enabled', 'name': 'Enabled', 'min': False, 'max': True, 'default': True, 'valueType': 2},
    {'symbolicID': '@trails', 'name': 'Trails', 'min': False, 'max': True, 'default': False, 'valueType': 2, 'displayType': 'off_on'},
    {'symbolicID': '@stereo', 'name': 'Stereo', 'min': False, 'max': True, 'default': False, 'valueType': 2}]}
DELAY_ORDER = [[{'TempoSync1': None}, {'SyncSelect1': 'Note Sync'}, {'Time': None}], {'BBD Size': None}, {'Mix': 'Blend'}, {'@trails': 'Trails'}]
NAM = {'symbolicID': 'HD2_AmpNAMLite', 'name': 'NAM A2 Lite', 'category': 1, 'params': [
    {'symbolicID': 'Index', 'name': 'Model', 'min': 1, 'max': 128, 'default': 1, 'valueType': 0, 'displayType': 'ir_select'},
    {'symbolicID': 'Drive', 'name': 'Input', 'min': 0.0, 'max': 1.0, 'default': .5, 'valueType': 1, 'displayType': 'generic_knob'},
    {'symbolicID': 'Polarity', 'name': 'Polarity', 'min': False, 'max': True, 'default': False, 'valueType': 2, 'displayType': 'polarity'},
    {'symbolicID': '@enabled', 'name': 'Enabled', 'min': False, 'max': True, 'default': True, 'valueType': 2}]}


def nul(value):
    """HX Edit's msgpack files end every string with a NUL."""
    if isinstance(value, dict):
        return {nul(k): nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [nul(v) for v in value]
    return value + '\0' if isinstance(value, str) else value


def resources(folder):
    res = Path(folder, 'res')
    (res / 'icons_models').mkdir(parents=True)
    (res / 'icons_models' / 'FX_Delay.png').write_bytes(b'png')
    (res / 'icons_models' / 'icon-inputs_%18.png').write_bytes(b'strip')
    tree = {'categories': [
        {'name': 'Delay', 'id': 5, 'color': '0x00CC00', 'subcategories': [
            {'name': 'Mono', 'models': [{'id': 'HD2_DelayTest', 'name': 'Test Delay', 'image': 'FX_Delay.png', 'params': DELAY_ORDER}]}]},
        {'name': 'Input', 'id': 18, 'color': '0x989898', 'models': [{'id': 'HD2_In', 'name': 'Input', 'image': 'icon-inputs_%18.png', 'params': []}]},
        {'name': 'NAM Amp', 'id': 24, 'color': '0xB070E0', 'subcategories': [
            {'name': 'All', 'models': [{'id': 'HD2_AmpNAMLite', 'name': 'NAM A2 Lite  ', 'image': 'X.png', 'params': [{'Index': 'Model'}]}]}]}]}
    definitions = [DELAY, NAM, {'symbolicID': 'HD2_In', 'name': 'Input', 'params': []}]
    (res / 'HelixModelDefs.bin').write_bytes(msgpack.packb(nul(definitions), use_single_float=True))
    (res / 'HX_ModelCatalog.bin').write_bytes(msgpack.packb(nul(tree), use_single_float=True))
    (res / 'HelixControls.json').write_text(json.dumps(CONTROLS), encoding='utf-8')
    return res


class ParameterTests(unittest.TestCase):
    def test_controls_follow_hx_edits_order_and_a_tempo_group_is_one_control(self):
        params = focus_view.parameters(DELAY, DELAY_ORDER, CONTROLS)
        self.assertEqual([p['id'] for p in params], ['Time', 'BBD Size', 'Mix', '@trails', 'Depth'])   # listed first, then the rest
        time_, size, mix, trails, depth = params
        self.assertEqual(time_['sync'], {'switch': 'TempoSync1', 'note': 'SyncSelect1', 'min': 1})
        self.assertEqual((time_['kind'], size['kind'], trails['kind'], depth['kind']), ('knob', 'steps', 'switch', 'knob'))
        self.assertEqual(mix['name'], 'Blend')                                                        # the catalog's own label wins
        self.assertEqual((time_['min'], time_['max'], time_['default']), (.02, 1.8, .4))

    def test_stereo_only_values_and_the_blocks_own_flags_are_not_controls(self):
        ids = [p['id'] for p in focus_view.parameters(DELAY, None, CONTROLS)]
        for hidden in ('Scale', '@enabled', '@stereo', 'SyncSelect1', 'TempoSync1'):
            self.assertNotIn(hidden, ids)
        self.assertIn('@trails', ids)

    def test_a_two_position_list_is_a_switch(self):
        params = {p['id']: p for p in focus_view.parameters(NAM, None, CONTROLS)}
        self.assertEqual(params['Polarity']['kind'], 'switch')
        self.assertEqual(params['Drive']['name'], 'Input')


class CatalogTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.res = resources(self.folder.name)

    def test_a_model_has_its_name_colour_scene_picture_and_controls(self):
        catalog = focus_view.catalog(self.res, {})
        delay = catalog['models']['HD2_DelayTest']
        self.assertEqual((delay['name'], delay['category'], delay['key'], delay['tint']), ('Test Delay', 'Delay', 'delay', [0, 204, 0]))
        self.assertEqual(delay['scene'], 'deep_sea')                                # the Floor tool's default for Delay
        self.assertEqual(delay['pictures'], ['https://models.focus.example/FX_Delay.png'])
        self.assertEqual(catalog['controls']['time_ms_20_1800']['dspToDisplayScale'], 1000.0)   # the alias is followed
        self.assertNotIn('step', catalog['controls']['generic_knob'])               # only what the page draws with
        self.assertIn('sync_note', catalog['controls'])
        self.assertIn('deep_sea', catalog['scenes'])
        self.assertEqual(catalog['scenes']['deep_sea']['pictures'], ['https://scenes.focus.example/deep_sea.png'])

    def test_the_nam_block_is_filed_as_the_floor_files_it_and_drawn_in_its_own_colour(self):
        nam = focus_view.catalog(self.res, {})['models']['HD2_AmpNAMLite']
        self.assertEqual((nam['name'], nam['category'], nam['key'], nam['scene']), ('NAM A2 Lite', 'NAM', 'amp', 'stage'))
        self.assertEqual(nam['tint'], [0xB0, 0x70, 0xE0])

    def test_the_stock_input_strip_is_never_a_picture(self):
        self.assertEqual(focus_view.catalog(self.res, {})['models']['HD2_In']['pictures'], [])

    def test_the_floor_look_pages_choice_moves_a_category_to_another_scene(self):
        settings = {'floorLook': {'assign': {'default': 'studio', 'category': {'delay': 'synthwave'}}}}
        self.assertEqual(focus_view.catalog(self.res, settings)['models']['HD2_DelayTest']['scene'], 'synthwave')

    def test_larger_pictures_are_used_where_this_pc_has_them(self):
        plates = Path(self.folder.name, 'plates')
        plates.mkdir()
        shutil.copyfile(ROOT / 'focus_backgrounds' / 'backgrounds' / 'deep_sea.png', plates / 'deep_sea.png')
        scene = focus_view.catalog(self.res, {'focusArt': {'scenes': str(plates)}})['scenes']['deep_sea']
        self.assertEqual(scene['pictures'][0], 'https://plates.focus.example/deep_sea.png')
        self.assertEqual((scene['w'], scene['h']), (800, 480))                      # read from the picture itself
        self.assertEqual(scene['small']['picture'], 'https://scenes.focus.example/deep_sea.png')
        self.assertIn('plates', focus_view.art_folders(self.res, {'focusArt': {'scenes': str(plates)}}))
        self.assertNotIn('plates', focus_view.art_folders(self.res, {'focusArt': {'scenes': str(plates / 'missing')}}))

    def test_a_test_build_can_name_this_pcs_folders_without_the_settings_file(self):
        from unittest.mock import patch
        plates = Path(self.folder.name, 'named')
        plates.mkdir()
        with patch.dict('os.environ', {'HX_EDIT_FOCUS_ART': json.dumps({'scenes': str(plates)})}):
            self.assertEqual(focus_view.art_folders(self.res, {})['plates'], plates)
        with patch.dict('os.environ', {'HX_EDIT_FOCUS_ART': 'not json'}):
            self.assertNotIn('plates', focus_view.art_folders(self.res, {}))

    def test_the_script_reads_every_control_and_its_tempo_pair(self):
        options = focus_view.frida_options(focus_view.catalog(self.res, {})['models'])
        self.assertEqual(options['focusParameters']['HD2_DelayTest'], ['Time', 'TempoSync1', 'SyncSelect1', 'BBD Size', 'Mix', '@trails', 'Depth'])
        self.assertIn('HD2_AmpNAMLite', options['focusNamEngines'])

    def test_the_pane_is_given_only_local_folders(self):
        command = focus_view.pane_command('FocusView.exe', 1234, 'profile', {'app': Path('a'), 'models': Path('m')})
        self.assertEqual(command, ['FocusView.exe', '1234', 'profile', 'https://app.focus.example/focus_view.html',
                                   f'app.focus.example={Path("a")}', f'models.focus.example={Path("m")}'])


class FakePane:
    """Stands in for FocusView.exe: its output is read line by line, its input is recorded."""
    def __init__(self, command, **_):
        import queue
        self.command, self.lines, self.events = command, [], queue.Queue()
        self.stdin, self.stdout = self, self
    def write(self, text): self.lines.append(text)
    def flush(self): pass
    def poll(self): return None
    def wait(self, timeout=None): return 0
    def __iter__(self): return iter(self.events.get, None)
    def say(self, value): self.events.put(json.dumps(value) + '\n')


class PaneDriverTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.panes, self.actions = [], []
        def factory(command, **options):
            self.panes.append(FakePane(command, **options))
            return self.panes[-1]
        self.view = focus_view.FocusView(resources(folder.name), process_factory=factory, exe='FocusView.exe',
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

    def test_the_pane_starts_when_focus_mode_is_on_and_hx_edit_has_said_where_it_goes(self):
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        time.sleep(.1)
        self.assertEqual(self.panes, [])                                # off: no process at all
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.assertEqual(self.panes[0].command[1], '4242')
        self.assertTrue(self.wait(lambda: self.lines('C')))
        self.assertEqual(self.lines('C')[-1], {'visible': True, 'x': 0, 'y': 41, 'w': 1920, 'h': 913})

    def test_the_page_gets_the_catalog_then_each_state_and_hides_when_turned_off(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {}}})
        self.assertTrue(self.wait(lambda: self.panes))
        time.sleep(.1)
        self.assertEqual(self.lines('P'), [])                           # nothing before the page has loaded
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: len(self.lines('P')) >= 2))
        first, second = self.lines('P')[:2]
        self.assertEqual(first['type'], 'catalog')
        self.assertIn('HD2_DelayTest', first['catalog']['models'])
        self.assertEqual(second, {'type': 'state', 'state': {'blocks': [], 'selected': None, 'values': {}}})
        self.view.receive({'type': 'focusState', 'state': {'blocks': [{'dsp': 0}], 'selected': None, 'values': {}}})
        self.assertTrue(self.wait(lambda: len(self.lines('P')) >= 3))
        self.view.set_on(False)
        self.assertTrue(self.wait(lambda: self.lines('C')[-1] == {'visible': False, 'x': 0, 'y': 41, 'w': 1920, 'h': 913}))
        self.assertFalse(self.view.receive({'type': 'dspLoad'}))        # not one of this pane's messages

    def test_the_pages_editor_button_and_a_pane_that_fails_reach_the_launcher(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'action', 'name': 'exit', 'value': None})
        self.panes[0].say({'type': 'error', 'text': 'no WebView2'})
        self.assertTrue(self.wait(lambda: len(self.actions) >= 2))
        self.assertEqual(self.actions[:2], [('exit', None), ('failed', 'no WebView2')])


def run_js(files, expression):
    source = '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in files)
    result = subprocess.run([NODE, '-e', source + f'\nprocess.stdout.write(JSON.stringify({expression}));'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, 'node is not installed')
class ScriptTests(unittest.TestCase):
    READER = '''(() => { const values = {
        "0|inputA|@model": "HD2_AppDSPFlow1Input", "0|outputA|@model": "HD2_AppDSPFlowOutput",
        "0|block0|@model": "HD2_AmpNAMLite", "0|block0|@position": 1, "0|block0|@path": 0, "0|block0|@enabled": true,
        "0|block0|Index": 28, "0|block0|Drive": 0.83, "0|block0|Polarity": false,
        "0|block3|@model": "HD2_DelayTest", "0|block3|@position": 4, "0|block3|@path": 1, "0|block3|@enabled": false,
        "1|inputA|@model": "HD2_AppDSPFlow1Input" };
      return (dsp, place, key) => values[dsp + "|" + place + "|" + key]; })()'''

    def test_a_preset_is_read_block_by_block_with_the_selected_blocks_values(self):
        state = run_js(['focus_view.js'], f'focusSnapshot({self.READER}, {{dsp: 0, block: "block0"}}, '
                       '{HD2_AmpNAMLite: ["Index", "Drive", "Polarity", "Gone"]}, ["HD2_AmpNAMLite"])')
        self.assertEqual([(b['dsp'], b['id']) for b in state['blocks']],
                         [(0, 'inputA'), (0, 'outputA'), (0, 'block0'), (0, 'block3'), (1, 'inputA')])
        nam, delay = state['blocks'][2], state['blocks'][3]
        self.assertEqual(nam, {'dsp': 0, 'id': 'block0', 'model': 'HD2_AmpNAMLite', 'position': 1, 'path': 0, 'enabled': True, 'slot': 28})
        self.assertEqual((delay['path'], delay['enabled']), (1, False))
        self.assertNotIn('slot', delay)
        self.assertEqual(state['selected'], {'dsp': 0, 'id': 'block0'})
        self.assertEqual(state['values'], {'Index': 28, 'Drive': 0.83, 'Polarity': False})     # a value that is not there is left out

    def test_no_cursor_or_a_cursor_on_nothing_selects_no_block(self):
        for cursor in ('null', '{dsp: 1, block: "block9"}'):
            state = run_js(['focus_view.js'], f'focusSnapshot({self.READER}, {cursor}, {{}}, [])')
            self.assertIsNone(state['selected'])
            self.assertEqual(state['values'], {})

    def test_the_pane_covers_the_signal_flow_and_the_edit_panel_across_the_window(self):
        box = run_js(['focus_view.js'], 'focusPaneBounds({x:318,y:45,w:1592,h:248}, {x:308,y:0,w:1612,h:954}, {x:0,y:0,w:1920,h:989})')
        self.assertEqual(box, {'x': 0, 'y': 41, 'w': 1920, 'h': 913})                 # HX Edit's top row and status bar stay
        self.assertIsNone(run_js(['focus_view.js'], 'focusPaneBounds(null, {x:308,y:0,w:1612,h:954}, {x:0,y:0,w:1920,h:989})'))
        self.assertIsNone(run_js(['focus_view.js'], 'focusPaneBounds({x:318,y:45,w:300,h:100}, {x:308,y:0,w:300,h:200}, {x:0,y:0,w:500,h:240})'))

    def test_the_script_checks_the_same_native_bytes_as_the_hooks_it_shares(self):
        guards = run_js(['focus_view.js', 'nav_banner.js'], '[focusViewGuards, navigationBannerGuards]')
        self.assertEqual(guards[0]['3b7e00'], guards[1]['3b7e00'])
        self.assertTrue(guards[0]['218a00'].startswith('558bec'))


class WiringTests(unittest.TestCase):
    def test_the_menu_item_reaches_the_launcher_and_its_tick_comes_back(self):
        self.assertIn('focusMode', DspMeter.CHOICES)
        helper = (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8')
        self.assertIn('Console.Out.WriteLine("focusMode")', helper)
        self.assertIn('state.TryGetValue("focusMode"', helper)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ("name == 'focusMode'", "'focus_view.js'", 'installFocusView(', "script.post({'type': 'focusMode'",
                      "meter.set_chain_option('focusMode', on)", 'focus.receive(payload)', 'focus.close()'):
            self.assertIn(piece, launcher)

    def test_the_script_only_reads(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        for writer in ('setIndex', 'setModel', 'addModel', 'writeValue', '.restore(', 'Interceptor.replace', 'write'):
            self.assertNotIn(writer, script.replace('writes', '').replace('Writes', ''))
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        peek = binding[binding.index('function peekValue'):binding.index('function setIndex')]
        self.assertIn('parameter(', peek)
        self.assertNotIn('writeValue', peek)

    def test_the_package_carries_the_page_the_script_and_the_pane(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('build_windows', ROOT / 'build-windows.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('focus_view.py', 'focus_view.js', 'focus_view.cs', 'focus_view.html'):
            self.assertIn(name, module.APP_FILES)
            self.assertTrue((ROOT / name).is_file())

    def test_the_page_is_local_and_asks_only_to_leave(self):
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        self.assertNotIn('http://', page)
        self.assertEqual(page.count('https://'), 0)                      # no font, script or picture from the internet
        self.assertIn("ask('exit')", page)
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('args.Cancel = args.Uri != page', pane)            # the pane opens nothing but the page


if __name__ == '__main__':
    unittest.main()
