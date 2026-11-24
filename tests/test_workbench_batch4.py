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
        self.assertIn("'layout': layout_kept()}", text)
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
        switch = between(text, 'function setLayout(name, mine) {', '// The chooser')
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


if __name__ == '__main__':
    unittest.main()
