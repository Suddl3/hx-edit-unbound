"""HX_EDIT_COPY_DIR: test launches prepare HX Edit's copy in one fixed folder (emptied first), so its path stays the
same from launch to launch; unset, each launch gets a new temporary folder under build/."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_startup_problems import launcher_module


class FixedCopyDir(unittest.TestCase):
    def test_fixed_folder_is_emptied_and_reused(self):
        launcher = launcher_module()
        with tempfile.TemporaryDirectory() as base:
            fixed = Path(base) / 'copy'
            (fixed / 'old').mkdir(parents=True)
            (fixed / 'old' / 'stale.txt').write_text('x')
            with mock.patch.dict(os.environ, {'HX_EDIT_COPY_DIR': str(fixed)}):
                with launcher.prepared_workspace() as first:
                    self.assertEqual(Path(first), fixed.resolve())
                    self.assertEqual(list(fixed.iterdir()), [])
                    (Path(first) / 'HX Edit NAM').mkdir()
                with launcher.prepared_workspace() as second:
                    self.assertEqual(second, first)
                    self.assertEqual(list(fixed.iterdir()), [])

    def test_unset_gives_a_new_temporary_folder(self):
        launcher = launcher_module()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('HX_EDIT_COPY_DIR', None)
            with launcher.prepared_workspace() as one, launcher.prepared_workspace() as two:
                self.assertNotEqual(one, two)
                self.assertTrue(Path(one).name.startswith('nam-'))


if __name__ == '__main__':
    unittest.main()
