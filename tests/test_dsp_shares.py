"""DSP shares are shown as a share of a DSP, never as the firmware's units (v0.7.3).

A DSP's budget on the Floor's meter is 75 units, and a block's load is its firmware cost / 100 (NAM A2 Lite on builder
firmware 807b4dbb: 3250 -> 32.5). The library side panel said "Original ... 32.5% of a DSP" for a block the picker and
the Floor show as 43%. Every text now shows units / 75 * 100, rounded, as the picker does (floor_firmware.share; PR #16
fixed the same in workbench.firmware_notice): 3250 -> 43%, 3600 -> 48%, the NAM Pedal's 750 -> 10%. No editor."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import floor_firmware  # noqa: E402
import nam_modes  # noqa: E402
import workbench  # noqa: E402
from test_focus_view import run_js_source  # noqa: E402
from test_workbench import NODE  # noqa: E402


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def piece(whole, start, end):
    at = whole.index(start)
    return whole[at:whole.index(end, at + len(start)) + len(end)]


class ShareTests(unittest.TestCase):

    def test_units_of_75_as_the_share_the_picker_shows(self):
        self.assertEqual([floor_firmware.share(u) for u in (32.5, 36.0, 7.5, 32.5 * 29 / 36, 29.0, 75.0)], [43, 48, 10, 35, 39, 100])

    def test_the_firmware_notice_uses_it(self):
        fw = lambda cost, pedal: floor_firmware.FloorFirmware(nam_cost=cost, pedal=pedal, source='remembered')
        self.assertIn('(NAM blocks at 43% of a DSP, NAM Pedal at 10%)', workbench.firmware_notice(fw(3250, True)))
        self.assertIn('(NAM blocks at 48% of a DSP, no NAM Pedal)', workbench.firmware_notice(fw(3600, False)))
        self.assertIn('floor_firmware.share(firmware.nam_load)', text('workbench.py'))

    def test_the_import_dialogs_modes(self):
        details = {key: detail for key, _, _, _, detail in nam_modes.MODES}
        self.assertIn('NAM A2 Lite block, about 48% of a DSP.', details['original'])
        self.assertIn('NAM Pedal block, about 10% of a DSP.', details['pedal'])
        self.assertIn('NAM Lite 16 block, about 39%.', details['16-quick'])
        self.assertIn('NAM Lite 14 block, about 37%.', details['14-standard'])
        self.assertNotIn('36% of a DSP', ' '.join(details.values()))
        self.assertNotIn('7.5% of a DSP', ' '.join(details.values()))


@unittest.skipUnless(NODE, 'node is not installed')
class PageShareTests(unittest.TestCase):

    def workbench_versions(self, nam_load, pedal_load):
        """The Workbench library panel's version lines (libVersions meta) and the "Make a lighter version" texts."""
        page = text('workbench.html')
        source = (piece(page, 'const unitShare = units =>', ';\n') + piece(page, 'const share1 = units =>', ';')
                  + f'\nconst namLoad = {nam_load}, pedalLoad = {pedal_load}, pedalBlock = true, pedalSuits = true;\n'
                  + piece(page, "  const meta = key => key === 'original'", ';\n')
                  + piece(page, "  const pedalSuits = row.gear === 'pedal', full =", ';\n').replace('const pedalSuits = row.gear === \'pedal\', ', 'const ')
                  + 'const option = (key, title, words) => words;\n')
        pedal = re.search(r"option\('pedal', .*?, pedalSuits\)", page).group(0)
        light = re.search(r"option\('light16', .*?, true\)", page).group(0)
        return run_js_source(source, f'[meta("original"), meta("pedal"), meta("light16"), {pedal}, {light}]')

    def test_the_workbench_library_panel_on_3250_and_3600(self):
        original, pedal, light, pedal_text, light_text = self.workbench_versions(32.5, 7.5)
        self.assertEqual((original, pedal, light), ('43% of a DSP', '10% of a DSP', '~35% after a firmware update'))
        self.assertIn('About 30 seconds. 10% of a DSP instead of 43%.', pedal_text)
        self.assertIn('then about 35% of a DSP instead of 43%.', light_text)
        original, pedal, light, pedal_text, light_text = self.workbench_versions(36, 7.5)
        self.assertEqual((original, pedal, light), ('48% of a DSP', '10% of a DSP', '~39% after a firmware update'))
        self.assertIn('10% of a DSP instead of 48%.', pedal_text)
        self.assertIn('then about 39% of a DSP instead of 48%.', light_text)

    def library_card(self, nam_load, pedal_load):
        card = text('library_card.html')
        source = (piece(card, 'let namLoad = 36, pedalLoad = 7.5;', '\n')
                  + piece(card, 'const unitShare = units =>', ';\n') + piece(card, 'const share = units =>', ';\n')
                  + piece(card, 'function versionMeta(key) {', '\n  }\n') + f'namLoad = {nam_load}; pedalLoad = {pedal_load};\n')
        return run_js_source(source, '[versionMeta("original"), versionMeta("pedal"), versionMeta("light16")]')

    def test_the_library_window_on_3250_and_3600(self):
        self.assertEqual(self.library_card(32.5, 7.5), ['43% DSP', '10% DSP', '~35% DSP after a firmware update'])
        self.assertEqual(self.library_card(36, 7.5), ['48% DSP', '10% DSP', '~39% DSP after a firmware update'])
        card = text('library_card.html')
        self.assertIn("then about ' + unitShare(namLoad * 29 / 36) + '% of a DSP instead of ' + full + '.'", card)
        self.assertNotIn('Math.round(namLoad * 29 / 36)', card)
        self.assertNotIn('Math.round(namLoad * 29 / 36)', text('workbench.html'))


if __name__ == '__main__':
    unittest.main()
