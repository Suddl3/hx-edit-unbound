"""The Workbench's Batch 4 (research/modern-ui/batch4-*.png): the layouts. The chooser in the logo menu, Classic+ (HX
Edit's own arrangement in the new look) and Rig on stage (the gear on its scene): other arrangements of the same page,
state and asks. No editor process, no device."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import workbench  # noqa: E402
from test_focus_view import NODE, run_js  # noqa: E402


def page():
    return (ROOT / 'workbench.html').read_text(encoding='utf-8')


def launcher():
    return (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def js(expression):
    return run_js(['workbench_layout.js'], expression)


class ChooserTests(unittest.TestCase):
    """Stage 1: the chooser in the logo menu, and the layout kept as the editor's own setting."""

    def test_the_layout_is_kept_in_settings_and_anything_else_is_the_workbench(self):
        self.assertEqual(workbench.LAYOUT, 'workbenchLayout')
        self.assertEqual(workbench.layout_of({}), 'workbench')
        self.assertEqual(workbench.layout_of(None), 'workbench')
        for name in ('workbench', 'classicplus', 'stage'):
            self.assertEqual(workbench.layout_of({'workbenchLayout': name}), name)
            self.assertEqual(workbench.checked_layout(name), name)
        for bad in ('classic', 'Classic+', '', None, 3, ['stage'], {'x': 1}):
            self.assertEqual(workbench.layout_of({'workbenchLayout': bad}), 'workbench')
            self.assertIsNone(workbench.checked_layout(bad))

    def test_the_launcher_keeps_the_choice_and_tells_the_page(self):
        text = launcher()
        handler = between(text, "if name == 'layout':", "if name == 'menu':")
        for piece in ('choice = checked_layout(value)', 'nam_catalog.save_setting(LAYOUT, choice)', 'workbench.show_options(menu_options())'):
            self.assertIn(piece, handler)
        self.assertIn("'layout': layout_kept(),", text)
        kept = between(text, 'def layout_kept():', 'def menu_options():')
        self.assertIn('return layout_of(nam_catalog.load_settings())', kept)
        self.assertIn("return 'workbench'", kept)                                  # (unreadable: the default)
        self.assertIn('checked_layout', between(text, 'from workbench import (LAYOUT,', ')'))
        # Classic stays HX Edit's own screen: the Workbench switched off, the layout setting untouched
        menu = between(text, "if name == 'menu':", "elif name == 'failed':")
        self.assertIn("if choice == 'classic':\n                        workbench_mode(False)", menu.replace('\r\n', '\n'))
        self.assertNotIn('LAYOUT', menu)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_only_a_built_layout_is_shown_and_an_unknown_one_falls_back(self):
        built = js('Object.keys(WORKBENCH_LAYOUTS).filter(k => WORKBENCH_LAYOUTS[k].built)')
        self.assertIn('workbench', built)
        for name in ('workbench', 'classicplus', 'stage'):
            self.assertEqual(js(f'workbenchLayoutOf({json.dumps(name)})'), name if name in built else 'workbench')
        for bad in ('classic', 'toString', '__proto__', '', None, 7):
            self.assertEqual(js(f'workbenchLayoutOf({json.dumps(bad)})'), 'workbench')

    def test_the_chooser_is_the_mock_up(self):
        menu = between(page(), 'function openMenu() {', 'function closeMenu() {')
        for words in ("card('workbench', 'A rail of tools, a big chain, knobs underneath.', 'Default',",
                      "card('classicplus', 'HX Edit’s own arrangement in the new look: lists on the left, the model list and sliders below.'",
                      "card('stage', 'Your gear standing on its scene, as Focus Mode shows it, with the controls docked below.'",
                      "card('classic', 'HX Edit exactly as Line 6 made it.', '', () => ask('menu', 'classic'))",
                      "el('p', 'same', 'Every layout has the same tools and does the same things. Focus Mode is the same from all of them.')",
                      "item(\"Show HX Edit's menu bar\""):
            self.assertIn(words, menu)
        # a layout not built yet: "later", and it cannot be picked; the one shown has the tick
        self.assertIn("if (!ready) { head.append(el('em', '', 'later')); button.disabled = true; }", menu)
        self.assertIn("if (on) button.insertAdjacentHTML('beforeend', TICK);", menu)
        self.assertIn("const LAYOUT_NAMES = {workbench: 'Workbench', classicplus: 'Classic+', stage: 'Rig on stage', classic: 'Classic'};", page())
        # the order of the cards, as drawn
        order = [menu.index(f"card('{k}',") for k in ('workbench', 'classicplus', 'stage', 'classic')]
        self.assertEqual(order, sorted(order))

    def test_a_switch_is_instant_and_keeps_the_pages_own_state(self):
        text = page()
        switch = between(text, 'function setLayout(name, mine) {', '// ---- Rig on stage')
        self.assertIn('const next = workbenchLayoutOf(name);', switch)
        self.assertIn("ask('layout', next)", switch)
        self.assertIn('commitView(workbenchSwitch(view, layout), true);', switch)
        # nothing of the preset, the selected block, a rename or the unsaved mark is touched; nothing restarts
        for kept in ('pendingName', 'naming', 'savedMark', 'state', "ask('select'", "ask('menu'", 'snapHeld', 'pending ='):
            self.assertNotIn(kept, switch.replace('picking', ''))
        # the kept layout comes with the options; an answer crossing a newer pick is not followed
        receive = between(text, "else if (message.type === 'options') {", 'drawRail(); return;')
        self.assertIn('setLayout(options.layout, false)', receive)
        self.assertIn("layoutAsked && Date.now() - layoutAsked.at < 2000 && options.layout !== layoutAsked.name", receive)
        self.assertIn('<div class="app lay-workbench" id="app">', text)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_what_is_open_moves_where_the_new_layout_has_a_place_for_it(self):
        switch = lambda view, to: js(f'workbenchSwitch({json.dumps(view)}, {json.dumps(to)})')
        none = {'drawer': '', 'half': '', 'full': ''}
        # to Classic+: its sidebar always shows a list (the Presets tab first), the rest stays
        self.assertEqual(switch(none, 'classicplus'), {**none, 'drawer': 'presets'})
        self.assertEqual(switch({**none, 'drawer': 'captures'}, 'classicplus'), {**none, 'drawer': 'captures'})
        self.assertEqual(switch({**none, 'half': 'look'}, 'classicplus'), {**none, 'drawer': 'presets', 'half': 'look'})
        self.assertEqual(switch({**none, 'full': 'library'}, 'classicplus'), {**none, 'drawer': 'presets', 'full': 'library'})
        # back to the Workbench: a list and a lower-half tool are never open together there (the tool stays)
        self.assertEqual(switch({**none, 'drawer': 'irs', 'half': 'level'}, 'workbench'), {**none, 'half': 'level'})
        self.assertEqual(switch({**none, 'drawer': 'irs'}, 'workbench'), {**none, 'drawer': 'irs'})
        self.assertEqual(switch({**none, 'full': 'presets', 'drawer': 'irs'}, 'workbench'), {**none, 'full': 'presets', 'drawer': 'irs'})
        # to the stage: no lower half there, a tool opens as its full view; a list stays a glass drawer
        self.assertEqual(switch({**none, 'half': 'look'}, 'stage'), {**none, 'full': 'look'})
        self.assertEqual(switch({**none, 'half': 'level', 'drawer': ''}, 'stage'), {**none, 'full': 'level'})
        self.assertEqual(switch({**none, 'drawer': 'captures'}, 'stage'), {**none, 'drawer': 'captures'})
        self.assertEqual(switch({**none, 'full': 'tone'}, 'stage'), {**none, 'full': 'tone'})
        # and back from the stage: its full view stays full
        self.assertEqual(switch({**none, 'full': 'look'}, 'workbench'), {**none, 'full': 'look'})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_which_things_show_where_in_each_layout(self):
        places = lambda layout, view: js(f'workbenchPlaces({json.dumps(layout)}, {json.dumps(view)})')
        v = {'drawer': 'captures', 'half': '', 'full': ''}
        self.assertEqual(places('workbench', v), {'rail': 'rail', 'sidebar': False, 'drawer': 'captures', 'half': '', 'full': '', 'chain': True})
        self.assertEqual(places('classicplus', v), {'rail': 'side', 'sidebar': True, 'drawer': 'captures', 'half': '', 'full': '', 'chain': True})
        self.assertEqual(places('stage', v), {'rail': 'glass', 'sidebar': False, 'drawer': 'captures', 'half': '', 'full': '', 'chain': True})
        full = {'drawer': 'presets', 'half': '', 'full': 'library'}
        self.assertEqual(places('workbench', full)['drawer'], '')                      # a full view covers the drawer
        self.assertEqual(places('classicplus', full)['drawer'], 'presets')             # Classic+'s sidebar stays
        self.assertEqual(places('stage', full)['drawer'], '')
        for layout in ('workbench', 'classicplus', 'stage'):
            self.assertFalse(places(layout, full)['chain'])
        self.assertEqual(places('stage', {'drawer': '', 'half': 'look', 'full': ''})['half'], '')
        self.assertEqual(places('classicplus', {'drawer': 'irs', 'half': 'look', 'full': ''})['half'], 'look')

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_each_layouts_rules_for_opening_and_closing(self):
        steps = lambda layout, seq: js('(() => { let v = {drawer: "", half: "", full: ""}; const out = [];'
                                       f' for (const [a, n] of {json.dumps(seq)}) {{ v = workbenchView(v, a, n, {json.dumps(layout)}); out.push([v.drawer, v.half, v.full]); }}'
                                       ' return out; })()')
        seq = [['rail', 'captures'], ['rail', 'captures'], ['rail', 'presets'], ['rail', 'look'], ['close', 'presets'], ['escape', '']]
        # the Workbench as before: a second click closes the drawer; a lower-half tool closes the drawer
        self.assertEqual(steps('workbench', seq), [['captures', '', ''], ['', '', ''], ['presets', '', ''], ['', 'look', ''], ['', 'look', ''], ['', '', '']])
        self.assertEqual(steps(None, seq), steps('workbench', seq))
        # Classic+: the sidebar's tab stays (a second click, a tool under the chain, Close); Esc closes the tool
        self.assertEqual(steps('classicplus', seq), [['captures', '', ''], ['captures', '', ''], ['presets', '', ''], ['presets', 'look', ''], ['presets', 'look', ''], ['presets', '', '']])
        # the stage: Floor look and Levels open full (no shrink there), the drawers as in the Workbench
        self.assertEqual(steps('stage', [['rail', 'look'], ['shrink', ''], ['rail', 'level'], ['rail', 'irs'], ['rail', 'irs']]),
                         [['', '', 'look'], ['', '', ''], ['', '', 'level'], ['irs', '', ''], ['', '', '']])
        self.assertEqual(js('workbenchSizes("stage").look'), ['full'])
        self.assertEqual(js('workbenchSizes("classicplus")'), js('WORKBENCH_SIZES'))
        self.assertTrue(js('workbenchRailOn({drawer: "presets", half: "", full: "library"}, "presets", "classicplus")'))
        self.assertFalse(js('workbenchRailOn({drawer: "presets", half: "", full: "library"}, "presets", "workbench")'))

    def test_the_page_draws_every_frame_with_the_layouts_rules(self):
        text = page()
        self.assertIn('const next = workbenchView(view, action, name, layout);', text)
        self.assertIn('more = workbenchSizes(layout)[full].length > 1', text)
        self.assertIn('workbenchRailOn(view, name, layout)', text)


SLIDER = '''(() => {
  const sent = [];
  globalThis.catalog = {controls: {}}; globalThis.state = {values: {Drive: 0.5, Time: 0.5, TempoSync1: false, SyncSelect1: 6}};
  globalThis.ask = (name, value) => sent.push([name, value.key, value.phase, Math.round(value.value * 100) / 100]);
  globalThis.requestAnimationFrame = f => f();
  const make = cls => {
    const dial = {classList: {contains: c => c === cls}, getBoundingClientRect: () => ({left: 100, width: 200}), setPointerCapture() {}};
    return {dial, el: {querySelector: s => s === '.dial, .track' ? dial : null, classList: {add() {}, remove() {}}}};
  };
  const block = {dsp: 0, id: 'block1'};
  const out = {};
  %s
  return out;
})()'''


class ClassicPlusTests(unittest.TestCase):
    """Stage 2: Classic+, HX Edit's own arrangement: the sidebar, the chain across the top, the Edit area with the model
    list in place of the picker and the controls as sliders."""

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_classic_plus_is_built_and_offered(self):
        self.assertTrue(js('WORKBENCH_LAYOUTS.classicplus.built'))
        self.assertEqual(js('workbenchLayoutOf("classicplus")'), 'classicplus')

    def test_the_lists_in_place_are_the_pickers_own_choices_and_asks(self):
        text = page()
        shared = between(text, 'function pickChoices(block) {', 'function drawPicker(block) {')
        picker = between(text, 'function drawPicker(block) {', "// ---- Classic+'s Edit area")
        edit = between(text, 'function drawEdit(block) {', 'function editTabs(enabled) {')
        # one list of choices, one way to pick: the picker draws cards, Classic+ rows
        for piece in ('pickChoices(', 'pickCategoryRows(', 'pickHead(', 'pickItems('):
            self.assertIn(piece, picker)
            self.assertIn(piece, edit)
        self.assertIn("pickChoice(block, s, item, 'card')", picker)
        self.assertIn("pickChoice(target, s, item, 'row')", edit)
        # the asks: the same as the picker's always were (a model, a capture, an add at the "+" picked)
        pick = between(text, 'function pickModel(block, symbol) {', '// The choices shown')
        self.assertIn("chainAsk('add', {dsp: block.dsp, lane: block.lane, place: block.place, symbol});", pick)
        self.assertIn("ask('model', {dsp: block.dsp, id: block.id, symbol});", pick)
        self.assertIn("chainAsk('add', {dsp: block.dsp, lane: block.lane, place: block.place, slot: c.slot});", pick)
        self.assertIn("ask('capture', {dsp: block.dsp, id: block.id, slot: c.slot});", pick)
        self.assertIn('item.symbol ? pickModel(block, item.symbol) : pickCapture(block, item.capture);', shared)
        # the same DSP room check: the room line, a choice that does not fit marked "full"
        self.assertIn('space: room(block)', shared)
        self.assertIn('full = !inUse && !!space && Number.isFinite(cost) && cost > space.left + 1e-6;', shared)
        self.assertEqual(text.count("ask('model',"), 1)
        self.assertEqual(text.count("ask('capture',"), 2)                           # (and the Captures drawer's swap, as before)
        # in Classic+ the panel is the Edit area; Change capture / model go to the lists, no dialog opens
        self.assertIn("if (layout === 'classicplus') { drawEdit(block); return; }", text)
        opener = between(text, 'function openPicker(tab) {', 'function closePicker() {')
        self.assertIn("if (layout !== 'classicplus') picking = {block: true};", opener)
        self.assertIn('if (picking && picking.block && layout === \'classicplus\') picking = false;', text)
        # the lists follow the block picked (its own category), and Remove block is there as in the picker
        self.assertIn('if (!target.isPlace) pickHome(target);', text)
        self.assertIn("if (found.remove) rows.append(el('hr'), found.remove);", edit)
        # the Edit area's tabs: Edit | Bypass and controllers | Snapshot values, the Workbench's own tabs' views
        self.assertIn("[['controls', 'Edit'], ['bypass', 'Bypass and controllers'], ['snaps', 'Snapshot values']]", text)
        self.assertIn("body = tab === 'bypass' ? bypassView(target, list) : snapshotView(target, list);", edit)
        # an input, an output, the split and the mixer: their own card (routing, the split's type) beside the sliders
        self.assertIn('} else body.append(card(target, false), editParams(target, list));', edit)

    def test_every_control_of_the_knob_panel_is_a_slider_or_its_own_widget(self):
        text = page()
        row = between(text, 'function sliderRow(p) {', '\n}\n')
        self.assertIn("if (isList(p)) {", row)                                          # a list: its drop-down, as the knob panel's
        self.assertIn('choices(p).forEach(([value, name]) => pick.append(new Option(name, String(value))));', row)
        self.assertIn("} else if (p.kind === 'switch') {", row)                         # a switch: a switch
        self.assertIn("const track = el('div', 'track');", row)                         # the rest: a slider
        self.assertIn("if (p.sync) { const sync = el('button', 'sync', 'Sync');", row)  # a time with its tempo sync
        self.assertIn("if (c && c.controller === 19) { const mark = el('i', 'snapmark', 'S');", row)   # moved by snapshots
        params = between(text, 'function editParams(block, list) {', 'function sliderRow(p) {')
        # every control the knob panel has (controlsOf), wired the same way (wireControl, setValue for a list)
        self.assertIn("if (isList(p)) { const pick = item.querySelector('select'); pick.onchange = () => { setValue(block, p.id, Number(pick.value), 'single'); pick.blur(); fill(item, p); }; }", params)
        self.assertIn('else wireControl(item, p, block, () => fill(item, p));', params)
        self.assertIn('list = target.isPlace ? [] : controlsOf(target)', text)
        fill = between(text, 'function fill(item, p) {', 'function card(block, picker) {')
        self.assertIn("const track = item.querySelector('.track');", fill)
        self.assertIn("track.querySelector('i').style.width = at; track.querySelector('u').style.left = at;", fill)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_slider_is_the_knob_laid_flat(self):
        # a press on the track goes there (a drag of its own: begin, move, end = one undo step), a drag follows the
        # pointer along it, and the wheel is left to the list
        flat = run_js(['pane_controls.js'], SLIDER % '''
          const {dial, el} = make('track'), p = {id: 'Drive', min: 0, max: 1, default: 0.5};
          wireControl(el, p, block, () => {});
          dial.onpointerdown({button: 0, clientX: 150, clientY: 0, pointerId: 1});
          dial.onpointermove({clientX: 250, clientY: 0});
          dial.onpointerup();
          out.sent = sent.splice(0); out.wheel = typeof dial.onwheel;
          dial.onkeydown({key: 'ArrowRight', shiftKey: false, preventDefault() {}});
          out.key = sent.splice(0).map(s => s[2]);
          dial.ondblclick(); out.back = sent.splice(0);''')
        self.assertEqual(flat['sent'], [['set', 'Drive', 'begin', 0.5], ['set', 'Drive', 'move', 0.25], ['set', 'Drive', 'move', 0.75], ['set', 'Drive', 'end', 0.75]])
        self.assertEqual(flat['wheel'], 'undefined')
        self.assertEqual(flat['key'], ['begin', 'move'])
        self.assertEqual(flat['back'], [['set', 'Drive', 'single', 0.5]])
        # the dial as it was: a press alone changes nothing, a vertical drag turns it
        dial = run_js(['pane_controls.js'], SLIDER % '''
          const {dial, el} = make('dial'), p = {id: 'Drive', min: 0, max: 1};
          wireControl(el, p, block, () => {});
          dial.onpointerdown({button: 0, clientX: 150, clientY: 100, pointerId: 1});
          out.press = sent.length;
          dial.onpointermove({clientX: 150, clientY: 81});
          dial.onpointerup();
          out.sent = sent.splice(0); out.wheel = typeof dial.onwheel;''')
        self.assertEqual(dial['press'], 0)
        self.assertEqual(dial['sent'], [['set', 'Drive', 'begin', 0.5], ['set', 'Drive', 'move', 0.6], ['set', 'Drive', 'end', 0.6]])
        self.assertEqual(dial['wheel'], 'function')
        # a time that follows the tempo: the slider sets the note
        synced = run_js(['pane_controls.js'], SLIDER % '''
          state.values.TempoSync1 = true;
          catalog.controls.sync_note = {format: ['1/1', '1/2', '1/4', '1/8']};
          const {dial, el} = make('track'), p = {id: 'Time', min: 0, max: 1, sync: {switch: 'TempoSync1', note: 'SyncSelect1', min: 6}};
          wireControl(el, p, block, () => {});
          dial.onpointerdown({button: 0, clientX: 300, clientY: 0, pointerId: 1});
          dial.onpointerup();
          out.sent = sent.splice(0);''')
        self.assertEqual(synced['sent'][-1], ['set', 'SyncSelect1', 'end', 9])

    def test_the_sidebar_holds_the_drawers_and_the_tools_box(self):
        text = page()
        self.assertIn('<div class="side" id="side">', text)
        side = between(text, '<div class="side" id="side">', '</div>\n')
        for piece in ('id="rail"', 'id="drawer"', '<div class="toolbox" id="toolbox"'):
            self.assertIn(piece, side.replace('\r\n', '\n'))
        rail = between(text, 'function drawRail() {', 'function drawDrawer() {')
        self.assertIn("$('toolbox').hidden = layout !== 'classicplus';", rail)
        self.assertIn("button('presets', 'Presets', 'presets', '', 'The setlist’s presets'),", rail)
        # the tools box: TONE3000, Floor look, Levels, Library, opening as they do in the Workbench (the same setView)
        for tool in ("button('tone', 'TONE3000'", "button('look', 'Floor look'", "button('level', 'Levels'", "button('library', 'Library'"):
            self.assertIn(tool, rail[:rail.index("$('rail').setAttribute('aria-label', 'Library');")])
        self.assertEqual(rail.count("b.onclick = () => setView('rail', name);"), 1)
        self.assertIn("const box = $('drawer'), drawer = workbenchPlaces(layout, view).drawer, kind = DRAWERS[drawer];", text)

    def test_the_chain_is_the_workbenchs_own_drawn_smaller_with_the_dsp_meters_over_it(self):
        text = page()
        self.assertIn("classicplus: {YA: 36, YB: 136, TILE_H: 84, TILE_TOP: 34, TILE_W: 105, TAG: 0}", text)
        chain = between(text, 'function drawChain(force) {', 'function dspShare(k) {')
        self.assertIn("const head = layout === 'classicplus' ? [flowHead()]", chain)
        self.assertIn('paths.map(p => drawPath(p, geometry(width), now))', chain)       # the same paths, drags and asks
        head = between(text, 'function flowHead() {', 'function drawPath(')
        self.assertIn("head.append(el('span', '', 'Signal flow'), el('span', 'sp'));", head)
        self.assertIn("item.append('DSP ' + (k + 1) + ' ',", head)

    def test_no_new_text_in_capitals(self):
        css = between(page(), '/* ================= Batch 4: the layouts', '</style>')
        self.assertNotIn('uppercase', css)
        script = page()[page().index('// ---- the layouts (Batch 4)'):]
        self.assertFalse(re.search(r"'[A-Z]{4,}[ ']", between(page(), '// The picker\'s choices for a block, shared', '// ---- the top bar')))


class StageTests(unittest.TestCase):
    """Stage 3: Rig on stage, the chain's gear on the preset's scene, a glass rail and drawers, the block's dock."""

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_rig_on_stage_is_built_and_offered(self):
        self.assertTrue(js('WORKBENCH_LAYOUTS.stage.built'))
        self.assertEqual(js('workbenchLayoutOf("stage")'), 'stage')

    def test_the_stage_is_the_workbenchs_own_chain_drawn_as_gear(self):
        text = page()
        chain = between(text, 'function drawChain(force) {', 'function dspShare(k) {')
        # the same paths, places, drags and asks; only the sizes and the look are the stage's
        self.assertIn('paths.map(p => drawPath(p, geometry(width), now))', chain)
        self.assertIn("const s = layout === 'stage' ? stageSizes(paths) : CHAIN_SIZES[layout] || CHAIN_SIZES.workbench;", text)
        self.assertIn("layout === 'stage' ? [stageHead()]", chain)
        path = between(text, 'function drawPath(p, g, now) {', '// ---- moving a block')
        self.assertIn("if (layout === 'stage') button.classList.add(...gearClass(block));", path)
        self.assertIn("layout === 'stage' ? image(stagePictures(block), 'pic', false, true) : image(pictures(block), 'pic', true)", path)
        for kept in ('button.onclick = () => { if (!dragDone) pickBlock(block); };', 'button.onpointerdown = event => liftBlock(event, block, button);',
                     'plus.onclick = () => openPlacePicker(p.dsp, lane, place);', "node.onpointerdown = event => liftNode(event, p, 'split', node, g);",
                     "node.onpointerdown = event => liftNode(event, p, 'join', node, g);", 'out.push(io(p.inputB, YB, false));', 'out.push(io(p.outputB, YB, true));'):
            self.assertIn(kept, path)
        self.assertEqual(text.count('function drawPath('), 1)
        self.assertEqual(text.count('function liftBlock('), 1)
        self.assertEqual(text.count('function liftLibrary('), 1)
        # the gear stands on a common line: its picture's height is the stage's, a pedal smaller than an amp
        self.assertIn("board.style.setProperty('--gh', TILE_TOP + 'px');", chain)
        self.assertIn("const STAGE_BIG = new Set(['amp', 'preamp', 'cab'])", text)

    def test_the_stage_fits_the_room_it_has_and_never_lays_out_per_frame(self):
        text = page()
        sizes = between(text, 'function stageSizes(paths) {', 'function stageScene() {')
        self.assertIn('lanes = (paths || []).reduce((n, p) => n + (p.b ? 2 : 1), 0) || 2;', sizes)   # both paths, lane B
        self.assertIn('const H = Math.round(Math.max(52, Math.min(most, room / lanes - 44)));', sizes)
        self.assertIn('return {YA: H + 8, YB: 2 * H + 52, TILE_H: H + 30, TILE_TOP: H, TILE_W: Math.round(Math.max(76, H * 1.15)), TAG: 104};', sizes)
        # pictures sized for what is shown: the large render only when the gear is shown larger than the small picture
        self.assertIn('const big = TILE_TOP * (window.devicePixelRatio || 1) > small;', sizes)
        # drawn again only when its room changes (a ResizeObserver, once a change), its dock first in a render
        self.assertIn("if (layout !== 'stage' || h === boardHeight) { boardHeight = h; return; }", text)
        self.assertIn("if (layout === 'stage') { drawPanel(); drawChain(); } else { drawChain(); drawPanel(); }", text)
        stage = between(text, '// ---- Rig on stage (Batch 4)', '// The chooser')
        self.assertNotIn('setInterval', stage)
        self.assertNotIn('requestAnimationFrame', stage)
        # what does not fit scrolls (nothing is hidden), the dock keeps its height and scrolls inside
        css = between(text, '/* ---- Rig on stage', '</style>')
        self.assertIn('overflow: hidden auto;', css)
        self.assertIn('height: clamp(168px, 26vh, 236px)', css)

    def test_the_scene_is_floor_looks_for_the_preset_and_opens_floor_look(self):
        text = page()
        scene = between(text, 'function stageScene() {', 'const stageKey')
        self.assertIn('const mine = look && presetLook(), whole = mine && usableScene(mine.scene);', scene)
        self.assertIn('if (whole) return whole;', scene)                                                    # the preset's own
        # (R2: else the picked block's own, the preset's or its kind's default (followScene), or the pinned one)
        self.assertIn("if (look) return now && isChain(now) ? blockScene(now).name : defaultSceneOf('default');", text)
        sync = between(text, 'function syncStage() {', 'function stageHead() {')
        self.assertIn("const box = $('stageScene'), on = layout === 'stage' && !!catalog;", sync)               # loaded only on the stage
        self.assertIn('const picture = sc ? sc.pictures[0] : \'\'', sync)                                        # the high-resolution plate first
        head = between(text, 'function stageHead() {', '// The chooser')
        self.assertIn("button.append('Scene: ' + (name ? sceneName(name) : 'none'));", head)
        self.assertIn("button.onclick = () => setView('open', 'look');", head)
        self.assertIn('<div class="scene" id="stageScene" aria-hidden="true" hidden></div>', text)

    def test_the_tools_and_the_dock_are_the_workbenchs_own(self):
        text = page()
        css = between(text, '/* ---- Rig on stage', '</style>')
        # the seven tools in a glass rail, the drawers glass panels over the scene (the stage makes room)
        self.assertIn('.lay-stage .rail {', css)
        self.assertIn('.lay-stage .drawer {', css)
        self.assertIn('.lay-stage.with-drawer > .board { padding-left: 408px; }', css)
        self.assertIn("app.classList.toggle('with-drawer', !!places.drawer);", text)
        # the dock is the block panel (its three tabs, the knobs, the capture), no lower half under a stage
        self.assertIn('.lay-stage > .insp {', css)
        self.assertIn('.lay-stage > .tool { display: none !important; }', css)
        self.assertNotIn("layout === 'stage' && drawPanel", text)
        self.assertIn("(panelTab === 'controls' ? '' : ' tabbed')", text)
        self.assertIn('.lay-stage > .vw {', css)                                                            # the full views

    def test_a_long_name_stays_in_its_own_column(self):
        # Live check 2026-11-24 14:20: an EVH capture's long name ran over its neighbour's label on the stage. A name is
        # cut with an ellipsis at its place's width (the picked one too), the whole name in the title.
        text = page()
        css = between(text, '/* ---- Rig on stage', '</style>')
        label = between(css, '.lay-stage .tile.gear .strip {', '}')
        for rule in ('max-width: var(--col, 120px);', 'white-space: nowrap;', 'overflow: hidden;', 'text-overflow: ellipsis;', 'display: block;'):
            self.assertIn(rule, label)
        self.assertNotIn('max-width: 150%', css)
        self.assertNotIn('max-width', between(css, '.lay-stage .tile.gear.on .strip {', '}'))   # the picked one: the same width
        self.assertIn("grid.style.setProperty('--col', Math.max(60, Math.floor(g.step) - 8) + 'px');", text)
        self.assertIn("button.title = title(block) + (capture(block) ?", text)                    # the gear's title: the whole name
        # the dock's title, Classic+'s block name and capture line: one line, cut, the whole name in the title
        self.assertIn('.lay-stage > .insp .card h4 { font-size: 30px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }', css)
        self.assertIn('.lay-stage > .insp .card { grid-template-columns: minmax(0, 1fr); }', css)
        self.assertIn("head.append(el('h4', '', title(block))); head.firstChild.title = title(block);", text)
        self.assertIn('.params .capline b { color: var(--ink); font-weight: 600; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }', text)
        self.assertIn('name.title = title(block);', text)
        self.assertIn('line.title = taken.name;', text)
        # already cut: Classic+'s chain names (the Workbench's strip), its list rows, the drawers' rows
        for rule in ('.tile .strip { width: calc(100% + 10px);', '.mrow span { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
                     '.caprow b { display: block; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'):
            self.assertIn(rule, text)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_floor_look_and_levels_open_full_on_the_stage(self):
        steps = js('(() => { let v = {drawer: "", half: "", full: ""}; const out = [];'
                   ' for (const [a, n] of [["open", "look"], ["back", ""], ["rail", "level"], ["escape", ""], ["rail", "presets"], ["expand", "presets"]])'
                   ' { v = workbenchView(v, a, n, "stage"); out.push([v.drawer, v.half, v.full]); } return out; })()')
        self.assertEqual(steps, [['', '', 'look'], ['', '', ''], ['', '', 'level'], ['', '', ''], ['presets', '', ''], ['presets', '', 'presets']])



class LiveCheckTests(unittest.TestCase):
    """The faults the live check of 2026-11-24 (~16:50, preset 032) found in the two new layouts."""

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_split_or_mixer_note_has_only_the_room_inside_the_chains_box(self):
        # 032: a split at Path 1's first place put "Split Y / evenly to lanes A and B" out over Classic+'s sidebar. The
        # split's note ends left of the split: the row up to there plus the path label's column; under 40 px it is left out.
        rooms = js('[workbenchNoteRoom("split", 74, 900, 0), workbenchNoteRoom("split", 74, 900, 88), workbenchNoteRoom("split", 74, 900, 104),'
                   ' workbenchNoteRoom("split", 180.6, 900, 0), workbenchNoteRoom("split", 50, 900, 0),'
                   ' workbenchNoteRoom("join", 700, 900, 88), workbenchNoteRoom("join", 860, 900, 88), WORKBENCH_NOTE_GAP, WORKBENCH_NOTE_LEAST]')
        self.assertEqual(rooms, [54, 142, 158, 160, 0, 180, 0, 20, 40])

    def test_the_notes_wrap_to_their_room_in_every_layout(self):
        text = page()
        chain = between(text, 'function drawPath(', '// ---- moving a block')
        self.assertIn("room = workbenchNoteRoom('split', g.gap(from), g.width, TAG);", chain)
        self.assertIn("room = workbenchNoteRoom('join', g.gap(to), g.width, TAG);", chain)
        # the split's note is placed by the split itself (its right end there), not by the row's width: on the stage
        # with a drawer open the row can be wider than the board, and a note set from the right moved under the drawer
        self.assertIn("note.style.cssText = `left:${g.gap(from) - WORKBENCH_NOTE_GAP}px;top:${YB}px;max-width:${room}px`;", chain)
        self.assertIn("note.style.cssText = `left:${g.gap(to) + WORKBENCH_NOTE_GAP}px;top:${YB}px;max-width:${room}px`;", chain)
        self.assertNotIn('right:${g.width - g.gap(from)', chain)
        self.assertEqual(chain.count('out.push(node); if (room) out.push(note);'), 2)
        self.assertIn("note.title = model(p.split).name + ': ' + words;", chain)
        self.assertIn("note.title = 'Mixer: ' + words;", chain)
        self.assertIn('.note { position: absolute; display: grid; gap: 1px; line-height: 1.2; width: max-content; white-space: normal; overflow-wrap: break-word;', text)
        self.assertIn('.note.r { text-align: right; transform: translateX(-100%); }', text)
        self.assertNotIn('.note { position: absolute; display: grid; gap: 1px; line-height: 1.2; white-space: nowrap;', text)
        # the path label's column is each layout's own (none in Classic+, where the label is hidden)
        self.assertIn('TAG = s.TAG || 0;', text)
        self.assertIn('classicplus: {YA: 36, YB: 136, TILE_H: 84, TILE_TOP: 34, TILE_W: 105, TAG: 0}', text)
        self.assertIn('.lay-classicplus .path .tag { display: none; }', text)

    def test_a_bypassed_gear_stays_grey_while_hovered(self):
        # The hover's brightness rule outranked the bypassed look: a bypassed pedal lit up as if it were on.
        css = between(page(), '/* ---- Rig on stage', '</style>')
        hover, off = '.lay-stage button.tile.gear:hover .pic {', '.lay-stage .tile.gear.off .pic {'
        both = '.lay-stage button.tile.gear.off:hover .pic {'
        self.assertIn(hover, css)
        self.assertIn(off, css)
        rule = between(css, both, '}')
        self.assertIn('grayscale(.85)', rule)
        self.assertIn('brightness(.6)', rule)                         # a slight lift over the bypassed .5, not the 1.12
        self.assertGreater(css.index(both), css.index(off))           # (and more specific than both: classes + :hover + .off)



# A made-up chain for the add tests: path 1 with Kinky Boost (block0, picked) and a NAM block, place 3 of lane A empty.
ADD = """(() => {
  const NAM = 'HD2_NAM', IR = 'HD2_ImpulseResponse1024';
  const base = [{dsp: 0, id: 'block0', model: 'HD2_DistKinkyBoost', position: 0, path: 0},
                {dsp: 0, id: 'block1', model: NAM, position: 1, path: 0, slot: 17}];
  const reading = (extra, selected, preset) => ({blocks: base.concat(extra || []), selected: selected === undefined ? {dsp: 0, id: 'block0'} : selected,
                                               preset: preset === undefined ? {setlist: 0, number: 32} : preset});
  const step = (follow, s, now) => workbenchAddSelect(follow, s, NAM, now === undefined ? 1000 : now);
  return (%s)();
})()"""


class AddPicksTheNewBlockTests(unittest.TestCase):
    """After a "+" add the new block is the picked one (Nick, 2026-11-24), in every layout and for every way to add."""

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_each_way_to_add_picks_the_block_once_hx_edit_shows_it(self):
        out = js(ADD % """() => {
          const ways = {model: {dsp: 0, lane: 0, place: 2, symbol: 'HD2_DelaySimpleDelay'},   // the picker / Classic+'s model list
                        capture: {dsp: 0, lane: 0, place: 2, slot: 21},                       // a capture: the picker, the list or the drawer
                        ir: {dsp: 0, lane: 0, place: 2, symbol: IR, slot: 5}};                // an IR from the IRs drawer
          const made = {model: {dsp: 0, id: 'block2', model: 'HD2_DelaySimpleDelay', position: 2, path: 0},
                        capture: {dsp: 0, id: 'block2', model: NAM, position: 2, path: 0, slot: 21},
                        ir: {dsp: 0, id: 'block2', model: IR, position: 2, path: 0, slot: 5}};
          const out = {};
          for (const way of Object.keys(ways)) {
            const follow = workbenchAddFollow(ways[way], reading(), 1000);
            out[way] = [step(follow, reading()), step(follow, reading([made[way]]))];
          }
          return out;
        }""")
        for way in ('model', 'capture', 'ir'):
            self.assertEqual(out[way][0], {'select': None, 'done': False}, way)                     # not there yet: wait
            self.assertEqual(out[way][1], {'select': {'dsp': 0, 'id': 'block2'}, 'done': True}, way)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_slow_add_waits_and_a_wrong_or_refused_one_picks_nothing(self):
        out = js(ADD % """() => {
          const follow = workbenchAddFollow({dsp: 0, lane: 0, place: 2, slot: 21}, reading(), 1000);
          const slotOne = {dsp: 0, id: 'block2', model: NAM, position: 2, path: 0, slot: 1};     // HX Edit first: NAM on IR slot 1
          const other = {dsp: 0, id: 'block2', model: 'HD2_DelaySimpleDelay', position: 2, path: 0};
          const ir = workbenchAddFollow({dsp: 0, lane: 0, place: 2, symbol: IR, slot: 5}, reading(), 1000);
          return {
            slotOne: step(follow, reading([slotOne]), 3000),                                       // a capture whose slot comes later
            late: step(follow, reading([{...slotOne, slot: 21}]), 6900),                           // ... within the wait
            tooLate: step(follow, reading([{...slotOne, slot: 21}]), 1000 + WORKBENCH_ADD_SELECT_MS + 1),
            wrongModel: step(follow, reading([other])),                                            // something else at the place
            otherPath: step(follow, reading([{...slotOne, slot: 21, dsp: 1}])),
            irDefault: step(ir, reading([{dsp: 0, id: 'block2', model: IR, position: 2, path: 0, slot: 1}])),   // the IR not on it yet
            nothing: step(follow, reading(), 1000 + WORKBENCH_ADD_SELECT_MS + 1),                  // refused / never came: given up
            none: workbenchAddSelect(null, reading(), NAM, 1000)};
        }""")
        self.assertEqual(out['slotOne'], {'select': None, 'done': False})
        self.assertEqual(out['late'], {'select': {'dsp': 0, 'id': 'block2'}, 'done': True})
        for name in ('tooLate', 'nothing'):
            self.assertEqual(out[name], {'select': None, 'done': True}, name)
        for name in ('wrongModel', 'otherPath', 'irDefault'):
            self.assertEqual(out[name], {'select': None, 'done': False}, name)
        self.assertEqual(out['none'], {'select': None, 'done': True})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_nothing_is_picked_over_the_players_own_pick_another_preset_or_hx_edits_own(self):
        out = js(ADD % """() => {
          const follow = workbenchAddFollow({dsp: 0, lane: 0, place: 2, symbol: 'HD2_DelaySimpleDelay'}, reading(), 1000);
          const made = {dsp: 0, id: 'block2', model: 'HD2_DelaySimpleDelay', position: 2, path: 0};
          return {
            picked: step(follow, reading([made], {dsp: 0, id: 'block1'})),                        // the player picked the NAM block
            preset: step(follow, reading([made], undefined, {setlist: 0, number: 33})),           // another preset came up
            noHeader: step(follow, reading([made], undefined, null)),                              // a reading without the header
            already: step(follow, reading([made], {dsp: 0, id: 'block2'})),                       // HX Edit picked it itself
            blank: step(follow, reading([], null)),                                                 // nothing selected while it adds
            fromNone: step(workbenchAddFollow({dsp: 0, lane: 0, place: 2, symbol: 'HD2_DelaySimpleDelay'}, reading([], null), 1000), reading([made], null)),
            key: workbenchPresetKey(reading())};
        }""")
        self.assertEqual(out['picked'], {'select': None, 'done': True})
        self.assertEqual(out['preset'], {'select': None, 'done': True})
        self.assertEqual(out['noHeader'], {'select': {'dsp': 0, 'id': 'block2'}, 'done': True})
        self.assertEqual(out['already'], {'select': None, 'done': True})                            # no second select
        self.assertEqual(out['blank'], {'select': None, 'done': False})
        self.assertEqual(out['fromNone'], {'select': {'dsp': 0, 'id': 'block2'}, 'done': True})
        self.assertEqual(out['key'], '0:32')

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_an_ir_added_shows_as_an_ir_block_while_it_comes(self):
        # (the chain shown meanwhile: an IR block, not a NAM block, and settled once it has the IR)
        out = js(ADD % """() => {
          const add = {action: 'add', dsp: 0, lane: 0, place: 2, symbol: IR, slot: 5};
          const coming = workbenchPending(base, add, NAM);
          const there = workbenchPending(base.concat([{dsp: 0, id: 'block2', model: IR, position: 2, path: 0, slot: 5}]), add, NAM);
          return [coming.settled, coming.blocks.find(b => b.position === 2).model, there.settled];
        }""")
        self.assertEqual(out, [False, 'HD2_ImpulseResponse1024', True])

    def test_one_place_in_the_page_for_every_way_to_add_and_layout(self):
        text = page().replace('\r\n', '\n')
        # every add goes through chainAsk (the picker, Classic+'s lists, the drawers' drops), none asks "add" itself
        self.assertEqual(text.count("chainAsk('add'"), 4)
        self.assertNotIn("ask('add'", text)
        chain_ask = between(text, 'function chainAsk(', 'function shownBlocks(')
        self.assertIn("addFollow = action === 'add' ? workbenchAddFollow(value, state, Date.now()) : null;", chain_ask)
        # each reading: the new block picked as a click picks it (pickBlock: one select ask, the same in all layouts)
        receive = between(text, "else if (message.type === 'state') {", "else if (message.type === 'dsp')")
        self.assertIn('const next = workbenchAddSelect(addFollow, state, catalog.nam[0], Date.now());', receive)
        self.assertIn('if (next.done) addFollow = null;', receive)
        self.assertIn('if (next.select) pickBlock(next.select, true);', receive)
        self.assertNotIn('layout', between(receive, 'if (addFollow && catalog)', 'pickBlock(next.select, true);'))
        pick = between(text, 'function pickBlock(block', '\n}')
        self.assertEqual(pick.count("ask('select', {dsp: block.dsp, id: block.id});"), 1)

    def test_undo_or_a_refusal_ends_the_wait_and_selecting_adds_no_step(self):
        text = page()
        ask_line = between(text, 'const ask = (name, value) => {', '};')
        self.assertIn("if (name === 'undo' || name === 'redo') addFollow = null;", ask_line)       # every undo the page asks
        self.assertIn("else if (message.type === 'notice') {", text)                                 # a refused add (no room, ...)
        self.assertIn("addFollow = null; swapAsked = null; replaced = null; toast(message.text);", text)
        # the page's select is not an edit: no unsaved mark and no undo step of the page's own
        self.assertNotIn("'select'", between(text, 'const EDIT_ASKS = new Set(', ');'))
        # after Undo the block is gone from HX Edit's reading: the panel is drawn from that reading (no block kept here)
        self.assertIn('return state.blocks.find(b => b.dsp === state.selected.dsp && b.id === state.selected.id) || null;', text)


class ShareOfTheBudgetTests(unittest.TestCase):
    def test_every_dsp_share_in_the_page_needs_a_budget(self):
        # (a reading without a budget made the path tag say NaN% or Infinity%; review of PR #7)
        import re
        lines = [line for line in page().split('\n') if re.search(r'100 \* (\w+)\.used / \1\.budget', line)]
        self.assertGreaterEqual(len(lines), 4)
        for line in lines:
            name = re.search(r'100 \* (\w+)\.used / \1\.budget', line).group(1)
            self.assertIn('&& %s.budget' % name, line, line.strip())


if __name__ == '__main__':
    unittest.main()
