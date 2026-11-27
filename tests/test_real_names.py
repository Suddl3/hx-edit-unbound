"""The "Real gear names" choice: off unless chosen, the player's own custom-names.csv wins, the catalog copy is renamed,
and both menus offer it. No HX Edit, no device."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import msgpack

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
import nam_catalog  # noqa: E402
import workbench  # noqa: E402
from dsp_meter import DspMeter  # noqa: E402


class RealNamesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        patches = [patch.object(nam_catalog, 'SETTINGS', self.folder / 'settings.json'),
                   patch.dict('os.environ', {'HX_EDIT_NAM_NAMES': ''})]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_off_until_chosen(self):
        self.assertFalse(nam_catalog.real_names_on())
        self.assertEqual(nam_catalog.model_names(self.folder / 'custom-names.csv'), {})

    def test_the_bundled_list_when_chosen(self):
        nam_catalog.save_setting(nam_catalog.REAL_NAMES_KEY, True)
        names = nam_catalog.model_names(self.folder / 'custom-names.csv')
        self.assertEqual(names['HD2_AmpA30FawnBrt\0'], 'Vox AC30 Fawn B\0')
        self.assertNotIn(nam_catalog.NAM_SYMBOL + '\0', names)

    def test_every_bundled_row_names_a_model_once(self):
        with nam_catalog.REAL_NAMES.open(newline='', encoding='utf-8-sig') as rows:
            found = list(csv.DictReader(rows))
        self.assertGreater(len(found), 400)
        self.assertTrue(all(row['internal'].strip() and row['real_name'].strip() for row in found))
        self.assertEqual(len({row['internal'] for row in found}), len(found))

    def test_the_players_own_file_wins(self):
        own = self.folder / 'custom-names.csv'
        own.write_text('internal,real_name\nHD2_AmpA30FawnBrt,My Vox\n', encoding='utf-8')
        self.assertEqual(nam_catalog.model_names(own), {'HD2_AmpA30FawnBrt\0': 'My Vox\0'})
        nam_catalog.save_setting(nam_catalog.REAL_NAMES_KEY, True)
        names = nam_catalog.model_names(own)
        self.assertEqual(names['HD2_AmpA30FawnBrt\0'], 'My Vox\0')
        self.assertGreater(len(names), 400)

    def test_the_catalog_copy_is_renamed(self):
        model = {'symbolicID\0': 'HD2_AmpA30FawnBrt\0', 'name\0': 'A30 Fawn Brt\0'}
        listed = {'id\0': 'HD2_AmpA30FawnBrt\0', 'name\0': 'A30 Fawn Brt\0'}
        (self.folder / 'HelixModelDefs.bin').write_bytes(msgpack.packb([model]))
        (self.folder / 'HX_ModelCatalog.bin').write_bytes(
            msgpack.packb({'categories\0': [{'subcategories\0': [{'models\0': [listed]}]}]}))
        nam_catalog.save_setting(nam_catalog.REAL_NAMES_KEY, True)
        nam_catalog.rename_stock_models(self.folder, nam_catalog.model_names(self.folder / 'custom-names.csv'))
        defs = msgpack.unpackb((self.folder / 'HelixModelDefs.bin').read_bytes())
        tree = msgpack.unpackb((self.folder / 'HX_ModelCatalog.bin').read_bytes())
        self.assertEqual(defs[0]['name\0'], 'Vox AC30 Fawn B\0')
        self.assertEqual(tree['categories\0'][0]['subcategories\0'][0]['models\0'][0]['name\0'], 'Vox AC30 Fawn B\0')

    def test_both_menus_offer_it(self):
        self.assertIn('realNames', DspMeter.CHOICES)
        self.assertEqual(workbench.WorkbenchView.checked_menu('realNames'), 'realNames')
        self.assertIn('realNames=Item(tools,"","realNames");', (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8'))
        self.assertIn("ask('menu', 'realNames')", (ROOT / 'workbench.html').read_text(encoding='utf-8'))
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn('nam_catalog.save_setting(nam_catalog.REAL_NAMES_KEY, on)', launcher)
        self.assertIn("elif choice == 'realNames':", launcher)

    def test_packaged_builds_carry_the_list(self):
        for build in ('build-windows.py', 'build-macos.py'):
            self.assertIn("'real_names.csv'", (ROOT / build).read_text(encoding='utf-8'), build)


if __name__ == '__main__':
    unittest.main()
