"""Before the reveal (Nick's review of the merged build, 2026-11-25; BACKLOG.md "Before the reveal", list A).

Each test names its item. No editor, no device: the page's and the scripts' own text, and their pure parts in node."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import NODE, run_js  # noqa: E402


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def between(whole, start, end):
    at = whole.index(start)
    return whole[at:whole.index(end, at + len(start))]


class ToneStripTests(unittest.TestCase):
    def test_a1_the_strip_under_the_title_has_no_logo_of_its_own(self):
        # (three logos on a diagonal: the window's icon, the layout chooser's logo and the strip's old X logo)
        browser = text('tone_browser.cs')
        bar = between(browser, '// The banner over the site', 'Controls.Add(targetBar);')
        self.assertNotIn('PictureBox', bar)
        self.assertNotIn('Icon.ToBitmap()', browser)
        self.assertIn('targetBar.Controls.Add(targetLabel);', bar)
        # popped out, the window itself still says what it is: its title and HX Edit Unbound's icon
        self.assertIn('floatingHost = new Form { Text = Text, Icon = Icon,', browser)
        self.assertIn('Text = "TONE3000 · HX Edit Unbound";', browser)


class PopOutTests(unittest.TestCase):
    """A2: Pop out puts TONE3000 in its own window and the Workbench goes back to the chain; previews play on from
    the window; the rail's TONE3000 button brings it back in with the tray; closing it ends its preview as before."""

    def test_the_window_says_when_it_pops_out_or_docks(self):
        import io
        from threading import Event
        from types import SimpleNamespace
        from tone_browser import ToneBrowser
        browser = ToneBrowser.__new__(ToneBrowser)
        browser.window_mode = 'embedded'
        browser.detached = Event()
        browser.process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(
            '{"type":"presentation","mode":"floating"}\n{"type":"presentation","mode":"floating"}\n'
            '{"type":"presentation","mode":"embedded"}\n'))
        browser._initialize_io()
        seen = []
        browser.on_presentation = seen.append
        browser.read_events()
        self.assertEqual(seen, ['floating', 'embedded'])          # (once per change)
        self.assertTrue(browser.actions.empty())                  # (not a preview action: the preview plays on)

    def test_the_session_tells_the_workbench_only_for_a_window_it_placed(self):
        from tone_preview import TonePreview
        preview = TonePreview.__new__(TonePreview)
        preview.bounds_override, preview.on_presentation, preview.workbench = None, None, False
        told = []
        preview.on_presentation = told.append
        preview._presentation('floating')
        self.assertEqual(told, [])                                # (HX Edit's own TONE3000 window: nothing to tell)
        preview.bounds_override = {'visible': True, 'x': 0, 'y': 0, 'w': 800, 'h': 600}
        preview._presentation('floating')
        self.assertEqual(told, ['floating'])

    def test_dock_asks_the_window_back_in_only_while_it_is_out(self):
        from tone_preview import TonePreview
        sent = []
        class Browser:
            window_mode = 'floating'
            def send(self, kind, **data):
                sent.append((kind, data)); return True
        preview = TonePreview.__new__(TonePreview)
        preview.workbench, preview.bounds_override, preview.browser = False, {'x': 0}, Browser()
        self.assertTrue(preview.dock_tool())
        self.assertEqual(sent, [('presentation', {'mode': 'embedded', 'focus': True})])
        preview.browser.window_mode = 'embedded'
        self.assertFalse(preview.dock_tool())
        preview.browser.window_mode, preview.bounds_override = 'floating', None
        self.assertFalse(preview.dock_tool())

    def test_the_launcher_and_the_page(self):
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("preview.on_presentation = workbench_tool_presentation if value['name'] == 'tone' else None", launcher)
        self.assertIn("workbench.show_session('presentation', {'mode': mode})", launcher)
        self.assertIn("workbench.set_raise(mode == 'floating')", launcher)
        self.assertIn("if name == 'toolDock':", launcher)
        preview = text('tone_preview.py')
        self.assertIn('browser.on_presentation = self._presentation', preview)
        page = text('workbench.html')
        sync = between(page, 'function syncTool() {', 'function toolClosed() {')
        # out: its frame closing does not close it; the view goes back to the chain
        self.assertIn("if (toolShown && !toolPopped) { toolShown = ''; ask('toolClose'); }", sync)
        self.assertIn("if (out && view.full === toolShown) setView('back');", sync)
        self.assertIn("else if (!out && view.full !== toolShown) setView('open', toolShown);", sync)
        # the rail's TONE3000 button while it is out: back in (its view, with the tray)
        self.assertIn("ask('toolDock', rect);", sync)
        self.assertIn("message.kind === 'presentation') { toolPresentation(message.data && message.data.mode); return; }", page)
        self.assertIn("if (name === 'tone' && toolPopped) { b.classList.add('out');", page)
        # closed (its own Close): the preview ends as before, and nothing stays marked
        closed = between(page, 'function toolClosed() {', 'function drawRail() {')
        self.assertIn("toolShown = ''; toolPopped = false;", closed)


class FloorSlotsIrTests(unittest.TestCase):
    def test_a3_a_plain_irs_row_and_panel_show_the_ir_blocks_own_picture(self):
        # (was a flat pink tile saying "IR"; the chain draws an IR block with its model's pictures: HX Edit's
        # res/icons_models FX_HX_IR_1024.png, the 3D gear art, small; the art pack's ir_1024.png large)
        page = text('workbench.html')
        self.assertIn("const irPictures = () => ((catalog && catalog.models.HD2_ImpulseResponse1024) || {pictures: []}).pictures;", page)
        self.assertIn("const pic = row.kind === 'ir' ? image(irPictures(), '', true, true) :", page)
        self.assertIn("hero.append(image(sel.kind === 'ir' ? irPictures() : captureUrls(sel), '', false, false));", page)
        self.assertNotIn("'irpic'", page)
        self.assertNotIn('.irpic', page)


class NewBlockTests(unittest.TestCase):
    def test_a4_a_click_on_a_block_ends_the_add_in_every_layout(self):
        page = text('workbench.html')
        pick = between(page, 'function pickBlock(block', '\n}')
        # (a "+" open: a click on any block ends it as Cancel would, then picks that block)
        self.assertIn("if (picking && picking.empty) { picking = false; shownPanel = '';", pick)
        self.assertLess(pick.index('picking = false'), pick.index("ask('select'"))
        # every way to click a block goes through pickBlock: a tile, an input or an output, the split, the mixer, a
        # small tile of a full view's header (the stage and Classic+ draw their chain with the same drawPath)
        self.assertEqual(page.count("ask('select',"), 1)
        for line in ("button.onclick = () => { if (!dragDone) pickBlock(block); };", "button.onclick = () => pickBlock(block);",
                     "pickBlock({dsp: p.dsp, id: 'split'})", "pickBlock({dsp: p.dsp, id: 'join'})", "setView('goto'); pickBlock(block);"):
            self.assertIn(line, page)
        # another "+" moves the add there
        self.assertIn('plus.onclick = () => openPlacePicker(p.dsp, lane, place);', page)
        self.assertIn('picking = {empty: true, dsp, lane, place};', page)

    def test_a5_after_a_choice_the_place_stays_until_the_new_block_is_picked(self):
        page = text('workbench.html')
        pick = between(page, 'function pickModel(block, symbol) {', '// After a model or a capture is clicked')
        # (no closePicker before the add: that showed the block picked before until HX Edit's reading picked the new one)
        self.assertNotIn('closePicker()', pick)
        self.assertEqual(pick.count('startAdding('), 2)
        self.assertIn("if (picking && picking.empty && picking.adding) { editFor = ''; drawAdding(placeTarget()); return; }   // (every layout)", page)
        self.assertLess(page.index("drawAdding(placeTarget()); return; }   // (every layout)"), page.index("if (layout === 'classicplus') { drawEdit(block); return; }"))
        # the new block picked by the add's own wait: the card stays until HX Edit shows it picked (or 2 s)
        self.assertIn('if (next.select) pickBlock(next.select, true);', page)
        self.assertIn("if (picking && picking.empty && added && picking.adding) picking.adding.picked = {dsp: block.dsp, id: block.id, until: Date.now() + 2000};", page)
        # a block appearing at the place does not end it (the wait does); a refusal, an undo or the time ends it
        self.assertIn('if (picking && picking.empty && !picking.adding && state.blocks.some(', page)
        settle = between(page, 'function settleAdding() {', '\n}')
        self.assertIn('if (a.picked ? !(same(on, a.picked) || now > a.picked.until) : !!addFollow && now <= a.until) return false;', settle)
        self.assertIn('settleAdding();', between(page, 'function render() {', '\n}'))
        self.assertIn("addFollow = null; swapAsked = null; toast(message.text);", page)               # (a refusal)
        self.assertIn("if (name === 'undo' || name === 'redo') addFollow = null;", page)              # (an undo)
        # the chain lights the coming tile, not the block picked before
        self.assertIn("const now = picking && picking.adding ? state.blocks.find(", page)
        # another "+" meanwhile: the earlier add is not picked over it
        self.assertIn('if (picking && picking.adding) addFollow = null;', page)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a5_the_wait_still_picks_nothing_after_a_refusal_or_another_pick(self):
        follow = {'dsp': 0, 'lane': 0, 'place': 7, 'symbol': 'HD2_DistKinkyBoost', 'was': {'dsp': 0, 'id': 'block4'}, 'preset': '0:6', 'until': 9000}
        base = {'preset': {'setlist': 0, 'number': 6}, 'selected': {'dsp': 0, 'id': 'block4'}, 'blocks': []}
        added = dict(base, blocks=[{'dsp': 0, 'id': 'block9', 'model': 'HD2_DistKinkyBoost', 'position': 7, 'path': 0}])
        run = lambda st, now: run_js(['workbench_layout.js'], 'workbenchAddSelect(%s, %s, "HD2_AmpNAMLite", %d)' % (json.dumps(follow), json.dumps(st), now))
        self.assertEqual(run(base, 1000), {'select': None, 'done': False})                       # not there yet: wait
        self.assertEqual(run(added, 1000), {'select': {'dsp': 0, 'id': 'block9'}, 'done': True})  # there: picked
        self.assertEqual(run(base, 9500), {'select': None, 'done': True})                        # timed out
        self.assertEqual(run(dict(added, selected={'dsp': 1, 'id': 'block0'}), 1000), {'select': None, 'done': True})


class SnapshotBarTests(unittest.TestCase):
    def test_a6_the_snapshot_pencil_has_its_room_kept_and_nothing_moves_on_hover(self):
        # (it was display: none until hover, then display: grid: the hovered button grew 80 -> 101 px and pushed the
        # others aside; preview, 1600 px wide)
        page = text('workbench.html')
        self.assertNotIn('.snaps button:hover .pen { display: grid; }', page)
        self.assertIn('.snaps button { position: relative; padding-right: 24px; }', page)
        self.assertIn('.snaps button .pen { position: absolute; right: 5px;', page)
        self.assertIn('display: grid; visibility: hidden;', between(page, '.snaps button .pen { position: absolute;', '}'))
        self.assertIn('.snaps button:hover .pen { visibility: visible; }', page)
        # (the 1-4 / 5-8 button has no pencil, so no room kept)
        self.assertIn(".snaps button.grp { padding-right: 12px; }", page)
        self.assertIn("const other = el('button', 'grp');", page)
        # the rules hold in every layout: no layout gives a snapshot button its own padding or shows the pencil otherwise
        for rule in page.split('}'):
            if '.snaps button' in rule and ('.lay-' in rule.split('{')[0]):
                self.assertNotIn('padding', rule)
                self.assertNotIn('.pen', rule.split('{')[0])


class ImmediatePickTests(unittest.TestCase):
    """A7: a block picked here is lit and its panel drawn at once, from what the page knows; HX Edit's reading fills in
    its values. Preview: 2-9 ms from the click to the drawn panel (was: HX Edit's round trip first)."""

    @staticmethod
    def picked(pick, selected, blocks, now):
        return run_js(['workbench_layout.js'], 'workbenchPicked(%s, %s, %s, %d)' % (json.dumps(pick), json.dumps(selected), json.dumps(blocks), now))

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_the_pick_holds_until_hx_edit_has_it_or_moves_elsewhere(self):
        blocks = [{'dsp': 0, 'id': 'block1'}, {'dsp': 0, 'id': 'block2'}, {'dsp': 0, 'id': 'block4'}, {'dsp': 1, 'id': 'block0'}]
        old, new = {'dsp': 0, 'id': 'block4'}, {'dsp': 0, 'id': 'block2'}
        pick = {'dsp': 0, 'id': 'block2', 'from': [old], 'until': 5000}
        # a reading made before HX Edit followed: still the old block there; the page shows the pick
        self.assertEqual(self.picked(pick, old, blocks, 1000), {'pick': pick, 'selected': new})
        # (a reading with nothing selected, as during an undo: held too)
        self.assertEqual(self.picked(pick, None, blocks, 1000)['pick'], pick)
        # HX Edit has it: the pick is done, the reading is shown as it is (its values are the block's)
        self.assertEqual(self.picked(pick, new, blocks, 1000), {'pick': None, 'selected': new})
        # HX Edit on a third block (the Floor, HX Edit itself): that one; the block gone; the time out
        self.assertEqual(self.picked(pick, {'dsp': 1, 'id': 'block0'}, blocks, 1000), {'pick': None, 'selected': {'dsp': 1, 'id': 'block0'}})
        self.assertIsNone(self.picked(pick, old, [b for b in blocks if b['id'] != 'block2'], 1000)['pick'])
        self.assertEqual(self.picked(pick, old, blocks, 6000), {'pick': None, 'selected': old})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_quick_picks_keep_what_hx_edit_may_show_meanwhile(self):
        code = '''(() => { const a = workbenchPick({dsp: 0, id: 'block1'}, null, {dsp: 0, id: 'block4'}, 1000);
          const b = workbenchPick({dsp: 0, id: 'block2'}, a, {dsp: 0, id: 'block4'}, 1100);
          const blocks = [{dsp: 0, id: 'block1'}, {dsp: 0, id: 'block2'}, {dsp: 0, id: 'block4'}];
          return [a.from, b.from, b.until, workbenchPicked(b, {dsp: 0, id: 'block1'}, blocks, 1200).selected]; })()'''
        a_from, b_from, until, shown = run_js(['workbench_layout.js'], code)
        self.assertEqual(a_from, [{'dsp': 0, 'id': 'block4'}])
        self.assertEqual(b_from, [{'dsp': 0, 'id': 'block4'}, {'dsp': 0, 'id': 'block1'}])
        self.assertEqual(until, 1100 + 2500)
        self.assertEqual(shown, {'dsp': 0, 'id': 'block2'})          # (HX Edit on the first click's block: no flash)

    def test_the_page_draws_the_pick_at_once_and_keeps_the_old_values_out(self):
        page = text('workbench.html')
        pick = between(page, 'function pickBlock(block, added) {', '\nfunction markComing() {')
        self.assertIn('localPick = workbenchPick(block, localPick, hxSelected, Date.now());', pick)
        self.assertIn('state.selected = {dsp: block.dsp, id: block.id}; state.values = {}; state.assign = null;', pick)
        self.assertLess(pick.index('state.selected = {dsp: block.dsp'), pick.index("ask('select'"))
        self.assertIn('drawChain(); drawPanel();', pick)
        self.assertIn('if (hxShown) Object.assign(state, hxShown);', pick)                 # (never followed: back)
        receive = between(page, "else if (message.type === 'state') {", "else if (message.type === 'dsp')")
        self.assertIn('const seen = workbenchPicked(localPick, state.selected, state.blocks, Date.now());', receive)
        self.assertIn('if (localPick) { state.selected = seen.selected; state.values = {}; state.assign = null; }', receive)
        # the overlay comes before everything else in the reading's handling (the add's wait sees the player's pick)
        self.assertLess(receive.index('workbenchPicked('), receive.index('workbenchAddSelect('))
        self.assertIn(".insp.coming .knobs, .insp.coming .sliders, .insp.coming .tabview { opacity: .45; pointer-events: none;", page)
        self.assertIn('markComing();', between(page, 'function render() {', '\n}'))

    def test_focus_view_clicks_before_its_reading_and_traces_the_time(self):
        script = text('focus_view.js')
        refresh = between(script, 'function refresh(window) {', '  function select(target) {')
        early = refresh.index('if (wanted && known && !editor.isNull()) {')
        self.assertLess(early, refresh.index('const bounds = paneBounds();'))
        self.assertGreater(early, refresh.index('while (writes.length) {'))
        self.assertIn("stage: 'select-failed'", refresh)
        self.assertIn('publish(state);\n      if (wanted) select(wanted);', refresh)              # (the first block: after)
        self.assertIn("stage: 'select-shown', block: selectAsked.id, ms: Date.now() - selectAsked.at, read: Date.now() - began, full", refresh)
        self.assertIn('selectAsked = {dsp: value.dsp, id: value.id, at: Date.now()};', script)
        # the rules already in place are untouched: one select per click (select()), the split and mixer by selectNode
        sel = between(script, '  function select(target) {', '  function publish(state) {')
        self.assertIn('targetBinding.selectNode(editor, block.dsp, block.id);', sel)
        self.assertIn('namView.clickChainPoint(spot.x, spot.y)', sel)


class PickerCardTests(unittest.TestCase):
    def test_a9_the_pickers_card_has_close_only_and_no_undo_of_its_own(self):
        # ("Put it back" was HX Edit's plain Undo: live 2026-11-25 it undid a compressor change on another path)
        page = text('workbench.html')
        self.assertNotIn('Put it back', page)
        self.assertEqual(page.count("ask('undo')"), 1)                       # (the top bar's Undo only)
        self.assertIn("$('undo').onclick = () => ask('undo');", page)
        card = between(page, '  if (picker) {', '    return box;')
        self.assertIn("close = el('button', 'btn pri', 'Close');", card)
        self.assertIn('close.onclick = closePicker;', card)
        self.assertNotIn("'Done'", card)
        self.assertIn('The top bar’s Undo puts the old one back.', card)
        # the card is drawn by the picker dialog only (the Workbench and the stage's dock); Classic+'s Edit area has none
        self.assertEqual(page.count('card(block, true)'), 1)
        self.assertIn('card(block, true)', between(page, 'function drawPicker(block) {', '\n}'))
        # what a click on a model does is not changed here (B10)
        self.assertIn("ask('model', {dsp: block.dsp, id: block.id, symbol});", page)


if __name__ == '__main__':
    unittest.main()
