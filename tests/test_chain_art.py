"""HX Unbound menu, Options: "3D pictures in the signal chain" (nam_catalog.patch_chain_art, tone_view chainPicture)."""
import struct
import tempfile
import unittest
from pathlib import Path

import nam_catalog
from dsp_meter import DspMeter
from nam_catalog import CHAIN_CAPTURES, CHAIN_MODELS, MODEL_ART, ROOT, chain_art_files, patch_chain_art


def png_size(path):
    data = Path(path).read_bytes()[:24]
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', data[16:24])


class ChainPictureTests(unittest.TestCase):
    def test_every_render_and_capture_picture_has_a_chain_picture_at_the_icon_size(self):
        renders = sorted(path.name for path in MODEL_ART.glob('*.png'))
        self.assertEqual(sorted(path.name for path in CHAIN_MODELS.glob('*.png')), renders)
        captures = sorted(path.name for path in nam_catalog.CAPTURE_ICONS.glob('*.png'))
        self.assertEqual(sorted(path.name for path in CHAIN_CAPTURES.glob('*.png')), captures)
        for on, off, _ in nam_catalog.CHAIN_LARGE_SETS:      # the large set: the same pictures, larger
            self.assertEqual(sorted(path.name for path in on.glob('*.png')),
                             sorted(path.name for path in nam_catalog.CHAIN_SETS[nam_catalog.CHAIN_LARGE_SETS.index((on, off, _))][0].glob('*.png')))
            self.assertEqual(sorted(path.name for path in off.glob('*.png')), sorted(path.name for path in on.glob('*.png')))
            for path in [*on.glob('*.png'), *off.glob('*.png')]:
                self.assertEqual(png_size(path), (85, 70), path.name)
        for on, off, _ in nam_catalog.CHAIN_SETS:            # every picture also with the bypassed ring
            self.assertEqual(sorted(path.name for path in off.glob('*.png')), sorted(path.name for path in on.glob('*.png')))
            for path in [*on.glob('*.png'), *off.glob('*.png')]:
                self.assertEqual(png_size(path), (38, 38), path.name)

    def test_the_build_adds_them_beside_the_pictures_they_stand_for(self):
        with tempfile.TemporaryDirectory() as folder:
            models = Path(folder, 'icons_models')
            models.mkdir()
            stock = sorted(CHAIN_MODELS.glob('*.png'))[0].name
            (models / stock).write_bytes(b'stock')
            added = patch_chain_art(Path(folder))
            captures = len(list(CHAIN_CAPTURES.glob('*.png')))
            self.assertEqual(added, 5 * (1 + captures))            # only stock pictures this copy has; on/off, two sizes, and the large one without its glow
            self.assertTrue((models / f'CHAINP_{stock}').is_file())
            self.assertFalse((models / f'CHAINP_OFF_{stock}').is_file())   # a bypassed block's picture has no glow either way
            self.assertTrue((models / f'CHAIN_{stock}').is_file())
            self.assertTrue((models / f'CHAIN_OFF_{stock}').is_file())
            self.assertTrue((models / f'CHAINL_{stock}').is_file())
            self.assertTrue((models / f'CHAINL_OFF_{stock}').is_file())
            files = chain_art_files(folder)
            self.assertIn(f'CHAIN_{stock}', files)
            self.assertEqual(sum(name.startswith('CHAIN_NAMCAP_') for name in files), captures)
            self.assertEqual(sum(name.startswith('CHAIN_OFF_NAMCAP_') for name in files), captures)
            self.assertEqual(chain_art_files(Path(folder, 'missing')), [])


class ChainOptionTests(unittest.TestCase):
    def test_the_menu_option_and_the_hook_are_wired(self):
        self.assertIn('chainArt', DspMeter.CHOICES)
        self.assertIn('chainLarge', DspMeter.CHOICES)
        self.assertIn('chainNames', DspMeter.CHOICES)
        self.assertIn('chainGlow', DspMeter.CHOICES)
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        # "Glow behind them" off: the large picture without the glow, where this copy has it; never for a bypassed block
        self.assertIn("return !chainGlow && !name.startsWith('OFF_') && chainFiles.has('CHAINP_' + name) ? 'CHAINP_' + name : 'CHAINL_' + name;", tone)
        self.assertIn("else if (name === 'chainGlow') chainGlow = on === true;", tone)
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("elif name in ('chainLarge', 'chainNames', 'chainGlow'):", launcher)
        # as a first launch has them: 3D pictures on, large, with block names, no glow; a choice made in the menu is kept
        # (Reveal B12: HX Edit's own icons in Classic's chain unless "3D gear" was chosen)
        for piece in ("chainArt=nam_catalog.load_settings().get('chainModelArt') is True,", "chainLarge=nam_catalog.load_settings().get('chainLarge') is not False,",
                      "chainNames=nam_catalog.load_settings().get('chainNames') is not False,", "chainGlow=nam_catalog.load_settings().get('chainGlow') is True)",
                      "nam_catalog.save_setting(name, on)"):
            self.assertIn(piece, launcher)
        self.assertIn('chainGlow = profile.chainGlow === true;', tone)
        self.assertIn('bool dots = true, art, large = true, names = true, glow;', (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8'))
        # the block list and grid show the renders with the option: put into the launch's copy of HX Edit's own pictures
        prepare = launcher[launcher.index('        if args.nam_category:\n'):launcher.rindex('run_editor(exe, workspace, device')]
        self.assertIn('from nam_catalog import choose_model_art, load_settings, patch_model_art, patch_nam_category', prepare)
        self.assertIn("patch_model_art(exe.parent / 'res')", prepare)
        self.assertIn("choose_model_art(exe.parent / 'res', load_settings().get('chainModelArt') is True)", prepare)
        import make_chain_pictures
        self.assertEqual(make_chain_pictures.GLOW_GAIN, 0.8)                         # a fifth softer than the first one
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        for marker in ("onEnter() { if (chainArt || chainColours.size || chainSized.size) chainLook(this.context.ecx); else rememberChainItem(this.context.ecx); }",
                       "function chainSet(file)", 'buttonSites.some(site => site.equals(this.site))',
                       'let chainArt = profile.chainArt === true;', "`CHAIN_NAMCAP_${capture.icon}.png`", "'CHAIN_' + picture",
                       'chainRedraw(entry.item);', 'setChainArt: on =>', 'const LARGE_BOX = {w: 68, h: 56}', 'const LABEL_DROP = 2;', 'shrinkBlock(item, own);', 'base.add(0x924324).add(0x38).readPointer()', 'Interceptor.replace(base.add(0x40a780)', 'selectedFrame(item, graphics);', 'settleChainLater();', 'dropRefused = true;',
                       'chainSized.set(key, widgetSize(icon));', 'resizePicture(icon, own.w, own.h);', "object.add(0x1c).readU8() !== 0",
                       "file.replace(/^CHAIN_/, 'CHAIN_OFF_')", 'const LABEL_OFF = 0.55;'):
            self.assertIn(marker, tone)
        self.assertIn("recv('chainArt'", (ROOT / 'nam_sidebar.js').read_text(encoding='utf-8'))
        helper = (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8')
        # the options menu: what depends on another option sits under it and is dimmed while that one is off
        for piece in ('chainArt.Text=Tick(0,art,"3D pictures of the gear");', 'chainLarge.Text=Tick(1,large,"Large pictures"); chainLarge.Enabled=art;',
                      'chainNames.Text=Tick(2,names,"Block names under them"); chainNames.Enabled=art&&large;', 'irDots.Text=Tick(0,dots,"Mark NAM slots");',
                      'chainGlow.Text=Tick(2,glow,"Glow behind them"); chainGlow.Enabled=art&&large;'):
            self.assertIn(piece, helper)
        self.assertIn("recv('chainOption'", (ROOT / 'nam_sidebar.js').read_text(encoding='utf-8'))
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("load_settings().get('chainModelArt') is True", launcher)   # (Reveal B12: off unless chosen)
        self.assertIn("save_setting('chainModelArt', on)", launcher)


if __name__ == '__main__':
    unittest.main()
