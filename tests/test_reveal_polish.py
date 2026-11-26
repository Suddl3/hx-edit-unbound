"""Before the reveal (Nick's review of the merged build, 2026-11-25; BACKLOG.md "Before the reveal", list A).

Each test names its item. No editor, no device: the page's and the scripts' own text, and their pure parts in node."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import NODE, run_js  # noqa: E402
from test_focus_view import run_js_source  # noqa: E402


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
        self.assertIn("if (toolShown && !toolPopped) { if (toolShown === 'tone') toneGone(); toolShown = ''; ask('toolClose'); }", sync)
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
        for line in ("button.onclick = () => { if (!dragDone) pickBlock(real); };", "button.onclick = () => pickBlock(block);",
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
        self.assertIn("addFollow = null; swapAsked = null; replaced = null; toast(message.text);", page)               # (a refusal)
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
        self.assertEqual(page.count("ask('undo')"), 0)                       # (the top bar's Undo only: askUndo, S5)
        self.assertIn("$('undo').onclick = () => askUndo('undo');", page)
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
        self.assertIn('replaced = {dsp: block.dsp, id: block.id, was: title(block),', swap)
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
        # the preset's own scene first; the pin off: the picked block's (followScene); on: the frozen one (R2)
        self.assertLess(scene.index('if (whole) return whole;'), scene.index('if (!scenePinned()) return followScene();'))
        self.assertIn('if (frozenScene && frozenScene.key === key) return frozenScene.name;', scene)
        self.assertIn('const scenePinned = () => options.scenePin !== false;', page)
        follow = between(page, 'function followScene() {', '\n}')
        self.assertIn("if (look) return now && isChain(now) ? blockScene(now).name : defaultSceneOf('default');", follow)
        # (R2: no rule of its own for "one scene for the preset": it is the scene showing when pinned, or as it comes up)
        self.assertNotIn('function presetScene()', page)
        # pressed on: the scene showing now is frozen for this preset; off: it follows again
        self.assertIn('frozenScene = pinned ? null : {key: sceneKey(), name: stageScene()};', page)
        # a preset coming up with the pin on: frozen once its blocks and a selection are read
        self.assertIn('if (state.blocks.length && state.selected) frozenScene = {key, name};', scene)
        self.assertIn("const sceneKey = () => { const p = state.preset; return JSON.stringify(p ? [p.setlist, p.number, p.name] : null); };", page)
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
        build = between(helper, 'Heading(tools,"LAYOUT");', 'Ticks();')
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
        self.assertIn("reason:'navigation-panel-unavailable',asked:options.asked", tone)

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


class SceneFadeTests(unittest.TestCase):
    def test_r3_the_stage_scene_cross_fades_as_focus_modes_does(self):
        page, focus = text('workbench.html'), text('focus_view.html')
        # Focus Mode's own plates: opacity .55s ease
        self.assertIn('.plate { position: absolute; inset: 0; opacity: 0; transition: opacity .55s ease; }', focus)
        self.assertIn('.app > .scene > .plate { position: absolute; inset: 0; background: center / cover no-repeat; opacity: 0; transition: opacity .55s ease; }', page)
        self.assertIn('@media (prefers-reduced-motion: reduce) { .app > .scene > .plate { transition: none; } }', page)
        sync = between(page, 'function syncStage() {', '\n}')
        self.assertIn("box.replaceChildren(el('i', 'plate'), el('i', 'plate'));", sync)
        self.assertIn("next.classList.add('on'); last.classList.remove('on');", sync)
        # (the first scene shows at once, not faded in)
        self.assertIn("if (first) { next.classList.add('now'); setTimeout(() => next.classList.remove('now'), 60); }", sync)


class ReplaceNoteTests(unittest.TestCase):
    def test_r4_the_note_shows_only_while_it_is_true(self):
        page = text('workbench.html')
        settle = between(page, 'function settleReplaced() {', '\n}')
        # the block still holds what Replace put there ...
        self.assertIn('const holds = replaced.route !== undefined ? endpointNow(block) === replaced.route', settle)
        self.assertIn(': replaced.symbol ? block.model === replaced.symbol : isNam(block) && block.slot === replaced.slot;', settle)
        # ... and that step is HX Edit's last one: the undo position the reading that showed it had
        self.assertIn('if (holds) replaced.at = state.undoAt;', settle)
        self.assertIn('if (!holds || state.undoAt !== replaced.at) replaced = null;', settle)
        # another block, a refusal, or no reading showing it within 4 s: gone
        self.assertIn('if (!block || !now || !same(now, replaced)) { replaced = null; return; }', settle)
        self.assertIn('addFollow = null; swapAsked = null; replaced = null; toast(message.text);', page)
        self.assertIn('settleReplaced();\n    if (addFollow && catalog) {', page)
        swap = between(page, 'function replaceWith(block, item, f) {', '\n}')
        self.assertIn('symbol: item.symbol || null, slot: item.capture ? item.capture.slot : null', swap)
        # (it never tells the player to press Undo when Redo is what would do it: after an Undo it is gone for good)
        self.assertNotIn("'Undo in the top bar", settle)


class ChainSwitchTests(unittest.TestCase):
    def test_r5_every_block_drawn_is_redrawn_at_the_switch(self):
        tone = text('tone_view.js')
        # with HX Edit's own icons (the default since B12) chainLook does not run, so no block was remembered and the
        # switch to 3D gear redrew none: they changed only as HX Edit repainted them (the pointer over them)
        self.assertIn('else rememberChainItem(this.context.ecx); },', tone)
        remember = between(tone, 'function rememberChainItem(item) {', '\n  }')
        self.assertIn('chainItems.set(item.toString(), {item, object, vtable: item.readPointer()});', remember)
        switch = between(tone, 'function setChainArt(on) {', '\n  }')
        self.assertIn('for (const [key, entry] of [...chainItems]) {', switch)
        self.assertIn('chainRedraw(entry.item);', switch)


class OneMenuTests(unittest.TestCase):
    def test_r6_one_menu_and_no_options_button(self):
        helper = text('NamLibrary.cs')
        button = between(helper, 'class UnboundButton : Form', '\n}\n')
        self.assertNotIn('options', between(button, 'readonly ContextMenuStrip', ';'))
        self.assertNotIn('GearWidth', helper)
        self.assertNotIn('a cog', button)
        self.assertIn('return new[]{ new Rectangle(0,0,focus,height), new Rectangle(focus+Gap,0,tools,height) };', button)
        # LAYOUT / CHAIN PICTURES (the pair, then 3D gear's three) / IR LIST / TOOLS, each choice once
        menu = between(button, 'Heading(tools,"LAYOUT");', 'Ticks();')
        order = [menu.index(x) for x in ('Heading(tools,"CHAIN PICTURES");', 'chainIcons=Item(tools,"","chainIcons");', 'chainGear=Item(tools,"","chainGear");',
                                         'chainLarge=Item(tools,"","chainLarge");', 'chainNames=Item(tools,"","chainNames");', 'chainGlow=Item(tools,"","chainGlow");',
                                         'Heading(tools,"IR LIST");', 'irDots=Item(tools,"","irDots");', 'Heading(tools,"TOOLS");')]
        self.assertEqual(order, sorted(order))
        for output in ('"chainIcons"', '"chainGear"', '"chainLarge"', '"chainNames"', '"chainGlow"', '"irDots"'):
            self.assertEqual(button.count(output), 1, output)
        self.assertNotIn('"chainArt"', button)                                   # (3D pictures of the gear: Chain pictures)
        # 3D gear's own options are indented under it and dimmed while it is off, as before
        self.assertIn('chainLarge.Text=Tick(1,large,"Large pictures"); chainLarge.Enabled=art;', button)
        self.assertIn('chainNames.Text=Tick(2,names,"Block names under them"); chainNames.Enabled=art&&large;', button)
        self.assertIn('chainGlow.Text=Tick(2,glow,"Glow behind them"); chainGlow.Enabled=art&&large;', button)


class EndpointTests(unittest.TestCase):
    """R7: an input's or an output's card offers "Change input" / "Change output": HX Edit's own list for that place,
    by the click rule (a click lines one up, Replace sets it), one write of @input / @output, one undo step."""

    @staticmethod
    def view(blocks):
        from focus_view import FocusView
        view = FocusView.__new__(FocusView)
        view.state = {'blocks': blocks}
        return view

    def test_r7_the_launcher_checks_the_place_and_the_number(self):
        blocks = [{'dsp': 0, 'id': 'inputA', 'model': 'HD2_AppDSPFlow1Input'}, {'dsp': 1, 'id': 'outputA', 'model': 'HD2_AppDSPFlowOutput'},
                  {'dsp': 0, 'id': 'outputA', 'model': 'HD2_AppDSPFlowOutput'}, {'dsp': 0, 'id': 'block1', 'model': 'HD2_DistMinotaur'}]
        view = self.view(blocks)
        if not hasattr(view, '_block'):
            self.skipTest('no _block')
        self.assertEqual(view.checked_endpoint({'dsp': 0, 'id': 'inputA', 'value': 2}),
                         {'action': 'endpoint', 'dsp': 0, 'id': 'inputA', 'key': '@input', 'value': 2})
        self.assertEqual(view.checked_endpoint({'dsp': 0, 'id': 'outputA', 'value': 3})['key'], '@output')   # path 1 -> Path 2B
        self.assertIsNone(view.checked_endpoint({'dsp': 1, 'id': 'outputA', 'value': 3}))     # path 2 cannot go to path 2
        self.assertIsNone(view.checked_endpoint({'dsp': 0, 'id': 'inputA', 'value': 17}))     # past HX Edit's list
        self.assertIsNone(view.checked_endpoint({'dsp': 0, 'id': 'inputA', 'value': True}))
        self.assertIsNone(view.checked_endpoint({'dsp': 0, 'id': 'block1', 'value': 1}))     # not an input or an output
        self.assertIsNone(view.checked_endpoint({'dsp': 1, 'id': 'inputB', 'value': 1}))     # not there
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("'endpoint': view.checked_endpoint,", launcher)

    def test_r7_the_script_writes_it_as_hx_edits_list_does(self):
        script = text('focus_view.js')
        body = between(script, "} else if (command.action === 'endpoint') {", "} else if (command.action === 'route') {")
        self.assertIn("targetBinding.setValue(editor, command.dsp, command.id, command.key, command.value, 'single');", body)
        self.assertIn('finish(editor, command.dsp, command.id, command.key, command.value);', body)
        self.assertIn("value.key === '@' + (value.id.startsWith('input') ? 'input' : 'output')", script)

    def test_r7_the_page(self):
        page = text('workbench.html')
        self.assertIn("(end ? (block.id.startsWith('input') ? 'Change input' : 'Change output') : 'Change model')", page)
        self.assertIn("change.onclick = () => end ? openEndpointPicker() : openPicker();", page)
        choices = between(page, 'function endpointChoices(block) {', '\n}')
        self.assertIn('.filter(c => input || block.dsp === 0 || ![2, 3, 4].includes(c.route));', choices)
        rule = between(page, 'function endpointRule(block, choice, how) {', '\n}')
        self.assertIn("if (how === 'click') { lined = {dsp: block.dsp, id: block.id, route: choice.route};", rule)
        self.assertIn('replaceEndpoint(block, choice.route);', rule)
        self.assertIn("ask('endpoint', {dsp: block.dsp, id: block.id, value: route});", page)
        self.assertIn("if (lined && lined.route !== undefined) { const block = current(); if (block && same(lined, block)) replaceEndpoint(block, lined.route); return; }", page)
        # every layout: drawPanel sends it there before Classic+'s Edit area
        panel = between(page, 'function drawPanel() {', '\n}')
        self.assertLess(panel.index('drawEndpointPicker(block)'), panel.index("if (layout === 'classicplus')"))
        self.assertIn('.lay-stage > .insp.pick.endpoint { grid-template-columns: 250px minmax(0, 1fr); }', page)
        # the split and the mixer keep their buttons
        self.assertIn("'The split and the mixer keep their model'", page)


class StageCardTests(unittest.TestCase):
    def test_r8_the_stage_docks_card_keeps_the_workbenchs_order(self):
        page = text('workbench.html')
        # the stage reverses its card's title block (the line above the name); that rule caught the lined-up box (its
        # picture went under its words) and the note (its two lines swapped)
        self.assertIn('.lay-stage > .insp .card > div:not(.btnrow):not(.swapbox):not(.swapnote) { display: flex; flex-direction: column-reverse;', page)
        self.assertNotIn('.lay-stage > .insp .card > div:not(.btnrow) {', page)
        self.assertIn('.swapbox { display: flex; align-items: center;', page)
        self.assertIn('.swapnote { display: grid;', page)


class ToneOverThePaneTests(unittest.TestCase):
    """S1: TONE3000 from the Workbench refused for the rest of the session after a visit to Focus Mode (owner-trials
    20261125-121738 12:31:34; 20261125-131943 13:28:58 on: `navigation-panel-unavailable`, also with R1's fallback)."""

    def test_s1_the_workbench_open_needs_no_pane_of_hx_edits(self):
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn('sidebar_action(\'catalog\', f"workbench|layout={layout_kept()}|focus={int(focus_seen[0])}")', launcher)
        self.assertIn('focus_seen[0] = True', launcher)
        sidebar = text('nam_sidebar.js')
        self.assertIn("const placed=typeof value.id==='string'&&value.id.startsWith('workbench');", sidebar)
        self.assertIn("toneView.openBrowser(window,{dockPanel:navigationBanner.dockPanel(),placed,asked:value.id||''});", sidebar)
        tone = text('tone_view.js')
        gate = between(tone, "if (!options.headless && (!bounds?.visible || bounds.w < 60 || bounds.h < 60)) {", "    active = { id: ++nextSession, navigation: true")
        self.assertIn("if (options.placed) {", gate)
        self.assertIn("stage:'placed-over-pane'", gate)
        self.assertIn('bounds = {visible:true, x:0, y:0, w:0, h:0, placed:true};', gate)
        # HX Edit's own TONE3000 button and the Classic tools still dock in its pane (nothing placed: refused as before)
        self.assertIn("send({type:'toneTrace',reason:'navigation-panel-unavailable',asked:options.asked||'',...panelReport(options.dockPanel)});", gate)

    def test_s1_a_refusal_says_why_in_full(self):
        tone = text('tone_view.js')
        report = between(tone, 'function panelReport(given) {', '\n  }\n')
        self.assertIn('return {first: one(given), own, selected};', report)
        self.assertIn('selected = {dsp: c.add(0x80).readS32(), block: block(c)};', report)
        self.assertIn('own = one(parameterPanel(c.add(0x58).readPointer()));', report)


class FocusSwitchTests(unittest.TestCase):
    def test_s2_focus_modes_way_back_is_the_editors_switch_in_its_place(self):
        focus, page = text('focus_view.html'), text('workbench.html')
        self.assertNotIn('class="back"', focus)
        self.assertIn('<div class="viewsw" role="group" aria-label="View"><button id="back" aria-pressed="false" title="Back to the editor (Esc)">Editor</button><button class="on" aria-pressed="true" tabindex="-1">Focus</button></div>', focus)
        self.assertIn("$('back').onclick = () => ask('exit');", focus)
        # the editor's: .view in its 58 px top bar, 16 px from the right; the same look, the current side lit
        self.assertIn('.view button { height: 28px; min-width: 68px; padding: 1px 14px 0; border-radius: 6px;', page)
        self.assertIn('.viewsw button { height: 28px; min-width: 68px; padding: 1px 14px 0; border-radius: 6px;', focus)
        self.assertIn('.viewsw { position: absolute; top: 10.5px; right: 16px;', focus)
        self.assertIn("padding: 0 16px 0 0;", between(page, '  .top {', '}'))
        self.assertIn('.viewsw button.on { background: #eceef2; color: #111; font-weight: 600;', focus)


class NoFlashTests(unittest.TestCase):
    def test_s3_one_pane_stays_over_hx_edit_through_the_switch(self):
        launcher = text('start-hx-edit-nam.pyw')
        mode = between(launcher, 'def focus_mode(on, notice=None):', '            def focus_load(')
        # going back: the Workbench first, then Focus Mode goes
        self.assertLess(mode.index('if not on:\n                    workbench_show()'), mode.index('focus.set_on(on)'))
        # coming in for the first time: the Workbench stays until Focus Mode's page is up (or 4 s)
        self.assertIn('if on and focus is not None and not focus.page_ready:', mode)
        self.assertIn('focus.on_ready = ready_then', mode)
        self.assertIn('Timer(4.0, ready_then).start()', mode)
        self.assertIn("trace({'type': 'focusView', 'event': 'waits-for-page'})", mode)
        pane = text('focus_view.py')
        self.assertIn('ready, self.on_ready = self.on_ready, None', pane)

    def test_s3_the_ready_call_runs_once(self):
        from focus_view import FocusView
        calls = []
        view = FocusView.__new__(FocusView)
        view.on_ready = lambda: calls.append(1)
        view.page_ready = False
        view.trace = lambda event: None
        view._write = lambda *a: None
        view.catalog = lambda: {}
        view._show_look = view._place = view._show_state = view._show_dsp = lambda: None
        view._handle('pane', {'type': 'ready'})
        view._handle('pane', {'type': 'ready'})
        self.assertEqual(calls, [1])
        self.assertTrue(view.page_ready)


class StageCaptureArtTests(unittest.TestCase):
    def test_s4_a_capture_takes_its_large_picture_once_it_stands_over_its_small_ones_size(self):
        page = text('workbench.html')
        pics = between(page, 'function stagePictures(block) {', '\n}')
        self.assertIn('const taken = capture(block), small = taken && taken.icon && !given ? 120 : 240;', pics)
        self.assertIn('const big = TILE_TOP * (window.devicePixelRatio || 1) > small;', pics)
        # the large one first when big: catalog.captures.pictures lists the art pack's (capturesfull) before the 128 px
        self.assertIn("for host in ('capturesfull', 'captures') if host in folders]", text('focus_view.py'))
        self.assertIn('return big ? urls.concat(own) : urls.slice().reverse().concat(own.slice().reverse());', pics)


class UndoAtOnceTests(unittest.TestCase):
    def test_s5_where_an_undos_time_goes_is_traced(self):
        script = text('focus_view.js')
        self.assertIn("undoAsked = {action: value.action, at: Date.now(), from: lastUndoAt, call: null};", script)
        self.assertIn('if (undoAsked) undoAsked.call = Date.now() - began;', script)
        self.assertIn("stage: 'undo-shown', action: undoAsked.action, ms: Date.now() - undoAsked.at, call: undoAsked.call,", script)

    def test_s5_the_bar_and_the_block_answer_at_once(self):
        page = text('workbench.html')
        self.assertIn("$('undo').onclick = () => askUndo('undo');", page)
        self.assertIn("$('redo').onclick = () => askUndo('redo');", page)
        ask = between(page, 'function askUndo(action) {', '\n}')
        # the page's own last Replace, still HX Edit's last step: shown undone at once, Redo lit
        self.assertIn("if (action === 'undo' && lastStep && lastStep.at !== undefined && state && state.undoAt === lastStep.at) {", ask)
        self.assertIn('Object.assign(b, lastStep.before); state.redo = true; state.values = {};', ask)
        self.assertLess(ask.index('Object.assign(b, lastStep.before)'), ask.index('ask(action);'))
        settle = between(page, 'function settleUndo() {', '\n}')
        self.assertIn('if (state.undoAt !== undoShow.from || Date.now() > undoShow.until) { undoShow = null; return; }', settle)
        # what the Replace and the input/output chooser note as the last step
        self.assertIn('noteStep(block, item.symbol ? {model: block.model} : {model: block.model, slot: block.slot ?? null},', page)
        self.assertIn('noteStep(block, {[key]: endpointNow(block) ?? null}, {[key]: route});', page)
        self.assertIn("$('undo').classList.toggle('busy', !!undoBusy && undoBusy.action === 'undo');", page)
        self.assertIn('@media (prefers-reduced-motion: reduce) { .icon.busy { animation: none; } }', page)
        # (a knob's own held value, 600 ms after its last write, gives way to HX Edit's answer on an Undo)
        self.assertIn('held.clear(); snapHeld.clear();', ask)
        self.assertIn("held.set(key, {value, until: phase === 'begin' || phase === 'move' ? 0 : Date.now() + 600});", text('pane_controls.js'))


class LevelsSaysWhatTests(unittest.TestCase):
    def test_s6_levels_says_what_it_is_for_first(self):
        page = text('workbench.html')
        self.assertIn("const LEVELS_WHAT = 'Evens out the volume of your presets and snapshots, so they are all as loud as each other.';", page)
        # the head of its panel (under the chain: its card's line; full view: its subtitle), then the empty state
        self.assertIn("level: {title: 'Levels', sub: 'Evens out the volume of your presets and snapshots', half: LEVELS_WHAT,", page)
        self.assertIn("empty.append(el('b', '', running ? 'Scanning…' : 'Nothing measured yet'), el('span', 'lvwhat', LEVELS_WHAT));", page)
        empty = between(page, "const empty = el('div', 'lvempty');", 'list.append(empty);')
        self.assertLess(empty.index('LEVELS_WHAT'), empty.index('The amp stays silent'))


class EditTabTests(unittest.TestCase):
    """After Focus Mode HX Edit's own panel was on BYPASS/CONTROLLER ASSIGN (live 2026-11-25 14:05, owner-trials
    20261125-140350-61f39929): no parameter pane, and the TONE3000 session could not bind the selected block."""

    def test_hx_edits_tab_is_read_from_its_own_views(self):
        view = text('nam_view.js')
        read = between(view, 'editPanelTab() {', '\n    },')
        self.assertIn('findWidget(view.editor, 0x696e7370, 1)', read)                       # insp
        self.assertIn('findWidget(insp, 0x65747677, 1)', read)                               # etvw: EDIT
        self.assertIn('findWidget(insp, 0x63617677, 1)', read)                               # cavw: the assign view
        click = between(view, 'showEditTab() {', '\n    },')
        self.assertIn('findWidget(insp, 0x656d7462, 1)', click)                              # emtb: the tab row
        self.assertIn('chainPoint.readS32() + Math.round(size.w / 4)', click)               # (EDIT: its left half)
        self.assertIn('postMessage(sidebarHost, 0x201, ptr(1), at);', click)
        res = Path(r'E:\Dev\HelixNam\research\hx-edit-nam-review\floor-port\navigation-build-20261112\live\app\res\editor.xml')
        if res.is_file():
            xml = res.read_text(encoding='utf-8', errors='replace')
            for wid in ('id="insp"', 'id="emtb"', 'id="etvw"', 'id="cavw"', '<label>EDIT</label>', '<label>BYPASS/CONTROLLER ASSIGN</label>'):
                self.assertIn(wid, xml)
            self.assertLess(xml.index('<label>EDIT</label>'), xml.index('<label>BYPASS/CONTROLLER ASSIGN</label>'))

    def test_while_a_pane_covers_hx_edit_its_tab_goes_back_to_edit_and_is_traced(self):
        script = text('focus_view.js')
        keep = between(script, 'function keepEditTab() {', '\n  }\n')
        self.assertIn("send({type: 'toneTrace', reason: 'focus-view', stage: 'hx-tab', tab: word, picked, found: tab});", keep)
        # (judged by HX Edit's parameter pane: the two views' own flags said "none" live while the tab was on assign)
        self.assertIn("const word = !tab ? 'unknown' : tab.prvw ? 'edit' : tab.assign ? 'assign' : /^block\\d{1,2}$/.test(picked) ? 'assign?' : 'none';", keep)
        self.assertIn("if ((word === 'assign' || word === 'assign?') && hxTabTries < 3 && Date.now() - hxTabFixedAt > 1000) {", keep)
        self.assertIn('if (word === \'edit\' || picked !== hxTabPicked) { hxTabTries = 0; hxTabPicked = picked; }', keep)
        view = text('nam_view.js')
        self.assertIn('let prvw = canonical(findWidget(insp, 0x50525657, 1));', view)
        self.assertIn('if (prvw.isNull()) prvw = canonical(findWidget(view.editor, 0x50525657, 1));', view)
        self.assertIn('seen: {etvw: flags(editView), cavw: flags(assignView), prvw: flags(prvw)}};', view)

    def test_our_select_clicks_the_blocks_picture_not_its_name(self):
        # (live 2026-11-25 14:27:41: a click on 031's block0 put HX Edit on BYPASS/CONTROLLER ASSIGN: the click was on the
        # name under the picture, where that block shows its custom footswitch label "Godzilla")
        script = text('focus_view.js')
        self.assertIn('y: Math.round(box.y + (row + .4) * box.h / 2)};', script)
        self.assertNotIn('(row + .8)', script)
        keep = between(script, 'function keepEditTab() {', '\n  }\n')
        self.assertIn("send({type: 'toneTrace', reason: 'focus-view', stage: 'hx-tab-edit', clicked});", keep)
        refresh = between(script, 'function refresh(window) {', '  function select(target) {')
        self.assertIn('keepEditTab();', refresh)
        sidebar = text('nam_sidebar.js')
        self.assertIn("stage:'hx-tab-edit',clicked:!!namView.showEditTab?.(),before:'tone3000'", sidebar)
        self.assertLess(sidebar.index("before:'tone3000'"), sidebar.index('placed,asked:value.id'))


class PreviewTargetTests(unittest.TestCase):
    """Which block a TONE3000 preview plays on (Batch 2 rules sheet rows 2 and 3, 2026-11-25): HX Edit's selected block
    still plays (it has the only parameter view a preview binds through); while a pane covers HX Edit the session puts
    its target there with a click on HX Edit's chain, and the Workbench keeps showing its own block."""

    STUBS = """
const AUDITION_SLOT = 128;
let active = {navigation: true, id: 1}, command = null, workflowRequest = null, toneImport = null;
const traces = [], replies = [];
const send = m => traces.push(m), reply = (r, v) => replies.push(v), publishTarget = () => {};
const namView = {profileLabel: s => ({9: 'Deluxe Reverb', 10: 'Klon Gain=0'})[s] || '', slotName: () => ''};
"""
    SCENES = """
const out = {}, copy = v => JSON.parse(JSON.stringify(v === undefined ? null : v));
const one = [{dsp: 0, id: 'block1', slot: 9, path: 0, position: 2}];
// row 2: an amp is selected and the preset has one NAM block
out.t1 = steerPreview({nams: one, cursor: {dsp: 0, id: 'block0'}});
out.t1target = copy(active.steer.target);
out.t1b = steerPreview({nams: one, cursor: {dsp: 0, id: 'block1'}});
out.pick = pagePick({dsp: 0, id: 'block2'});
out.t1c = steerPreview({nams: one, cursor: {dsp: 0, id: 'block1'}});
// the Floor's knob moves HX Edit's selection: followed, and not steered back
out.floor = steerPreview({nams: one, cursor: {dsp: 0, id: 'block4'}});
out.floorSteer = copy({target: active.steer.target, aside: active.steer.aside});
out.floor2 = steerPreview({nams: one, cursor: {dsp: 0, id: 'block4'}});
// row 3: two NAM blocks, none selected: asked; a choice is clicked on HX Edit's chain
active = {navigation: true, id: 2};
const two = [{dsp: 0, id: 'block1', slot: 9}, {dsp: 1, id: 'block3', slot: 10}];
out.t2 = steerPreview({nams: two, cursor: {dsp: 0, id: 'block0'}});
out.t2steer = copy({ask: active.steer.ask, target: active.steer.target});
chooseTarget({dsp: 1, block: 'block3'});
out.t2b = steerPreview({nams: two, cursor: {dsp: 0, id: 'block0'}});
out.t2b2 = steerPreview({nams: two, cursor: {dsp: 1, id: 'block3'}});
// while a preview plays: the chooser waits for Stop, a NAM block picked in the Workbench is only shown
active.transfer = {slot: 128};
try { chooseTarget({dsp: 0, block: 'block1'}); out.refused = ''; } catch (error) { out.refused = error.message; }
out.namWhilePlaying = pagePick({dsp: 0, id: 'block1'});
out.t2c = steerPreview({nams: two, cursor: {dsp: 1, id: 'block3'}});
active.transfer = null;
// a NAM block picked in the Workbench (nothing playing) plays from then on; HX Edit selects it as before
out.namPick = pagePick({dsp: 0, id: 'block1'});
out.t2d = steerPreview({nams: two, cursor: {dsp: 0, id: 'block1'}});
out.t2dTarget = active.steer.target.id;
// the session ends: HX Edit gets the Workbench's block back
active = {navigation: true, id: 3};
out.p1 = steerPreview({nams: one, cursor: {dsp: 0, id: 'block0'}});
out.p2 = steerPreview({nams: one, cursor: {dsp: 0, id: 'block1'}});
active = null;
out.back = steerPreview({nams: one, cursor: {dsp: 0, id: 'block1'}});
out.after = steerPreview({nams: one, cursor: {dsp: 0, id: 'block0'}});
// no NAM block: said, nothing clicked
active = {navigation: true, id: 4};
out.none = steerPreview({nams: [], cursor: {dsp: 0, id: 'block0'}});
out.noneSteer = copy({none: active.steer.none, ask: active.steer.ask});
// the Library's own (headless) session and the Workbench's Levels session are not steered
active = {navigation: true, id: 5, headless: true};
out.headless = steerPreview({nams: one, cursor: {dsp: 0, id: 'block0'}});
out.stages = traces.map(t => t.stage);
out.replies = replies;
out
"""

    def scenes(self):
        tone = text('tone_view.js')
        piece = between(tone, '  let previewHold = null;', '  function parameterPanel(')
        return run_js_source(self.STUBS + piece, '(() => {' + self.SCENES.replace('\nout\n', '\nreturn out;\n') + '})()')

    def test_row2_one_nam_block_plays_while_the_workbench_keeps_its_own_block(self):
        out = self.scenes()
        b = lambda dsp, id: {'dsp': dsp, 'id': id}
        self.assertEqual(out['t1'], {'page': b(0, 'block0'), 'click': b(0, 'block1')})
        self.assertEqual(out['t1target']['name'], 'Deluxe Reverb')
        self.assertEqual(out['t1b'], {'page': b(0, 'block0'), 'click': None})       # HX Edit has it: the page keeps block0
        self.assertTrue(out['pick'])                                                 # another block: only shown
        self.assertEqual(out['t1c'], {'page': b(0, 'block2'), 'click': None})
        self.assertEqual(out['floor'], {'page': b(0, 'block4'), 'click': None})     # the Floor moved it: followed
        self.assertEqual(out['floorSteer'], {'target': None, 'aside': True})
        self.assertEqual(out['floor2'], {'page': b(0, 'block4'), 'click': None})    # and not fought

    def test_row3_two_nam_blocks_ask_once_and_the_choice_is_selected_in_hx_edit(self):
        out = self.scenes()
        b = lambda dsp, id: {'dsp': dsp, 'id': id}
        self.assertEqual(out['t2'], {'page': b(0, 'block0'), 'click': None})
        self.assertEqual(out['t2steer'], {'ask': True, 'target': None})
        self.assertEqual(out['t2b'], {'page': b(0, 'block0'), 'click': b(1, 'block3')})
        self.assertEqual(out['t2b2'], {'page': b(0, 'block0'), 'click': None})
        self.assertEqual(out['refused'], 'Stop the preview first, then choose the block it plays on.')
        self.assertTrue(out['namWhilePlaying'])
        self.assertEqual(out['t2c'], {'page': b(0, 'block1'), 'click': None})       # playing: the target does not move
        self.assertFalse(out['namPick'])                                             # HX Edit selects it as before
        self.assertEqual(out['t2d'], {'page': b(0, 'block1'), 'click': None})
        self.assertEqual(out['t2dTarget'], 'block1')
        self.assertEqual(out['replies'], [{'target': True}])

    def test_the_workbench_block_goes_back_when_the_session_ends_and_none_or_headless_are_left_alone(self):
        out = self.scenes()
        b = lambda dsp, id: {'dsp': dsp, 'id': id}
        self.assertEqual(out['p1'], {'page': b(0, 'block0'), 'click': b(0, 'block1')})
        self.assertEqual(out['p2'], {'page': b(0, 'block0'), 'click': None})
        self.assertEqual(out['back'], {'page': b(0, 'block0'), 'click': b(0, 'block0')})
        self.assertEqual(out['after'], {'page': b(0, 'block0'), 'click': None})
        self.assertEqual(out['none'], {'page': b(0, 'block0'), 'click': None})
        self.assertEqual(out['noneSteer'], {'none': True, 'ask': False})
        self.assertEqual(out['headless'], {'page': b(0, 'block0'), 'click': None})
        for stage in ('select', 'page-only', 'moved-outside', 'chosen', 'picked-nam', 'hold-back'):
            self.assertIn(stage, out['stages'])

    def test_the_target_rides_the_sessions_word_and_clean_up_rules_are_untouched(self):
        tone = text('tone_view.js')
        publish = between(tone, '  function publishTarget(', '  function observeController(')
        self.assertIn("choices: steer ? steer.nams.map(named) : [], target: steer && steer.target ? named(steer.target) : null,", publish)
        self.assertIn("ask: !!steer?.ask && !bound, none: !!steer?.none, held: !!steer?.held,", publish)
        self.assertIn("'This preset has no NAM block: add one to hear a tone here.'", publish)
        run = between(tone, '  function run(request) {', '      if (!active.bound || active.quarantined || !atTarget()')
        self.assertIn("request.action !== 'bind' && request.action !== 'target'", run)
        self.assertIn("if (request.action === 'target') return chooseTarget(request);", run)
        # a preset load forgets the choice and the hold
        self.assertIn('previewHold = null; steerClick = null; steerAside = false; steerSeen = undefined;', tone)
        # the selection-change clean-up and atTarget are as they were
        self.assertIn("invalidate('selection-changed');", between(tone, 'function observeController(', 'function openBrowser('))
        self.assertIn('active.controller.equals(selectedController)', between(tone, 'function atPosition(', 'function atTarget('))
        api = between(tone, 'return { openBrowser,', 'cursorBlock: () => {')
        self.assertIn('steerPreview: reading =>', api)
        self.assertIn('pagePick: pick =>', api)

    def test_the_workbench_reads_its_own_block_and_picks_go_page_only_while_held(self):
        script = text('focus_view.js')
        refresh = between(script, 'function refresh(window) {', '  function focusSteer(cursor) {')
        self.assertIn('const {shown, steerTo} = focusSteer(cursor);', refresh)
        self.assertIn('focusValues(peek, known, shown, parameters, namEngines)', refresh)
        self.assertIn('state = focusSnapshot(peek, shown, parameters, namEngines);', refresh)
        self.assertIn("else if (steerTo) chainClick(steerTo, 'preview-select');", refresh)
        steer = between(script, '  function focusSteer(cursor) {', '  function select(target) {')
        self.assertIn("known.filter(block => namEngines.includes(block.model) && /^block\\d{1,2}$/.test(block.id))", steer)
        select = between(script, '  function select(target) {', '  function chainClick(target, stage) {')
        self.assertIn('toneView.pagePick({dsp: target.dsp, id: target.id})', select)
        self.assertIn("stage: 'select-page-only'", select)
        self.assertLess(select.index('pagePick'), select.index("chainClick(target, 'select');"))

    def test_the_tray_asks_and_names_the_block_and_the_head_marks_it(self):
        page = text('workbench.html')
        tray = between(page, 'function drawTray() {', 'function libraryRow(')
        # (T1, 2026-11-25: the question is the Plays on row's line, the row always at the top)
        self.assertIn("el('div', 'askline', 'Which block should play it? Click one.')", tray)
        self.assertIn("if (!on) tile.onclick = () => ask('tray', {do: 'target', dsp: c.dsp, id: c.id});", tray)
        self.assertIn("'This preset has no NAM block: add one to hear a tone here.'", tray)
        self.assertIn("title(aim) + ', Path ' + (aim.dsp + 1)", tray)
        self.assertLess(tray.index('Which block should play it?'), tray.index('if (playing) {'))
        mini = between(page, 'function miniButton(block, now) {', 'function drawMini() {')
        self.assertIn("(target ? ' tgt' : '')", mini)
        self.assertIn('.mini button.tgt { box-shadow: 0 0 0 2px #b070e0;', page)
        self.assertIn("toneTray = message.data || null; shownTray = ''; drawTray(); drawMini(); drawChain(); return;", page)

    def test_the_choice_travels_from_the_tray_and_the_strip(self):
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("preview.tone_action(f\"target:{value['dsp']}:{value['id']}\")", launcher)
        preview = text('tone_preview.py')
        self.assertIn(r"re.fullmatch(r'keep:\d{1,6}|save:\d{1,6}:\d{1,3}|end|target:[01]:block\d{1,2}|model:\d{1,12}', action)", preview)
        self.assertIn("reply = self.command(session, 'target', dsp=int(dsp), block=block)", preview)
        self.assertIn("'ask': bool(state.get('ask')), 'none': bool(state.get('none')),", preview)
        strip = text('tone_browser.cs')
        # (T3, 2026-11-25: the strip's menu went; the Plays on row is the one place to choose)
        self.assertNotIn('ShowTargetMenu', strip)
        self.assertNotIn('ContextMenuStrip', strip)
        self.assertIn('else if (IsSideAction(action)) SendAction(action);', strip)

    def test_tone_action_takes_a_target_only_in_its_shape(self):
        sys.path.insert(0, str(ROOT))
        from tone_preview import TonePreview
        put = []
        fake = type('B', (), {'actions': type('Q', (), {'put': lambda self, v: put.append(v)})()})()
        preview = TonePreview.__new__(TonePreview)
        preview.workbench, preview.bounds_override, preview.browser = False, (0, 0, 10, 10), fake
        self.assertTrue(preview.tone_action('target:1:block3'))
        for bad in ('target:2:block3', 'target:0:split', 'target:0:block123', 'target:0:block1;end'):
            self.assertFalse(preview.tone_action(bad))
        self.assertEqual(put, ['target:1:block3'])


class PreviewLiveFixTests(unittest.TestCase):
    """The live check of 671e369 (2026-11-25 15:4x, owner-trials 20261125-154143-d7fe4b41): F1 a Workbench knob turn
    ended the preview, F2 the tray's card stayed on "Playing on", F3 "Select a NAM block" with a block chosen, F4 Undo
    right after a preview left the block on the emptied slot 128."""

    def test_f1_the_refresh_write_is_only_for_the_block_hx_edit_has_selected(self):
        script = text('focus_view.js')
        finish = between(script, '  function finish(target, dsp, id, key, value) {', '\n  }\n')
        self.assertIn("targetBinding.peekGlobal(target, 'global', '@cursor_dsp') === dsp && targetBinding.peekGlobal(target, 'global', '@cursor_group') === id", finish)
        self.assertIn("stage: 'refresh-skipped'", finish)
        self.assertLess(finish.index("stage: 'refresh-skipped'"), finish.index("setValue(target, dsp, id, key, value, 'refresh')"))
        binding = text('target_binding.js')
        self.assertIn('refresh: 0x40000000', binding)

    def test_f1_hx_edits_setter_moves_its_cursor_only_with_the_refresh_flag(self):
        exe = Path(r'E:\Dev\HelixNam\research\hx-edit-nam-review\floor-port\navigation-build-20261112\live\app\HX Edit.exe')
        if not exe.is_file():
            self.skipTest('HX Edit.exe is not here')
        data = exe.read_bytes()
        # (0x5178c0 + image base 0x400000; .text: file offset = rva - 0x1000 + 0x400)
        at = lambda rva: data[rva - 0x1000 + 0x400:]
        self.assertTrue(at(0x5178c0).startswith(bytes.fromhex('558bec6aff')))
        # flags & 0x40000000 kept at [ebp-0x34] ...
        self.assertTrue(at(0x5178f0).startswith(bytes.fromhex('8bc1250000')))
        # ... and the "@cursor_dsp" write is behind "cmp [ebp-0x34], 0; je" (0x518108)
        self.assertTrue(at(0x518108).startswith(bytes.fromhex('837dcc00')))
        self.assertEqual(at(0x5181d0)[:5], bytes.fromhex('68742fcb00'))      # push "@cursor_dsp"

    def test_f2_an_ended_preview_ends_the_trays_card_and_the_strip_keeps_the_blocks_name(self):
        tone = text('tone_view.js')
        self.assertIn('active.previewEnds = (active.previewEnds || 0) + 1;', tone)
        self.assertIn('ends: active.previewEnds || 0,', between(tone, '  function publishTarget(', '  function observeController('))
        preview = text('tone_preview.py')
        ended = between(preview, "ends = state.get('ends')", "if state.get('version') == self.navigation_state.get('version'):")
        self.assertIn("tray_now['trial'] = None", ended)
        self.assertIn('slot, free_slots, kept = None, [], None', ended)
        self.assertIn('tray_out()', ended)
        piece = between(tone, '  let previewHold = null;', '  function parameterPanel(')
        out = run_js_source(PreviewTargetTests.STUBS + piece, '''(() => {
          const nams = [{dsp: 1, id: 'block2', slot: 10}];
          steerPreview({nams, cursor: {dsp: 1, id: 'block2'}});
          const before = active.steer.target.name;
          steerPreview({nams: [{dsp: 1, id: 'block2', slot: 128}], cursor: {dsp: 1, id: 'block2'}});
          return [before, active.steer.target.name];
        })()''')
        self.assertEqual(out, ['Klon Gain=0', 'Klon Gain=0'])

    def test_f3_a_chosen_block_is_named_not_select_a_nam_block(self):
        tone = text('tone_view.js')
        publish = between(tone, '  function publishTarget(', '  function observeController(')
        self.assertIn("steer?.target ? `Pick a tone to hear it on ${steer.target.name}, Path ${steer.target.dsp + 1}.` :", publish)
        self.assertLess(publish.index('steer?.target ?'), publish.index("'Select a NAM block to audition.'"))
        preview = text('tone_preview.py')
        self.assertIn("text.startswith('Select a NAM block')", preview)
        self.assertIn("nav_said[0] = state.get('text') or ''", preview)

    def test_f4_undo_and_redo_step_over_a_finished_previews_own_steps(self):
        code = ('[focusPreviewSteps({from: 5, to: 7}, 7, 33, true, false), focusPreviewSteps({from: 31, to: 1, tainted: true}, 1, 33, true, false),'
                ' focusPreviewSteps({from: 5, to: 7}, 6, 33, true, false), focusPreviewSteps({from: 5, to: 7}, 5, 33, false, true),'
                ' focusPreviewSteps({from: 5, to: 7}, 5, 33, false, false), focusPreviewSteps({from: 5, to: 20}, 20, 33, true, false),'
                ' focusStepsGone({from: 5, to: 7}, 6, 33), focusStepsGone({from: 5, to: 7}, 9, 33), focusStepsGone({from: 5, to: 7}, 4, 33),'
                ' focusStepsGone({from: 5, to: 7}, 7, 33)]')
        self.assertEqual(run_js(['focus_view.js'], code), [
            {'count': 2, 'tainted': False}, {'count': 3, 'tainted': True}, None, {'count': 2, 'tainted': False}, None, None,
            True, False, True, False])
        script = text('focus_view.js')
        undo = between(script, "} else if (command.action === 'redo' || command.action === 'undo') {", "} else if (command.action === 'splitType') {")
        self.assertIn('const over = previewStepsAt(undoing);', undo)
        self.assertIn('for (let i = 0; i < over.count; i++) step();', undo)
        self.assertIn('if (!over.tainted)', undo)
        self.assertIn("stage: 'undo-preview-steps'", undo)
        tone = text('tone_view.js')
        self.assertIn("previewSteps = {from: origin.undo, to: after, tainted: !!active.previewTainted, context: contextVersion, at: Date.now()};", tone)
        self.assertIn('previewSteps = null;                   // (a new preview', tone)
        self.assertIn('previewSteps: () => previewSteps && previewSteps.context === contextVersion ? {...previewSteps} : null,', tone)


class ToneTargetAlwaysTests(unittest.TestCase):
    """Nick, 2026-11-25 19:15 (mock-up research/modern-ui/reveal/mock-tone-target): the block choice always visible
    (T1), moving a playing preview (T2), one place to choose (T3), the popped window with the same side panel (T4), a
    banner on the chain while a preview plays (T5)."""

    def test_t1_the_plays_on_row_is_always_at_the_top(self):
        page = text('workbench.html')
        tray = between(page, 'function drawTray() {', 'function libraryRow(')
        self.assertIn("plays.append(el('h5', '', 'Plays on'));", tray)
        self.assertIn("'Which block should play it? Click one.'", tray)
        self.assertIn("'This preset has no NAM block: add one to hear a tone here.'", tray)
        self.assertIn("'Picked the wrong one? Click the other block: the preview moves there and this block gets its own capture back.'", tray)
        self.assertIn("if (!on) tile.onclick = () => ask('tray', {do: 'target', dsp: c.dsp, id: c.id});", tray)
        self.assertLess(tray.index("'Plays on'"), tray.index('if (playing) {'))
        self.assertNotIn('if (!playing && t.ask', tray)                  # (not only before a choice any more)
        self.assertIn(".plays .tiles button.on::before { content: '\\25B6  plays here';", page)

    def test_t2_another_block_while_playing_moves_the_preview(self):
        preview = text('tone_preview.py')
        move = between(preview, "if self.navigation and isinstance(action, str) and re.fullmatch(r'target:[01]:block\\d{1,2}', action):",
                       'continue\n            if self.navigation and action in')
        self.assertIn("moving = bool(self.navigation_state.get('preview')) and current is not None", move)
        self.assertLess(move.index("reply = self.command(session, 'end')"),
                        move.index("reply = self.command(session, 'target', dsp=int(dsp), block=block)"))
        self.assertIn('waiting_tone[0] = True', move)
        self.assertIn("if aim.get('dsp') == int(dsp) and aim.get('id') == block:", move)
        audition = between(preview, 'def prepared():', 'message = play(prepared, capture, replace')
        self.assertIn('found = prepared_files.get((key, mode))', audition)
        self.assertIn('if found and Path(found).is_file():', audition)

    def test_t3_one_place_to_choose_and_one_card(self):
        strip = text('tone_browser.cs')
        self.assertNotIn('ShowTargetMenu', strip)
        self.assertNotIn('\\u25BE', strip)
        page = text('workbench.html')
        tray = between(page, 'function drawTray() {', 'function libraryRow(')
        self.assertIn("line.append(eq, 'Playing on ', el('em', '', where), '. Nothing is saved.'", tray)
        self.assertIn("pick.onchange = () => { if (pick.value) ask('tray', {do: 'profile', id: Number(pick.value)}); };", tray)
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("preview.tone_action(f\"model:{value['id']}\")", launcher)
        card = text('tone_card.html')
        self.assertIn('<body $tray>', card)
        self.assertIn("document.querySelector('#keepers').hidden = trial == null || trayMode;", card)
        preview = text('tone_preview.py')
        self.assertIn('visible = tone is not None and not tray', preview)
        self.assertEqual(preview.count('tray=self._in_workbench())'), 6)
        self.assertIn("message = ('Previewing. Nothing is saved yet.' if self.navigation else", preview)

    def test_t4_the_popped_window_has_the_side_panel(self):
        strip = text('tone_browser.cs')
        self.assertIn('const string SideUrl = "https://hx-edit-nam.invalid/side";', strip)
        self.assertIn('int width = windowMode == WindowMode.Floating && sideHtml != null ? SideWidth : 0;', strip)
        self.assertIn('layout.Controls.Add(side, 1, 0);', strip)
        self.assertIn('layout.SetColumnSpan(details, 2);', strip)
        self.assertIn(r'@"^(end|keep:\d{1,6}|save:\d{1,6}:\d{1,3}|target:[01]:block\d{1,2}|model:\d{1,12})$"', strip)
        preview = text('tone_preview.py')
        self.assertIn("browser.send('sidePage', html=SIDE.read_text(encoding='utf-8'))", preview)
        self.assertIn("browser.send('side', data=side)", preview)
        side = text('tone_side.html')
        for words in ("el('h5', '', 'Plays on')", "'Which block should play it? Click one.'", "say('target:' + c.dsp + ':' + c.id)",
                      "say('end')", "say('save:' + t.trial + ':' + free[0])", "say('keep:' + t.trial)", "say('model:' + list.value)",
                      'img-src data:'):
            self.assertIn(words, side)
        self.assertIn("'tone_side.html'", text('build-windows.py'))

    def test_t4_the_side_page_draws_the_same_states(self):
        side = text('tone_side.html')
        script = between(side, '<script>', '</script>')[len('<script>'):]
        dom = '''
class Node { constructor(tag) { this.tag = tag; this.children = []; this.className = ''; this.textContent = ''; this.title = ''; }
  append(...kids) { for (const k of kids) this.children.push(typeof k === 'string' ? {text: k} : k); }
  replaceChildren(...kids) { this.children = []; this.append(...kids); } }
const boxes = {}; const document = {createElement: tag => new Node(tag), querySelector: id => boxes[id] || (boxes[id] = new Node('section'))};
class Option { constructor(text, value) { this.text = text; this.value = value; } }
const window = {};
const words = node => [node.text || '', node.textContent || '', ...(node.children || []).map(words)].join(' ');
'''
        out = run_js_source(dom + script, '''(() => {
          const choices = [{dsp: 0, id: 'block0', name: 'Deluxe Reverb'}, {dsp: 1, id: 'block2', name: 'Jcm800'}];
          const tray = [{key: 'a', name: 'Matchless', state: 'ready', trial: 3, kept: false}];
          const r = {};
          window.hxToneSide({choices, ask: true, target: null, tray: [], trial: 0});
          r.ask = words(boxes['#plays']);
          window.hxToneSide({choices, target: {dsp: 1, id: 'block2'}, tray, trial: 3, free_slots: [29], preview: true});
          r.chosen = words(boxes['#plays']); r.card = words(boxes['#card']);
          r.rings = boxes['#plays'].children[1].children.map(b => b.className.trim());
          window.hxToneSide({none: true, choices: []});
          r.none = words(boxes['#plays']);
          return r;
        })()''')
        self.assertIn('Which block should play it? Click one.', out['ask'])
        self.assertIn('Picked the wrong one?', out['chosen'])
        self.assertEqual(out['rings'], ['', 'on'])
        self.assertIn('Playing on', out['card'])
        self.assertIn('Jcm800, Path 2', out['card'])
        self.assertIn('Load on Floor', out['card'])
        self.assertIn('This preset has no NAM block: add one to hear a tone here.', out['none'])

    def test_t5_the_chain_shows_a_banner_and_a_preview_tag(self):
        page = text('workbench.html')
        banner = between(page, 'function previewBanner() {', 'function dspShare(k) {')
        self.assertIn("words.textContent = 'Previewing ' + p.tone + (p.block ? ' on ' + title(p.block) + ', Path ' + (p.block.dsp + 1) : '');", banner)
        for words in ("'Back to TONE3000'", "'Load on Floor'", "'Keep on this PC'", "'Stop'", "ask('toolFront')",
                      "ask('tray', {do: 'end', trial: p.trial});", "ask('tray', {do: 'keep', trial: p.trial});"):
            self.assertIn(words, banner)
        now = between(page, 'function previewNow() {', 'function previewKey()')
        self.assertIn('if (!t || !t.preview || !state) return null;', now)
        chain = between(page, 'function drawChain(force) {', 'function dspShare(k) {')
        self.assertIn('previewKey()]);', chain)
        self.assertIn('if (banner) head.unshift(banner);', chain)
        tile = between(page, 'const tileOf = (block, place, y) => {', 'return button;')
        self.assertIn("if (pv) { button.classList.add('previewing'); block = previewed.block; }", tile)
        self.assertIn("if (pv) button.append(el('span', 'pvtag', 'PREVIEW'));", tile)
        self.assertNotIn('.tile.pv ', page)                              # (.pv is the presets view's own class)
        self.assertIn('function toneGone() { toneTray = null;', page)
        launcher = text('start-hx-edit-nam.pyw')
        self.assertIn("if name == 'toolFront':", launcher)
        self.assertIn('def front_tool(self):', text('tone_preview.py'))


class ToneTargetLiveFixTests(unittest.TestCase):
    """The live check of 1fedb3b (2026-11-25 20:25-20:28, owner-trials 20261125-202456-d8d1f0e5): G1 the first open's
    tray said "no NAM block", G2 "IR slot 128" for the playing block, G3 a moved preview played on the old block."""

    def test_g1_the_tray_gets_the_sessions_word_at_the_start_and_says_none_only_when_known(self):
        preview = text('tone_preview.py')
        browse = between(preview, '    def browse(self, browser, session, client_id):', '        while (action := browser.next_action()) is not None:')
        self.assertIn("        tray_out()\n\n        if self.initial_look and self.library:", browse)
        handler = between(preview, "if 'navigation' in action:", 'if light is not None and')
        self.assertIn('\n                    tray_out()\n', handler)                     # (every target word, any version)
        page = text('workbench.html')
        tray = between(page, 'function drawTray() {', 'function libraryRow(')
        self.assertIn("if (t.none) plays.append(el('div', 'note2', 'This preset has no NAM block: add one to hear a tone here.'));", tray)
        self.assertIn("else if (!choices.length) plays.append(el('div', 'note2', 'Looking at the preset\\u2019s NAM blocks\\u2026'));", tray)

    def test_g2_a_block_playing_128_keeps_its_own_capture_slot(self):
        tone = text('tone_view.js')
        piece = between(tone, '  let previewHold = null;', '  function parameterPanel(')
        out = run_js_source(PreviewTargetTests.STUBS + 'let selectedController = null; const controllerReady = () => false, block = () => "", releaseTarget = () => {}; let targetVersion = 0;\n' + piece, '''(() => {
          steerPreview({nams: [{dsp: 1, id: 'block2', slot: 10}], cursor: {dsp: 1, id: 'block2'}});
          steerPreview({nams: [{dsp: 1, id: 'block2', slot: 128}], cursor: {dsp: 1, id: 'block2'}});
          return [active.steer.target.name, active.steer.target.own, active.steer.target.slot];
        })()''')
        self.assertEqual(out, ['Klon Gain=0', 10, 128])
        self.assertIn('own: b.own ?? null', between(tone, '  function publishTarget(', '  function observeController('))
        page = text('workbench.html')
        own = between(page, 'function ownBlock(block, choice) {', '\n}\n')
        self.assertIn('if (!block || block.slot !== 128) return block;', own)
        self.assertIn("return c && Number.isInteger(c.own) && c.own !== 128 ? {...block, slot: c.own} : block;", own)
        self.assertIn('const block = ownBlock((state.blocks || []).find(b => same(b, c)), c)', page)          # the tiles
        self.assertIn('return t && state ? ownBlock(', page)                                                   # the card
        self.assertIn('const block = t.target ? ownBlock(', between(page, 'function previewNow() {', 'function previewKey()'))   # the banner
        self.assertIn("if (pv) { button.classList.add('previewing'); block = previewed.block; }", page)         # the chain
        self.assertIn('button.onclick = () => { if (!dragDone) pickBlock(real); };', page)

    def test_g3_the_old_block_is_not_bound_while_steering_to_the_chosen_one(self):
        tone = text('tone_view.js')
        auto = between(tone, '  function autoBindSelected() {', '  function bindSelected(request) {')
        self.assertIn('const aim = toneSession() && active.steer && active.steer.target;', auto)
        self.assertIn('if (aim && !(aim.dsp === selected.controller.add(0x80).readS32() && aim.id === selected.block)) return false;', auto)
        self.assertLess(auto.index('const aim'), auto.index('bindSelectedTarget();'))
        choose = between(tone, '  function chooseTarget(request) {', '\n  }\n')
        self.assertIn('if (active.bound && !sameBlock(now, nam)) {', choose)
        self.assertIn('active.bound = active.valid = false;', choose)
        preview = text('tone_preview.py')
        self.assertIn("if (waiting_tone[0] and state.get('version') == self.navigation_state.get('version') and state.get('bound')", preview)

    def test_back_to_tone3000_goes_through_hx_edit_as_a_reopen_does(self):
        tone = text('tone_view.js')
        front = between(tone, '  function listenFront() {', '  function listenBrowserProcess() {')
        self.assertIn("recv('toneFront'", front)
        self.assertIn('if (active.browserPid) allowForeground(active.browserPid);', front)
        self.assertIn("send({ type: 'toneFocus', session: active.id, page: '' });", front)
        preview = text('tone_preview.py')
        self.assertIn("self.script.post({'type': 'toneFront', 'payload': {'session': self.session}})", preview)


if __name__ == '__main__':
    unittest.main()
