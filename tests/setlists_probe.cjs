'use strict';
// setlists.js (Batch 3) in a fake Frida world: HX Edit's Presets list controller found by its own constructor, the
// setlist names read from its chooser's items, another setlist asked for as HX Edit's chooser asks it, and a preset of
// the setlist the list shows loaded as its double-click loads it.
const assert = require('node:assert/strict');
const {setlistGuards: guards, setlistNamesFrom, installSetlists: install, SETLIST_CONTROLLER_VTABLE} = require('../src/setlists.js');
const BASE = 0x400000, memory = new Map(), strings = new Map(), hooks = new Map(), calls = [];
let address = 0x20000000;
class Pointer {
  constructor(value) { this.value = Number(value); }
  add(n) { return new Pointer(this.value + n); }
  isNull() { return this.value === 0; }
  equals(other) { return other instanceof Pointer && this.value === other.value; }
  readU32() { return Number(memory.get(this.value) || 0) >>> 0; }
  readS32() { return this.readU32() | 0; }
  writeS32(value) { memory.set(this.value, value >>> 0); return this; }
  writeU32(value) { memory.set(this.value, value >>> 0); return this; }
  readPointer() { return new Pointer(this.readU32()); }
  readCString() { return strings.get(this.value); }
  readByteArray(size) {
    const rva = (this.value - BASE).toString(16);
    return Uint8Array.from(Buffer.from(guards[rva] || '00'.repeat(size), 'hex')).buffer;
  }
}
const p = value => new Pointer(value);
const alloc = size => { const at = p(address); address += size + 64; return at; };
global.NULL = p(0);
global.Process = {arch: 'ia32', pointerSize: 4, mainModule: {base: p(BASE)}};
global.Interceptor = {attach(at, callbacks) { hooks.set(at.value - BASE, callbacks); return {detach() {}}; }};
global.NativeFunction = function (at) {
  const rva = at.value - BASE;
  return (...args) => { calls.push([rva.toString(16), ...args.map(a => a instanceof Pointer ? a.value : a)]); };
};

// the pure part: names as the chooser's items give them
assert.deepEqual(setlistNamesFrom(2, i => ['USER 1 ', 'TEMPLATES'][i]), ['USER 1', 'TEMPLATES']);
assert.equal(setlistNamesFrom(0, () => 'x'), null);
assert.equal(setlistNamesFrom(33, () => 'x'), null);
assert.equal(setlistNamesFrom(2, i => ['USER 1', null][i]), null);
assert.equal(setlistNamesFrom(1, () => 'Café'), null);
assert.equal(setlistNamesFrom(1, () => ''), null);

const api = install();
assert.deepEqual([...hooks.keys()].map(r => r.toString(16)).sort(), ['240210', '244a60']);
// nothing found yet: nothing read, nothing asked
assert.equal(api.ready(), false);
assert.equal(api.names(), null);
assert.equal(api.shown(), null);
assert.throws(() => api.look(1), /not ready/);
assert.equal(calls.length, 0);

// HX Edit builds its Presets list: the controller, its model, its chooser with the Floor's eight setlist names
const NAMES = ['FACTORY 1', 'FACTORY 2', 'USER 1', 'USER 2', 'USER 3', 'USER 4', 'USER 5', 'TEMPLATES'];
const controller = alloc(0x300), model = alloc(0x40), chooser = alloc(0x200), array = alloc(16), items = alloc(4 * NAMES.length);
controller.writeU32(BASE + SETLIST_CONTROLLER_VTABLE);
controller.add(0x29c).writeU32(model.value); controller.add(0x40).writeU32(chooser.value); controller.add(0x54).writeS32(2);
controller.add(0x2b0).writeU32(0x210001);
chooser.add(0x150 + 0x7c).writeU32(array.value); array.add(4).writeU32(items.value); array.add(8).writeU32(NAMES.length);
NAMES.forEach((name, i) => { const item = alloc(64); strings.set(item.value, name); items.add(4 * i).writeU32(item.value); });
const made = {context: {ecx: controller}};
hooks.get(0x240210).onEnter.call(made); hooks.get(0x240210).onLeave.call(made);
assert.equal(api.ready(), true);
assert.deepEqual(api.names(), NAMES);
assert.equal(api.shown(), 2);

// looking at the setlist the list shows already: nothing to ask
assert.equal(api.look(2), false);
assert.equal(calls.length, 0);
// another setlist: +0x54 as HX Edit's chooser sets it, then "get preset names" (0..0x7f) and the chooser shows it
assert.equal(api.look(0), true);
assert.equal(api.shown(), 0);
assert.deepEqual(calls, [['3fc720', model.value, 0, 0, 0x7f], ['3bcb20', chooser.value, 0, 1, 0]]);
// (a device HX Edit asks fewer presets of: as HX Edit does)
calls.length = 0; controller.add(0x2b0).writeU32(0x210006);
api.look(1);
assert.deepEqual(calls[0], ['3fc720', model.value, 1, 0, 0x7d]);
controller.add(0x2b0).writeU32(0x210001);
// only a setlist the chooser lists
calls.length = 0;
for (const bad of [8, -1, 1.5, '2']) assert.throws(() => api.look(bad), /no such setlist/);
assert.equal(calls.length, 0);

// a preset of the setlist the list shows: loaded as its double-click loads it; of another: refused
calls.length = 0;
assert.equal(api.load(1, 32), true);
assert.deepEqual(calls, [['3f89c0', model.value, 1, 32]]);
assert.throws(() => api.load(3, 32), /shows another setlist/);
assert.throws(() => api.load(1, 128), /no such preset/);
assert.equal(calls.length, 1);

// the object is no longer HX Edit's controller (freed, another class): nothing is read or asked
controller.writeU32(0x1234);
assert.equal(api.names(), null);
assert.throws(() => api.look(0), /not ready/);
assert.throws(() => api.load(1, 3), /not ready/);
// a controller seen by its command handler is taken (made before this script, or anew)
const other = alloc(0x300);
other.writeU32(BASE + SETLIST_CONTROLLER_VTABLE); other.add(0x29c).writeU32(model.value); other.add(0x40).writeU32(chooser.value); other.add(0x54).writeS32(5);
hooks.get(0x244a60).onEnter.call({context: {ecx: other}});
assert.equal(api.shown(), 5);
hooks.get(0x244a60).onEnter.call({context: {ecx: alloc(8)}});      // something else: ignored
assert.equal(api.shown(), 5);
assert.equal(calls.length, 1);

// a byte guard that does not hold: nothing installed
const original = Pointer.prototype.readByteArray;
Pointer.prototype.readByteArray = function (size) { return new Uint8Array(size).buffer; };
assert.throws(() => install(), /Setlists native byte guard failed/);
Pointer.prototype.readByteArray = original;
console.log('setlists probe passed');
