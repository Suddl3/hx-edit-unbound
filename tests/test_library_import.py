"""Import NAM files into the library on this PC (library window: Import, or files and folders dropped on it).
No device, no editor: the library's own side, the status line, and the page's wiring."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))

from nam_library import Library, check_nam  # noqa: E402


def nam(name='Plexi', gear='amp', weights=(0.1, 0.2)):
    return json.dumps({'version': '0.5.4', 'architecture': 'WaveNet', 'config': {}, 'weights': list(weights),
                       'metadata': {'name': name, 'gear_type': gear}}).encode('utf-8')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.library = Library(Path(self.folder.name, 'library'))
        self.told = []
        self.library.subscribe(lambda: self.told.append(1))

    def test_a_file_is_kept_as_it_is_with_its_name_and_gear(self):
        data = nam(gear='pedal')
        identity, new = self.library.add_data(data, 'TS9 Drive 6.nam', source='file')
        self.assertTrue(new)
        entry = self.library.entries()[identity]
        self.assertEqual((entry['name'], entry['gear'], entry['source']), ('TS9 Drive 6', 'pedal', 'file'))
        self.assertEqual(Path(self.library.folder, identity + '.nam').read_bytes(), data)    # not converted

    def exported(self, *files):
        """The slot names HX Edit would be given for captures imported from these file names, in order."""
        kept = [self.library.add_data(nam(weights=(0.1, i)), file, source='file')[0] for i, file in enumerate(files)]
        out = Path(self.folder.name, 'out')
        return [self.library.export(identity, out).stem for identity in kept]

    def test_a_short_name_is_used_as_it_is(self):
        self.assertEqual(self.exported('TS9 Drive 6.nam', 'TS9 Drive 7.nam'), ['TS9 Drive 6', 'TS9 Drive 7'])

    def test_names_cut_alike_keep_their_endings(self):
        names = self.exported(*(f'Fuzz Factory V-4 G-6 C-10 D-5 S-{n}.nam' for n in (0, 3, 5, 7, 10)))
        self.assertEqual(len(set(names)), 5)
        self.assertTrue(all(len(name) <= 31 for name in names), names)
        self.assertEqual([name.rsplit('S-', 1)[1] for name in names], ['0', '3', '5', '7', '10'])
        names = self.exported('Fender Super Reverb_ EQ Flat, Volume 3, AKG 414.nam',
                              'Fender Super Reverb_ EQ Flat, Volume 3, sm57 and AKG 414.nam',
                              'Fender Super Reverb_ EQ Flat, Volume 3, sm57.nam')
        self.assertEqual(len(set(names)), 3, names)

    def test_a_name_alone_in_its_cut_is_still_cut_at_the_end(self):
        self.assertEqual(self.exported('Marshall 1959BJA SUPER BOWL SETTINGS.nam'), ['Marshall 1959BJA SUPER BOWL SET'])

    def test_the_very_same_name_gets_a_number_and_the_catalog_is_not_changed(self):
        long = 'A very long capture name that is the same all the way through'
        names = self.exported('a/Plexi.nam', 'b/plexi.nam', f'a/{long}.nam', f'b/{long}.nam')
        self.assertEqual(names[:2], ['Plexi', 'plexi 2'] if names[0] == 'Plexi' else ['Plexi 2', 'plexi'])
        self.assertEqual(len({name.casefold() for name in names}), 4, names)
        self.assertTrue(all(len(name) <= 31 for name in names), names)
        self.assertEqual(sorted({entry['irName'] for entry in self.library.entries().values()}),
                         sorted({'Plexi', 'plexi', long[:31].rstrip()}))

    def test_a_lighter_copy_keeps_the_ending_too(self):
        from nam_modes import light_name
        names = {light_name(Path(f'Fuzz Factory V-4~10 D-5 S-{n}.nam'), 0) for n in (0, 3)}
        self.assertEqual(len(names), 2, names)
        self.assertTrue(all(len(Path(name).stem) <= 31 for name in names), names)

    def test_the_same_capture_twice_stays_one_entry(self):
        first = self.library.add_data(nam(), 'a/Plexi.nam', source='file')
        second = self.library.add_data(nam(), 'b/Plexi copy.nam', source='file')
        self.assertEqual((first[0], first[1], second[1]), (second[0], True, False))
        self.assertEqual(len(self.library.entries()), 1)
        self.assertEqual(self.library.entries()[first[0]]['name'], 'Plexi')                   # its first name stays

    def test_an_import_does_not_hide_where_a_capture_came_from_first(self):
        identity = self.library.add_data(nam(), 'Plexi.nam', source='tone3000')[0]
        self.library.add_data(nam(), 'Plexi.nam', source='file')
        self.assertEqual(self.library.entries()[identity]['source'], 'tone3000')

    def test_many_files_tell_the_library_once(self):
        for k in range(5):
            self.library.add_data(nam(weights=(k,)), f'{k}.nam', source='file', notify=False)
        self.assertEqual(self.told, [])
        self.library.changed()
        self.assertEqual(self.told, [1])
        self.library.add_data(nam(weights=(9,)), '9.nam')                                        # one file: at once
        self.assertEqual(self.told, [1, 1])

    def test_add_still_takes_a_path(self):
        path = Path(self.folder.name, 'Deluxe.nam')
        path.write_bytes(nam(gear='amp_cab'))
        identity = self.library.add(path, source='file')
        self.assertEqual(self.library.entries()[identity]['gear'], 'amp-cab')

    def test_only_nam_model_files_are_accepted(self):
        check_nam(nam())
        check_nam(b'\xef\xbb\xbf' + nam())                                                     # with a byte order mark
        for bad in (b'', b'not json', b'[]', b'{"architecture": "WaveNet"}', b'{"weights": []}', b'\xff\xfe\x00'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_nam(bad)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        import tone_preview
        self.summary = tone_preview.import_summary

    def test_the_status_line_says_what_happened(self):
        self.assertEqual(self.summary({'added': 136, 'same': 0, 'bad': []}),
                         'Added 136 captures to your NAM library on this PC. Nothing was put on the Floor.')
        self.assertEqual(self.summary({'added': 1, 'same': 2, 'bad': []}),
                         'Added 1 capture to your NAM library on this PC. Nothing was put on the Floor. 2 were already in the library.')
        self.assertEqual(self.summary({'added': 0, 'same': 1, 'bad': ['a.nam', 'b.nam', 'c.nam', 'd.nam']}),
                         '1 was already in the library. 4 files could not be added (not a NAM capture): a.nam, b.nam, c.nam and 1 more.')
        self.assertEqual(self.summary({'added': 0, 'same': 0, 'bad': []}), 'No NAM files were found to import.')
        self.assertEqual(self.summary({'added': 2000, 'same': 0, 'bad': [], 'more': True}),
                         'Added 2000 captures to your NAM library on this PC. Nothing was put on the Floor. That folder has more '
                         '.nam files than one import takes: the rest were not looked at. Import its subfolders one at a time for those.')


class PageTests(unittest.TestCase):
    def test_the_page_and_the_preview_carry_the_import(self):
        page = (ROOT / 'library_card.html').read_text(encoding='utf-8')
        for needle in ('id="import"', 'id="importFiles" type="file" accept=".nam" multiple',
                       'id="importFolder" type="file" webkitdirectory', 'id="dropZone"',
                       "host?.postMessage('importNam:' + encodeURIComponent(file.name) + ':' + data)",
                       "host?.postMessage('importDone')", 'webkitGetAsEntry', "includes('Files')",
                       'Import your .nam files'):
            self.assertIn(needle, page)
        source = (ROOT / 'tone_preview.py').read_text(encoding='utf-8')
        for needle in ("command == 'importNam'", "check_nam(data)", "source='file', notify=False",
                       "command == 'importDone'", 'self.library.changed()'):
            self.assertIn(needle, source)
        self.assertIn('choose Import to add your .nam files', (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8'))

    def test_the_library_page_still_renders(self):
        # library_card.html is a string.Template: a stray "$" in its script stops the whole window from rendering.
        from nam_library import render_library
        page = render_library({}, None, None)
        self.assertIn('id="import"', page)
        self.assertIn(r'/\.nam$/i.test(file.name)', page)


if __name__ == '__main__':
    unittest.main()
