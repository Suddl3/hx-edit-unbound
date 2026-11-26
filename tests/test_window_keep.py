import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
NODE = shutil.which('node')

# A fake Frida world: base 0x400000, one window that is visible or not, and the helper hook.
HARNESS = r"""
const sent = [];
let hook = null, visible = 1;
const mem = new Map([[0x5a6034, '6a016a0153e8826c4600'], [0xa0ccc0, '558bec568b750885f6745b56']]);
class P {
  constructor(v) { this.v = v; }
  add(n) { return new P(this.v + n); }
  equals(o) { return o.v === this.v; }
  isNull() { return this.v === 0; }
  readByteArray(n) { const hex = mem.get(this.v); return Uint8Array.from(hex.match(/../g).slice(0, n).map(h => parseInt(h, 16))).buffer; }
}
globalThis.NULL = new P(0);
globalThis.Process = { arch: 'ia32', pointerSize: 4, mainModule: { base: new P(0x400000) },
  getModuleByName: () => ({ getExportByName: () => new P(1) }) };
globalThis.NativeFunction = function () { return () => visible; };
globalThis.Interceptor = { attach(at, callbacks) { hook = { at: at.v, ...callbacks }; return { detach() {} }; } };
globalThis.send = m => sent.push(m);
""" + (ROOT / 'window_keep.js').read_text(encoding='utf-8') + r"""
installWindowKeeper();
function call(returnAddress, hwnd, isVisible) {
  visible = isVisible; const args = [new P(hwnd)];
  hook.onEnter.call({ returnAddress: new P(returnAddress) }, args);
  return args[0].v;
}
const out = {
  hookAt: hook.at,
  reconnectVisible: call(0x5a603e, 0x1234, 1),   // reconnect, window on screen: helper gets null
  startupHidden: call(0x5a603e, 0x1234, 0),      // first show at startup: untouched
  otherCaller: call(0x5a7000, 0x1234, 1),        // any other caller: untouched
  sent,
};
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class WindowKeeperTests(unittest.TestCase):
    def test_only_the_reconnect_show_of_a_visible_window_is_skipped(self):
        result = subprocess.run([NODE, '-e', HARNESS], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out['hookAt'], 0xa0ccc0)
        self.assertEqual(out['reconnectVisible'], 0)
        self.assertEqual(out['startupHidden'], 0x1234)
        self.assertEqual(out['otherCaller'], 0x1234)
        self.assertEqual(out['sent'], [{'type': 'windowKeeper', 'event': 'kept'}])

    def test_guard_mismatch_installs_nothing(self):
        broken = HARNESS.replace("'558bec568b750885f6745b56']]", "'90909090909090909090909090']]", 1)
        result = subprocess.run([NODE, '-e', broken], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Window keeper native byte guard failed at 60ccc0', result.stderr)

    def test_launcher_and_build_include_it(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'window_keep.js'", launcher)
        self.assertIn('try {{ installWindowKeeper(', launcher)                       # (with the start-up cover's option, J4)
        self.assertIn("'window_keep.js'", (ROOT / 'build-windows.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()


# The start-up cover (J4): the same fake world, with calls recorded, memory stubbed, and recv/timers kept for the test.
COVER = HARNESS.replace("globalThis.NativeFunction = function () { return () => visible; };",
                        "const calls = []; let waiting = null; const timers = []; let intervals = 0, cleared = 0;\n"
                        "globalThis.recv = (type, fn) => { waiting = {type, fn}; };\n"
                        "globalThis.setTimeout = (fn, ms) => { timers.push(ms); };\n"
                        "globalThis.setInterval = (fn, ms) => { intervals = ms; return 7; };\n"
                        "globalThis.clearInterval = id => { cleared = id; };\n"
                        "globalThis.ptr = n => new P(n);\n"
                        "P.prototype.writeU32 = function () { return this; }; P.prototype.writePointer = function () { return this; };\n"
                        "P.prototype.writeS32 = function () { return this; }; P.prototype.readS32 = function () { return 100; };\n"
                        "globalThis.Memory = { alloc: () => new P(0x9000), allocUtf16String: () => new P(0x9100), allocAnsiString: () => new P(0x9200) };\n"
                        "globalThis.NativeFunction = function (at) { const name = at.name; return (...a) => { calls.push([name, ...a.map(x => x && x.v !== undefined ? x.v : x)]); return name === 'IsWindowVisible' ? visible : name === 'CreateWindowExW' ? new P(0x7777) : name === 'GetModuleHandleW' || name === 'GetProcAddress' || name === 'LoadCursorW' || name === 'CreateSolidBrush' ? new P(5) : 1; }; };") \
    .replace("getModuleByName: () => ({ getExportByName: () => new P(1) }) };",
             "getModuleByName: () => ({ base: new P(2), getExportByName: name => Object.assign(new P(1), {name}) }) };") \
    .replace("installWindowKeeper();", "installWindowKeeper({cover: true});") \
    .replace("""const out = {
  hookAt: hook.at,
  reconnectVisible: call(0x5a603e, 0x1234, 1),   // reconnect, window on screen: helper gets null
  startupHidden: call(0x5a603e, 0x1234, 0),      // first show at startup: untouched
  otherCaller: call(0x5a7000, 0x1234, 1),        // any other caller: untouched
  sent,
};""", """visible = 0; const args = [new P(0x1234)], ctx = { returnAddress: new P(0x5a603e) };
hook.onEnter.call(ctx, args);                                        // the first show: covered, the window still shown
const first = args[0].v, made = calls.map(c => c[0]), create = calls.find(c => c[0] === 'CreateWindowExW');
calls.length = 0;
hook.onLeave.call(ctx);                                              // shown: the cover to its client area
const placed = calls.map(c => c[0]);
calls.length = 0;
waiting.fn({payload: {on: false, why: 'page-ready'}});
const out = {first, made, create: create.slice(1, 5), owner: create[9], placed, waitingFor: waiting.type, timers, intervals, cleared,
             uncovered: calls.map(c => c.slice(0, 3)), sent: sent.map(m => m.event)};""")


@unittest.skipUnless(NODE, 'node is not installed')
class StartCoverTests(unittest.TestCase):
    def test_the_first_show_gets_our_dark_window_over_it_until_the_launchers_word(self):
        result = subprocess.run([NODE, '-e', COVER], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out['first'], 0x1234)                                  # HX Edit's own show goes on untouched
        self.assertNotIn('SetLayeredWindowAttributes', out['made'])             # (its window is not made transparent)
        self.assertNotIn('SetWindowLongW', out['made'])
        self.assertIn('RegisterClassExW', out['made'])
        self.assertEqual(out['create'], [0x08000080, 0x9100, 0, 0x90000000])    # NOACTIVATE|TOOLWINDOW; POPUP|VISIBLE
        self.assertEqual(out['owner'], 0x1234)                                  # owned by HX Edit's window
        self.assertEqual(out['placed'], ['GetClientRect', 'ClientToScreen', 'SetWindowPos'])
        self.assertEqual(out['waitingFor'], 'startCover')
        self.assertEqual(out['timers'], [10000])
        self.assertEqual(out['intervals'], 150)
        self.assertEqual(out['cleared'], 7)
        self.assertEqual(out['uncovered'], [['PostMessageW', 0x7777, 0x10]])     # WM_CLOSE to the cover only
        self.assertEqual(out['sent'], ['cover-up', 'cover-down'])
