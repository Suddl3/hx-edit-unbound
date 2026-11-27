"""Startup problems are said, not swallowed (v0.7.2, 2026-11-27).

On 2026-11-27 Nick's own install showed "IR slot 127 / Not in the NAM library" and "0 captures" after a firmware
flash, and he thought his captures were lost. The library was in another folder (a copy made from inside the Claude
app had landed in that app's private copy of %LOCALAPPDATA%), and an editor started from inside that app refused every
capture ("Local capture path changed"). Separately, an editor started soon after the Floor rebooted got no answer to
the firmware question and quietly used the basic firmware settings. Nothing told him any of it.

Now: the launcher writes one "startup" line to trace.log (the firmware and where it came from, the library folder, its
size, the library index's result; no capture names); the Workbench says when the library cannot be used instead of
"No captures yet"; and it says when the Floor did not answer the firmware question. No HX Edit, no device."""
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import floor_firmware  # noqa: E402
from floor_firmware import FloorFirmware  # noqa: E402
from floor_inventory import prime_library  # noqa: E402
from nam_library import Library  # noqa: E402
import workbench  # noqa: E402
from test_workbench import NODE, run_js  # noqa: E402

CAPTURE = json.dumps({'architecture': 'WaveNet', 'weights': [0.0], 'config': {}}).encode()
SECRET = 'Secret Plexi Capture Name'


def launcher_module():
    loader = SourceFileLoader('startup_problems_launcher_test', str(ROOT / 'start-hx-edit-nam.pyw'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def kept_library(folder, names=(SECRET,)):
    library = Library(folder)
    for index, name in enumerate(names):
        source = Path(folder).parent / f'source-{index}.nam'
        source.write_bytes(CAPTURE[:-1] + f', "n": {json.dumps(name)}}}'.encode())    # (each its own content)
        library.add(source, name=name)
    return library


def remembered_memory(folder, captures=2):
    slots = {str(slot): {'name': f'Slot {slot}', 'contentId': f'{slot:064x}'} for slot in range(1, captures + 1)}
    Path(folder).mkdir(parents=True, exist_ok=True)
    Path(folder, 'floor-memory.json').write_text(json.dumps({'slots': slots}), encoding='utf-8')


class TestsKeepToTemporaryFolders(unittest.TestCase):
    """Test runs wrote into the player's own %LOCALAPPDATA%\\HX Edit NAM\\trace.log (seen 2026-11-27 10:40-10:47)."""

    def test_localappdata_is_a_temporary_folder(self):
        local = Path(os.environ['LOCALAPPDATA']).resolve()
        self.assertTrue(str(local).startswith(str(Path(tempfile.gettempdir()).resolve())), local)
        import nam_catalog
        import nam_library
        import dsp_costs
        for path in (nam_library.FOLDER, nam_catalog.SETTINGS, dsp_costs.FILE):
            self.assertTrue(str(Path(path).resolve()).startswith(str(Path(tempfile.gettempdir()).resolve())), path)
        self.assertTrue(str(Library().folder.resolve()).startswith(str(Path(tempfile.gettempdir()).resolve())))

    def test_the_launcher_traces_into_the_temporary_folder(self):
        launcher = launcher_module()
        self.assertEqual(launcher.TRACE, Path(os.environ['LOCALAPPDATA']) / 'HX Edit NAM' / 'trace.log')
        launcher.trace({'type': 'test'})
        self.assertIn('"type": "test"', launcher.TRACE.read_text(encoding='utf-8'))


class FirmwareOriginTests(unittest.TestCase):
    def test_four_words_for_where_the_profile_came_from(self):
        self.assertEqual(floor_firmware.origin(FloorFirmware(source='floor')), 'floor')
        self.assertEqual(floor_firmware.origin(FloorFirmware(source='remembered')), 'remembered')
        self.assertEqual(floor_firmware.origin(FloorFirmware(source='settings')), 'configured')
        self.assertEqual(floor_firmware.origin(FloorFirmware(source='environment')), 'configured')
        self.assertEqual(floor_firmware.origin(FloorFirmware(source='assumed')), 'assumed')
        self.assertIsNone(floor_firmware.origin(None))

    def test_asking_follows_the_setting_and_the_variable(self):
        with patch.dict(os.environ):
            os.environ.pop('HX_EDIT_FLOOR_ASK', None)
            self.assertTrue(floor_firmware.asking({}))
            self.assertFalse(floor_firmware.asking({'floorFirmwareAsk': False}))
            os.environ['HX_EDIT_FLOOR_ASK'] = '0'
            self.assertFalse(floor_firmware.asking({}))


class FirmwareNoticeTests(unittest.TestCase):
    def test_no_notice_when_the_floor_answered(self):
        self.assertIsNone(workbench.firmware_notice(FloorFirmware(nam_cost=3250, pedal=True, source='floor')))
        self.assertIsNone(workbench.firmware_notice(None))

    def test_the_last_known_settings(self):
        text = workbench.firmware_notice(FloorFirmware(nam_cost=3250, pedal=True, source='remembered'))
        self.assertEqual(text, "The Floor did not answer when the editor started, so it is using the Floor's last known "
                               "firmware settings (NAM blocks at 43% of a DSP, NAM Pedal at 10%). If the Floor was just switched on, close the "
                               "editor and start it again in a minute.")

    def test_the_basic_settings(self):
        text = workbench.firmware_notice(FloorFirmware(source='assumed'))
        self.assertEqual(text, 'The Floor did not answer when the editor started, so it is using basic firmware settings '
                               '(NAM blocks at 48% of a DSP, no NAM Pedal). If the Floor was just switched on, close the editor and start it '
                               'again in a minute.')

    def test_settings_set_by_hand(self):
        text = workbench.firmware_notice(FloorFirmware(nam_cost=3250, source='settings'))
        self.assertIn('so it is using the firmware settings set by hand (NAM blocks at 43% of a DSP, no NAM Pedal)', text)

    def test_no_notice_when_asking_is_turned_off(self):
        self.assertIsNone(workbench.firmware_notice(FloorFirmware(source='assumed'), asked=False))


class LibraryProblemTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / 'NAM Library'

    def test_a_working_library_and_an_empty_new_one_are_fine(self):
        self.assertIsNone(workbench.library_problem(Library(self.folder)))          # nothing yet: "No captures yet"
        library = kept_library(self.folder)
        self.assertIsNone(Library(self.folder).catalog_problem())
        identity = next(iter(library.entries()))
        primed = {'indexed': 1, 'unsupported': [], 'timedOut': False}
        self.assertIsNone(workbench.library_problem(library, primed, remembered=3))
        # some captures failed, not all: the others work
        library = kept_library(self.folder, ('Other',))
        primed = {'indexed': 1, 'unsupported': [{'id': identity, 'reason': 'Unsupported'}], 'timedOut': False}
        self.assertIsNone(workbench.library_problem(library, primed))

    def test_a_catalog_that_cannot_be_read(self):
        self.folder.mkdir(parents=True)
        (self.folder / 'catalog.json').write_text('{not json', encoding='utf-8')
        library = Library(self.folder)
        self.assertEqual(library.catalog_problem(), 'its list of captures is damaged')
        problem = workbench.library_problem(library, {'indexed': 0, 'unsupported': [], 'timedOut': False}, remembered=4)
        self.assertEqual(problem['kind'], 'unreadable')
        self.assertEqual(problem['text'],
                         'Your NAM library could not be read (its list of captures is damaged). Your captures are not '
                         'lost: their files are still in the library folder, and the ones on the Floor still play there. '
                         'Close the editor and start it again from its usual shortcut. If this message stays, the '
                         'details are in trace.log.')
        self.assertEqual(problem['folder'], str(self.folder))
        (self.folder / 'catalog.json').unlink()
        (self.folder / 'catalog.json').mkdir()                         # a catalog that cannot be opened at all
        self.assertTrue(Library(self.folder).catalog_problem().startswith('its list of captures could not be opened: '))

    def test_every_capture_refused_by_the_index(self):
        # As on 2026-11-27: each file resolved somewhere else than the library folder (nam_library._source).
        library = kept_library(self.folder, (SECRET, 'Second capture'))
        with tempfile.TemporaryDirectory() as workspace, \
             patch('nam_convert.convert_batch', return_value=[Path(workspace) / 'x.wav']), \
             patch.object(Library, '_source', side_effect=ValueError('Local capture path changed')):
            primed = prime_library(library, 'nam2ir.py', workspace, timeout=10)
        self.assertEqual((primed['indexed'], len(primed['unsupported'])), (0, 2))
        problem = workbench.library_problem(library, primed)
        self.assertEqual(problem['kind'], 'unopened')
        self.assertEqual(problem['text'],
                         'Your NAM library could not be read (none of its 2 captures could be opened: Local capture '
                         'path changed). Your captures are not lost: their files are still in the library folder, and '
                         'the ones on the Floor still play there. Close the editor and start it again from its usual '
                         'shortcut. If this message stays, the details are in trace.log.')
        self.assertNotIn(SECRET, json.dumps(problem))
        # a capture added since works: the library can be used again, nothing more to say
        kept_library(self.folder, ('Third capture',))
        self.assertIsNone(workbench.library_problem(library, primed))

    def test_an_empty_library_where_the_floor_had_captures_from_it(self):
        remembered_memory(self.folder, captures=25)
        library = Library(self.folder)
        problem = workbench.library_problem(library, {'indexed': 0, 'unsupported': [], 'timedOut': False}, remembered=25)
        self.assertEqual(problem['kind'], 'empty')
        self.assertEqual(problem['text'],
                         'Your NAM library could not be found (the library folder is empty, but this PC remembers 25 '
                         'captures from it on the Floor). Your captures are not lost: the ones on the Floor still play '
                         'there. Close the editor and start it again from its usual shortcut. If this message stays, the '
                         'details are in trace.log.')
        self.assertIsNone(workbench.library_problem(library, remembered=0))

    def test_the_view_carries_it(self):
        self.folder.mkdir(parents=True)
        (self.folder / 'catalog.json').write_text('[]', encoding='utf-8')
        view = workbench.library_view(Library(self.folder), workbench.library_problem(Library(self.folder)))
        self.assertEqual(view['rows'], [])
        self.assertEqual(view['problem']['kind'], 'unreadable')
        self.assertIsNone(workbench.library_view(Library(self.folder))['problem'])


class StartupLineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / 'NAM Library'
        self.launcher = launcher_module()

    def test_one_line_with_the_firmware_the_library_and_the_index(self):
        library = kept_library(self.folder, (SECRET, 'Another'))
        primed = {'indexed': 0, 'timedOut': False,
                  'unsupported': [{'id': i, 'reason': 'Local capture path changed'} for i in library.entries()]}
        firmware = FloorFirmware(nam_cost=3250, pedal=True, source='remembered')
        line = self.launcher.startup_line(firmware, library, primed, workbench.library_problem(library, primed))
        self.assertEqual(line, {'type': 'startup', 'firmware': 'NAM A2 Lite 32.5% + NAM Pedal 7.5%',
                                'firmwareSource': 'remembered', 'library': str(self.folder), 'entries': 2,
                                'primed': {'indexed': 0, 'unsupported': 2, 'firstReason': 'Local capture path changed',
                                           'timedOut': False},
                                'libraryProblem': 'unopened'})
        self.assertNotIn(SECRET, json.dumps(line))
        # no Floor profile, no index (a launch without the navigation): said as such
        line = self.launcher.startup_line(None, Library(self.folder), None)
        self.assertEqual((line['firmware'], line['firmwareSource'], line['primed'], line['libraryProblem']),
                         (None, None, None, None))

    def test_the_navigation_launch_writes_it_once(self):
        library = kept_library(self.folder, (SECRET,))
        primed = {'indexed': 0, 'timedOut': False,
                  'unsupported': [{'id': i, 'reason': 'Local capture path changed'} for i in library.entries()]}
        launcher = self.launcher
        launcher.FLOOR_SEEN = FloorFirmware(source='assumed')
        device, session, script = Mock(), Mock(), Mock()
        callbacks, events = {}, {}
        device.spawn.return_value = 123
        device.attach.return_value = session
        session.on.side_effect = lambda name, callback: callbacks.__setitem__(name, callback)
        session.create_script.return_value = script
        script.on.side_effect = lambda name, callback: events.__setitem__(name, callback)
        script.load.side_effect = lambda: events['message']({'type': 'send', 'payload': {'type': 'ready'}}, None)
        device.resume.side_effect = lambda _: callbacks['detached']()
        with patch('nam_catalog.ir_parameters', return_value={}), \
             patch('nam_catalog.sidebar_width', return_value=320), \
             patch('floor_inventory.prime_library', return_value=primed), \
             patch('navigation_host.NavigationHost'), patch('nam_sidebar.prepare_sidebar'), \
             patch('nam_sidebar.NamSidebar'), patch('tone_preview.TonePreview') as preview:
            preview.return_value.thread = None
            exe = Path(self.folder.parent, 'copy', 'HX Edit.exe')
            launcher.run_editor(exe, self.folder.parent, device, {}, floor_reference=True, navigation=True,
                                library=library)
        lines = [json.loads(line) for line in launcher.TRACE.read_text(encoding='utf-8').splitlines()]
        startup = [line for line in lines if line.get('type') == 'startup']
        self.assertEqual(len(startup), 1, startup)
        self.assertEqual((startup[0]['firmwareSource'], startup[0]['entries'], startup[0]['primed']['indexed'],
                          startup[0]['libraryProblem']), ('assumed', 1, 0, 'unopened'))
        self.assertNotIn(SECRET, launcher.TRACE.read_text(encoding='utf-8'))

    def test_the_launcher_keeps_what_it_detected_for_the_editor(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        main = launcher[launcher.index('def main():'):]
        self.assertIn('global FLOOR_SEEN', main)
        self.assertIn('FLOOR_SEEN = floor = floor_firmware.detect(CONVERTER.parent)', main)
        # the Workbench is told both: the library's trouble with the library, the firmware notice with its options
        self.assertIn("'firmwareNotice': firmware_note", launcher)
        self.assertIn('workbench.show_library(library_view(library, library_trouble()))', launcher)


class WorkbenchPageTests(unittest.TestCase):
    PAGE = (ROOT / 'workbench.html').read_text(encoding='utf-8')

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_words_never_say_no_captures_while_the_library_could_not_be_read(self):
        problem = {'kind': 'unopened', 'text': 'Your NAM library could not be read (x). Your captures are not lost: y'}
        library = {'empty': 'No captures yet. Import .nam files, or find some on TONE3000.', 'none': 'No capture matches.'}
        drawer = {'empty': 'No captures on the Floor yet. Add some with the NAM library (in the rail).', 'none': 'No capture matches.'}
        def words(lib, total, shown, kind):
            return run_js(['workbench_layout.js'], f'workbenchLibraryWords({json.dumps(lib)}, {total}, {shown}, {json.dumps(kind)})')
        fine = {'rows': [], 'problem': None}
        self.assertEqual(words(fine, 0, 0, library), {'trouble': '', 'empty': library['empty']})
        self.assertEqual(words(fine, 0, 0, drawer), {'trouble': '', 'empty': drawer['empty']})
        self.assertEqual(words(fine, 3, 0, drawer), {'trouble': '', 'empty': 'No capture matches.'})
        self.assertEqual(words(fine, 3, 3, drawer), {'trouble': '', 'empty': ''})
        broken = {'rows': [], 'problem': problem}
        for kind in (library, drawer):
            said = words(broken, 0, 0, kind)
            self.assertEqual(said, {'trouble': problem['text'], 'empty': ''})
        self.assertEqual(words(broken, 2, 2, library), {'trouble': problem['text'], 'empty': ''})
        self.assertEqual(words(None, 0, 0, drawer), {'trouble': '', 'empty': drawer['empty']})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_firmware_notice_shows_until_ok(self):
        note = 'The Floor did not answer when the editor started, so it is using basic firmware settings.'
        def shown(options, dismissed):
            return run_js(['workbench_layout.js'], f'workbenchFirmwareNote({json.dumps(options)}, {json.dumps(dismissed)})')
        self.assertEqual(shown({'firmwareNotice': note}, ''), note)
        self.assertEqual(shown({'firmwareNotice': note}, note), '')
        self.assertEqual(shown({'firmwareNotice': None}, ''), '')
        self.assertEqual(shown({}, ''), '')
        self.assertEqual(shown(None, ''), '')

    def test_the_page_uses_them(self):
        page = self.PAGE
        library = page[page.index('function drawLibrary() {'):page.index('function putLibrary(')]
        self.assertIn('workbenchLibraryWords(lib, all.length, rows.length, LIBRARY_WORDS)', library)
        self.assertNotIn("'No captures yet. Import .nam files, or find some on TONE3000.'));", library)
        drawer = page[page.index('function drawDrawer() {'):page.index('function render() {')]
        self.assertIn("workbenchLibraryWords(drawer === 'captures' ? lib : null, all.length, shown.length, kind)", drawer)
        self.assertIn("else if (message.type === 'library') { lib = message.library && typeof message.library === 'object' ? message.library : null; shownLib = ''; shownDrawer = ''; drawLibrary(); drawDrawer(); return; }", page)
        self.assertIn('id="fwnote"', page)
        self.assertIn('drawFirmwareNote();', page[page.index("else if (message.type === 'options') {"):])
        # the notice is not one of the page's own notices: a docked tool's window does not step aside for it
        self.assertIn("document.querySelector('body > .modal, body > .sticky')", page)
        self.assertNotIn('class="sticky', page[page.index('id="fwnote"') - 40:page.index('id="fwnote"') + 40])


if __name__ == '__main__':
    unittest.main()
