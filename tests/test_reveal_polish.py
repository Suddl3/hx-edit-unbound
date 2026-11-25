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
        self.assertIn("close = el('button', 'btn', 'Close');", card)
        self.assertIn('close.onclick = closePicker;', card)
        self.assertNotIn("'Done'", card)
        self.assertIn('Undo in the top bar puts it back.', card)
        # the card is drawn by the picker dialog only (the Workbench and the stage's dock); Classic+'s Edit area has none
        self.assertEqual(page.count('card(block, true)'), 1)
        self.assertIn('card(block, true)', between(page, 'function drawPicker(block) {', '\n}'))
        # what a click on a model does is not changed here (B10)
        self.assertIn("ask('model', {dsp: block.dsp, id: block.id, symbol});", page)


class OneCategoryListTests(unittest.TestCase):
    """B9: the captures are one category of their own, "NAM captures", after HX Edit's own categories (ending with
    Looper); its kinds are the head row's tabs. Mock-ups: research/modern-ui/reveal-picker-one-list.png, -nam.png."""

    def test_b9_one_list_with_nam_captures_after_the_stock_categories(self):
        page = text('workbench.html')
        rows = between(page, 'function pickCategoryRows(block, s, redraw, cls) {', '\n}')
        self.assertIn("nam.append(el('span', 'led'), el('span', '', 'NAM captures'), el('b', 'num', String(s.captures.length)));", rows)
        self.assertIn('const caps = [nam];', rows)
        self.assertNotIn("'All captures'", rows)
        # the picker dialog (Workbench, the stage's dock): one column; Classic+'s Edit area: the same rows, no tabs
        picker = between(page, 'function drawPicker(block) {', '\n}')
        self.assertIn("models.append(el('h6', '', 'Models'), ...rows.models, el('hr'), ...rows.caps);", picker)
        self.assertIn('if (rows.remove) models.append(el(\'hr\'), rows.remove);', picker)
        edit = between(page, 'function drawEdit(block) {', 'function editTabs(enabled) {')
        self.assertIn("rows.append(...found.models, el('hr'), ...found.caps);", edit)
        self.assertNotIn('kindtabs', page)
        self.assertIn('.pcats { border-right: 1px solid var(--line); display: grid; grid-template-columns: 1fr; min-height: 0; }', page)
        self.assertIn('.insp.pick { grid-template-columns: 250px 212px minmax(0, 1fr); }', page)

    def test_b9_its_kinds_are_tabs_and_stock_categories_carry_no_captures(self):
        page = text('workbench.html')
        head = between(page, 'function pickHead(block, s, redraw, inputId) {', '\n}')
        self.assertIn("kindTab('', 'All');", head)
        self.assertIn("for (const kind of namKinds()) kindTab(kind.name, kind.name.replace(/^NAM /, ''));", head)
        self.assertNotIn("tab('captures'", head)
        choices = between(page, 'function pickChoices(block) {', '\n}')
        self.assertIn('const kinds = [];', choices)
        self.assertIn("const mine = pickedTab === 'all' ? captures.filter(c => !pickedKind || namKind(c) === pickedKind) : [];", choices)
        self.assertNotIn('captureTabs', choices)
        # a NAM block (and Change capture) opens on NAM captures with its own capture's kind
        home = between(page, 'function pickHome(block, tab) {', '\n}')
        self.assertIn("pickedCategory = tab === 'captures' || isNam(block) ? '' : categoryOf(block);", home)
        self.assertIn("pickedTab = tab === 'captures' || isNam(block) ? 'all' : '';", home)
        # the search box there searches captures (of the kind picked)
        self.assertIn("input.placeholder = 'Search ' + (pickedTab === 'all' && pickedKind ? pickedKind : pickedTab === 'all' || pickedTab === 'captures' ? 'captures'", head)


class ClickRuleTests(unittest.TestCase):
    """B10: a click lines a model up, Replace swaps it (reveal-card-states.png). Kept in one place: pickRule."""

    def test_b10_one_rule_in_one_place(self):
        page = text('workbench.html')
        choice = between(page, 'function pickChoice(block, s, item, shape) {', '\n}')
        # every choice, in every layout (the picker's cards, Classic+'s rows), goes through pickRule only
        self.assertIn("choice.onclick = () => pickRule(block, item, 'click');", choice)
        self.assertIn("choice.ondblclick = () => pickRule(block, item, 'double');", choice)
        self.assertNotIn('pickModel(', choice)
        self.assertEqual(page.count("pickRule(block, item, '"), 2)
        rule = between(page, 'function pickRule(block, item, how) {', '\n}')
        # a "+": a click adds at once
        self.assertIn("if (block.isPlace) { item.symbol ? pickModel(block, item.symbol) : pickCapture(block, item.capture); return; }", rule)
        # a click lines up (no ask), a double-click replaces
        click = between(rule, "if (how === 'click') {", '  }\n')
        self.assertNotIn('ask(', click)
        self.assertIn('lined = {dsp: block.dsp, id: block.id', click)
        self.assertIn('replaceWith(block, item, f);', rule)
        # Replace is the same one edit as before (pickModel / pickCapture: one ask, the room check, the repeat guard)
        swap = between(page, 'function replaceWith(block, item, f) {', '\n}')
        self.assertIn('if (f.full || f.inUse) return;', swap)
        self.assertIn('item.symbol ? pickModel(block, item.symbol) : pickCapture(block, item.capture);', swap)
        self.assertIn("replaced = {dsp: block.dsp, id: block.id, was: title(block)}; lined = null;", swap)
        # Enter replaces with what is lined up
        self.assertIn("if (e.key === 'Enter' && visible && lined && !naming && !e.target.closest('input, textarea, select')) { e.preventDefault(); replaceLined(); return; }", page)

    def test_b10_the_card_and_classic_plus_say_it_in_the_same_words(self):
        page = text('workbench.html')
        box = between(page, 'function swapBox(block, item, shape) {', '\n}')
        self.assertIn("el('small', '', 'Replace with')", box)
        self.assertIn("'Not enough room on DSP '", box)
        self.assertIn("go = el('button', 'btn pri swapgo', 'Replace');", box)
        self.assertIn('go.disabled = f.full;', box)
        card = between(page, '  if (picker) {', '    return box;\n  }')
        self.assertIn("'Click a model to line it up here. Double-click it, or press Enter, to replace at once.'", card)
        self.assertIn("'Replaced ' + replaced.was + '.'", card)
        self.assertIn("'Undo in the top bar puts it back.'", card)
        self.assertIn("hint = 'Click another model to line it up, or close.';", card)
        self.assertNotIn("'Done'", card)
        params = between(page, 'function editParams(block, list) {', '\nfunction ')
        self.assertIn("lines.append(...swapBox(block, item, 'line'));", params)
        self.assertIn("'Replaced ' + replaced.was + '.'", params)
        # the lined up choice: a white ring; the one in use: dashed
        self.assertIn('.mc.sel { border-color: #eceef2;', page)
        self.assertIn('.insp.pick .mc.on { box-shadow: none; border-style: dashed;', page)
        # it goes when the picker closes, another opens, or Classic+ moves to another block
        for where, end in (('function closePicker() {', '\n}'), ('function openPicker(tab) {', '\n}'), ('function editHome(target) {', '\n}')):
            self.assertIn('lined = replaced = null;', between(page, where, end))
        # the panel is drawn again for each change of it
        self.assertIn('s.captures.map(c => [c.slot, c.name, c.icon, c.gear]), lined, replaced]);', page)
        self.assertIn('s.captures.map(c => [c.slot, c.name, c.icon, c.gear]), lined, replaced] : null,', page)


class ScenePinTests(unittest.TestCase):
    """B11: Rig on stage's pin beside "Scene: <name>" (reveal-stage-scene-pin.png): on (the default) one scene for the
    preset, off the picked block's, as before. Kept in settings.json like the layout."""

    def test_b11_the_setting(self):
        from workbench import SCENE_PIN, checked_scene_pin, scene_pin_of
        self.assertEqual(SCENE_PIN, 'workbenchScenePin')
        self.assertTrue(scene_pin_of({}))
        self.assertTrue(scene_pin_of(None))
        self.assertTrue(scene_pin_of({SCENE_PIN: 'no'}))
        self.assertFalse(scene_pin_of({SCENE_PIN: False}))
        self.assertIs(checked_scene_pin(False), False)
        self.assertIsNone(checked_scene_pin('false'))
        self.assertIsNone(checked_scene_pin(0))
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("'scenePin': scene_pin_kept()}", launcher)
        self.assertIn("if name == 'scenePin':", launcher)
        self.assertIn('nam_catalog.save_setting(SCENE_PIN, choice)', launcher)

    def test_b11_the_page(self):
        page = text('workbench.html')
        scene = between(page, 'function stageScene() {', '\n}')
        # the preset's own scene first, then with the pin one for the preset, without it the picked block's kind's
        self.assertLess(scene.index('if (whole) return whole;'), scene.index('if (look && scenePinned()) return presetScene();'))
        self.assertIn("if (look) return defaultSceneOf(now && isChain(now) ? kindKeyOf(now) : 'default');", scene)
        self.assertIn('const scenePinned = () => options.scenePin !== false;', page)
        whole = between(page, 'function presetScene() {', '\n}')
        # worked out once per preset and Floor look defaults (not per pick, add or remove)
        self.assertIn('key = JSON.stringify([p ? [p.setlist, p.number, p.name] : null, look.assign]);', whole)
        self.assertIn('if (pinnedScene && pinnedScene.key === key) return pinnedScene.name;', whole)
        self.assertNotIn('current()', whole)
        head = between(page, 'function stageHead() {', '\n}')
        self.assertIn("pin = el('button', 'glassbtn scenepin' + (pinned ? ' on' : ''));", head)
        self.assertIn("'One scene for this preset. Click to let the scene follow the picked block.'", head)
        self.assertIn("'The scene follows the picked block. Click to keep one scene for this preset.'", head)
        self.assertIn("ask('scenePin', !pinned);", head)
        self.assertIn('const stageKey = () => [stageScene(), !!look, scenePinned()];', page)
        # Focus Mode is not changed
        self.assertNotIn('scenePin', text('focus_view.html'))


class ClassicChooserTests(unittest.TestCase):
    """B12: Classic's UNBOUND button has the logo and opens Classic's own chooser (a native menu: the layouts, Classic
    ticked; Chain pictures: HX Edit's icons (the default) | 3D gear; the tools). reveal-classic-chooser.png."""

    def test_b12_the_menu(self):
        helper = text('NamLibrary.cs')
        layouts = between(helper, 'public static readonly Tuple<string,string>[] Layouts = {', '};')
        self.assertEqual([line.strip() for line in layouts.strip().splitlines()[1:]],
                         ['Tuple.Create("Workbench", "layout:workbench"),', 'Tuple.Create("Classic+", "layout:classicplus"),',
                          'Tuple.Create("Rig on stage", "layout:stage"),', 'Tuple.Create("Classic", ""),'])
        self.assertNotIn('Workbench (the modern screen)', helper)
        build = between(helper, 'Heading(tools,"LAYOUT");', 'Heading(options,"SIGNAL CHAIN");')
        self.assertIn('Item(tools,Tick(0,choice.Item2=="",choice.Item1),choice.Item2);', build)     # (Classic ticked)
        self.assertLess(build.index('Heading(tools,"CHAIN PICTURES");'), build.index('Heading(tools,"TOOLS");'))
        self.assertIn('chainIcons=Item(tools,"","chainIcons");', build)
        self.assertIn('chainGear=Item(tools,"","chainGear");', build)
        self.assertIn('chainIcons.Text=Tick(0,!art,"HX Edit\\u2019s icons"); chainGear.Text=Tick(0,art,"3D gear");', helper)
        self.assertIn('Tuple.Create("Level presets…", "level"),', helper)
        self.assertIn('if(output.Length==0)return;', helper)                    # (Classic itself: nothing to do)
        self.assertIn("HX Edit Unbound's logo", helper)
        from dsp_meter import DspMeter
        for name in ('layout:workbench', 'layout:classicplus', 'layout:stage', 'chainIcons', 'chainGear'):
            self.assertIn(name, DspMeter.CHOICES)
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("elif name.startswith('layout:'):", launcher)
        self.assertIn('nam_catalog.save_setting(LAYOUT_KEY, choice)', launcher)
        self.assertIn("elif name in ('chainIcons', 'chainGear') and (name == 'chainGear') != chain_art[0]:", launcher)
        self.assertIn("nam_catalog.choose_model_art(exe.parent / 'res', on)", launcher)
        self.assertIn("chainArt=nam_catalog.load_settings().get('chainModelArt') is True,", launcher)
        # (the trial build calls run_editor without main(): the set is chosen there, before HX Edit is started)
        run = between(launcher, 'def run_editor(', "    pid = device.spawn([str(exe)], cwd=str(exe.parent))")
        self.assertIn("nam_catalog.choose_model_art(exe.parent / 'res', nam_catalog.load_settings().get('chainModelArt') is True)", run)

    def test_b12_both_picture_sets_are_kept_and_either_put_in_place(self):
        import tempfile
        import nam_catalog
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            res, art = Path(folder) / 'res', Path(folder) / 'art'
            (res / 'icons_models').mkdir(parents=True); art.mkdir()
            (res / 'icons_models' / 'A.png').write_bytes(b'stock A')
            (res / 'icons_models' / 'B.png').write_bytes(b'stock B')                # (no render: stays stock)
            (res / 'icons_models' / 'CHAIN_A.png').write_bytes(b'chain')
            (art / 'A.png').write_bytes(b'gear A')
            old = nam_catalog.MODEL_ART
            nam_catalog.MODEL_ART = art
            try:
                self.assertEqual(nam_catalog.patch_model_art(res), 1)
                self.assertEqual(nam_catalog.patch_model_art(res), 1)                 # (again: the stock copy is not lost)
            finally:
                nam_catalog.MODEL_ART = old
            self.assertEqual((res / 'icons_models_stock' / 'A.png').read_bytes(), b'stock A')
            self.assertEqual((res / 'icons_models_3d' / 'A.png').read_bytes(), b'gear A')
            self.assertEqual((res / 'icons_models_3d' / 'B.png').read_bytes(), b'stock B')
            self.assertFalse((res / 'icons_models_3d' / 'CHAIN_A.png').exists())
            self.assertEqual(nam_catalog.choose_model_art(res, False), 1)
            self.assertEqual((res / 'icons_models' / 'A.png').read_bytes(), b'stock A')
            self.assertEqual(nam_catalog.choose_model_art(res, True), 1)
            self.assertEqual((res / 'icons_models' / 'A.png').read_bytes(), b'gear A')
            self.assertEqual(nam_catalog.choose_model_art(res, True), 0)
            # the panes (the Workbench, Focus Mode) take their model pictures from the 3D set
            import focus_view
            self.assertEqual(Path(focus_view.art_folders(res, {})['models']), res / 'icons_models_3d')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'icons_models').mkdir()
            import focus_view
            self.assertEqual(Path(focus_view.art_folders(Path(folder), {})['models']), Path(folder) / 'icons_models')


class ToneOpensTests(unittest.TestCase):
    """R1: TONE3000 did not open after an input or an output had been selected (live 2026-11-25 12:31:34, 12:31:42,
    12:38:28: "navigation-panel-unavailable"; in every earlier trace no input or output was selected before an open)."""

    def test_r1_the_window_docks_in_a_parameter_pane_that_shows(self):
        tone = text('tone_view.js')
        pick = between(tone, 'function dockPanelFor(given) {', '\n  }')
        self.assertIn('if (usablePanel(given)) return given;', pick)
        self.assertIn('own = parameterPanel(controller.add(0x58).readPointer());', pick)
        self.assertIn("send({type:'toneTrace',reason:'navigation-panel',stage:'own-view'}); return own;", pick)
        self.assertIn('const panel = options.headless ? (options.dockPanel || NULL) : dockPanelFor(options.dockPanel || NULL);', tone)
        self.assertIn('active.panel = dockPanelFor(options.dockPanel);', tone)
        # (the refusal itself stays: with no pane at all, nothing is opened)
        self.assertIn("send({type:'toneTrace',reason:'navigation-panel-unavailable'});", tone)

    def test_r1_the_view_never_waits_for_ever(self):
        page = text('workbench.html')
        self.assertIn('const TOOL_WAIT_MS = 6000;', page)
        self.assertIn("ask('tool', {name, ...rect}); waitForTool(); }", page)
        fail = between(page, 'function send2page(why) {', '\n}')
        self.assertIn("el('b', '', 'TONE3000 did not open.')", fail)
        self.assertIn("again = el('button', 'btn', 'Try again');", fail)
        self.assertIn("ask('toolClose', {why});", fail)
        self.assertIn("message.kind === 'toolOpen') { toolArrived(); return; }", page)
        self.assertIn("message.kind === 'tone') { toolArrived();", page)
        preview = text('tone_preview.py')
        self.assertIn("self._to_workbench('toolOpen', {'ready': True})", preview)
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("trace({'type': 'workbench', 'event': 'tool-not-open', 'name': 'tone'})", launcher)


if __name__ == '__main__':
    unittest.main()
