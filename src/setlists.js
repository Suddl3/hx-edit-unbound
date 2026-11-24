'use strict';

// The Workbench's setlists (Batch 3): the Floor's setlist names, another setlist's preset names, and a preset of
// another setlist loaded, each the way HX Edit's own Presets list does it. Static study of HX Edit.exe 3.82 x86
// (2026-11-24; research/modern-ui/PRESETS-FINDINGS.md has the addresses, which it first gave as virtual addresses):
// - The Presets list's controller (constructor 0x240210, vtable 0x8e0b24, its command handler 0x244a60) keeps the
//   setlist its list shows at +0x54, its Librarian model at +0x29c, the kind of device at +0x2b0 and the setlist
//   chooser at +0x40 (HX Edit's own lookup of the "setl" widget, in that constructor, 0x2403cc). The library
//   container that makes it keeps it at +0x58 (0x214c14), beside the IR list's controller at +0x5c (nam_view's).
// - The chooser's items (0x3ac030 -> 0x386220: chooser +0x150, an array at +0x7c with the items at +4 and their count
//   at +8) each begin with the setlist's name as a C string. HX Edit fills them only when the Floor answers the
//   Librarian operation 9, "get setlist names" (the answer's handler, 0x2552e5..0x255437), and it asks for them only
//   on two device events (0x2555b2 after a setlist was renamed, 0x255971: model 0x3fcbc0(0, setlists - 1), 8 setlists
//   on a Floor). Reading them is reading memory, nothing else.
// - A setlist chosen in HX Edit's chooser ("setl", "cva!", 0x244be8): +0x54 = its index, then the model's
//   0x3fc720(setlist, 0, last) (last = 0x7f on a Floor, from +0x2b0): the Librarian operation 2, "get preset names".
//   It reads the names from the Floor's library and loads nothing; the list's rows follow when the Floor answers.
//   HX Edit's own chooser is then shown that setlist (0x3bcb20(index, 1, 0), as HX Edit does after it fills it).
// - A double-click on a preset of the list ("plst", "dbl!", 0x244ac8): the model's 0x3f89c0(setlist, index), the
//   Librarian operation 29, "load preset": what HX Edit's own list does to load a preset of the setlist it shows.
// Every call is made on HX Edit's UI thread (the caller's job: focus_view.js's reading runs there), only on the
// controller found by its own constructor and vtable, and only for a setlist the chooser lists.
//
// Live check 2026-11-24 08:22 (HX Edit started with the Floor off, the Floor on a minute later): the names were not
// read and nothing said why. So: (1) explain() says how far a reading got (focus_view.js traces it when it changes);
// (2) the controller is also taken from the library container on its tab switch (0x2156a0, the hook nam_view relies
// on: hooked there before this script, so guarded by nav_banner.js, not here); (3) a chooser still empty while the
// Presets list has its rows is filled as HX Edit fills it: the model's own "get setlist names" (0x3fcbc0(0, last), as
// at 0x25596d), asked at most SETLIST_ASKS times, SETLIST_ASK_MS apart, per controller (askNames). Assumed until the
// next live check: that the chooser was empty in that launch (the trace now says), and that this ask fills it.
const setlistGuards = Object.freeze({
  '240210': '558bec6aff',                 // the Presets list's controller: its constructor
  '240238': '8bf1',                       //   mov esi, ecx (the controller)
  '240341': '89869c020000',               //   mov [esi+0x29c], eax: its Librarian model
  '214c14': '894758',                     // the library container keeps it: mov [edi+0x58], eax
  '244a60': '558bec6aff68',               // its command handler
  '244bfd': '8bd089565481f905',           //   the chooser's "cva!": mov [esi+0x54], edx; cmp ecx, 0x2100.. (+0x2b0)
  '244c23': '8b8e9c020000',               //   mov ecx, [esi+0x29c] before 0x3fc720
  '244ad1': 'ffb000010000ff7654e8e13e1b', //   the list's "dbl!": push row; push [esi+0x54]; call 0x3f89c0
  '3fc720': '558bec6aff',                 // the model's "get preset names" (operation 2)
  '3f89c0': '558bec6aff',                 // the model's "load preset" (operation 29)
  '3fcbc0': '558bec6aff',                 // the model's "get setlist names" (operation 9)
  '3fcc2b': 'c745d809000000',             //   operation = 9
  '25596d': '48506a00e84a721a00',         // HX Edit's own ask: dec eax; push eax (last); push 0; call 0x3fcbc0
  '3ac030': '558bec81c1500100005de9',     // the chooser's item: add ecx, 0x150; jmp 0x386220
  '386220': '558bec8b417c8b4d083b4808730e8b400485c0740d8b0488',   // items at [+0x7c]+4, count at +8
  '3bcb20': '558bec807d1000b8',           // the chooser's selection (index, 1, 0)
});
const SETLIST_CONTROLLER_VTABLE = 0x8e0b24;
const SETLIST_DEVICE_LAST = Object.freeze({0x210005: 0x7f, 0x210006: 0x7d});   // the last preset HX Edit asks for (else 0x7f)
const SETLIST_DEVICE_COUNT = Object.freeze({0x210005: 1, 0x210006: 1, 0x21000b: 1});   // setlists HX Edit asks names of (else 8)
const SETLIST_ASKS = 3, SETLIST_ASK_MS = 10000;

// The names in a chooser's item array as read memory gives them: {names: 1..32 names of up to 32 printable
// characters, or null; word: how far the reading got, for the trace}.
function setlistRead(count, read) {
  if (!Number.isInteger(count)) return {names: null, word: 'count-unreadable'};
  if (count === 0) return {names: null, word: 'chooser-empty'};
  if (count < 0 || count > 32) return {names: null, word: 'count-' + count};
  const names = [];
  for (let index = 0; index < count; index++) {
    const name = read(index);
    if (name === null || name === undefined) return {names: null, word: `item-${index}-null (count ${count})`};
    if (typeof name !== 'string' || !/^[\x20-\x7e]{1,32}$/.test(name)) {
      return {names: null, word: `item-${index}-refused (count ${count}): ` + JSON.stringify(String(name).slice(0, 40)) + ' length ' + String(name).length};
    }
    names.push(name.trim());
  }
  return {names, word: 'ok-' + count};
}
const setlistNamesFrom = (count, read) => setlistRead(count, read).names;

function installSetlists() {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Setlists require HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, hex] of Object.entries(setlistGuards)) {
    const bytes = new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(hex.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error(`Setlists native byte guard failed at ${rva}`);
  }
  const method = (rva, type, args) => new NativeFunction(base.add(rva), type, ['pointer', ...args], 'thiscall');
  const askPresetNames = method(0x3fc720, 'void', ['int', 'int', 'int']);
  const askSetlistNames = method(0x3fcbc0, 'void', ['int', 'int']);
  const loadPreset = method(0x3f89c0, 'void', ['int', 'int']);
  const selectItem = method(0x3bcb20, 'void', ['int', 'int', 'int']);
  const vtable = base.add(SETLIST_CONTROLLER_VTABLE);
  let controller = NULL, via = '', asks = 0, askedAt = 0;
  const usable = object => { try { return !object.isNull() && object.readPointer().equals(vtable); } catch (_) { return false; } };
  function take(object, how) {
    if (!usable(object) || object.equals(controller)) return;
    controller = object; via = how; asks = 0; askedAt = 0;
    send({type: 'toneTrace', reason: 'setlists', stage: 'controller', via: how});
  }
  // The controller as HX Edit makes it (our script is in place before HX Edit's window is built), from its command
  // handler, and from the library container on its tab switch, whichever comes first.
  Interceptor.attach(base.add(0x240210), {
    onEnter() { this.self = this.context.ecx; },
    onLeave() { take(this.self, 'constructor'); },
  });
  Interceptor.attach(base.add(0x244a60), {
    onEnter() { take(this.context.ecx, 'handler'); },
  });
  Interceptor.attach(base.add(0x2156a0), {
    onEnter() { try { take(this.context.ecx.add(0x58).readPointer(), 'container'); } catch (_) { /* not the container */ } },
  });
  function parts() {
    // {model, chooser, word}: the controller's parts, or a word for what is missing
    if (controller.isNull()) return {word: 'no-controller'};
    if (!usable(controller)) return {word: 'controller-vtable-differs (' + via + ')'};
    const model = controller.add(0x29c).readPointer(), chooser = controller.add(0x40).readPointer();
    if (model.isNull()) return {word: 'no-model (' + via + ')'};
    if (chooser.isNull()) return {word: 'no-chooser (' + via + ')'};
    return {model, chooser, word: ''};
  }
  function read() {
    // {names, word}: the setlists' names as HX Edit's chooser has them, or null and how far the reading got
    try {
      const found = parts();
      if (!found.chooser) return {names: null, word: found.word};
      const array = found.chooser.add(0x150).add(0x7c).readPointer();
      if (array.isNull()) return {names: null, word: 'no-item-array (' + via + ')'};
      const count = array.add(8).readU32(), items = array.add(4).readPointer();
      if (items.isNull() && count) return {names: null, word: `items-null (count ${count}, ${via})`};
      const result = setlistRead(count, index => {
        const item = items.add(4 * index).readPointer();
        return item.isNull() ? null : item.readCString(64);
      });
      return {names: result.names, word: result.word + ' (' + via + ')'};
    } catch (error) { return {names: null, word: 'read-failed: ' + String(error.message).slice(0, 60)}; }
  }
  const names = () => read().names;
  function shownWord() {
    const found = parts();
    if (!found.chooser) return found.word;
    const index = controller.add(0x54).readS32();
    return index >= 0 && index < 32 ? 'shown-' + index : 'shown-out-of-range-' + index;
  }
  function shown() {
    // The setlist HX Edit's list shows now (its index), or null.
    if (!parts().chooser) return null;
    const index = controller.add(0x54).readS32();
    return index >= 0 && index < 32 ? index : null;
  }
  function explain() {
    // How far the readings get, for the trace: "names: ok-8 (constructor); shown: shown-3"
    let shownNow;
    try { shownNow = shownWord(); } catch (error) { shownNow = 'read-failed: ' + String(error.message).slice(0, 60); }
    return 'names: ' + read().word + '; shown: ' + shownNow;
  }
  function askNames(now = Date.now()) {
    // The chooser is still empty although the Presets list has its rows (the caller says so): HX Edit's own
    // "get setlist names" for every setlist, as it asks on a device event (0x25596d). UI thread only. True: asked.
    const found = parts();
    if (!found.chooser || asks >= SETLIST_ASKS || (askedAt && now - askedAt < SETLIST_ASK_MS)) return false;
    let count = 0;
    try { const array = found.chooser.add(0x150).add(0x7c).readPointer(); count = array.isNull() ? 0 : array.add(8).readU32(); } catch (_) { return false; }
    if (count !== 0) return false;
    const kind = controller.add(0x2b0).readU32(), setlists = SETLIST_DEVICE_COUNT[kind] ?? 8;
    asks++; askedAt = now;
    askSetlistNames(found.model, 0, setlists - 1);
    send({type: 'toneTrace', reason: 'setlists', stage: 'ask-names', via, last: setlists - 1, ask: asks});
    return true;
  }
  function look(index) {
    // HX Edit's list shows another setlist, as its own chooser does: the Floor is asked for that setlist's names.
    // Nothing is loaded. UI thread only.
    const found = parts(), listed = names();
    if (!found.chooser || !listed) throw new Error('HX Edit\'s Presets list is not ready');
    if (!Number.isInteger(index) || index < 0 || index >= listed.length) throw new Error('no such setlist');
    if (shown() === index) return false;                                   // (already there: nothing to ask)
    const kind = controller.add(0x2b0).readU32();
    controller.add(0x54).writeS32(index);
    askPresetNames(found.model, index, 0, SETLIST_DEVICE_LAST[kind] ?? 0x7f);
    try { selectItem(found.chooser, index, 1, 0); } catch (_) { /* HX Edit's own chooser only shows it */ }
    return true;
  }
  function load(setlist, number) {
    // A preset of the setlist HX Edit's list shows, loaded as a double-click in that list loads it. UI thread only.
    const found = parts();
    if (!found.chooser) throw new Error('HX Edit\'s Presets list is not ready');
    if (shown() !== setlist) throw new Error('HX Edit\'s list shows another setlist');
    if (!Number.isInteger(number) || number < 0 || number > 127) throw new Error('no such preset');
    loadPreset(found.model, setlist, number);
    return true;
  }
  return {names, shown, look, load, explain, askNames, ready: () => !!parts().chooser};
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { setlistGuards, setlistRead, setlistNamesFrom, installSetlists, SETLIST_CONTROLLER_VTABLE, SETLIST_ASKS, SETLIST_ASK_MS };
}
