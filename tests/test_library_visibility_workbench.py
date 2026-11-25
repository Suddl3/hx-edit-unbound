"""The Workbench's Library and the slot check (live check 2026-11-25 00:53, owner-trials/20261125-004555-9e8dd925): Put
on the Floor still stayed at "Going to slot 29..." while the Library was open, after a063e9e. The Workbench's session
is headless (the Workbench draws its pages), and the session told HX Edit's script whether the library is shown
(toneLibraryVisibility -> nam_view setLibraryBrowsing) only for a session with a window. So "the Library is shown"
was never true in the Workbench, and neither setWorkflowBusy(false) nor resumeLibraryCheck could lift the pause.
Now the Workbench's session says it for its Library page, and not for Levels or the TONE3000 page. No HX Edit."""
from pathlib import Path
import unittest
from unittest.mock import patch

import test_preview_cleanup_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[1] / 'src'


class WorkbenchLibraryVisibilityTests(unittest.TestCase):

    def run_session(self, actions, *, workbench=True, initial_level=False):
        preview, browser, events = lifecycle.PreviewCleanupLifecycleTests.make_preview(self, actions)
        preview.headless = workbench
        preview.workbench = workbench
        preview.level = True
        preview.initial_level = preview.initial_library = initial_level
        posted = []
        before = preview.script.post.side_effect
        def post(message):
            if message['type'] == 'toneLibraryVisibility':
                posted.append(message['payload']['visible'])
            return before(message)
        preview.script.post.side_effect = post
        with patch('tone_preview.WorkbenchSession', return_value=browser), patch('nam_level_flow.LevelFlow') as flow:
            flow.return_value.view.return_value = {'message': 'Levels'}
            lifecycle.PreviewCleanupLifecycleTests.run_offline(self, preview)
        return posted

    def test_the_workbench_session_says_when_its_library_is_shown(self):
        posted = self.run_session(['library', 'levelOpen', 'library', 'finish'])
        self.assertTrue(posted, 'the Workbench session never said whether the library is shown')
        # library shown; Levels: not; the library again: shown (the session's end clears it in tone_view)
        changes = [v for i, v in enumerate(posted) if i == 0 or posted[i - 1] != v]
        self.assertEqual(changes, [True, False, True])
        posted = self.run_session(['finish'], initial_level=True)
        self.assertEqual(posted, [False])                              # opened on Levels: never shown

    def test_the_old_window_is_as_before(self):
        posted = self.run_session(['library', 'finish'], workbench=False)
        self.assertEqual(set(posted), {True})

    def test_the_slot_check_traces_where_its_pause_is_decided(self):
        view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        self.assertIn("slotCheckTrace('slot-changed', resumed);", view)
        self.assertIn("slotCheckTrace('workflow-ended', resumed);", view)
        self.assertIn("slotCheckTrace('library-' + (value ? 'shown' : 'hidden'), null);", view)
        self.assertIn("send({type: 'toneTrace', reason: 'slot-check', stage: resumed === true ? 'resumed' : resumed === false ? 'held' : why,", view)
        preview = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        self.assertIn('if self.navigation and (not self.headless or self.workbench):', preview)
        self.assertIn('shown = bool(library) and not (self.workbench and (level_page or look_page))', preview)

