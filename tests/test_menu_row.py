"""menu_row.js: HX Edit finds its menu commands while its menu row is off the window. A fake Frida world."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
NODE = shutil.which('node')

# Base 0x400000; the search routine's hook; one kept menu (0x98e107b) that is a menu or not.
HARNESS = r"""
const sent = [], waiting = [];
let hook = null, menus = new Set([0x98e107b]);
const mem = new Map([[0x9b4200, '558bec83ec3053560f57c0c7'], [0x9b477b, '50e87ffaffff'], [0x9b4797, '50e863faffff']]);
class P {
  constructor(v) { this.v = v; }
  add(n) { return new P(this.v + n); }
  equals(o) { return o.v === this.v; }
  isNull() { return this.v === 0; }
  readByteArray(n) { const hex = mem.get(this.v); return Uint8Array.from(hex.match(/../g).slice(0, n).map(h => parseInt(h, 16))).buffer; }
}
globalThis.NULL = new P(0);
globalThis.ptr = v => new P(v);
globalThis.Process = { arch: 'ia32', pointerSize: 4, mainModule: { base: new P(0x400000) },
  getModuleByName: () => ({ getExportByName: () => new P(1) }) };
globalThis.NativeFunction = function () { return menu => menus.has(menu.v) ? 1 : 0; };
globalThis.Interceptor = { attach(at, callbacks) { hook = { at: at.v, ...callbacks }; return { detach() {} }; } };
globalThis.send = m => sent.push(m);
globalThis.recv = (type, callback) => waiting.push({ type, callback });
""" + (ROOT / 'menu_row.js').read_text(encoding='utf-8') + r"""
installMenuRow();
const tell = payload => { const next = waiting.shift(); next.callback({ payload }); };
function search(returnAddress, menu) {
  const args = [new P(menu), new P(32779)];
  hook.onEnter.call({ returnAddress: new P(returnAddress) }, args);
  return args[0].v;
}
const out = { hookAt: hook.at, listensFor: waiting[0].type };
out.before = search(0x9b4781, 0);                    // nothing kept: "no menu" stays "no menu"
tell({ kept: 0x98e107b });
out.handler = search(0x9b4781, 0);                   // the command handler, the row away: the kept menu
out.otherWindow = search(0x9b479d, 0);               // and its second look
out.withMenu = search(0x9b4781, 0x1111);             // a window that has its menu: untouched
out.recursion = search(0x9b426c, 0);                 // the search calling itself: untouched
out.elsewhere = search(0x9b9999, 0);                 // any other caller: untouched
menus.clear();
out.gone = search(0x9b4781, 0);                      // the kept handle is no menu any more: untouched
menus.add(0x98e107b);
tell({ kept: 0 });
out.back = search(0x9b4781, 0);                      // the row is back: nothing kept
tell({ kept: 'x' }); tell({});
out.bad = search(0x9b4781, 0);
out.stillListening = waiting.length;
out.sent = sent;
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class MenuRowTests(unittest.TestCase):
    def test_only_the_command_handlers_search_of_no_menu_gets_the_kept_one(self):
        result = subprocess.run([NODE, '-e', HARNESS], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out['hookAt'], 0x9b4200)
        self.assertEqual(out['listensFor'], 'menuRow')
        self.assertEqual(out['before'], 0)
        self.assertEqual(out['handler'], 0x98e107b)
        self.assertEqual(out['otherWindow'], 0x98e107b)
        self.assertEqual(out['withMenu'], 0x1111)
        self.assertEqual(out['recursion'], 0)
        self.assertEqual(out['elsewhere'], 0)
        self.assertEqual(out['gone'], 0)
        self.assertEqual(out['back'], 0)
        self.assertEqual(out['bad'], 0)
        self.assertEqual(out['stillListening'], 1)
        self.assertEqual(out['sent'], [{'type': 'menuRow', 'event': 'ready'}, {'type': 'menuRow', 'event': 'kept'},
                                       {'type': 'menuRow', 'event': 'none'}, {'type': 'menuRow', 'event': 'none'},
                                       {'type': 'menuRow', 'event': 'none'}])

    def test_guard_mismatch_installs_nothing(self):
        broken = HARNESS.replace("'50e863faffff']]", "'909090909090']]", 1)
        result = subprocess.run([NODE, '-e', broken], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Menu row native byte guard failed at 5b4797', result.stderr)

    def test_the_guards_hold_no_address_that_moves_with_the_program(self):
        # HX Edit.exe has a dynamic base: its absolute operands (the GetMenu import, ff 15 ...) change from run to run.
        source = (ROOT / 'menu_row.js').read_text(encoding='utf-8')
        guards = source[source.index('const menuRowGuards'):source.index('function installMenuRow()')]
        self.assertNotIn('ff15', guards)
        self.assertNotIn('c98478', guards.replace('0x', ''))

    def test_launcher_and_build_include_it_and_the_row_waits_for_it(self):
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("'window_keep.js', 'menu_row.js',", launcher)
        self.assertIn("try { installMenuRow(); } catch (error) { send({type: 'menuRow', event: 'unavailable'", launcher)
        self.assertIn("frame.allow_menu(payload.get('event') == 'ready')", launcher)
        self.assertIn("script.post({'type': 'menuRow', 'payload': {'kept': handle}})", launcher)
        self.assertIn("'menu_row.js'", (ROOT / 'build-windows.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
