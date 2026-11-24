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
        self.assertIn("'snapValue', 'splitType', 'ir', 'rename'):", source)
        self.assertIn("'rename': view.checked_rename}[name]", source)
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


if __name__ == '__main__':
    unittest.main()
