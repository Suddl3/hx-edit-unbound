"""A new user's setup from scratch (install check 2026-11-25): the TONE3000 window's icon without a prepared editor
copy, one launch with everything on, the saved TONE3000 key, the Workbench on a first launch, setup.ps1 / start.ps1."""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'src'
sys.path.insert(0, str(ROOT))

import tone_browser  # noqa: E402
import tone_preview  # noqa: E402
import workbench  # noqa: E402

POWERSHELL = shutil.which('powershell')


class EditorIconTests(unittest.TestCase):
    """I1: TONE3000 did not open on a fresh clone ("The local HX Edit application icon is unavailable")."""

    def test_the_installed_hx_edit_is_used_when_there_is_no_prepared_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'src').mkdir()
            installed = folder / 'Line6' / 'HX Edit'
            installed.mkdir(parents=True)
            exe = installed / 'HX Edit.exe'
            exe.write_bytes(b'MZ the editor')
            right = sha256(exe.read_bytes()).hexdigest()
            with patch.object(tone_browser, 'ROOT', folder / 'src'), \
                    patch.dict(os.environ, {'HX_EDIT_SOURCE_DIRECTORY': str(installed)}), \
                    patch('nam_catalog.EXE_HASH', right):
                self.assertEqual(tone_browser.stock_editor_exe(), exe)
            with patch.object(tone_browser, 'ROOT', folder / 'src'), \
                    patch.dict(os.environ, {'HX_EDIT_SOURCE_DIRECTORY': str(installed)}), \
                    patch('nam_catalog.EXE_HASH', '0' * 64):
                self.assertIsNone(tone_browser.stock_editor_exe())          # not 3.82: not used
            # the default folder under ProgramFiles(x86), as prepare_copy looks
            env = {key: value for key, value in os.environ.items() if key != 'HX_EDIT_SOURCE_DIRECTORY'}
            env['ProgramFiles(x86)'] = str(folder)
            with patch.object(tone_browser, 'ROOT', folder / 'src'), patch.dict(os.environ, env, clear=True), \
                    patch('nam_catalog.EXE_HASH', right):
                self.assertEqual(tone_browser.stock_editor_exe(), exe)
            # a prepared copy still comes first
            prepared = folder / 'src' / 'build' / 'HX Edit'
            prepared.mkdir(parents=True)
            (prepared / 'HX Edit.exe').write_bytes(b'MZ prepared')
            with patch.object(tone_browser, 'ROOT', folder / 'src'):
                self.assertEqual(tone_browser.stock_editor_exe(), prepared / 'HX Edit.exe')

    def test_the_window_build_takes_the_icon_from_that_lookup(self):
        build = tone_browser.prepare_browser.__code__
        self.assertIn('stock_editor_exe', build.co_names)
        source = (ROOT / 'tone_browser.py').read_text(encoding='utf-8')
        self.assertNotIn('Rebuild the prepared editor copy', source)


class LaunchFlagTests(unittest.TestCase):
    """I2: the documented --floor-reference --navigation left out the NAM categories and the 3D gear set."""

    def test_one_flag_turns_everything_on_and_navigation_brings_the_nam_category(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        parse = launcher[launcher.index("    parser.add_argument('--nam-category'"):launcher.index("    if args.navigation and not args.floor_reference:")]
        self.assertIn("parser.add_argument('--unbound', action='store_true',", parse)
        self.assertIn('        args.floor_reference = args.navigation = True', parse)
        self.assertIn("    if args.navigation and not args.no_nam_category:\n        args.nam_category = True", parse)
        self.assertLess(parse.index('args = parser.parse_args()'), parse.index('if args.unbound:'))
        # the old flags still parse (an existing clone's command runs as before, now with the categories on)
        for flag in ("'--floor-reference'", "'--navigation'", "'--nam-category'", "'--tone-window'", "'--hx-nam'"):
            self.assertIn('parser.add_argument(' + flag, launcher)


class SavedKeyTests(unittest.TestCase):
    """I3: the TONE3000 key saved once (setup.ps1), read when T3K_PUBLISHABLE_KEY is not set."""

    def test_the_environment_wins_then_the_file_and_only_a_publishable_key(self):
        with tempfile.TemporaryDirectory() as folder:
            saved = Path(folder) / 'tone3000-publishable-key'
            key = tone_preview.publishable_key
            self.assertEqual(key({}, saved), '')                                    # nothing saved
            saved.write_text('t3k_pub_fromfile\r\n', encoding='utf-8-sig')
            self.assertEqual(key({}, saved), 't3k_pub_fromfile')
            self.assertEqual(key({'T3K_PUBLISHABLE_KEY': ''}, saved), 't3k_pub_fromfile')
            self.assertEqual(key({'T3K_PUBLISHABLE_KEY': ' t3k_pub_env '}, saved), 't3k_pub_env')
            self.assertEqual(key({'T3K_PUBLISHABLE_KEY': 't3k_sec_nope'}, saved), '')   # a Secret Key: never
            saved.write_text('t3k_sec_secret', encoding='utf-8')
            self.assertEqual(key({}, saved), '')
            saved.write_text('t3k_pub_with space', encoding='utf-8')
            self.assertEqual(key({}, saved), '')
        self.assertEqual(tone_preview.KEY_FILE.parts[-2:], ('HX Edit NAM', 'tone3000-publishable-key'))
        source = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        self.assertIn('client_id = (self.client_id or publishable_key()).strip()', source)


class FirstLaunchTests(unittest.TestCase):
    """I4: a first launch opens the Workbench (Nick, 2026-11-25); Classic chosen stays Classic."""

    def test_missing_is_on_false_stays_off(self):
        self.assertTrue(workbench.setting_on({}))
        self.assertTrue(workbench.setting_on(None))
        self.assertFalse(workbench.setting_on({'workbench': False}))
        self.assertTrue(workbench.setting_on({'workbench': True}))
        # the source launch and the trial build's launch (launch_navigation.py -> run_editor) both ask setting_on
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('workbench_start = setting_on(nam_catalog.load_settings())', launcher)


class ScriptTests(unittest.TestCase):
    """I5: setup.ps1 and start.ps1 at the repository's root."""

    def test_setup_checks_and_installs_what_the_docs_name(self):
        setup = (REPO / 'setup.ps1').read_text(encoding='utf-8')
        self.assertTrue(setup.isascii())
        from nam_catalog import EXE_HASH
        self.assertIn(f"$HxEditHash = '{EXE_HASH}'", setup)
        self.assertIn("$ConverterCommit = 'c94834768546393420692794fdbb27c9cc31d718'", setup)
        self.assertIn("$Packages = @('frida==17.5.2', 'msgpack==1.2.4', 'numpy', 'sounddevice==0.5.6', 'soundfile==0.14.0')", setup)
        self.assertIn("[string]$ArtTag = 'gear-art-2026-11-22'", setup)
        self.assertIn("$ArtPacks = @('helix-gear-art', 'nam-gear-art', 'focus-backgrounds')", setup)
        self.assertIn("$KeyFile = Join-Path $SettingsFolder 'tone3000-publishable-key'", setup)
        self.assertIn("return $value -match '^t3k_pub_\\S+$'", setup)
        self.assertIn("$Converter = Join-Path (Split-Path -Parent $Here) 'helix-lt-nam'", setup)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("base / 'helix-lt-nam' / 'tools' / 'nam2ir.py' for base in (ROOT.parent, ROOT.parent.parent)", launcher)
        self.assertIn("PACK = ROOT.parent / 'art'", (ROOT / 'focus_view.py').read_text(encoding='utf-8'))
        self.assertIn('/.venv/', (REPO / '.gitignore').read_text(encoding='utf-8'))

    def test_start_launches_the_full_set_and_refuses_with_hx_edit_open(self):
        start = (REPO / 'start.ps1').read_text(encoding='utf-8')
        self.assertTrue(start.isascii())
        self.assertIn("$Arguments = @(\"`\"$Launcher`\"\", '--unbound')", start)
        self.assertIn("$_.ProcessName -in @('HX Edit', 'HX Edit NAM')", start)
        self.assertIn('HX Edit is open. Close it, then run .\\start.ps1 again.', start)
        self.assertLess(start.index('if ($DryRun)'), start.index('Start-Process'))

    @unittest.skipUnless(POWERSHELL, 'Windows PowerShell is not here')
    def test_start_dry_run_says_the_command_and_starts_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            shutil.copy2(REPO / 'start.ps1', folder / 'start.ps1')
            run = lambda: subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                          str(folder / 'start.ps1'), '-DryRun'], capture_output=True, text=True, timeout=60)
            first = run()
            self.assertEqual(first.returncode, 1)
            self.assertIn('Run .\\setup.ps1 first.', first.stdout)
            (folder / '.venv' / 'Scripts').mkdir(parents=True)
            (folder / '.venv' / 'Scripts' / 'pythonw.exe').write_bytes(b'')
            second = run()
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn('Would start: ', second.stdout)
            self.assertIn('start-hx-edit-nam.pyw" --unbound', second.stdout)


if __name__ == '__main__':
    unittest.main()
