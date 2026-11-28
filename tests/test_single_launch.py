"""Only one HX Edit Unbound launcher at a time: a second quick start of the shortcut shows the running editor instead
of starting another launch into the same HX Edit (2026-11-27: two launches shared one HX Edit and stalled its Floor
slot check)."""
import os
import unittest
import uuid

from test_startup_problems import launcher_module


@unittest.skipUnless(os.name == 'nt', 'Windows named mutex')
class SingleLaunch(unittest.TestCase):
    def test_a_second_claim_of_the_same_launch_is_refused(self):
        launcher = launcher_module()
        name = 'Local\\HXEditUnboundLauncherTest-' + uuid.uuid4().hex
        self.assertTrue(launcher.claim_launch(name))
        self.assertFalse(launcher.claim_launch(name))

    def test_main_stops_before_starting_anything_when_refused(self):
        launcher = launcher_module()
        shown = []
        launcher.claim_launch = lambda name=None: False
        launcher.show_running_editor = lambda: shown.append(True)
        self.assertIsNone(launcher.main())
        self.assertEqual(shown, [True])


if __name__ == '__main__':
    unittest.main()
