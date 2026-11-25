"""menu_dark.js: HX Edit's menu row drawn dark while a pane covers its screen. A fake Frida world with memory."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
NODE = shutil.which('node')

# Memory that can be allocated, read and written; every Windows call recorded by its name; HX Edit's window is 0x720cee
# at (-8, -8), its menu row at screen (0, 23)-(1920, 43), its client area starting 44 px under the window's top.
HARNESS = r"""
const sent = [], waiting = [], calls = [];
let hook = null, next = 0x100000;
const heap = [];
class P {
  constructor(v) { this.v = v >>> 0; }
  add(n) { return new P(this.v + n); }
  equals(o) { return o.v === this.v; }
  isNull() { return this.v === 0; }
  toUInt32() { return this.v; }
  at() { const block = heap.find(b => this.v >= b.base && this.v < b.base + b.size); if (!block) throw new Error('bad pointer ' + this.v.toString(16)); return [block.view, this.v - block.base]; }
  readU32() { const [v, o] = this.at(); return v.getUint32(o, true); }
  readS32() { const [v, o] = this.at(); return v.getInt32(o, true); }
  readPointer() { return new P(this.readU32()); }
  writeU32(n) { const [v, o] = this.at(); v.setUint32(o, n >>> 0, true); return this; }
  writeS32(n) { const [v, o] = this.at(); v.setInt32(o, n, true); return this; }
  writeU16(n) { const [v, o] = this.at(); v.setUint16(o, n, true); return this; }
  writePointer(p) { return this.writeU32(p.v); }
}
const alloc = size => { const base = next; next += 0x1000; heap.push({ base, size, view: new DataView(new ArrayBuffer(size)) }); return new P(base); };
const rectOf = p => [p.readS32(), p.add(4).readS32(), p.add(8).readS32(), p.add(12).readS32()];
globalThis.NULL = new P(0);
globalThis.ptr = v => new P(v);
globalThis.Memory = { alloc, allocAnsiString: text => { const p = alloc(64); p.text = text; return p; } };
const WINDOW = 0x720cee, MENU = 0x98e107b, DC = 0x5555, WINDOW_DC = 0x6666;
let hasMenu = true, modeCalls = [];
const fakes = {
  GetProcAddress: (module, name) => name.v === 135 ? new P(0x7001) : name.v === 136 ? new P(0x7002) : new P(0x77001000),
  GetMenu: () => new P(hasMenu ? MENU : 0),
  GetMenuBarInfo: (window, object, item, info) => { info.add(4).writeS32(0); info.add(8).writeS32(23); info.add(12).writeS32(1920); info.add(16).writeS32(43); return 1; },
  GetMenuItemInfoW: (menu, position, byPosition, info) => { calls.push(['item', menu.v, position, info.readU32(), info.add(4).readU32()]); return 1; },
  GetWindowRect: (window, rect) => { rect.writeS32(-8); rect.add(4).writeS32(-8); rect.add(8).writeS32(1928); rect.add(12).writeS32(1040); return 1; },
  GetClientRect: (window, rect) => { rect.writeS32(0); rect.add(4).writeS32(0); rect.add(8).writeS32(1920); rect.add(12).writeS32(989); return 1; },
  MapWindowPoints: (from, to, points) => { points.add(4).writeS32(points.add(4).readS32() + 44 - 8); points.add(12).writeS32(points.add(12).readS32() + 44 - 8); return 1; },
  GetWindowDC: () => new P(WINDOW_DC), ReleaseDC: (window, dc) => { calls.push(['release', dc.v]); return 1; },
  FillRect: (dc, rect, brush) => { calls.push(['fill', dc.v, rectOf(rect), brush.v]); return 1; },
  DrawTextW: (dc, text, count, rect, flags) => { calls.push(['text', dc.v, rectOf(rect), flags]); return 1; },
  RedrawWindow: (window, a, b, flags) => { calls.push(['redraw', window.v, flags]); return 1; },
  DrawMenuBar: window => { calls.push(['bar', window.v]); return 1; },
  SystemParametersInfoW: () => 1, CreateSolidBrush: colour => new P(0x800000 + colour), CreateFontIndirectW: () => new P(0x4444),
  SelectObject: (dc, object) => { calls.push(['select', object.v]); return new P(0x3333); },
  SetTextColor: (dc, colour) => { calls.push(['colour', colour]); return 0; }, SetBkMode: () => 1,
};
globalThis.NativeFunction = function (address) {
  if (address.v === 0x7001) return mode => { modeCalls.push(['mode', mode]); return 0; };
  if (address.v === 0x7002) return () => { modeCalls.push(['flush']); };
  return (...args) => fakes[address.name](...args);
};
const module = name => ({ base: new P(0x10000000), getExportByName: export_ => Object.assign(new P(0x20000000), { name: export_ }) });
globalThis.Process = { arch: 'ia32', pointerSize: 4, getModuleByName: module };
globalThis.Interceptor = { attach(at, callbacks) { hook = { at: at.v, ...callbacks }; return { detach() {} }; } };
globalThis.send = m => sent.push(m);
globalThis.recv = (type, callback) => waiting.push({ type, callback });
""" + (ROOT / 'menu_dark.js').read_text(encoding='utf-8') + r"""
installMenuDark();
const tell = payload => { const next = waiting.shift(); next.callback({ payload }); };
function message(hwnd, number, lParam) {
  const args = [new P(hwnd), new P(number), new P(0), lParam || new P(0)], self = {};
  hook.onEnter.call(self, args);
  hook.onLeave.call(self);
  return args[1].v;
}
const bar = alloc(12); bar.writeU32(MENU); bar.add(4).writeU32(DC);                 // UAHMENU {hmenu, hdc, flags}
const item = state => {                                                              // UAHDRAWMENUITEM
  const p = alloc(96); p.add(16).writeU32(state);
  p.add(28).writeS32(8); p.add(32).writeS32(31); p.add(36).writeS32(42); p.add(40).writeS32(51);
  p.add(48).writeU32(MENU); p.add(52).writeU32(DC); p.add(60).writeS32(2);
  return p;
};
const out = { hookAt: hook.at, listensFor: waiting[0].type };
out.offBar = message(WINDOW, 0x91, bar);                       // not dark: Windows draws it
out.offCalls = calls.length;
tell({ window: WINDOW, on: true });
out.modeOn = modeCalls.splice(0); out.told = calls.splice(0);
out.otherWindow = message(0x1234, 0x91, bar);                  // another window: untouched
out.otherCalls = calls.length;
out.bar = message(WINDOW, 0x91, bar); out.barCalls = calls.splice(0);
out.item = message(WINDOW, 0x92, item(0x100)); out.itemCalls = calls.splice(0);
out.hot = message(WINDOW, 0x92, item(0x40)); out.hotCalls = calls.splice(0);
out.greyed = message(WINDOW, 0x92, item(0x02)); out.greyedCalls = calls.splice(0);
out.paint = message(WINDOW, 0x85); out.paintCalls = calls.splice(0);
out.active = message(WINDOW, 0x86); out.activeCalls = calls.length; calls.splice(0);
hasMenu = false;
out.noMenu = message(WINDOW, 0x85); out.noMenuCalls = calls.length;      // the row is off the window: no line to paint
hasMenu = true;
out.other = message(WINDOW, 0x0f); out.otherMessageCalls = calls.length; // WM_PAINT: nothing of ours
tell({ window: WINDOW, on: false });
out.modeOff = modeCalls.splice(0); calls.splice(0);
out.plain = message(WINDOW, 0x92, item(0)); out.plainCalls = calls.length;
tell({ window: 'x', on: true });
out.bad = message(WINDOW, 0x91, bar);
tell({ window: WINDOW, on: true });                            // a drawing that fails: Windows draws, said once
const fill = fakes.FillRect; fakes.FillRect = () => { throw new Error('gdi gone'); };
out.failedBar = message(WINDOW, 0x91, bar); message(WINDOW, 0x92, item(0)); message(WINDOW, 0x85);
fakes.FillRect = fill;
out.sent = sent;
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class MenuDarkTests(unittest.TestCase):
    def run_harness(self):
        result = subprocess.run([NODE, '-e', HARNESS], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_nothing_is_drawn_until_dark_is_asked_and_only_for_hx_edits_window(self):
        out = self.run_harness()
        self.assertEqual(out['hookAt'], 0x77001000)                    # DefWindowProcW as GetProcAddress resolves it
        self.assertEqual(out['listensFor'], 'menuDark')
        self.assertEqual((out['offBar'], out['offCalls']), (0x91, 0))
        self.assertEqual((out['otherWindow'], out['otherCalls']), (0x91, 0))
        self.assertEqual((out['other'], out['otherMessageCalls']), (0x0f, 0))
        self.assertEqual((out['plain'], out['plainCalls']), (0x92, 0)) # dark off again: Windows draws it
        self.assertEqual(out['bad'], 0x91)                             # no window: not dark

    def test_the_row_and_its_items_are_drawn_in_the_panes_colours(self):
        out = self.run_harness()
        bar_brush, hot_brush = 0x800000 + 0x001b1614, 0x800000 + 0x00332925
        # the row: where GetMenuBarInfo says, in the window's own coordinates, with the line under it; then WM_NULL
        self.assertEqual(out['bar'], 0)
        self.assertEqual(out['barCalls'], [['fill', 0x5555, [8, 31, 1928, 52], bar_brush]])
        # an item: its text by position, the row's colour, Windows' menu font, ink, centred on one line
        self.assertEqual(out['item'], 0)
        self.assertEqual(out['itemCalls'], [['item', 0x98e107b, 2, 48, 0x40], ['fill', 0x5555, [8, 31, 42, 51], bar_brush],
                                            ['select', 0x4444], ['colour', 0x00d6cdc9], ['text', 0x5555, [8, 31, 42, 51], 0x25 | 0x100000],
                                            ['select', 0x3333]])
        self.assertIn(['fill', 0x5555, [8, 31, 42, 51], hot_brush], out['hotCalls'])           # under the pointer
        self.assertIn(['text', 0x5555, [8, 31, 42, 51], 0x25], out['hotCalls'])                 # (underlines shown: Alt)
        self.assertIn(['colour', 0x006c605a], out['greyedCalls'])                               # greyed

    def test_the_line_under_the_row_is_painted_over_after_windows_drew_the_frame(self):
        out = self.run_harness()
        bar_brush = 0x800000 + 0x001b1614
        self.assertEqual(out['paint'], 0x85)                           # the message itself goes on as it is
        self.assertEqual(out['paintCalls'], [['fill', 0x6666, [8, 43, 1928, 44], bar_brush], ['release', 0x6666]])
        self.assertEqual(out['activeCalls'], 2)
        self.assertEqual((out['noMenu'], out['noMenuCalls']), (0x85, 0))

    def test_the_launchers_word_redraws_the_row_and_sets_the_drop_downs(self):
        out = self.run_harness()
        self.assertEqual(out['modeOn'], [['mode', 2], ['flush']])      # SetPreferredAppMode(ForceDark), FlushMenuThemes
        self.assertEqual(out['modeOff'], [['mode', 0], ['flush']])
        self.assertEqual(out['told'], [['bar', 0x720cee], ['redraw', 0x720cee, 0x0401]])
        self.assertEqual(out['sent'][:3], [{'type': 'menuDark', 'event': 'ready'}, {'type': 'menuDark', 'event': 'dark', 'popups': True},
                                           {'type': 'menuDark', 'event': 'plain', 'popups': True}])

    def test_a_drawing_that_fails_is_left_to_windows_and_said_once(self):
        out = self.run_harness()
        self.assertEqual(out['failedBar'], 0x91)                       # not WM_NULL: Windows draws the row itself
        failed = [m for m in out['sent'] if m.get('event') == 'draw-failed']
        self.assertEqual(failed, [{'type': 'menuDark', 'event': 'draw-failed', 'where': 'row', 'error': 'gdi gone'}])

    def test_launcher_and_build_include_it(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'menu_row.js', 'menu_dark.js',", launcher)
        self.assertIn("try { installMenuDark(); } catch (error) { send({type: 'menuDark', event: 'unavailable'", launcher)
        self.assertIn("script.post({'type': 'menuDark', 'payload': {'window': int(window) & 0xffffffff, 'on': bool(on)}})", launcher)
        self.assertIn('frame = WindowFrame(trace=trace, on_kept=frame_kept, on_dark=frame_dark,', launcher)
        self.assertIn("'menu_dark.js'", (ROOT / 'build-windows.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
