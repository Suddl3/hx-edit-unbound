"""The Workbench's Batch 3 (research/modern-ui/batch3-*.png): renaming a preset or a snapshot in place, switching
setlists, the Floor's slots with Clear. No editor process, no device."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import focus_view  # noqa: E402
import workbench  # noqa: E402
from test_focus_view import NODE, FakePane, resources, run_js  # noqa: E402


def setUpModule():
    from unittest.mock import patch
    local = patch.object(focus_view, 'LOCAL_ART', {})
    local.start()
    unittest.addModuleCleanup(local.stop)


def page():
    return (ROOT / 'workbench.html').read_text(encoding='utf-8')


def launcher():
    return (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')


class RenameTests(unittest.TestCase):
    """Stage 1: a name box of our own, in the top bar for the preset and in a snapshot's button."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'preset': {'setlist': 3, 'number': 32, 'name': 'Spare'}, 'snapshots': ['Clean', 'Crunch', 'Lead', 'Ambient']}

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_names_keep_what_the_floor_keeps_as_they_are_typed(self):
        typed = lambda text, limit: run_js(['workbench_layout.js'], f'workbenchNameTyped({json.dumps(text)}, {limit})')
        self.assertEqual(typed('Crunch Rhythm', 10), 'Crunch Rhy')
        self.assertEqual(typed('Café – Lead\tx', 16), 'Caf  Leadx')            # outside the Floor's characters: left out
        self.assertEqual(typed('John Mayer Lead!~', 16), 'John Mayer Lead!')
        self.assertEqual(typed(None, 16), '')
        done = lambda text, before, limit: run_js(['workbench_layout.js'], f'workbenchNameDone({json.dumps(text)}, {json.dumps(before)}, {limit})')
        self.assertEqual(done('Rhythm  ', 'Crunch', 10), 'Rhythm')                     # spaces at the end go
        self.assertIsNone(done('   ', 'Crunch', 10))                                   # nothing left: the old name stays
        self.assertIsNone(done('Crunch ', 'Crunch', 10))                               # the same name: nothing to do
        self.assertEqual(done(' Lead', 'Lead', 10), ' Lead')                           # a space in front is the Floor's own
        self.assertEqual(run_js(['workbench_layout.js'], 'WORKBENCH_NAME_LIMITS'), {'preset': 16, 'snapshot': 10})

    def test_only_a_snapshot_of_the_loaded_preset_is_renamed_and_only_with_a_name_the_floor_keeps(self):
        check = self.view.checked_rename
        self.assertEqual(check({'what': 'snapshot', 'index': 1, 'name': 'Crunch Rhy'}),
                         {'action': 'rename', 'what': 'snapshot', 'index': 1, 'name': 'Crunch Rhy'})
        for refused in ({'what': 'snapshot', 'index': 4, 'name': 'Lead'},          # the preset has 4 snapshots
                        {'what': 'snapshot', 'index': -1, 'name': 'Lead'}, {'what': 'snapshot', 'index': True, 'name': 'Lead'},
                        {'what': 'snapshot', 'index': 1, 'name': 'Eleven char'}, {'what': 'snapshot', 'index': 1, 'name': ''},
                        {'what': 'snapshot', 'index': 1, 'name': 'Café'}, {'what': 'snapshot', 'index': 1, 'name': 'Rhythm '},
                        {'what': 'snapshot', 'index': 1, 'name': 'Crunch'},       # its name now
                        {'what': 'preset', 'name': 'New Name'},                  # held: HX Edit renames only the stored copy
                        {'what': 'snapshot', 'index': 1}, 'Crunch', None):
            self.assertIsNone(check(refused), refused)

    def test_the_launcher_sends_the_checked_rename_to_the_script_and_the_script_writes_the_edit_buffer(self):
        source = launcher()
        self.assertIn("'snapValue', 'splitType', 'ir', 'rename'", source)
        self.assertIn("'rename': view.checked_rename,", source)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'rename' && value.what === 'snapshot' && Number.isInteger(value.index)", script)
        self.assertIn('/^[\\x20-\\x7e]{1,10}$/.test(value.name)', script)
        self.assertIn('targetBinding.renameSnapshot(editor, command.index, command.name);', script)
        # (a failure says so in the pane, as for any other change of the chain)
        self.assertIn("'redo', 'ir', 'undo', 'rename'].includes(command.action)) send({type: 'dspNotice'", script)

    def test_the_name_boxes_are_the_mock_ups_and_a_preset_rename_says_it_is_held(self):
        source = page()
        for words in ("kbdHint('Enter', 'rename')", "kbdHint('Esc', 'keep the old name')", "'The Floor shows it once you Save the preset.'",
                      "'Saved with the preset. Undo takes it back.'", "kbdHint('Esc', 'keep “' + (before || 'Snapshot ' + (index + 1)) + '”')"):
            self.assertIn(words, source)
        # ways in: the pencil, a double-click, F2 for the preset
        self.assertIn("$('presetRename').onclick = () => startRename('preset');", source)
        self.assertIn("$('presetButton').ondblclick = () => startRename('preset');", source)
        self.assertIn("if (e.key === 'F2' && visible && !e.target.closest('input, textarea')) { e.preventDefault(); startRename('preset'); return; }", source)
        self.assertIn("button.ondblclick = () => startRename('snapshot', index);", source)
        self.assertIn("pen.onclick = e => { e.stopPropagation(); startRename('snapshot', index); };", source)
        # Enter / Esc; a click elsewhere keeps the old name
        self.assertIn("if (e.key === 'Enter') { e.preventDefault(); done(true); }", source)
        self.assertIn("else if (e.key === 'Escape') { e.preventDefault(); done(false); }", source)
        self.assertIn('input.onblur = () => done(false);', source)
        # a snapshot: asked of HX Edit; a preset: held unless this build says it may (it does not)
        self.assertIn("ask('rename', {what: 'snapshot', index, name});", source)
        self.assertIn("else if (name && options.presetRename) ask('rename', {what: 'preset', name});", source)
        self.assertIn('else if (name) toast(PRESET_RENAME_HELD);', source)
        self.assertNotIn('presetRename:', launcher())
        # while a box is open, a click on its button does not open the list or recall the snapshot
        self.assertIn("$('presetButton').onclick = () => { if (!naming) $('presetList').hidden ? openPresets() : closePresets(); };", source)
        self.assertIn("button.onclick = () => { if (!naming) ask('snapshot', index); };", source)


SETLISTS = ['FACTORY 1', 'FACTORY 2', 'USER 1', 'USER 2', 'USER 3', 'USER 4', 'USER 5', 'TEMPLATES']


class SetlistTests(unittest.TestCase):
    """Stage 2: the setlists by their own names; looking at another setlist loads nothing."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'preset': {'setlist': 2, 'number': 6, 'name': 'John Mayer Style'}, 'presets': ['Preset'] * 128,
                           'setlists': {'names': SETLISTS, 'shown': 2}, 'looking': None}

    def test_the_setlist_probe_in_a_fake_frida_world(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('node is not installed')
        result = subprocess.run([node, str(ROOT.parent / 'tests' / 'setlists_probe.cjs')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('setlists probe passed', result.stdout)

    def test_the_setlist_guards_hold_on_hx_edit_382_and_move_with_nothing(self):
        import re
        from test_target_binding import FIXTURE, _reader
        source = (ROOT / 'setlists.js').read_text(encoding='utf-8')
        guards = re.findall(r"'([0-9a-f]+)': '([0-9a-f]+)'", source[source.index('const setlistGuards'):source.index('const SETLIST_CONTROLLER_VTABLE')])
        self.assertEqual(len(guards), 12)
        # (HX Edit.exe has a dynamic base: no absolute operand in a guard)
        for _, expected in guards:
            self.assertNotIn('ff15', expected)
        if not FIXTURE.is_file():
            self.skipTest('pinned editor fixture unavailable')
        read = _reader(FIXTURE)
        for rva, expected in guards:
            self.assertEqual(read(int(rva, 16), len(expected) // 2).hex(), expected, rva)
        # the controller's vtable is the one its constructor sets, and slot 1 is its command handler
        self.assertEqual(read(0x240269, 6).hex(), 'c706240bce00')                       # mov [esi], 0xce0b24 (base 0x400000)
        self.assertEqual(read(0x8e0b28, 4).hex(), '604a6400')                           # -> 0x644a60
        # the Librarian operations the model's calls build: 2 "get preset names", 29 "load preset"
        self.assertEqual(read(0x3fc78b, 7).hex(), 'c745d802000000')
        self.assertEqual(read(0x3f8a2b, 7).hex(), 'c745d81d000000')

    def test_only_a_setlist_hx_edit_lists_is_looked_at(self):
        self.assertEqual(self.view.checked_look({'setlist': 0}), {'action': 'look', 'setlist': 0})
        self.assertEqual(self.view.checked_look({'setlist': 2}), {'action': 'look', 'setlist': 2})      # back to the loaded one
        for refused in ({'setlist': 8}, {'setlist': -1}, {'setlist': True}, {'setlist': '1'}, {}, 3, None):
            self.assertIsNone(self.view.checked_look(refused), refused)
        self.view.state['setlists'] = None                                                              # names not known
        self.assertIsNone(self.view.checked_look({'setlist': 0}))

    def test_a_preset_of_another_setlist_loads_only_once_its_names_were_read_there(self):
        check = self.view.checked_preset
        # of the loaded setlist: as before, a Program Change (the launcher's focus_load)
        self.assertEqual(check({'setlist': 2, 'number': 12}), {'action': 'preset', 'number': 12})
        self.assertIsNone(check({'setlist': 2, 'number': 6}))                                          # the loaded one
        # of another setlist: only the one looked at and read
        self.assertIsNone(check({'setlist': 0, 'number': 3}))
        self.view.state['looking'] = {'setlist': 0, 'state': 'reading'}
        self.assertIsNone(check({'setlist': 0, 'number': 3}))
        self.view.state['looking'] = {'setlist': 0, 'state': 'ok', 'names': ['US Double Nrm'] * 128}
        self.view.state['presets'] = None                                     # (HX Edit's list shows that setlist now)
        self.assertEqual(check({'setlist': 0, 'number': 3}), {'action': 'presetIn', 'setlist': 0, 'number': 3})
        for refused in ({'setlist': 1, 'number': 3}, {'setlist': 0, 'number': 128}, {'setlist': 0, 'number': True},
                        {'setlist': 9, 'number': 1}, {'setlist': 0}):
            self.assertIsNone(check(refused), refused)
        # the loaded setlist's numbers still go while another is looked at (its names are not read then)
        self.assertEqual(check(12), {'action': 'preset', 'number': 12})
        self.assertEqual(check('next'), {'action': 'preset', 'number': 7})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_look_waits_for_the_lists_rows_to_settle_on_the_other_setlists_names(self):
        def steps(look, readings):
            code = '(() => { let look = %s; const out = [];\n' % json.dumps(look)
            code += 'for (const [names, now] of %s) { look = focusLookStep(look, names, now); out.push(look.state); } return [out, look.names || null]; })()' % json.dumps(readings)
            return run_js(['focus_view.js'], code)
        old, new = ['Preset'] * 128, ['US Double Nrm'] * 128
        start = {'setlist': 0, 'at': 0, 'before': json.dumps(old, separators=(',', ':')), 'last': '', 'lastAt': 0, 'same': False, 'state': 'reading'}
        # the rows change to the other setlist's, then stand still: read
        states, names = steps(start, [[old, 100], [new, 600], [new, 900], [new, 1200]])
        self.assertEqual(states, ['reading', 'reading', 'reading', 'ok'])
        self.assertEqual(names, new)
        # rows that never change (two setlists with the same names): read after a longer wait
        states, _ = steps(start, [[old, 100], [old, 700], [old, 2000], [old, 2600]])
        self.assertEqual(states, ['reading', 'reading', 'reading', 'ok'])
        # the list was already there: as soon as the rows stand still
        states, _ = steps({**start, 'same': True}, [[old, 100], [old, 700]])
        self.assertEqual(states, ['reading', 'ok'])
        # nothing usable: failed after a while
        states, names = steps(start, [[None, 100], ['no-list', 4000], [None, 8100]])
        self.assertEqual(states, ['reading', 'reading', 'failed'])
        self.assertIsNone(names)

    def test_the_script_asks_hx_edits_list_and_loads_as_its_double_click(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'look' && Number.isInteger(value.setlist) && value.setlist >= 0 && value.setlist <= 7", script)
        self.assertIn('const asked = setlists.look(command.setlist);', script)
        self.assertIn('setlists.load(command.setlist, command.number);', script)
        self.assertIn('state.looking = looking ?', script)
        self.assertIn('state.setlists = header.setlists;', script)
        self.assertIn("if (command.action === 'look') looking = {setlist: command.setlist, at: Date.now(), state: 'failed'};", script)
        source = launcher()
        self.assertIn("'setlists.js', 'focus_view.js')) + '\\n'", source)
        self.assertIn("let setlists = null; try { setlists = installSetlists(); }", source)
        self.assertIn('installFocusView({json.dumps(focus_options)}, {{targetBinding, namView, toneView, setlists}})', source)
        self.assertIn("'setlist': view.checked_look}[name]", source)
        # ("look" is the Floor look's own request, handled before these: the setlist's is "setlist")
        self.assertNotIn("'look': view.checked_look", source)
        self.assertIn("'setlists.js'", (ROOT / 'build-windows.py').read_text(encoding='utf-8'))

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_setlists_own_names(self):
        name = lambda names, index: run_js(['workbench_layout.js'], f'workbenchSetlistName({json.dumps(names)}, {index})')
        self.assertEqual(name(SETLISTS, 2), 'USER 1')
        self.assertEqual(name(None, 2), 'Setlist 3')
        self.assertEqual(name(['A', ' '], 1), 'Setlist 2')
        count = lambda names: run_js(['workbench_layout.js'], f'workbenchSetlistCount({json.dumps(names)})')
        self.assertEqual(count(['A'] * 128), '128')
        self.assertEqual(count(['New Preset'] * 125 + ['A', 'B', 'C']), '3')
        self.assertEqual(count(['New Preset'] * 128), 'empty')
        self.assertEqual(count(None), '')

    def test_the_page_shows_setlists_in_the_three_places_and_loads_through_the_guard(self):
        source = page()
        self.assertIn("$('setlist').textContent = preset && Number.isInteger(preset.setlist) ? setlistName(preset.setlist)", source)
        # the top bar's list: setlists beside the presets, the dot, the mock-up's words
        self.assertIn("sl.append(el('p', '', 'Looking at a setlist changes nothing. The dot is the setlist the loaded preset is in.'));", source)
        self.assertIn("index === setlistOf() ? el('i', 'dot')", source)
        self.assertIn("head.append(el('b', '', setlistName(shown)), el('span', '', 'click a preset to load it'));", source)
        # the strip and the way back
        self.assertIn("words.append('You are looking at ', el('b', '', setlistName(at)), '. Still loaded: '", source)
        self.assertIn("' Nothing changes until you click a preset.'", source)
        self.assertIn("const back = el('button', 'btn sm', 'Back to ' + setlistName(setlistOf()));", source)
        # tabs over the whole setlist, a chooser in the drawer
        self.assertIn("const main = body.querySelector('.pv .main'), tabs = el('div', 'sltabs')", source)
        self.assertIn("const pick = el('select', 'slpick');", source)
        # a click on a preset of another setlist: loadPreset, so the unsaved-changes prompt applies
        self.assertIn('const presetTarget = number => lookingAt() === null ? number : {setlist: lookingAt(), number};', source)
        self.assertEqual(source.count('loadPreset(presetTarget('), 3)                     # the list, the drawer, the grid
        self.assertIn("const other = !!target && typeof target === 'object', number = other ? target.number : target;", source)
        # looking asks HX Edit's list for the names; nothing else; back to the loaded setlist once nothing looks elsewhere
        self.assertIn("ask('setlist', {setlist: index})", source)
        self.assertIn("backTries.count++; backAskedAt = Date.now(); ask('setlist', {setlist: setlistOf()});", source)
        self.assertIn('settleLook(false);', source)
        # pins are per setlist
        self.assertIn("pin(number, !isPinned(number, shown), shown)", source)


if __name__ == '__main__':
    unittest.main()
