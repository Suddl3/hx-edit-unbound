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

import floor_store  # noqa: E402
import focus_view  # noqa: E402
from dsp_meter import DspMeter  # noqa: E402

NODE = shutil.which('node')


def setUpModule():
    # The tests describe a clone without the art pack: what this PC has unzipped into art/ must not change them.
    from unittest.mock import patch
    local = patch.object(focus_view, 'LOCAL_ART', {})
    local.start()
    unittest.addModuleCleanup(local.stop)
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
            {'name': 'All', 'models': [{'id': 'HD2_DelayTest', 'name': 'Test Delay', 'image': 'FX_Delay.png', 'params': DELAY_ORDER}]},
            {'name': 'Mono', 'models': [{'id': 'HD2_DelayTest', 'name': 'Test Delay', 'image': 'FX_Delay.png', 'params': DELAY_ORDER},
                                        {'id': 'HD2_DelayOther', 'name': 'Other Delay', 'image': 'FX_Delay.png', 'params': []}]},
            {'name': 'Stereo', 'models': [{'id': 'HD2_DelayTest', 'use_subcategory': 4}, {'id': 'HD2_DelayOther', 'name': 'Other Delay'},
                                          {'id': 'HD2_DelayWide', 'name': 'Wide Delay', 'image': 'FX_Delay.png', 'params': []}]}]},
        {'name': 'Input', 'id': 18, 'color': '0x989898', 'models': [{'id': 'HD2_In', 'name': 'Input', 'image': 'icon-inputs_%18.png', 'params': []}]},
        {'name': 'NAM Amp', 'id': 24, 'color': '0xB070E0', 'subcategories': [
            {'name': 'All', 'models': [{'id': 'HD2_AmpNAMLite', 'name': 'NAM A2 Lite  ', 'image': 'X.png', 'params': [{'Index': 'Model'}]}]}]}]}
    definitions = [DELAY, NAM, {'symbolicID': 'HD2_In', 'name': 'Input', 'params': []},
                   {'symbolicID': 'HD2_DelayOther', 'name': 'Other Delay', 'load': 30.0, 'params': []},
                   {'symbolicID': 'HD2_DelayWide', 'name': 'Wide Delay', 'load': 4.5, 'params': []}]
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
        self.assertTrue(size.get('whole'))                                                            # whole steps only
        self.assertNotIn('whole', mix)

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
        self.assertTrue(delay['bypass'])                                            # it has an "@enabled" of its own
        self.assertFalse(catalog['models']['HD2_In']['bypass'])
        self.assertEqual(catalog['controls']['time_ms_20_1800']['dspToDisplayScale'], 1000.0)   # the alias is followed
        self.assertNotIn('step', catalog['controls']['generic_knob'])               # only what the page draws with
        self.assertIn('sync_note', catalog['controls'])
        self.assertIn('deep_sea', catalog['scenes'])
        self.assertEqual(catalog['scenes']['deep_sea']['pictures'], ['https://scenes.focus.example/deep_sea.png'])

    def test_the_pictures_a_block_can_be_given_are_the_models_and_the_captures(self):
        catalog = focus_view.catalog(self.res, {})
        self.assertEqual(catalog['models']['HD2_DelayTest']['picture'], 'model:FX_Delay.png')
        self.assertIsNone(catalog['models']['HD2_In']['picture'])                   # the stock input strip is not a picture
        self.assertEqual(catalog['pictures']['model:FX_Delay.png'],
                         {'name': 'Test Delay', 'group': 'Delay', 'urls': ['https://models.focus.example/FX_Delay.png']})
        capture = catalog['pictures']['capture:brit_gold_head']
        self.assertEqual((capture['name'], capture['group']), ('Brit gold head', 'NAM'))
        self.assertEqual(capture['urls'][-1], 'https://captures.focus.example/brit_gold_head.png')
        self.assertTrue(all(focus_view.PICTURE_ID.fullmatch(ident) for ident in catalog['pictures']))

    def test_the_kinds_of_nam_capture_are_the_block_pickers(self):
        kinds = focus_view.catalog(self.res, {})['nam_kinds']
        self.assertEqual([kind['name'] for kind in kinds], ['NAM Amp', 'NAM Amp + cab', 'NAM Cab', 'NAM Pedal', 'NAM Other'])
        self.assertEqual(kinds[1]['gears'], ['amp-cab', 'amp-pedal-cab'])
        self.assertEqual(kinds[-1]['gears'], [])                                    # the last one takes the rest
        import nam_catalog
        self.assertEqual([kind['name'] for kind in kinds], [name for name, _ in nam_catalog.NAM_CATEGORY_GROUPS])
        # the same rule as the block picker's own (tone_view.js captureGroup)
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("return gear === 'amp' || gear === 'preamp' ? 1 : gear === 'amp-cab' || gear === 'amp-pedal-cab' ? 2 :\n"
                      "      gear === 'cab' ? 3 : gear === 'pedal' || gear === 'pedal-amp' ? 4 : 5;", tone)

    def test_the_nam_block_is_filed_as_the_floor_files_it_and_drawn_in_its_own_colour(self):
        nam = focus_view.catalog(self.res, {})['models']['HD2_AmpNAMLite']
        self.assertEqual((nam['name'], nam['category'], nam['key'], nam['scene']), ('NAM A2 Lite', 'NAM', 'amp', 'stage'))
        self.assertEqual(nam['tint'], [0xB0, 0x70, 0xE0])

    def test_the_lists_a_model_is_chosen_from_are_hx_edits_own_without_repeats(self):
        lists = focus_view.catalog(self.res, {})['lists']
        self.assertEqual([group['name'] for group in lists], ['Delay'])           # no Input, no NAM category: those are not models to pick
        self.assertEqual(lists[0]['tint'], [0, 204, 0])
        # "All" repeats the folders beside it; a model listed again under Stereo is the same model.
        self.assertEqual(lists[0]['folders'], [{'name': 'Mono', 'models': ['HD2_DelayTest', 'HD2_DelayOther']},
                                               {'name': 'Stereo', 'models': ['HD2_DelayWide']}])
        self.assertEqual(focus_view.model_loads(self.res), {'HD2_DelayOther': 30.0, 'HD2_DelayWide': 4.5})
        # (the lists must not disturb the pictures' addresses: a capture's picture comes from these)
        self.assertEqual(focus_view.catalog(self.res, {})['captures']['pictures'], ['https://captures.focus.example/{icon}.png'])

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

    def test_the_art_pack_unzipped_into_the_clone_is_found_without_a_setting(self):
        from unittest.mock import patch
        pack = Path(self.folder.name, 'art')
        for part in ('helix-gear-art/full', 'nam-gear-art/full', 'focus-backgrounds/sources'):
            (pack / part).mkdir(parents=True)
        named = Path(self.folder.name, 'named')
        named.mkdir()
        local = {'full': (pack / 'helix-gear-art' / 'full',), 'capturesfull': (pack / 'nam-gear-art' / 'full',),
                 'plates': (pack / 'focus-backgrounds' / 'sources',)}
        with patch.object(focus_view, 'LOCAL_ART', local):
            folders = focus_view.art_folders(self.res, {})
            self.assertEqual((folders['full'], folders['capturesfull'], folders['plates']),
                             (pack / 'helix-gear-art' / 'full', pack / 'nam-gear-art' / 'full', pack / 'focus-backgrounds' / 'sources'))
            self.assertEqual(focus_view.art_folders(self.res, {'focusArt': {'models': str(named)}})['full'], named)  # a named folder wins
        self.assertEqual(focus_view.PACK, ROOT.parent / 'art')

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


class LookTests(unittest.TestCase):
    """Looks: the defaults (one background per kind of block), what a preset changes, what a block in it changes."""
    SCENES = {'studio': {}, 'stage': {}, 'space': {}, 'synthwave': {}, 'deep_sea': {}}
    PICTURES = {'model:FX_Delay.png': {}, 'capture:brit_gold_head': {}}
    MODELS = {'HD2_DelayTest': {}, 'HD2_AmpNAMLite': {}}
    PRESET = {'setlist': 3, 'number': 5, 'name': 'Mahadeva'}
    HERE = {'setlist': 3, 'number': 5}

    def change(self, settings, change, preset=None):
        return focus_view.look_change(settings, change, preset or self.PRESET, self.SCENES, self.PICTURES, self.MODELS)

    def keep(self, settings, change, preset=None):
        changed = self.change(settings, change, preset)
        self.assertTrue(changed, change)
        settings.update(changed)
        return settings

    def test_a_block_gets_its_own_background_and_picture_in_the_loaded_preset_only(self):
        settings = {}
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'synthwave'})
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'slot:18', 'picture': 'model:FX_Delay.png'})
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'picture': 'capture:brit_gold_head'})
        self.assertEqual(settings['presetLooks'], {'3:5': {'name': 'Mahadeva', 'blocks': {
            'HD2_DelayTest': {'scene': 'synthwave', 'picture': 'capture:brit_gold_head'}, 'slot:18': {'picture': 'model:FX_Delay.png'}}}})
        self.assertNotIn('floorLook', settings)                                      # the defaults are not touched
        # one of them put back: the other stays; the last one put back: nothing is kept for the preset
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': None})
        self.assertEqual(settings['presetLooks']['3:5']['blocks']['HD2_DelayTest'], {'picture': 'capture:brit_gold_head'})
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'picture': None})
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'slot:18', 'picture': None})
        self.assertEqual(settings['presetLooks'], {})

    def test_what_is_not_this_editors_or_not_the_loaded_preset_is_refused(self):
        for refused in ({'scope': 'block', 'preset': {'setlist': 3, 'number': 6}, 'key': 'HD2_DelayTest', 'scene': 'space'},   # another preset
                        {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_Unknown', 'scene': 'space'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'slot:129', 'scene': 'space'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'slot:0', 'scene': 'space'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'no_such_scene'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'picture': 'model:Other.png'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'picture': '../x.png'},
                        {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest'},                                      # nothing to change
                        {'scope': 'preset', 'preset': self.HERE, 'scene': 'no_such_scene'}, {'scope': 'preset', 'preset': self.HERE},
                        {'scope': 'preset', 'preset': self.HERE, 'clear': True}, {'scope': 'preset', 'preset': self.HERE, 'adopt': True},
                        {'scope': 'default', 'category': 'nonsense', 'scene': 'space'}, {'scope': 'default', 'category': 'delay', 'scene': 'nope'},
                        {'scope': 'elsewhere'}, 'look', None):
            self.assertEqual(self.change({}, refused), {}, refused)
        for preset in (None, {'setlist': 3, 'number': 128, 'name': ''}, {'setlist': True, 'number': 5, 'name': ''}):          # no preset known
            self.assertEqual(focus_view.look_change({}, {'scope': 'preset', 'preset': self.HERE, 'scene': 'space'}, preset,
                                                    self.SCENES, self.PICTURES, self.MODELS), {})

    def test_a_preset_has_one_background_and_goes_back_to_the_defaults(self):
        settings = self.keep({}, {'scope': 'preset', 'preset': self.HERE, 'scene': 'space'})
        self.keep(settings, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'synthwave'})
        self.assertEqual(settings['presetLooks']['3:5'], {'name': 'Mahadeva', 'scene': 'space', 'blocks': {'HD2_DelayTest': {'scene': 'synthwave'}}})
        self.keep(settings, {'scope': 'preset', 'preset': self.HERE, 'scene': None})           # by kind of block again: the block keeps its own
        self.assertEqual(settings['presetLooks']['3:5'], {'name': 'Mahadeva', 'blocks': {'HD2_DelayTest': {'scene': 'synthwave'}}})
        self.keep(settings, {'scope': 'preset', 'preset': self.HERE, 'clear': True})
        self.assertEqual(settings['presetLooks'], {})

    def test_a_background_that_is_the_one_the_block_would_have_anyway_is_not_its_own(self):
        models = {'HD2_DelayTest': {'key': 'delay'}, 'HD2_AmpNAMLite': {'key': 'amp'}}
        change = lambda settings, asked: focus_view.look_change(settings, asked, self.PRESET, self.SCENES, self.PICTURES, models)
        # the default for its kind chosen again (the list's "Default" cell): nothing of its own is kept
        self.assertEqual(change({}, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'deep_sea'}), {})
        self.assertEqual(change({}, {'scope': 'block', 'preset': self.HERE, 'key': 'slot:18', 'scene': 'stage'}), {})   # a NAM block is an amp
        own = change({}, {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'space'})
        self.assertEqual(own['presetLooks']['3:5']['blocks'], {'HD2_DelayTest': {'scene': 'space'}})
        back = change(dict(own), {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'deep_sea'})
        self.assertEqual(back, {'presetLooks': {}})
        # the default is changed to what the block has: the block is on the default now, and follows it from then on
        settings = dict(own)
        settings.update(change(settings, {'scope': 'default', 'category': 'delay', 'scene': 'space'}))
        self.assertEqual(settings['presetLooks'], {})
        self.assertEqual(settings['floorLook']['assign']['category']['delay'], 'space')
        # ... and what was kept that way before (the owner's 030: its own Desert Dusk on a Desert Dusk default) is dropped by the next change
        old = {'presetLooks': {'3:5': {'name': 'Mahadeva', 'blocks': {'slot:25': {'scene': 'stage', 'picture': 'capture:brit_gold_head'},
                                                                      'slot:16': {'scene': 'space'}}}}}
        after = change(old, {'scope': 'default', 'category': 'looper', 'scene': 'stage'})
        self.assertEqual(after['presetLooks']['3:5']['blocks'], {'slot:25': {'picture': 'capture:brit_gold_head'}, 'slot:16': {'scene': 'space'}})
        # the preset's own background chosen for a block again is the preset's
        whole = change({}, {'scope': 'preset', 'preset': self.HERE, 'scene': 'space'})
        self.assertEqual(change(dict(whole), {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'space'}), {})
        both = change(dict(whole), {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'deep_sea'})
        self.assertEqual(both['presetLooks']['3:5']['blocks'], {'HD2_DelayTest': {'scene': 'deep_sea'}})   # its kind's default, but not the preset's

    def test_a_look_kept_under_another_name_is_another_presets_until_it_is_taken_over(self):
        settings = self.keep({}, {'scope': 'preset', 'preset': self.HERE, 'scene': 'space'})
        renamed = {'setlist': 3, 'number': 5, 'name': 'Something else'}
        taken = self.keep(json.loads(json.dumps(settings)), {'scope': 'preset', 'preset': self.HERE, 'adopt': True}, renamed)
        self.assertEqual(taken['presetLooks']['3:5'], {'name': 'Something else', 'scene': 'space', 'blocks': {}})
        # without taking it over, the first choice made for the new preset starts a look of its own
        fresh = self.keep(json.loads(json.dumps(settings)), {'scope': 'block', 'preset': self.HERE, 'key': 'HD2_DelayTest', 'scene': 'stage'}, renamed)
        self.assertEqual(fresh['presetLooks']['3:5'], {'name': 'Something else', 'blocks': {'HD2_DelayTest': {'scene': 'stage'}}})

    def test_a_default_is_the_floor_look_pages_own_choice(self):
        settings = self.keep({'floorLook': {'gearArt': 'X:/art'}}, {'scope': 'default', 'category': 'delay', 'scene': 'space'})
        look = settings['floorLook']
        self.assertEqual((look['gearArt'], look['assign']['category']['delay'], look['assign']['category']['amp']), ('X:/art', 'space', 'stage'))
        self.assertEqual(look['assign'], floor_store.assignment(focus_view.assignment(settings), list(self.SCENES)))   # as the page would save it
        self.keep(settings, {'scope': 'default', 'category': 'default', 'scene': 'stage'})
        self.assertEqual(focus_view.assignment(settings)['default'], 'stage')
        self.keep(settings, {'scope': 'default', 'reset': True})
        self.assertEqual(settings['floorLook'], {'gearArt': 'X:/art'})
        self.assertEqual(focus_view.assignment(settings)['category']['delay'], 'deep_sea')

    def test_the_page_is_given_the_defaults_and_every_presets_look_without_anything_malformed(self):
        settings = {'presetLooks': {'3:5': {'name': 'Mahadeva', 'scene': 'space', 'blocks': {'HD2_DelayTest': {'scene': 'synthwave', 'picture': '../x'},
                                                                                             'slot:999': {'scene': 'space'}, 'bad key!': {'scene': 'space'}}},
                                    '03:005': {'name': 'x' * 80, 'scene': 'stage'}, '40:5': {'scene': 'space'}, '3:128': {'scene': 'space'},
                                    'x': {'scene': 'space'}, '1:1': {'name': 'Empty', 'blocks': {}}, '2:2': 'space'}}
        view = focus_view.look_view(settings)
        self.assertEqual(view['presets'], {'3:5': {'name': 'x' * 32, 'scene': 'stage', 'blocks': {}}})     # (the later spelling of 3:5 stands)
        self.assertEqual(view['assign']['category']['delay'], 'deep_sea')
        self.assertEqual(view['factory'], {'default': 'studio', 'category': floor_store.DEFAULT_ASSIGN['category']})
        self.assertIn(['delay', 'Delay'], view['categories'])
        self.assertEqual(focus_view.look_view(None)['presets'], {})


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

    def test_the_bars_dsp_meters_and_snapshot_choice(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        figures = [{'load': 58.6, 'used': 43.6, 'budget': 75, 'level': 'green'}, None]
        self.assertTrue(self.view.receive({'type': 'dspLoad', 'dsp': figures}))       # the DSP meter's own figures
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {},
                                                           'snapshots': ['clean', 'lead', 'SNAPSHOT 3'], 'snapshot': 1}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: any(line.get('type') == 'dsp' for line in self.lines('P'))))
        self.assertEqual([line for line in self.lines('P') if line.get('type') == 'dsp'][-1], {'type': 'dsp', 'dsp': figures})
        self.assertEqual(self.view.checked_snapshot(2), {'action': 'snapshot', 'index': 2})
        for refused in (3, -1, 8, True, '1', None, 1.0):                             # only one of this preset's snapshots
            self.assertIsNone(self.view.checked_snapshot(refused))

    def test_the_bars_preset_choice_is_checked_then_loaded_once_the_script_is_ready(self):
        names = ['Preset %d' % n for n in range(128)]
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {}, 'presets': names,
                                                           'preset': {'setlist': 2, 'number': 5, 'name': 'Preset 5'}}})
        self.assertTrue(self.wait(lambda: self.view.state))
        self.assertEqual(self.view.checked_preset('next'), {'action': 'preset', 'number': 6})
        self.assertEqual(self.view.checked_preset('previous'), {'action': 'preset', 'number': 4})
        self.assertEqual(self.view.checked_preset(127), {'action': 'preset', 'number': 127})
        for refused in (5, 128, -1, True, '6', None, 6.0, 'first'):                  # the loaded one, or not a preset
            self.assertIsNone(self.view.checked_preset(refused))
        # focus_view.js has closed any drag: only then is the launcher asked to load it
        self.assertTrue(self.view.receive({'type': 'focusPreset', 'number': 6}))
        self.assertTrue(self.wait(lambda: ('load', 6) in self.actions))
        for refused in (128, -1, True, '6', None):
            self.view.receive({'type': 'focusPreset', 'number': refused})
        time.sleep(.1)
        self.assertEqual([action for action in self.actions if action[0] == 'load'], [('load', 6)])

    def test_the_arrows_go_around_the_ends_and_work_without_a_list(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {}, 'presets': None,
                                                           'preset': {'setlist': 0, 'number': 127, 'name': 'Last'}}})
        self.assertTrue(self.wait(lambda: self.view.state))
        self.assertEqual(self.view.checked_preset('next'), {'action': 'preset', 'number': 0})
        self.assertEqual(self.view.checked_preset('previous'), {'action': 'preset', 'number': 126})
        self.assertIsNone(self.view.checked_preset(3))                               # no list was given: no row to choose
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {}, 'preset': None}})
        self.assertTrue(self.wait(lambda: self.view.state.get('preset') is None))
        self.assertIsNone(self.view.checked_preset('next'))                          # no preset known: nothing to step from

    def test_a_refusal_is_said_in_the_page_while_focus_mode_is_on(self):
        self.assertFalse(self.view.receive({'type': 'dspNotice', 'text': 'DSP 1 has no room for that model (80 of 75).'}))   # off: the DSP meter says it
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: any(line.get('type') == 'catalog' for line in self.lines('P'))))
        self.assertTrue(self.view.receive({'type': 'dspNotice', 'text': 'DSP 1 has no room for that model (80 of 75).'}))
        self.view.notice('Preset 006 did not load.')
        self.view.notice('')
        self.assertTrue(self.wait(lambda: len([line for line in self.lines('P') if line.get('type') == 'notice']) == 2))
        self.assertEqual([line['text'] for line in self.lines('P') if line.get('type') == 'notice'],
                         ['DSP 1 has no room for that model (80 of 75).', 'Preset 006 did not load.'])

    def test_the_page_gets_the_looks_and_a_change_is_checked_for_the_loaded_preset(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 0, 'w': 1920, 'h': 954}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: any(line.get('type') == 'look' for line in self.lines('P'))))
        kinds = [line.get('type') for line in self.lines('P')]
        self.assertLess(kinds.index('catalog'), kinds.index('look'))                 # what it draws with, then the looks
        self.assertEqual(self.lines('P')[kinds.index('look')]['look']['presets'], {})
        change = {'scope': 'block', 'preset': {'setlist': 3, 'number': 5}, 'key': 'HD2_DelayTest', 'scene': 'aurora'}
        self.assertEqual(self.view.changed_look(change, {}), {})                     # no preset known yet
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {},
                                                           'preset': {'setlist': 3, 'number': 5, 'name': 'Mahadeva'}}})
        self.assertTrue(self.wait(lambda: self.view.state))
        kept = self.view.changed_look(change, {})
        self.assertEqual(kept, {'presetLooks': {'3:5': {'name': 'Mahadeva', 'blocks': {'HD2_DelayTest': {'scene': 'aurora'}}}}})
        self.assertEqual(self.view.changed_look({**change, 'key': 'HD2_NotAModel'}, {}), {})
        self.assertEqual(self.view.changed_look({**change, 'picture': 'model:FX_Delay.png'}, {})['presetLooks']['3:5']['blocks']['HD2_DelayTest'],
                         {'scene': 'aurora', 'picture': 'model:FX_Delay.png'})
        self.view.show_look(kept)
        self.assertTrue(self.wait(lambda: [line for line in self.lines('P') if line.get('type') == 'look'][-1]['look']['presets']))
        self.assertEqual([line for line in self.lines('P') if line.get('type') == 'look'][-1]['look']['presets'], kept['presetLooks'])

    def test_the_page_gets_the_catalog_then_each_state_and_hides_when_turned_off(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        self.view.receive({'type': 'focusState', 'state': {'blocks': [], 'selected': None, 'values': {}}})
        self.assertTrue(self.wait(lambda: self.panes))
        time.sleep(.1)
        self.assertEqual(self.lines('P'), [])                           # nothing before the page has loaded
        self.panes[0].say({'type': 'ready'})
        self.assertTrue(self.wait(lambda: len(self.lines('P')) >= 3))
        first, looks, second = self.lines('P')[:3]
        self.assertEqual(first['type'], 'catalog')
        self.assertIn('HD2_DelayTest', first['catalog']['models'])
        self.assertEqual(looks['type'], 'look')                         # the looks come before the first state is drawn
        self.assertEqual(second, {'type': 'state', 'state': {'blocks': [], 'selected': None, 'values': {}}})
        self.view.receive({'type': 'focusState', 'state': {'blocks': [{'dsp': 0}], 'selected': None, 'values': {}}})
        self.assertTrue(self.wait(lambda: len(self.lines('P')) >= 3))
        self.view.set_on(False)
        self.assertTrue(self.wait(lambda: self.lines('C')[-1] == {'visible': False, 'x': 0, 'y': 41, 'w': 1920, 'h': 913}))
        self.assertFalse(self.view.receive({'type': 'navigationBanner'}))   # not one of this pane's messages

    def test_a_value_set_in_the_page_is_one_control_of_the_shown_block_inside_its_range(self):
        self.view.receive({'type': 'focusState', 'state': {'blocks': [
            {'dsp': 0, 'id': 'block2', 'model': 'HD2_DelayTest'}, {'dsp': 1, 'id': 'block0', 'model': 'HD2_AmpNAMLite'},
            {'dsp': 0, 'id': 'inputA', 'model': 'HD2_In'}], 'selected': None, 'values': {}}})
        self.assertTrue(self.wait(lambda: self.view.state))
        ask = lambda key, value, phase='single', dsp=0, block='block2': self.view.checked_set(
            {'dsp': dsp, 'id': block, 'key': key, 'value': value, 'phase': phase})
        self.assertEqual(ask('Mix', .25, 'move'), {'action': 'set', 'dsp': 0, 'id': 'block2', 'key': 'Mix', 'value': .25, 'phase': 'move'})
        self.assertEqual(ask('Mix', 7)['value'], 1.0)                              # kept inside the model's range
        self.assertAlmostEqual(ask('Time', -3)['value'], .02, places=6)
        self.assertEqual(ask('BBD Size', 2.6)['value'], 3)                         # a list of positions: whole steps
        self.assertIs(type(ask('BBD Size', 1.2)['value']), int)
        self.assertEqual(ask('@trails', True)['value'], True)
        self.assertEqual(ask('TempoSync1', True)['value'], True)                   # the control's own tempo switch
        self.assertEqual(ask('SyncSelect1', 9)['value'], 2)                        # and its note, inside the list of notes
        self.assertEqual(ask('@enabled', False)['value'], False)                   # bypass
        self.assertEqual(ask('Polarity', True, dsp=1, block='block0')['value'], True)
        for refused in (ask('@model', 'HD2_X'), ask('@position', 3), ask('Scale', .5), ask('Nope', 1), ask('Mix', 'loud'),
                        ask('Mix', None), ask('Mix', True), ask('@trails', 1), ask('Mix', float('nan')), ask('Mix', .5, phase='now'),
                        ask('Mix', .5, block='block9'), ask('@enabled', False, block='inputA'),   # an input has no bypass
                        self.view.checked_set('Mix'), self.view.checked_set(None)):
            self.assertIsNone(refused)

    def test_a_model_or_a_capture_chosen_in_the_page_is_checked_against_what_there_is(self):
        self.view.receive({'type': 'focusState', 'state': {'blocks': [
            {'dsp': 0, 'id': 'block2', 'model': 'HD2_DelayTest'}, {'dsp': 1, 'id': 'block0', 'model': 'HD2_AmpNAMLite', 'slot': 18},
            {'dsp': 0, 'id': 'inputA', 'model': 'HD2_In'}], 'selected': None, 'values': {},
            'captures': [{'slot': 18, 'name': 'Jcm800', 'icon': 'brit_gold_head'}, {'slot': 24, 'name': 'Acoustic Guitar', 'icon': ''}]}})
        self.assertTrue(self.wait(lambda: self.view.state))
        model = lambda symbol, dsp=0, block='block2': self.view.checked_model({'dsp': dsp, 'id': block, 'symbol': symbol})
        self.assertEqual(model('HD2_DelayOther'), {'action': 'model', 'dsp': 0, 'id': 'block2', 'symbol': 'HD2_DelayOther'})
        self.assertEqual(model('HD2_DelayWide', 1, 'block0')['symbol'], 'HD2_DelayWide')      # a NAM block can become a stock one
        for refused in (model('HD2_DelayTest'),                       # the model it already is
                        model('HD2_AmpNAMLite'), model('HD2_In'), model('HD2_Nope'), model(7),
                        model('HD2_DelayOther', 0, 'inputA'), model('HD2_DelayOther', 0, 'block9'), self.view.checked_model(None)):
            self.assertIsNone(refused)
        capture = lambda slot, dsp=1, block='block0': self.view.checked_capture({'dsp': dsp, 'id': block, 'slot': slot})
        self.assertEqual(capture(24), {'action': 'capture', 'dsp': 1, 'id': 'block0', 'slot': 24})
        self.assertEqual(capture(18, 0, 'block2')['slot'], 18)        # another block becomes a NAM block with that capture
        for refused in (capture(3), capture(128), capture(0), capture('24'), capture(True), capture(24, 0, 'inputA'),
                        self.view.checked_capture('24')):
            self.assertIsNone(refused)
        # A capture slot is never set as a plain value.
        self.assertIsNone(self.view.checked_set({'dsp': 1, 'id': 'block0', 'key': 'Index', 'value': 24, 'phase': 'single'}))

    def test_every_capture_has_a_picture_as_the_library_gives_it_one(self):
        import capture_icons
        state = self.view.with_pictures({'blocks': [], 'captures': [
            {'slot': 18, 'name': 'Jcm800', 'icon': '', 'gear': 'amp-cab'},
            {'slot': 24, 'name': 'Acoustic Guitar', 'icon': 'acoustic_guitar', 'gear': ''},
            {'slot': 9, 'name': 'Tube Screamer Gain=4', 'icon': 'u_0123456789abcdef', 'gear': 'pedal'}]})
        jcm, guitar, pedal = state['captures']
        self.assertEqual(jcm['icon'], capture_icons.pick('Jcm800', 'amp-cab'))       # none recorded: picked from its name
        self.assertIn(jcm['icon'], capture_icons.known_icons())
        self.assertEqual(guitar['icon'], 'acoustic_guitar')                          # its own picture is kept
        self.assertEqual(pedal['icon'], capture_icons.pick('Tube Screamer Gain=4', 'pedal'))   # an uploaded one: the pack's stand-in
        self.assertEqual(self.view.with_pictures({'blocks': []}), {'blocks': []})
        self.assertIsNone(self.view.with_pictures(None))

    def test_the_pages_editor_button_and_a_pane_that_fails_reach_the_launcher(self):
        self.view.set_on(True)
        self.view.receive({'type': 'focusBounds', 'window': 4242, 'bounds': {'x': 0, 'y': 41, 'w': 1920, 'h': 913}})
        self.assertTrue(self.wait(lambda: self.panes))
        self.panes[0].say({'type': 'action', 'name': 'exit', 'value': None})
        self.panes[0].say({'type': 'error', 'text': 'no WebView2'})
        self.assertTrue(self.wait(lambda: len(self.actions) >= 2))
        self.assertEqual(self.actions[:2], [('exit', None), ('failed', 'no WebView2')])


def run_js_source(source, expression):
    """The value of a JavaScript expression after the given source (a piece of the page's own script)."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / 'piece.cjs'
        script.write_text(source + f'\nprocess.stdout.write(JSON.stringify({expression}));', encoding='utf-8')
        return json.loads(subprocess.run(['node', str(script)], capture_output=True, text=True, check=True, timeout=30).stdout)


def run_js(files, expression):
    source = '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in files)
    # (from a file: with a long expression the script is more than a Windows command line may hold)
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder, 'run.cjs')
        script.write_text(source + f'\nprocess.stdout.write(JSON.stringify({expression}));', encoding='utf-8')
        result = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=30)
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

    def test_between_full_readings_only_values_and_bypass_are_read(self):
        blocks = run_js(['focus_view.js'], f'focusSnapshot({self.READER}, null, {{}}, ["HD2_AmpNAMLite"]).blocks')
        asked = '''(() => { const read = %s, keys = []; const peek = (dsp, place, key) => { keys.push(key); return read(dsp, place, key); };
          const state = focusValues(peek, %s, {dsp: 0, block: "block0"}, {HD2_AmpNAMLite: ["Drive", "Polarity"]}, ["HD2_AmpNAMLite"]);
          return {state, keys: [...new Set(keys)].sort()}; })()''' % (self.READER, json.dumps(blocks))
        result = run_js(['focus_view.js'], asked)
        self.assertEqual(result['keys'], ['@enabled', '@model', 'Drive', 'Index', 'Polarity'])      # no position, no path
        self.assertEqual(result['state']['values'], {'Drive': 0.83, 'Polarity': False})
        self.assertEqual(result['state']['selected'], {'dsp': 0, 'id': 'block0'})
        self.assertEqual([b['enabled'] for b in result['state']['blocks']], [b['enabled'] for b in blocks])
        # Another model on the selected block, or a cursor on a block not seen yet: everything is read again.
        other = json.dumps([dict(b, model='HD2_Other') if b['id'] == 'block0' else b for b in blocks])
        self.assertIsNone(run_js(['focus_view.js'], f'focusValues({self.READER}, {other}, {{dsp: 0, block: "block0"}}, {{}}, [])'))
        self.assertIsNone(run_js(['focus_view.js'], f'focusValues({self.READER}, {json.dumps(blocks)}, {{dsp: 1, block: "block5"}}, {{}}, [])'))
        idle = run_js(['focus_view.js'], f'focusValues({self.READER}, {json.dumps(blocks)}, {{dsp: -1, block: ""}}, {{}}, [])')
        self.assertIsNone(idle['selected'])

    def test_captures_stay_named_while_hx_edit_rechecks_the_slots(self):
        before = [{'slot': 16, 'name': 'Klon'}, {'slot': 25, 'name': 'Tweed'}, {'slot': 30, 'name': 'Gone'}]
        call = lambda found, inventory: run_js(['focus_view.js'], f'focusCaptures({json.dumps(found)}, {json.dumps(before)}, {json.dumps(inventory)})')
        # A chain change: the checked list is empty, the slots it still shows keep their captures (30 was deleted).
        refreshing = {'state': 'refreshing', 'entries': [[16, 'a'], [25, 'b']]}
        self.assertEqual([c['name'] for c in call([], refreshing)], ['Klon', 'Tweed'])
        self.assertEqual([c['name'] for c in call([{'slot': 25, 'name': 'New'}], refreshing)], ['Klon', 'New'])  # checked wins
        # Checked (or disconnected): only what the check found.
        self.assertEqual(call([], {'state': 'verified', 'entries': [[16, 'a']]}), [])
        self.assertEqual(call([], {'state': 'unverified', 'entries': []}), [])
        self.assertEqual(call([], None), [])

    def test_a_block_is_selected_by_a_click_on_its_cell_of_hx_edits_chain(self):
        box = '{x: 318, y: 45, w: 1592, h: 120}'
        point = lambda block: run_js(['focus_view.js'], f'focusChainPoint({box}, {json.dumps(block)})')
        self.assertEqual(point({'id': 'inputA'}), {'x': 398, 'y': 93})                # the first of ten cells, on the name
        self.assertEqual(point({'id': 'block0', 'position': 1, 'path': 0}), {'x': 716, 'y': 93})
        self.assertEqual(point({'id': 'block4', 'position': 7, 'path': 1}), {'x': 1671, 'y': 153})   # the lower path
        self.assertEqual(point({'id': 'outputA'}), {'x': 1830, 'y': 93})
        for nowhere in ({'id': 'split', 'position': 0}, {'id': 'join', 'position': 8}, {'id': 'block0', 'position': None},
                        {'id': 'block0', 'position': 9, 'path': 0}):
            self.assertIsNone(point(nowhere))
        self.assertIsNone(run_js(['focus_view.js'], 'focusChainPoint(null, {id: "inputA"})'))

    def test_of_a_drags_changes_only_the_newest_waits_and_its_begin_and_end_are_kept(self):
        run = '''(() => { const queue = [];
          for (const [key, phase, value] of %s) focusQueue(queue, {dsp: 0, id: "block0", key, value, phase}, 4);
          return queue.map(c => c.key + ":" + c.phase + ":" + c.value); })()'''
        steps = [['a', 'begin', 1], ['a', 'move', 2], ['a', 'move', 3], ['a', 'move', 4], ['a', 'end', 4]]
        self.assertEqual(run_js(['focus_view.js'], run % json.dumps(steps)), ['a:begin:1', 'a:move:4', 'a:end:4'])
        mixed = [['a', 'move', 1], ['b', 'move', 2], ['a', 'move', 3]]            # another value in between: both kept, in order
        self.assertEqual(run_js(['focus_view.js'], run % json.dumps(mixed)), ['a:move:1', 'b:move:2', 'a:move:3'])
        full = [['a', 'begin', 1], ['b', 'move', 2], ['c', 'single', 3], ['d', 'single', 4], ['e', 'end', 5], ['f', 'single', 6], ['g', 'single', 7]]
        # Full: a waiting change makes room for an end; with only begins, singles and ends waiting, the newest is refused.
        self.assertEqual(run_js(['focus_view.js'], run % json.dumps(full)), ['a:begin:1', 'c:single:3', 'd:single:4', 'e:end:5'])

    def test_the_bar_reads_the_presets_own_values_and_recalls_a_snapshot_as_level_presets_does(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        self.assertIn("const groupPattern = /^(?:global|snapshot[0-7])$/;", binding)
        peek = binding[binding.index('function peekGlobal'):binding.index('function recallSnapshot')]
        self.assertIn("parameter({editor, dsp: -1, blockName: group}, key).value", peek)
        self.assertNotIn('writeValue', peek)
        recall = binding[binding.index('function recallSnapshot'):binding.index('// Focus Mode: a value of a block written')]
        for piece in ('index < 0 || index > 7', "string('global')", "string('@current_snapshot')", 'WRITE_FLAGS.single'):
            self.assertIn(piece, recall)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("targetBinding.recallSnapshot(editor, command.index)", script)
        self.assertIn("targetBinding.peekGlobal(editor, 'global', '@current_snapshot')", script)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'snapshot': view.checked_snapshot", launcher)          # (pane_request: Focus Mode's and the Workbench's)

    def test_a_preset_with_nothing_selected_shows_its_first_block_never_an_input(self):
        blocks = [{'dsp': 0, 'id': 'inputA', 'position': None, 'path': 0}, {'dsp': 0, 'id': 'split', 'position': 0, 'path': 0},
                  {'dsp': 1, 'id': 'block0', 'position': 0, 'path': 0}, {'dsp': 0, 'id': 'block4', 'position': 2, 'path': 1},
                  {'dsp': 0, 'id': 'block7', 'position': 2, 'path': 0}, {'dsp': 0, 'id': 'block2', 'position': 5, 'path': 0},
                  {'dsp': 0, 'id': 'outputA', 'position': None, 'path': 0}]
        self.assertEqual(run_js(['focus_view.js'], f'focusFirstBlock({json.dumps(blocks)})'), {'dsp': 0, 'id': 'block7'})
        self.assertEqual(run_js(['focus_view.js'], f'focusFirstBlock({json.dumps(blocks[2:3])})'), {'dsp': 1, 'id': 'block0'})   # only path 2 has blocks
        self.assertIsNone(run_js(['focus_view.js'], f'focusFirstBlock({json.dumps(blocks[:2] + blocks[-1:])})'))                # an empty preset
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        pick = script[script.index("const key = state.preset ? state.preset.setlist + ':' + state.preset.number : '';"):script.index('if (wanted) select(wanted);')]
        self.assertIn('if (state.selected) pickTries = PICK_TRIES;', pick)           # never again once something was selected in it
        self.assertIn('pickTries < PICK_TRIES', pick)
        self.assertIn("name === 'EditBuffer_DevicePresetChanged'", script)           # the same preset loaded again counts as a new one

    def test_the_preset_list_is_hx_edits_own_only_when_it_is_the_loaded_presets_setlist(self):
        names = ['Preset %d ' % n for n in range(128)]
        listed = run_js(['focus_view.js'], f'focusPresetNames({json.dumps(names)}, {{setlist: 1, number: 5, name: "Preset 5"}})')
        self.assertEqual((len(listed), listed[5], listed[127]), (128, 'Preset 5', 'Preset 127'))
        for other in ('{setlist: 1, number: 5, name: "Mahadeva"}',                   # another setlist is showing, or a new name
                      '{setlist: 1, number: 128, name: "Preset 5"}', 'null'):
            self.assertIsNone(run_js(['focus_view.js'], f'focusPresetNames({json.dumps(names)}, {other})'))
        for unread in ('"another-list-class"', 'null', json.dumps(names[:40]), json.dumps(names[:127] + [5])):
            self.assertIsNone(run_js(['focus_view.js'], f'focusPresetNames({unread}, {{setlist: 1, number: 5, name: "Preset 5"}})'))

    def test_the_preset_names_are_read_like_the_ir_lists_rows_and_a_preset_loads_as_a_footswitch_loads_it(self):
        reader = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        names = reader[reader.index('    presetNames() {'):reader.index('    favoriteSlot: name =>')]
        for piece in ("findWidget(libraryRoot, 0x706c7374, 1)", "!list.readPointer().equals(known.readPointer())",
                      "count < 1 || count > 128", "getIrRow(list, index)"):
            self.assertIn(piece, names)
        for write in ('write', 'selectRow', 'clearSelection', 'appendRow', 'postMessage'):   # reading only
            self.assertNotIn(write, names)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        load = script[script.index("} else if (command.action === 'preset') {"):script.index("} else if (['add', 'remove', 'move', 'moveSplit', 'route', 'assign', 'snapValue', 'splitType'].includes(command.action)) change(command);")]
        self.assertLess(load.index("endDrag('a preset change')"), load.index("send({type: 'focusPreset', number: command.number})"))
        self.assertNotIn('targetBinding', load)                                      # nothing is written to load it
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ("'preset': view.checked_preset", 'nam_level.load_preset(number)', 'Thread(target=focus_load, args=(value, view), daemon=True).start()'):
            self.assertIn(piece, launcher)
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        for piece in ("ask('preset', 'previous')", "ask('preset', 'next')", "ask('preset', index)", "message.type === 'notice'"):
            self.assertIn(piece, page)

    def test_change_look_asks_the_launcher_which_keeps_it_and_sends_the_looks_back(self):
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        for piece in ("ask('look', {scope: 'block', preset: presetRef(), key, ...more})", "ask('look', {scope: 'preset', preset: presetRef(), scene: name})",
                      "ask('look', {scope: 'default', category: key, scene: name})", "ask('lookSave')", "message.type === 'look'",
                      "const blockKey = block => isNam(block) && Number.isInteger(block.slot) ? 'slot:' + block.slot : block.model;",
                      "return kept && kept.name === (state.preset.name || '') ? kept : null;",
                      "showScene(sceneOf(block).name); showGear(block);"):
            self.assertIn(piece, page)
        look = page[page.index('// ---- Change look: this block'):page.index('// ---- the top bar: preset, snapshot')]
        # its button sits in the bar beside Floor preview, and is lit only while the panel is open
        views = page[page.index('<div class="views">'):page.index('<nav class="chain"')]
        self.assertLess(views.index('id="lookButton" aria-pressed="false"'), views.index('id="floorToggle"'))
        self.assertNotIn('class="tools"', page)
        # a default that has been changed is marked as on the Floor look page: a dot on its row, its starting background outlined
        for piece in ("const changed = !!usable(starting) && now !== starting;", "el('button', changed ? 'changed' : '')",
                      "cell.classList.add('start');", ".scenes button.start { outline: 2px dashed #8a8a8a; outline-offset: 1px; }",
                      ".cats > button.changed span:first-child::after"):
            self.assertIn(piece, page)
        # the same dot on what is not at its default elsewhere: a block of the preset, the preset's own background, a block's two choices, a tab
        for piece in (".cats > button.changed span:first-child::after, .blocks button.changed b::after, .parts button.changed b::after {",
                      "(from.from !== 'default' ? ' changed' : '')", "el('button', whole ? 'changed' : '')",
                      # under the name, the kind alone
                      "el('small', '', kindOf(item) || 'Block')",
                      # the tag beside a block's background speaks for the background alone
                      "el('span', 'tag ' + from.from, from.from === 'own' ? 'Its own' : from.from === 'preset' ? 'Preset' : 'Default')",
                      "tag.title = 'Its background: '"):
            self.assertIn(piece, page)
        self.assertNotIn('.scope button.changed', page)                               # not on the tabs (the owner: a dot too many)
        # a picture of its own is not said in words in the preset's list (the owner: confusing); the picture itself shows it
        self.assertNotIn('Own picture', page)
        self.assertNotIn('small.pictured', page)
        # a background of its own that is the one the block would have anyway is not "its own"
        self.assertIn("if (own && own !== under) return {name: own, from: 'own'};", page)
        # a row left open closes when its tab is left
        self.assertIn("tab.onclick = () => { lookTab = tab.dataset.tab; lookKind = null; drawLook(true); };", page)
        # a NAM block's big line is its capture's name, the model the small one under it
        for piece in ("title.classList.toggle('named', !!taken);", ".title.named .capture { order: 2;", ".title.named .model { order: 3;"):
            self.assertIn(piece, page)
        # a look change draws again only what it changes (the gear does not come in again for another kind's default)
        self.assertIn("else if (message.type === 'look') look = message.look;", page)
        # a NAM block says which kind of capture it plays, and the captures are listed under their kinds
        for piece in ("$('cat').textContent = kindOf(block) || 'Block';", "const capturesByKind = () => namKinds().flatMap(kind => {",
                      "const list = capturesByKind();"):
            self.assertIn(piece, page)
        card = (ROOT / 'library_card.html').read_text(encoding='utf-8')               # the same marks as the page it follows
        self.assertIn('#pickerBody button.scene.start { outline: 2px dashed #8a8a8a; outline-offset: 1px; }', card)
        self.assertIn('background: #e05a5b', card)
        self.assertIn('background: #e05a5b', look if 'background: #e05a5b' in look else page)
        self.assertNotIn('look.presets[', look)                                      # the panel never edits the looks itself
        self.assertNotIn('localStorage', page)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ('changed = focus.changed_look(value, nam_catalog.load_settings())', 'nam_catalog.save_setting(key, kept)',
                      'focus.show_look(nam_catalog.load_settings())', 'Thread(target=focus_look_save, daemon=True).start()',
                      "floor_store.write_for(library, FloorMemory(library.folder),"):
            self.assertIn(piece, launcher)

    def test_hx_edits_toolbar_steps_aside_and_undo_is_hx_edits_own(self):
        helper = (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8')
        self.assertIn('if(focusMode){ if(unboundButton!=null)unboundButton.Show(Rectangle.Empty); shown=false; ShowWindow(Handle,0); return; }', helper)
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('if ((string)name == "undo") { PressInEditor(0x5A, false); return; }', pane)   # Ctrl+Z in HX Edit's window
        self.assertIn('if ((string)name == "redo") { PressInEditor(0x5A, true); return; }', pane)    # Ctrl+Shift+Z, as its Edit menu
        self.assertIn('if (shift) keybd_event(0x10, 0, 0, UIntPtr.Zero);', pane)
        self.assertNotIn('Ctrl+Y', pane + (ROOT / 'focus_view.html').read_text(encoding='utf-8'))
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        for piece in ("ask('undo')", "ask('redo')", "ask('snapshot', index)"):
            self.assertIn(piece, page)

    def test_a_model_is_refused_where_the_dsp_has_no_room(self):
        room = lambda view, now, then: run_js(['focus_view.js'], f'focusRoom({json.dumps(view)}, {{A: 5, B: 30, C: 20}}, {json.dumps(now)}, {json.dumps(then)}, 1)')
        self.assertEqual(room({'used': 54, 'budget': 75}, 'A', 'B'), 'DSP 2 has no room for that model (79 of 75).')
        self.assertIsNone(room({'used': 54, 'budget': 75}, 'A', 'C'))               # 69 of 75
        self.assertIsNone(room({'used': 54, 'budget': 75}, 'B', 'B'))
        self.assertIsNone(room(None, 'A', 'B'))                                     # no figure from the Floor: HX Edit decides
        self.assertIsNone(room({'used': 54, 'budget': 75}, 'A', 'Unknown'))

    def test_a_value_is_written_with_the_flags_hx_edits_own_sliders_use(self):
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        self.assertIn('WRITE_FLAGS = Object.freeze({single: 0x80000000, begin: 0x80000001, move: 0x80000003, end: 0x80000002,', binding)
        write = binding[binding.index('function setValue'):binding.index('function setIndex')]
        for check in ('fixedKeys.has(key)', 'placePattern.test(blockName)', "typeof value !== 'boolean'", 'Number.isFinite(value)'):
            self.assertIn(check, write)
        self.assertIn("new Set(['@model', '@position', '@path', '@type', '@stereo'])", binding)   # never through this door
        # HX Edit's own sliders are shown a value set from the pane by a second write, for its views only: the flag
        # its undo writes with. The slider-style write before it is the one HX Edit keeps for undo.
        self.assertIn('refresh: 0x40000000', binding)
        self.assertIn('writeValue(editor, dsp, block, name, variant, WRITE_FLAGS[phase])', write)
        self.assertTrue(focus_view.write_notify({}))
        self.assertFalse(focus_view.write_notify({'focusWriteNotify': False}))
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("targetBinding.setValue(target, dsp, id, key, value, 'refresh')", script)
        self.assertEqual(script.count('finish('), 8)   # (and a value in another snapshot, a capture added in one step)                       # defined once; after a single change, each way a drag ends, a capture, an added capture

    def test_the_pane_never_outlives_hx_edit(self):
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('if (!IsWindow(parent)) Environment.Exit(0);', pane)      # even hidden, even after a crash
        self.assertIn('if (!OnUi(Shutdown)) Environment.Exit(0);', pane)

    def test_wide_gear_stands_larger_than_a_square_box_would_leave_it(self):
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        rule = page[page.index('function focusGearBox('):page.index('function place() {')]
        box = lambda shape, widest=800: run_js_source(rule, f'focusGearBox(400, {shape}, {widest})')
        self.assertEqual(box(0.6), {'w': 400, 'h': 400})                             # a pedal: as before, 400 high
        self.assertEqual(box(1), {'w': 400, 'h': 400})
        head = box(1.45)                                                             # an amp head: 345 high, not the 276 a square leaves it
        self.assertEqual((round(head['w']), round(head['h'])), (500, 345))
        wide = box(2.25)                                                             # a rack unit: 289 high, not 178
        self.assertEqual((round(wide['w']), round(wide['h'])), (651, 289))
        tight = box(2.25, 450)                                                       # no wider than the scene has room for
        self.assertEqual((round(tight['w']), round(tight['h'])), (450, 200))
        # the scene leans less, eased by the page, and goes back to rest outside the scene or over a panel
        for piece in ("translate(calc(var(--px, 0) * -5px), calc(var(--py, 0) * -3px))", "translate(calc(var(--px, 0) * 3px), calc(var(--py, 0) * 1.5px))",
                      "if (e.target.closest('.look, .picker, .floor')) { leanTo(0, 0); return; }", "scene.addEventListener('pointerleave', () => leanTo(0, 0));",
                      "const rate = lean.toX === 0 && lean.toY === 0 ? .018 : .03;"):
            self.assertIn(piece, page)

    def test_the_pane_covers_the_signal_flow_and_the_edit_panel_across_the_window(self):
        box = run_js(['focus_view.js'], 'focusPaneBounds({x:318,y:45,w:1592,h:248}, {x:308,y:0,w:1612,h:954}, {x:0,y:0,w:1920,h:989})')
        self.assertEqual(box, {'x': 0, 'y': 0, 'w': 1920, 'h': 954})                  # over HX Edit's toolbar; its status bar stays
        self.assertIsNone(run_js(['focus_view.js'], 'focusPaneBounds(null, {x:308,y:0,w:1612,h:954}, {x:0,y:0,w:1920,h:989})'))
        self.assertIsNone(run_js(['focus_view.js'], 'focusPaneBounds({x:318,y:45,w:300,h:100}, {x:308,y:0,w:300,h:200}, {x:0,y:0,w:500,h:240})'))

    def test_the_script_checks_the_same_native_bytes_as_the_hooks_it_shares(self):
        guards = run_js(['focus_view.js', 'nav_banner.js'], '[focusViewGuards, navigationBannerGuards]')
        self.assertEqual(guards[0]['3b7e00'], guards[1]['3b7e00'])
        # 0x218a00 is already hooked when this script installs (its bytes are Frida's jump): never guarded here.
        self.assertEqual(list(guards[0]), ['3b7e00'])


class WiringTests(unittest.TestCase):
    def test_the_menu_item_reaches_the_launcher_and_its_tick_comes_back(self):
        self.assertIn('focusMode', DspMeter.CHOICES)
        helper = (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8')
        self.assertIn('if(at==0){ tools.Close(); options.Close(); Say("focusMode"); }', helper)   # its own button: one click
        tools = helper[helper.index('Heading(tools,"TOOLS");'):helper.index('Heading(options,"SIGNAL CHAIN");')]
        self.assertNotIn('focusMode', tools)                                         # no longer an item of the menu
        self.assertIn('state.TryGetValue("focusMode"', helper)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        for piece in ("name == 'focusMode'", "'focus_view.js'", 'installFocusView(', "script.post({'type': 'focusMode'",
                      "payload.get('reason') == 'focus-view' and payload.get('stage') == 'unavailable'",
                      "meter.set_chain_option('focusMode', on)", 'focus.receive(payload)', 'focus.close()'):
            self.assertIn(piece, launcher)

    def test_the_script_writes_only_values_and_a_selection_is_a_click_on_the_chain(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        for other in ('writeValue', '.restore(', 'Interceptor.replace', 'writePointer', 'writeU32'):
            self.assertNotIn(other, script)
        # The Workbench's chain changes, each once, only inside change() (test_workbench has their checks).
        body = script[script.index('function change(command)'):script.index('function followAdd(')]
        # (moveBlock also in followDown: a block pasted on the other path's lane A going down to lane B)
        for call, times in (('targetBinding.addModel(', 1), ('targetBinding.removeBlock(', 1), ('targetBinding.moveBlock(', 2)):
            self.assertEqual(script.count(call), times, call)
            self.assertIn(call, body)
        # A model or a capture from the pane's list: HX Edit's own picker calls, on a block of the chain, room checked first.
        self.assertEqual((script.count('targetBinding.setModel('), script.count('targetBinding.setIndex(')), (2, 2))   # (a swap, the split's type; a capture added)
        swap = script[script.index('function swap(command)'):script.index('function finish(') if script.index('function finish(') > script.index('function swap(command)') else script.index('function endDrag(')]
        self.assertLess(swap.index('focusRoom('), swap.index('targetBinding.setModel('))
        self.assertIn('!chainBlock.test(block.id)', swap)
        # Every write is a value of a block the pane shows, one of its model's controls or its bypass.
        self.assertIn("command.key === '@enabled' || (parameters[block.model] || []).includes(command.key)", script)
        self.assertEqual(script.count('targetBinding.setValue('), 5)   # (and a value in another snapshot)      # the write, a drag closed for the pane (twice), the refresh
        self.assertIn('namView.clickChainPoint(spot.x, spot.y)', script)
        self.assertIn('if (full) { onFloor = captures(onFloor); header = presetHeader(); }', script)   # the captures are listed whatever the preset holds
        view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        click = view[view.index('clickChainPoint(x, y)'):view.index('// Main-window client coordinates of the pointer')]
        self.assertIn('!inChain(x, y)', click)                            # never a click outside the chain
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'action': 'select'", launcher)
        # a value, a model or a capture from the page is checked before it is sent (pane_request, for either pane)
        for piece in ("'set': view.checked_set", "'model': view.checked_model", "'capture': view.checked_capture", 'command = check(value) if shown else None'):
            self.assertIn(piece, launcher)
        binding = (ROOT / 'target_binding.js').read_text(encoding='utf-8')
        peek = binding[binding.index('function peekValue'):binding.index("// Focus Mode's top bar: a value of the preset itself")]
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

    def test_the_page_is_local_and_asks_only_for_what_the_launcher_checks(self):
        page = (ROOT / 'focus_view.html').read_text(encoding='utf-8')
        self.assertNotIn('http://', page)
        self.assertEqual(page.count('https://'), 0)                      # no font, script or picture from the internet
        self.assertIn("ask('exit')", page)
        self.assertIn("ask('select', {dsp: b.dsp, id: b.id})", page)
        shared = (ROOT / 'pane_controls.js').read_text(encoding='utf-8')               # its controls' writes, shared with the Workbench
        self.assertIn('<script src="pane_controls.js"></script>', page)
        self.assertIn("ask('set', {dsp: block.dsp, id: block.id, key, value, phase})", shared)
        self.assertIn("ask('model', {dsp: block.dsp, id: block.id, symbol})", page)
        self.assertIn("ask('capture', {dsp: block.dsp, id: block.id, slot: c.slot})", page)
        pane = (ROOT / 'focus_view.cs').read_text(encoding='utf-8')
        self.assertIn('args.Cancel = args.Uri != page', pane)            # the pane opens nothing but the page


if __name__ == '__main__':
    unittest.main()
