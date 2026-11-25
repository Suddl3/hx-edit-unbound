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
from test_focus_view import NODE, FakePane, resources, run_js, run_js_source  # noqa: E402


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
                        {'what': 'preset', 'name': 'New Name'},                  # a preset: its own check (setlist, number)
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

    def test_the_name_boxes_are_the_mock_ups(self):
        source = page()
        for words in ("kbdHint('Enter', 'rename')", "kbdHint('Esc', 'keep the old name')", "'The Floor shows it once you Save the preset. It is not an Undo step.'",

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
        # a snapshot: asked of HX Edit; a preset: kept pending until the next Save (PresetRenameTests)
        self.assertIn("ask('rename', {what: 'snapshot', index, name});", source)
        self.assertNotIn('PRESET_RENAME_HELD', source)
        self.assertNotIn('options.presetRename', source)
        # while a box is open, a click on its button does not open the list or recall the snapshot
        self.assertIn("$('presetButton').onclick = () => { if (!naming) $('presetList').hidden ? openPresets() : closePresets(); };", source)
        self.assertIn("button.onclick = () => { if (!naming) ask('snapshot', index); };", source)


SETLISTS = ['FACTORY 1', 'FACTORY 2', 'USER 1', 'USER 2', 'USER 3', 'USER 4', 'USER 5', 'TEMPLATES']


class PresetRenameTests(unittest.TestCase):
    """Nick, 2026-11-24: a preset's new name is kept until the next Save, then the stored copy is renamed."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'preset': {'setlist': 3, 'number': 32, 'name': 'Spare'}, 'snapshots': ['Clean'], 'presetRenameReady': True}

    def test_only_the_loaded_preset_with_a_name_the_floor_keeps_and_only_when_the_script_can(self):
        check = self.view.checked_rename
        ask = lambda **v: check({'what': 'preset', 'setlist': 3, 'number': 32, 'name': 'Spare Test', **v})
        self.assertEqual(ask(), {'action': 'presetRename', 'setlist': 3, 'number': 32, 'name': 'Spare Test'})
        self.assertEqual(ask(name='Sixteen chars!!!')['name'], 'Sixteen chars!!!')
        for refused in ({'number': 33}, {'setlist': 2}, {'setlist': True}, {'name': 'Seventeen chars!!'}, {'name': 'Spare'},
                        {'name': 'Café'}, {'name': 'Trailing '}, {'name': ''}, {'name': None}):
            self.assertIsNone(ask(**refused), refused)
        self.view.state['presetRenameReady'] = False                   # the script's guards did not hold
        self.assertIsNone(ask())
        self.view.state['presetRenameReady'] = None
        self.assertIsNone(ask())

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_pending_name_is_for_one_preset_and_the_stored_name_again_clears_it(self):
        named = lambda *a: run_js(['workbench_layout.js'], 'workbenchPendingNamed(%s)' % ', '.join(json.dumps(x) for x in a))
        self.assertEqual(named('3:32', 'Spare Test', 'Spare'), {'key': '3:32', 'name': 'Spare Test'})
        self.assertIsNone(named('3:32', 'Spare', 'Spare'))              # back to the stored name: nothing pending
        self.assertIsNone(named('3:32', 'Spare  ', 'Spare'))
        self.assertIsNone(named('', 'Spare Test', 'Spare'))
        here = lambda pending, key: run_js(['workbench_layout.js'], f'workbenchPendingHere({json.dumps(pending)}, {json.dumps(key)})')
        self.assertEqual(here({'key': '3:32', 'name': 'X'}, '3:32'), {'key': '3:32', 'name': 'X'})
        self.assertIsNone(here({'key': '3:32', 'name': 'X'}, '3:33'))  # never follows to another preset
        self.assertIsNone(here(None, '3:32'))

    def test_save_runs_first_then_the_stored_copy_is_renamed_and_read_back(self):
        source = page()
        save = source[source.index('function saveNow() {'):source.index('const SAVE_WAIT_MS = 2000;')]

        self.assertLess(save.index("ask('save');"), save.index("ask('rename', {what: 'preset', setlist: ask_.setlist, number: ask_.number, name: ask_.name})"))
        self.assertIn('if (presetWord() === ask_.key && renameAsked === ask_)', save)
        self.assertIn('}, SAVE_WAIT_MS);', save)
        # a pending name is an unsaved change: the dot, and the prompt before leaving; leaving drops it
        self.assertIn('const changedHere = () => unsaved() || !!pendingHere();', source)
        self.assertIn("$('edited').hidden = !changedHere();", source)
        self.assertIn("if (!changedHere()) { ask('preset', target); return; }", source)
        self.assertIn('if (before !== after) pendingName = null;', source)
        self.assertIn("if (outcome.state === 'failed') toast('HX Edit did not rename ' + number3(renameAsked.number) + ' on the Floor. Its name is as it was.');", source)
        # Enter: pending (or nothing, back to the stored name); without the script's rename, said so and nothing kept
        self.assertIn("else if (name) pendingName = workbenchPendingNamed(presetWord(), name, state.preset.name);", source)
        self.assertIn("} else if (name && state.presetRenameReady !== true) toast(PRESET_RENAME_UNAVAILABLE);", source)
        self.assertIn("'The Floor shows it once you Save the preset. It is not an Undo step.'", source)
        # the lists show it for the loaded preset only, marked
        self.assertIn("pendingHere().name + ' (not saved)' : names[index];", source)
        self.assertEqual(source.count('pendingRow('), 3)                  # the top bar's list, the drawer, the grid
        # Ctrl+S in the pane is the Workbench's own Save
        self.assertIn("String(e.key).toLowerCase() === 's' && visible && !naming && !leaving) { e.preventDefault(); savePreset(); return; }", source)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'presetRename' && Number.isInteger(value.setlist)", script)
        self.assertIn('setlists.renamePreset(command.setlist, command.number, command.name);', script)
        self.assertIn("if ((here && header.preset.name === renaming.name) || row === renaming.name) renaming = {...renaming, state: 'ok'};", script)
        self.assertIn("else if (Date.now() > renaming.until) renaming = {...renaming, state: 'failed', error: 'not seen'};", script)
        self.assertIn('state.presetRenameReady = header.renameReady === true;', script)


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
        self.assertEqual(len(guards), 27)
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
        # rows that never change: never taken as the other setlist's (the ask may not have worked): failed, and "Try
        # again" (the list shows that setlist by then: same) reads them as they stand
        states, names = steps(start, [[old, 100], [old, 700], [old, 2600], [old, 5900], [old, 6100], [old, 20000], [old, 31000], [old, 40000]])
        self.assertEqual(states, ['reading', 'reading', 'reading', 'reading', 'failed', 'failed', 'failed', 'failed'])
        self.assertIsNone(names)
        # a slow first answer (live check 2026-11-24 10:13: ~2.7 s after a launch) is not a failure: read when it comes
        states, names = steps(start, [[old, 100], [old, 2500], [new, 2727], [new, 3300]])
        self.assertEqual(states, ['reading', 'reading', 'reading', 'ok'])
        self.assertEqual(names, new)
        # rows that come after it was called failed turn it into ok by themselves, while it is watched (30 s)
        states, names = steps(start, [[old, 100], [old, 6100], [new, 9000], [new, 9600]])
        self.assertEqual(states, ['reading', 'failed', 'failed', 'ok'])
        self.assertEqual(names, new)
        states, names = steps(start, [[old, 100], [old, 6100], [old, 31000], [new, 32000], [new, 33000]])
        self.assertEqual(states, ['reading', 'failed', 'failed', 'failed', 'failed'])    # no longer watched: not taken
        self.assertIsNone(names)
        # the list was already there: as soon as the rows stand still
        states, _ = steps({**start, 'same': True}, [[old, 100], [old, 700]])
        self.assertEqual(states, ['reading', 'ok'])
        # nothing usable: failed after a while; rows that come later still turn it into ok
        states, names = steps(start, [[None, 100], ['no-list', 4000], [None, 8100], [new, 9000], [new, 9600]])
        self.assertEqual(states, ['reading', 'reading', 'failed', 'failed', 'ok'])
        self.assertEqual(names, new)
        # a failure made by the ask itself (setlists.look threw) is not watched
        states, _ = steps({'setlist': 0, 'at': 0, 'state': 'failed'}, [[new, 100], [new, 700]])
        self.assertEqual(states, ['failed', 'failed'])
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('FOCUS_LOOK_SAME_MS = 6000, FOCUS_LOOK_GIVE_UP_MS = 8000, FOCUS_LOOK_LATE_MS = 30000', script)
        self.assertIn("if (looking && (looking.state === 'reading' || (looking.state === 'failed' && looking.watch))) {", script)

    def test_the_script_asks_hx_edits_list_and_loads_as_its_double_click(self):
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("value.action === 'look' && Number.isInteger(value.setlist) && value.setlist >= 0 && value.setlist <= 7", script)
        self.assertIn('const asked = setlists.look(command.setlist);', script)
        self.assertIn('setlists.load(command.setlist, command.number);', script)
        self.assertIn('state.looking = looking ?', script)
        self.assertIn('state.setlists = header.setlists;', script)
        self.assertIn("if (command.action === 'look') looking = {setlist: command.setlist, at: Date.now(), state: 'failed'};", script)
        # (live check 2026-11-24: how far the setlist reading gets goes to the trace when it changes; an empty chooser
        # is filled as HX Edit fills it, only once the Presets list has its rows)
        self.assertIn("if (word !== setlistsWord) { setlistsWord = word; send({type: 'toneTrace', reason: 'focus-view', stage: 'setlists', result: word}); }", script)
        self.assertIn('else if (setlists && Array.isArray(names)) setlists.askNames();', script)
        source = launcher()
        self.assertIn("'setlists.js', 'focus_view.js')) + '\\n'", source)
        self.assertIn("let setlists = null; try { setlists = installSetlists(); }", source)
        self.assertIn('installFocusView({json.dumps(focus_options)}, {{targetBinding, namView, toneView, setlists}})', source)
        self.assertIn("'setlist': view.checked_look}[name]", source)
        # ("look" is the Floor look's own request, handled before these: the setlist's is "setlist")
        self.assertNotIn("'look': view.checked_look", source)
        self.assertIn("'setlists.js'", (ROOT / 'build-windows.py').read_text(encoding='utf-8'))

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_hx_edits_list_is_asked_back_at_once_on_a_way_out_and_then_retried_without_a_state_message(self):
        # Live check 2026-11-24 09:58: after a look at setlist 4 and Esc, HX Edit's list stayed on 4 (the page asked only
        # on a state message, and an idle HX Edit sends none).
        def run(steps):
            code = '(() => { let tries = {word: "", count: 0}, askedAt = 0; const out = [];\n'
            code += 'for (const s of %s) { const d = workbenchBackAsk({...s, askedAt, tries}); tries = d.tries; if (d.ask) askedAt = s.now; out.push(d.ask); }\n' % json.dumps(steps)
            code += 'return out; })()'
            return run_js(['workbench_layout.js'], code)
        away = {'looking': None, 'loaded': 3, 'shown': 4}
        # the list closed (forced): asked at once; then the timer every second: again only WORKBENCH_BACK_MS apart
        self.assertEqual(run([{**away, 'now': 1000, 'force': True}, {**away, 'now': 2000}, {**away, 'now': 3500}, {**away, 'now': 4000}, {**away, 'now': 7100}]),
                         [True, False, False, True, True])
        # at most WORKBENCH_BACK_TRIES times for the same pair, unless forced (a button, a load)
        steps = [{**away, 'now': 1000 + 4000 * i} for i in range(8)] + [{**away, 'now': 40000, 'force': True}]
        self.assertEqual(run(steps), [True] * 5 + [False] * 3 + [True])
        # never while something still looks elsewhere, nor when the list shows the loaded setlist, nor without readings
        for quiet in ({**away, 'looking': 4}, {**away, 'shown': 3}, {**away, 'shown': None}, {**away, 'loaded': None}):
            self.assertEqual(run([{**quiet, 'now': 1000, 'force': True}]), [False], quiet)
        # another pair starts afresh
        self.assertEqual(run([{**away, 'now': 1000 + 4000 * i} for i in range(5)] + [{**away, 'shown': 5, 'now': 30000}]), [True] * 6)
        self.assertEqual(run_js(['workbench_layout.js'], '[WORKBENCH_BACK_MS, WORKBENCH_BACK_TRIES]'), [3000, 5])

    def test_every_way_out_sends_hx_edits_list_back(self):
        source = page()
        close = source[source.index('function closePresets(keepLook) {'):source.index('// ---- a name box of our own')]
        self.assertLess(close.index("$('presetList').hidden = true;"), close.index('letLookGo();'))              # Esc, a click outside, a pick
        let_go = source[source.index('function letLookGo() {'):source.index('// What a click on a preset of the setlist shown does')]
        self.assertIn("if (lookAt === null || !$('presetList').hidden || view.full === 'presets' || view.drawer === 'presets') return false;", let_go)
        self.assertIn('settleLook(true);', let_go)                                                             # at once
        commit = source[source.index('function commitView(next, relaid) {'):source.index('function pickBlock(block, added) {')]
        self.assertIn('letLookGo();', commit)                                                                   # the drawer or view left
        self.assertIn('if (lookAt === null) settleLook(true);', source)                                         # "Back to X"
        self.assertIn("if (!(target && typeof target === 'object')) settleLook(true);", source)                 # a load of the loaded setlist
        self.assertIn('const BACK_TIMER = setInterval(() => { if (visible && state) { letLookGo(); if (lookAt === null) settleLook(false); } }, 1000);', source)
        render = source[source.index('function render() {'):source.index('function receive(message) {')]
        self.assertIn('letLookGo();\n  settleLook(false);', render)

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
        self.assertEqual(source.count('loadPreset(presetTarget('), 2)                     # the drawer, the grid
        self.assertIn('const target = presetTarget(index); closePresets(typeof target === \'object\');', source)   # the list
        self.assertIn("const other = !!target && typeof target === 'object', number = other ? target.number : target;", source)
        # looking asks HX Edit's list for the names; nothing else; back to the loaded setlist once nothing looks elsewhere
        self.assertIn("ask('setlist', {setlist: index})", source)
        self.assertIn("if (decided.ask) { backAskedAt = Date.now(); ask('setlist', {setlist: setlistOf()}); }", source)
        self.assertIn('settleLook(false);', source)
        # pins are per setlist
        self.assertIn("pin(number, !isPinned(number, shown), shown)", source)


class FloorSlotTests(unittest.TestCase):
    """Stage 3: the Floor's slots, with Clear; slot 128's new rule for previews."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe', costs_file=None)
        self.addCleanup(self.view.close)
        self.view.state = {'preset': {'setlist': 2, 'number': 6, 'name': 'John Mayer Style'},
                           'captures': [{'slot': 17, 'name': 'Klon'}, {'slot': 22, 'name': 'Brit Gold Crunch'}],
                           'irs': [{'slot': 1, 'name': 'York 4x12'}], 'slot128': {'name': 'Room Mic'},
                           'blocks': [{'dsp': 0, 'id': 'block0', 'model': 'HD2_AmpNAMLite', 'slot': 17}]}

    def test_clear_is_only_for_slots_shown_in_use_and_never_one_the_loaded_preset_uses(self):
        check = self.view.checked_clear
        self.assertEqual(check({'slots': [22]}), {'action': 'clear', 'slots': [22]})
        self.assertEqual(check({'slots': [128, 1, 22]}), {'action': 'clear', 'slots': [1, 22, 128]})
        for refused in ({'slots': [17]},                 # the loaded preset uses it (as HX Edit's own Clear refuses)
                        {'slots': [22, 17]}, {'slots': [5]}, {'slots': [22, 22]}, {'slots': []}, {'slots': [True]},
                        {'slots': [0]}, {'slots': [129]}, {'slots': '22'}, {'slot': 22}, None):
            self.assertIsNone(check(refused), refused)
        self.view.state['slot128'] = None
        self.assertIsNone(check({'slots': [128]}))                       # nothing in 128

    def test_the_launcher_clears_through_the_check_and_shows_who_uses_each_slot(self):
        source = launcher()
        self.assertIn("command = workbench.checked_clear(value) if workbench_on[0] and not focus_on[0] else None", source)
        self.assertIn("workbench.show_usage(usage_view(memory.presets()))", source)
        self.assertIn("workbench.show_previews(previews_view(memory.previews(), memory.preview()))", source)
        self.assertIn("ownPreviews=list(memory.previews())", source)
        self.assertIn("if workbench is not None and payload.get('type') in ('previewOwned', 'tonePreviewState'):", source)
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('const result = namView.clearSlotsChecked(command.slots);', script)
        self.assertIn("try { slot128 = namView.slotName?.(128) || ''; } catch (_) { slot128 = ''; }", script)
        self.assertIn('state.clearing = clearing ? clearing.slots : null;', script)
        self.assertIn('clearNote = {text: `HX Edit did not clear slot ${left.join(\', \')}.`, at: Date.now()};', script)

        # HX Edit's own Clear, with its protection: never a slot the loaded preset uses, nor while that cannot be read
        reader = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        body = reader[reader.index('    clearSlotsChecked(slots) {'):reader.index('    previewSlotEmpty(transfer) {')]
        self.assertIn("if (!(preset?.slots instanceof Set)) return {refused: 'unknown'", body)

        self.assertIn("if (used.length) return {refused: 'used', slots: used};", body)
        self.assertIn('submitClear(librarian, vector, sorted);', body)
        self.assertLess(body.index("return {refused: 'used'"), body.index('submitClear('))
        self.assertNotIn('trustedClear', body)

    def test_usage_and_our_previews_for_the_page(self):
        self.assertEqual(workbench.usage_view([[2, 6, 'John Mayer Style', [17, 21]], [2, 7, 'Unread', None], [3, 1, 'X', [0, 129, 5, True]], 'bad']),
                         [{'setlist': 2, 'preset': 6, 'name': 'John Mayer Style', 'slots': [17, 21]}, {'setlist': 3, 'preset': 1, 'name': 'X', 'slots': [5]}])
        self.assertEqual(workbench.previews_view({'Plexi a3f9c1': '2026-11-22'}), [{'name': 'Plexi a3f9c1', 'when': '2026-11-22', 'onBlock': False}])
        # the one a block still plays (floor_memory's leftover record) says so: clearing it would leave that block silent
        self.assertEqual(workbench.previews_view({'A 000001': '2026-11-21', 'B 000002': '2026-11-22'}, {'name': 'B 000002', 'dsp': 0})[1]['onBlock'], True)
        self.assertEqual(workbench.previews_view(None), [])

    def test_our_previews_are_remembered_from_one_launch_to_the_next(self):
        from floor_memory import PREVIEWS, FloorMemory
        memory = FloorMemory(self.folder)
        self.assertTrue(memory.receive({'type': 'previewOwned', 'name': 'Plexi a3f9c1'}))
        memory.receive({'type': 'tonePreviewState', 'state': {'dsp': 0, 'block': 'block3', 'originalSlot': 17, 'name': 'Tweed 0b12aa'}})
        memory.receive({'type': 'previewOwned', 'name': ''})
        memory.receive({'type': 'previewOwned', 'name': 'x' * 65})
        self.assertEqual(list(FloorMemory(self.folder).previews()), ['Plexi a3f9c1', 'Tweed 0b12aa'])
        self.assertEqual(FloorMemory(self.folder).preview()['name'], 'Tweed 0b12aa')        # (the leftover record is unchanged)
        for n in range(PREVIEWS + 5):
            memory.receive({'type': 'previewOwned', 'name': f'p{n}'})
        kept = FloorMemory(self.folder).previews()
        self.assertEqual(len(kept), PREVIEWS)
        self.assertNotIn('Plexi a3f9c1', kept)                                             # the oldest go first

    def test_a_preview_of_ours_in_128_is_replaced_without_asking_and_anything_else_is_asked_once(self):
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("ours128: !!name128 && (ownPreviews.has(name128) || (!!leftover && leftover.name === name128)),", tone)
        self.assertIn('allowed128: request.replace === AUDITION_SLOT', tone)
        self.assertIn('ownPreview(record.name);', tone)
        self.assertIn("send({type: 'previewOwned', name});", tone)
        self.assertIn("error.replace = [[128, String(state.name128 || '')]];", tone)
        # the session's answer to "Replace it and preview" is its own replace of slot 128 (checked as before)
        self.assertEqual(workbench.checked_floor({'do': 'replace', 'arg': 128}, {}), 'replace:128')
        source = page()
        self.assertIn("if (taken.length === 1 && taken[0][0] === 128) {", source)
        self.assertIn("go.onclick = () => done(true);", source)
        self.assertIn("if (go) ask('levels', {do: 'replace', arg: 128});", source)
        for words in ("'Slot 128 is in use. Replace it to preview?'", "'Don’t preview'", "'Replace it and preview'",
                      "'Replacing it takes it off the Floor for good. This is asked once for each thing found there, never for a preview of our own.'"):
            self.assertIn(words, source)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_slots_list_folds_the_free_ones_and_names_who_uses_each(self):
        rows = run_js(['workbench_layout.js'], 'workbenchSlotRows([{slot: 22, name: "Brit", icon: "amp"}, {slot: 128, name: "pv"}, {slot: 3, name: "dup"}], [{slot: 3, name: "IR"}, {slot: 1, name: "York"}])')
        self.assertEqual([(r['slot'], r['kind']) for r in rows], [(1, 'ir'), (3, 'capture'), (22, 'capture')])   # 128 apart; a capture wins
        self.assertEqual(run_js(['workbench_layout.js'], 'workbenchFreeRanges([1, 2, 3, 17, 21, 22, 127])'), [[4, 16], [18, 20], [23, 126]])
        self.assertEqual(run_js(['workbench_layout.js'], 'workbenchFreeRanges([])'), [[1, 127]])
        usage = [{'setlist': 2, 'preset': 6, 'name': 'Loaded', 'slots': [17]}, {'setlist': 2, 'preset': 12, 'name': 'Blues', 'slots': [17, 22]}]
        users = run_js(['workbench_layout.js'], f'workbenchSlotUsers({json.dumps(usage)}, 17, {{setlist: 2, number: 6}})')
        self.assertEqual(users, [{'setlist': 2, 'preset': 12, 'name': 'Blues'}])

    def test_the_tab_and_its_question_are_the_mock_ups(self):
        source = page()
        self.assertIn("for (const [key, words] of [['captures', 'Captures'], ['slots', 'Floor slots']]) {", source)
        # (only what is known about what is in 128: an old preview of ours looks the same as anything else)
        self.assertIn("'Preview slot · holds something with no record of ours'", source)
        self.assertIn("'HX Edit Unbound has no record of putting “' + name + '” in slot 128.", source)
        self.assertNotIn('did not put there', source + (ROOT / 'tone_view.js').read_text(encoding='utf-8'))
        self.assertNotIn('outside HX Edit Unbound', source)
        self.assertIn("head.append(libTabs(), find, sort, layout, el('span', 'sp'), t3k, imp);", source)
        for words in ("'Clear slot ' + rows[0].slot + ' on the Floor?'", "' taken off the Floor. '", "' in your library on this PC.'",
                      "' filled again. Undo does not bring a cleared slot back: you would put '", "'. Only presets opened in this editor are known.'",
                      "'Keep ' + (one ? 'it' : 'them')", "'Clear ' + picked.length + ' selected…'", "'Preview slot · holds a preview that was left behind'",
                      "' that never ended. It is one of ours, so the next preview replaces it without asking.'", "'Show in the library'",
                      "'Captures and IRs share the Floor’s 128 IR slots. Who uses a slot is known only for presets opened in this editor.'"):
            self.assertIn(words, source)
        # Clear asks first: the question's button is the only way to "clear" (and a preview of ours in 128 needs none)
        self.assertEqual(source.count("ask('clear', {slots: "), 2)
        self.assertIn("if (go) { ask('clear', {slots: rows.map(r => r.slot)});", source)
        self.assertIn("clear.onclick = () => { if (ours && !ours.onBlock) ask('clear', {slots: [128]}); else askClear([row]); };", source)
        # a slot the loaded preset uses cannot be cleared (HX Edit's own protection), and says why
        self.assertIn('clear.disabled = row.here || clearing.size > 0;', source)


class LiveCheckFixTests(unittest.TestCase):
    """The faults of the 2026-11-24 10:39-10:47 live check (trial 20261124-103902-1c6b00d9), one by one."""

    def test_a_a_looked_at_rows_click_loads_that_setlists_preset_never_the_same_number_elsewhere(self):
        # Cause: the click closed the list first, which let the look go, so presetTarget gave a bare number.
        source = page()
        self.assertIn("button.onclick = () => { const target = presetTarget(index); closePresets(typeof target === 'object'); if (index !== at) loadPreset(target); };", source)
        close = source[source.index('function closePresets(keepLook) {'):source.index('// ---- a name box of our own')]
        self.assertIn('if (!keepLook) letLookGo();', close)
        let_go = source[source.index('function letLookGo() {'):source.index('// What a click on a preset of the setlist shown does')]
        self.assertIn('if (leaving || Date.now() < holdLookUntil) return false;', let_go)     # the prompt open, or the load on its way
        self.assertIn('else holdLookUntil = Date.now() + HOLD_LOOK_MS;', source)
        # the drawer and the grid never closed anything before reading the target
        self.assertIn("button.onclick = () => { if (index !== at) loadPreset(presetTarget(index)); };", source)
        self.assertIn('b.onclick = () => { if (number !== at) loadPreset(presetTarget(number)); };', source)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_b_a_step_hx_edit_makes_by_itself_right_after_a_load_is_not_an_unsaved_change(self):
        mark = lambda *a: run_js(['workbench_layout.js'], 'workbenchSettledMark(%s)' % ', '.join(json.dumps(x) for x in a))
        loaded = {'key': '0:0', 'at': 0, 'settle': 12500}                      # loaded at 10000
        self.assertEqual(mark(loaded, '0:0', 1, 11000, 0)['at'], 1)             # the step a second later moves the mark
        self.assertEqual(mark(loaded, '0:0', 1, 11000, 10500)['at'], 0)         # the page asked for a change: counted
        self.assertEqual(mark(loaded, '0:0', 1, 13000, 0)['at'], 0)             # after the settling time: counted
        self.assertEqual(mark(loaded, '3:31', 1, 11000, 0)['at'], 0)            # another preset: not this mark
        self.assertEqual(mark({'key': '0:0', 'at': 0}, '0:0', 1, 11000, 0)['at'], 0)   # a Save's mark never settles
        self.assertEqual(run_js(['workbench_layout.js'], 'WORKBENCH_LOAD_SETTLE_MS'), 2500)
        source = page()
        self.assertIn('savedMark = {key: after, at: state.undoAt, settle: Date.now() + WORKBENCH_LOAD_SETTLE_MS};', source)
        self.assertIn('else savedMark = workbenchSettledMark(savedMark, after, state.undoAt, Date.now(), editAskedAt);', source)
        self.assertIn('if (EDIT_ASKS.has(name)) editAskedAt = Date.now();', source)

    def test_c_back_from_a_full_view_the_block_panel_is_drawn_again(self):
        # Cause: commitView drew the chain but not the panel; the panel waited for a state message.
        source = page()
        commit = source[source.index('function commitView(next, relaid) {'):source.index('function pickBlock(block, added) {')]
        self.assertIn("if (catalog && state && !view.full) { drawChain(true); shownPanel = ''; drawPanel(); }", commit)

    def test_d_clear_reads_any_preset_and_its_refusal_stays_on_screen(self):
        # Cause: the strict preset reader refuses preset shapes it does not know ("unsupported-global-node").
        reader = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        body = reader[reader.index('    clearSlotsChecked(slots) {'):reader.index('    previewSlotEmpty(transfer) {')]
        self.assertIn('const preset = presetSlotsForClear();', body)
        shared = reader[reader.index('  function presetSlotsForClear() {'):reader.index('  function presetSlotUse(slot) {')]
        self.assertIn('const raw = readCurrentPreset(true, true);', shared)
        self.assertIn('return presetIrSlotsLenient(raw.tree, irParameters, AUDITION_SLOT);', shared)
        self.assertNotIn('irList().isNull()', body)                          # HX Edit's own IR list need not be built
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn("if (result.refused) clearNote = {text: (CLEAR_REFUSED[result.refused] || CLEAR_REFUSED.bad)(result.slots || []), at: Date.now()};", script)
        self.assertIn('state.clearNote = clearNote;', script)
        source = page()
        self.assertIn('if (state.clearNote && state.clearNote.at !== seenClearNote) { seenClearNote = state.clearNote.at; stickyNote(state.clearNote.text); }', source)
        self.assertIn("const ok = el('button', 'btn sm', 'OK'); ok.onclick = () => note.remove();", source)

    def test_e_a_preview_named_with_a_dash_is_found_again_and_its_word_goes_to_the_page(self):
        # Cause: the staged name had an en dash; HX Edit stores it as "?", the read-back never matched, the upload
        # was then treated as not ours after 12 s.
        from nam_convert import ascii_name
        self.assertEqual(ascii_name('LA-2A Classic – Medium'), 'LA-2A Classic - Medium')
        self.assertEqual(ascii_name('Café “Big” — Amp…'), 'Caf "Big" - Amp...')
        self.assertEqual(ascii_name('☃☃'), 'Preview')
        convert = (ROOT / 'nam_convert.py').read_text(encoding='utf-8')
        self.assertIn("name = ascii_name(source.stem)[:IR_NAME_LIMIT - len(tag)].rstrip(' .') + tag + '.wav'", convert)
        reader = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        self.assertIn("const plain = String(transfer.name).replace(/[^\\x20-\\x7e]/g, '?');", reader)
        preview = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        self.assertIn("to_page = bool(self.workbench_sink) and (self.workbench or self.bounds_override is not None)", preview)
        self.assertIn("if notice and to_page:\n                self._to_workbench('notice', {'text': str(notice[0])})", preview.replace('\r\n', '\n'))
        source = page()
        self.assertIn("else if (message.type === 'session' && message.kind === 'notice') { stickyNote(message.data && message.data.text); return; }", source)
        # the slot 128 question opens by itself once for each thing found there, not again when the status changes
        self.assertIn("if (asked128 !== name && !busy) { asked128 = name; setTimeout(() => ask128(name), 0); }", source)

    def test_f_the_dimmed_floor_buttons_say_why(self):
        source = page()
        self.assertIn("'Put on the Floor and Preview work on the NAM block selected in the chain. Select one there (Back to the chain), then come back.'", source)


class PreviewEndTests(unittest.TestCase):
    """Live check 2026-11-24 11:47 (trial 20261124-114511-df7e104e): End preview on 032 put the block back on 127 but
    its own clean-up of slot 128 was refused ("clear-refused"); the preset kept an unsaved dot; after the Floor slots
    tab cleared 128 by hand, leaving the library said "Preview slot ownership changed"."""

    def test_the_preview_clean_up_uses_the_floor_slots_clear_check(self):
        # Cause: canClearPreview / previewUse asked the strict preset reader, which refuses 032's shape.
        reader = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        use = reader[reader.index('  function presetSlotUse(slot) {'):reader.index('  // --- Which presets use each IR slot')]
        self.assertIn('const preset = presetSlotsForClear();', use)
        self.assertIn("return preset.slots.has(slot) ? 'used' : 'unused';", use)
        view = reader[reader.index('    canClearPreview(transfer) {'):reader.index('    clearPreview(transfer) {')]
        self.assertIn("return this.previewUse(transfer) === 'unused';", view)
        self.assertIn('return presetSlotUse(transfer.slot);', view)
        self.assertIn('const use = presetSlotUse(AUDITION_SLOT);', view)       # the leftover from an earlier launch too
        self.assertNotIn('readCurrentPreset()', view)

    def test_the_lenient_check_counts_128_and_snapshot_controlled_slots(self):
        source = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        helper = source[source.index('function presetIrSlotsLenient('):source.index('function previewSlotUnused(')]
        tree = {'global': {}, 'globalNodes': {'snapshot0': {'controllers': {'dsp0': {'block1': {'Index': {'@value': 128}}}}},
                                              'unknownNode': {'x': {'y': 1}}},
                'dsp0': {'block0': {'@model': 'NAM', 'Index': 127}, 'block1': {'@model': 'NAM', 'Index': 9}}, 'dsp1': {}}
        slots = run_js_source(helper, '[...presetIrSlotsLenient(%s, {NAM: ["Index"]}, 128).slots].sort((a, b) => a - b)' % json.dumps(tree))
        self.assertEqual(slots, [9, 127, 128])                    # an unknown global node is no refusal


    def test_end_preview_ends_with_the_block_back_even_when_128_stays(self):
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        body = tone[tone.index('  function restoreOwnedPreview(request, completed) {'):tone.index('  function slotGone(request, completed) {')]
        self.assertIn("const use = namView.previewUse(transfer);", body)
        self.assertIn("if (use === 'unknown' && !expired) return null;", body)
        self.assertIn("'It stays marked as ours, so the next preview replaces it; Floor slots can clear it.'", body)
        self.assertNotIn("retained('clear-refused'", body)                # the block is back: the session is not held
        self.assertNotIn("retained('clear-not-confirmed'", body)
        self.assertNotIn('Preview slot ownership changed', tone)
        # emptied by the user: no note; something else there: plain words
        self.assertIn('if (namView.previewSlotEmpty(transfer)) return slotGone(request, completed);', body)
        self.assertIn("return completed('Slot 128 holds something else now, so the preview\\'s clean-up left it and the block as they are.');", tone)
        # the next preview never replaces a 128 this preset uses
        self.assertIn("if (namView.slotUse?.(AUDITION_SLOT) === 'used') {", tone)

    def test_the_previews_own_two_steps_are_not_an_unsaved_change(self):
        mark = lambda *a: run_js(['workbench_layout.js'], 'workbenchPreviewMark(%s)' % ', '.join(json.dumps(x) for x in a))
        clean = {'key': '3:31', 'at': 1}
        ended = {'from': 1, 'to': 3, 'at': 10000}
        self.assertEqual(mark(clean, '3:31', 3, ended, 11000)['at'], 3)        # 1 -> preview 2 -> back 3: unchanged
        self.assertEqual(mark(clean, '3:31', 4, ended, 11000)['at'], 1)        # one step more: a real change
        self.assertEqual(mark({'key': '3:31', 'at': 0}, '3:31', 3, ended, 11000)['at'], 0)   # changed before it began
        self.assertEqual(mark(clean, '3:32', 3, ended, 11000)['at'], 1)        # another preset
        self.assertEqual(mark(clean, '3:31', 3, ended, 19000)['at'], 1)        # long after
        self.assertEqual(mark(clean, '3:31', 3, None, 11000)['at'], 1)
        self.assertEqual(run_js(['workbench_layout.js'], 'WORKBENCH_PREVIEW_END_MS'), 8000)
        self.assertIn('savedMark = workbenchPreviewMark(savedMark, after, state.undoAt, state.previewEnded, Date.now());', page())
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('state.previewEnded = toneView.previewEnded ? toneView.previewEnded() : null;', script)
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("previewEnd = {from: origin.undo, to: active.undoAfter + 1, at: Date.now()};", tone)
        self.assertIn('if (!active.origin.structural && undoBefore !== (active.previewChain ?? active.origin.undo)) active.previewTainted = true;', tone)
        self.assertIn('previewEnded: () => previewEnd,', tone)


class SaveDuringPreviewTests(unittest.TestCase):
    """Live check 2026-11-24 13:09 (trial 20261124-130606-2341be22): on 032 with a library preview playing, the unsaved
    prompt offered "Save, then load it". HX Edit's Save would have stored the NAM block on slot 128, which the preview's
    clean-up then empties."""

    def test_which_preview_plays(self):
        on = lambda *a: run_js(['workbench_layout.js'], 'workbenchPreviewOn(%s)' % ', '.join(json.dumps(x) for x in a))
        self.assertEqual(on({'previewing': True}, {'trial': 3}, None), 'library')
        tray = {'trial': 7, 'tray': [{'state': 'ready', 'trial': 7}]}
        self.assertEqual(on({'previewing': True}, {'trial': None}, tray), 'tray')
        self.assertEqual(on({'previewing': True}, None, {'trial': 7, 'tray': [{'state': 'ready', 'trial': None}]}), 'session')
        self.assertEqual(on({'previewing': False}, {'trial': None}, None), '')
        self.assertEqual(on({'previewing': None}, None, None), '')            # (an older script: nothing known, nothing held)

    def test_the_save_waits_for_the_step_back(self):
        hold = lambda *a: run_js(['workbench_layout.js'], 'workbenchSaveHold(%s)' % ', '.join(json.dumps(x) for x in a))
        held = {'since': 1000, 'until': 11000, 'offAt': 0}
        self.assertEqual(hold(held, 2000, True, 2, None), {'next': 'wait', 'offAt': 0})
        self.assertEqual(hold(held, 11500, True, 2, None)['next'], 'give-up')        # never ended: no Save
        ended = {'from': 1, 'to': 3, 'at': 2500}
        self.assertEqual(hold(held, 3000, False, 2, ended), {'next': 'wait', 'offAt': 3000})   # off, the step back not yet
        self.assertEqual(hold({**held, 'offAt': 3000}, 3200, False, 3, ended)['next'], 'save')
        self.assertEqual(hold({**held, 'offAt': 3000}, 4600, False, 2, ended)['next'], 'save')  # 1.5 s after: saved anyway
        self.assertEqual(hold(held, 3000, False, 2, {**ended, 'at': 500})['next'], 'save')     # an older preview's record
        self.assertEqual(run_js(['workbench_layout.js'], '[WORKBENCH_PREVIEW_END_WAIT_MS, WORKBENCH_PREVIEW_STEP_MS]'), [10000, 1500])

    def piece(self):
        source = page()
        return source[source.index('let saveHeld = null;'):source.index('const SAVE_WAIT_MS = 2000;')]

    def run_page(self, steps):
        # The page's own savePreset / holdSave / saveNow, with the rest of the page stubbed.
        layout = (ROOT / 'workbench_layout.js').read_text(encoding='utf-8')
        stubs = '''
          let now = 1000; const Date = {now: () => now};
          const asked = [], notes = [], toasts = [], timers = [];
          const ask = (name, value) => asked.push([name, value === undefined ? null : value]);
          const stickyNote = words => notes.push(words), toast = words => toasts.push(words), drawBar = () => {};
          const setInterval = () => 0, setTimeout = (f, ms) => timers.push(f);
          let state = {preset: {setlist: 3, number: 32, name: 'x'}, undoAt: 1, previewing: true, previewEnded: null};
          let floorStatus = {trial: 4, text: ''}, toneTray = null, savedMark = {key: '', at: null}, renameAsked = null;
          const presetWord = () => state.preset.setlist + ':' + state.preset.number, pendingHere = () => null;
          const SAVE_WAIT_MS = 2000; let followed = 0;
        '''
        return run_js_source(layout + stubs + self.piece() + steps, '{asked, notes, toasts, savedMark, followed}')

    def test_a_save_ends_the_library_preview_first_then_saves(self):
        result = self.run_page('''
          savePreset(() => followed++);
          const first = asked.length;
          now = 2000; holdSave();                                     // still playing
          floorStatus = {trial: null}; state.previewing = false;
          state.previewEnded = {from: 1, to: 3, at: 2500}; state.undoAt = 2;
          now = 3000; holdSave();                                     // ended, the step back not in the record yet
          state.undoAt = 3; now = 3250; holdSave();                   // now
          holdSave();
        ''')
        self.assertEqual(result['asked'], [['levels', {'do': 'end'}], ['save', None]])
        self.assertEqual(result['followed'], 1)                       # "Save, then load": the load only after the Save
        self.assertEqual(result['savedMark'], {'key': '3:32', 'at': 3})
        self.assertEqual(result['notes'], [])
        self.assertIn('Ending the preview first', result['toasts'][0])

    def test_a_preview_that_does_not_end_means_no_save_and_says_why(self):
        result = self.run_page('''
          floorStatus = {trial: 4, text: 'The previous block rejected restoration. Preview remains in User IR 128.'};
          savePreset(() => followed++);
          now = 12000; holdSave();
        ''')
        self.assertEqual(result['asked'], [['levels', {'do': 'end'}]])
        self.assertEqual(result['followed'], 0)                       # no Save, no load
        self.assertIn('Not saved. The preview could not be ended', result['notes'][0])
        self.assertIn('rejected restoration', result['notes'][0])

    def test_the_tray_preview_is_stopped_the_trays_way(self):
        result = self.run_page('''
          floorStatus = null; toneTray = {trial: 9, text: '', tray: [{state: 'ready', trial: 9}]};
          savePreset();
          toneTray = {trial: 9, tray: [{state: 'ready', trial: null}]}; state.previewing = false; now = 1500; holdSave();
        ''')
        self.assertEqual(result['asked'], [['tray', {'do': 'end', 'trial': 9}], ['save', None]])

    def test_no_preview_saves_at_once_and_an_unknown_one_is_not_saved(self):
        result = self.run_page('''
          floorStatus = null; state.previewing = false; savePreset(() => followed++);
        ''')
        self.assertEqual(result['asked'], [['save', None]])
        self.assertEqual(result['followed'], 1)
        result = self.run_page('''
          floorStatus = null; savePreset(() => followed++);
        ''')
        self.assertEqual(result['asked'], [])
        self.assertEqual(result['followed'], 0)
        self.assertIn('Not saved. A preview is playing from slot 128', result['notes'][0])

    def test_every_save_of_the_page_goes_through_the_gate(self):
        source = page()
        self.assertEqual(source.count("ask('save')"), 1)              # only saveNow asks HX Edit's Save
        self.assertIn("$('save').onclick = savePreset;", source)
        self.assertIn("e.preventDefault(); savePreset(); return; }", source)          # Ctrl+S in the pane
        self.assertIn('save.onclick = savePreset;', source)
        guard = source[source.index('function loadPreset(target) {'):source.index('function openMenu() {')]
        self.assertIn('savePreset(() => {', guard)                    # "Save, then load": the load follows the Save
        self.assertNotIn('savePreset();', guard)
        # (a pending preset rename rides on saveNow: asked after HX Edit's Save)
        self.assertIn("ask('rename', {what: 'preset'", source[source.index('function saveNow() {'):source.index('const SAVE_WAIT_MS = 2000;')])
        script = (ROOT / 'focus_view.js').read_text(encoding='utf-8')
        self.assertIn('state.previewing = toneView.previewing ? toneView.previewing() : null;', script)
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn('previewing: () => !!active && !!(active.transfer || active.pendingTransfer),', tone)




if __name__ == '__main__':
    unittest.main()
