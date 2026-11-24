'use strict';

// The Workbench's setlists (Batch 3): the Floor's setlist names, another setlist's preset names, and a preset of
// another setlist loaded, each the way HX Edit's own Presets list does it. Static study of HX Edit.exe 3.82 x86
// (2026-11-24; research/modern-ui/PRESETS-FINDINGS.md has the addresses, which it first gave as virtual addresses):
// - The Presets list's controller (constructor 0x240210, vtable 0x8e0b24, its command handler 0x244a60) keeps the
//   setlist its list shows at +0x54, its Librarian model at +0x29c, the kind of device at +0x2b0 and the setlist
//   chooser at +0x40.
// - The chooser's items (0x3ac030 -> 0x386220: chooser +0x150, an array at +0x7c with the items at +4 and their count
//   at +8) each begin with the setlist's name as a C string: HX Edit copies each name there when the Floor sends the
//   names (0x255450). Reading them is reading memory, nothing else.
// - A setlist chosen in HX Edit's chooser ("setl", "cva!", 0x244be8): +0x54 = its index, then the model's
//   0x3fc720(setlist, 0, last) (last = 0x7f on a Floor, from +0x2b0): the Librarian operation 2, "get preset names".
//   It reads the names from the Floor's library and loads nothing; the list's rows follow when the Floor answers.
//   HX Edit's own chooser is then shown that setlist (0x3bcb20(index, 1, 0), as HX Edit does after it fills it).
// - A double-click on a preset of the list ("plst", "dbl!", 0x244ac8): the model's 0x3f89c0(setlist, index), the
//   Librarian operation 29, "load preset": what HX Edit's own list does to load a preset of the setlist it shows.
// Every call is made on HX Edit's UI thread (the caller's job: focus_view.js's reading runs there), only on the
// controller found by its own constructor and vtable, and only for a setlist the chooser lists. Not run against the
// Floor yet (2026-11-24): the Workbench says when a reading or a load did not happen.
const setlistGuards = Object.freeze({
  '240210': '558bec6aff',                 // the Presets list's controller: its constructor
  '240238': '8bf1',                       //   mov esi, ecx (the controller)
  '240341': '89869c020000',               //   mov [esi+0x29c], eax: its Librarian model
  '244a60': '558bec6aff68',               // its command handler
  '244bfd': '8bd089565481f905',           //   the chooser's "cva!": mov [esi+0x54], edx; cmp ecx, 0x2100.. (+0x2b0)
  '244c23': '8b8e9c020000',               //   mov ecx, [esi+0x29c] before 0x3fc720
  '244ad1': 'ffb000010000ff7654e8e13e1b', //   the list's "dbl!": push row; push [esi+0x54]; call 0x3f89c0
  '3fc720': '558bec6aff',                 // the model's "get preset names" (operation 2)
  '3f89c0': '558bec6aff',                 // the model's "load preset" (operation 29)
  '3ac030': '558bec81c1500100005de9',     // the chooser's item: add ecx, 0x150; jmp 0x386220
  '386220': '558bec8b417c8b4d083b4808730e8b400485c0740d8b0488',   // items at [+0x7c]+4, count at +8
  '3bcb20': '558bec807d1000b8',           // the chooser's selection (index, 1, 0)
});
const SETLIST_CONTROLLER_VTABLE = 0x8e0b24;
const SETLIST_DEVICE_LAST = Object.freeze({0x210005: 0x7f, 0x210006: 0x7d});   // the last preset HX Edit asks for (else 0x7f)

// The names in a chooser's item array, as read memory gives them: 1..32 names of up to 32 printable characters, or
// null when that is not what is there.
function setlistNamesFrom(count, read) {
  if (!Number.isInteger(count) || count < 1 || count > 32) return null;
  const names = [];
  for (let index = 0; index < count; index++) {
    const name = read(index);
    if (typeof name !== 'string' || !/^[\x20-\x7e]{1,32}$/.test(name)) return null;
    names.push(name.trim());
  }
  return names;
}

function installSetlists() {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Setlists require HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, hex] of Object.entries(setlistGuards)) {
    const bytes = new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(hex.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error(`Setlists native byte guard failed at ${rva}`);
  }
  const method = (rva, type, args) => new NativeFunction(base.add(rva), type, ['pointer', ...args], 'thiscall');
  const askNames = method(0x3fc720, 'void', ['int', 'int', 'int']);
  const loadPreset = method(0x3f89c0, 'void', ['int', 'int']);
  const selectItem = method(0x3bcb20, 'void', ['int', 'int', 'int']);
  const vtable = base.add(SETLIST_CONTROLLER_VTABLE);
  let controller = NULL;
  const usable = object => { try { return !object.isNull() && object.readPointer().equals(vtable); } catch (_) { return false; } };
  // The controller as HX Edit makes it (our script is in place before HX Edit's window is built), and again from its
  // command handler, should it ever be made before or anew.
  Interceptor.attach(base.add(0x240210), {
    onEnter() { this.self = this.context.ecx; },
    onLeave() { if (usable(this.self)) controller = this.self; },
  });
  Interceptor.attach(base.add(0x244a60), {
    onEnter() { const self = this.context.ecx; if (!self.equals(controller) && usable(self)) controller = self; },
  });
  function ready() {
    if (!usable(controller)) return null;
    const model = controller.add(0x29c).readPointer(), chooser = controller.add(0x40).readPointer();
    return model.isNull() || chooser.isNull() ? null : {model, chooser};
  }
  function names() {
    // The setlists' names as HX Edit's chooser has them, or null.
    const parts = ready();
    if (!parts) return null;
    try {
      const array = parts.chooser.add(0x150).add(0x7c).readPointer();
      if (array.isNull()) return null;
      const items = array.add(4).readPointer();
      if (items.isNull()) return null;
      return setlistNamesFrom(array.add(8).readU32(), index => {
        const item = items.add(4 * index).readPointer();
        return item.isNull() ? null : item.readCString(64);
      });
    } catch (_) { return null; }
  }
  function shown() {
    // The setlist HX Edit's list shows now (its index), or null.
    if (!ready()) return null;
    const index = controller.add(0x54).readS32();
    return index >= 0 && index < 32 ? index : null;
  }
  function look(index) {
    // HX Edit's list shows another setlist, as its own chooser does: the Floor is asked for that setlist's names.
    // Nothing is loaded. UI thread only.
    const parts = ready(), listed = names();
    if (!parts || !listed) throw new Error('HX Edit\'s Presets list is not ready');
    if (!Number.isInteger(index) || index < 0 || index >= listed.length) throw new Error('no such setlist');
    if (shown() === index) return false;                                   // (already there: nothing to ask)
    const kind = controller.add(0x2b0).readU32();
    controller.add(0x54).writeS32(index);
    askNames(parts.model, index, 0, SETLIST_DEVICE_LAST[kind] ?? 0x7f);
    try { selectItem(parts.chooser, index, 1, 0); } catch (_) { /* HX Edit's own chooser only shows it */ }
    return true;
  }
  function load(setlist, number) {
    // A preset of the setlist HX Edit's list shows, loaded as a double-click in that list loads it. UI thread only.
    const parts = ready();
    if (!parts) throw new Error('HX Edit\'s Presets list is not ready');
    if (shown() !== setlist) throw new Error('HX Edit\'s list shows another setlist');
    if (!Number.isInteger(number) || number < 0 || number > 127) throw new Error('no such preset');
    loadPreset(parts.model, setlist, number);
    return true;
  }
  return {names, shown, look, load, ready: () => !!ready()};
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { setlistGuards, setlistNamesFrom, installSetlists, SETLIST_CONTROLLER_VTABLE };
}
