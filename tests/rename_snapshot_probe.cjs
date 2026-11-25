'use strict';
// target_binding renameSnapshot (Batch 3): a snapshot's name in the edit buffer, written as HX Edit's own snapshot
// rename writes it (dsp -1, "snapshot<n>", "@name", a String), with the single-change flag (one undo step) and then the
// refresh flag (HX Edit's own views), and read back. A fake Frida world: the edit buffer is a map.
const assert = require('node:assert/strict');
const {installTargetBinding: install, targetBindingGuards: guards} = require('../src/target_binding.js');
const memory = new Map(), text = new Map(), native = new Map();
let address = 0x20000000, constructions = 0, destructions = 0, writes = [], refuse = false, ignore = false;
class Pointer {
  constructor(value) { this.value = Number(value); }
  add(n) { return new Pointer(this.value + n); }
  isNull() { return this.value === 0; }
  equals(other) { return this.value === other.value; }
  readU32() { return Number(memory.get(this.value) || 0) >>> 0; }
  readS32() { return this.readU32() | 0; }
  readU8() { return this.readU32() & 255; }
  writeU32(value) { memory.set(this.value, value); return this; }
  readPointer() { return new Pointer(this.readU32()); }
  readFloat() { return Number(memory.get(this.value) || 0); }
  writeFloat(value) { memory.set(this.value, value); }
  writeByteArray(bytes) { for (let i = 0; i < bytes.length; i++) memory.set(this.value + i, bytes[i]); }
  readUtf8String(length) { return text.get(this.value).slice(0, length); }
  readByteArray(size) { return Uint8Array.from(Buffer.from(guards[(this.value - 0x400000).toString(16)] || '00'.repeat(size), 'hex')).buffer; }
}
const p = value => new Pointer(value);
function alloc(size) { const result = p(address); address += size + 32; return result; }
function utf8(value) { const result = alloc(value.length + 1); text.set(result.value, value); return result; }
function putString(object, value) {
  const rep = alloc(20), data = utf8(value);
  object.add(4).writeU32(rep.value); rep.add(4).writeU32(value.length); rep.add(16).writeU32(data.value);
}
function getString(object) { const rep = object.add(4).readPointer(); return rep.add(16).readPointer().readUtf8String(rep.add(4).readU32()); }
function putValue(pointer, value) {
  pointer.writeU32(10); const object = alloc(8); putString(object, value); pointer.add(8).writeU32(object.value); constructions++;
}
const getValue = pointer => getString(pointer.add(8).readPointer());
global.Process = {arch: 'ia32', pointerSize: 4, mainModule: {base: p(0x400000)}, getCurrentThreadId: () => 42};
global.Memory = {alloc, allocUtf8String: utf8};
global.NativeFunction = function (at) { assert.ok(native.has(at.value - 0x400000)); return native.get(at.value - 0x400000); };
const editor = alloc(0x300);
editor.writeU32(0xd63dfc); p(0xd63dfc + 0x7c).writeU32(0x9178c0);
p(0xd63dfc + 0x88).writeU32(0x904f50); p(0xd63dfc + 0xdc).writeU32(0x91aaf0);
const tree = new Map([['-1:snapshot0', {'@name': 'Clean'}], ['-1:snapshot1', {'@name': 'Crunch'}]]);
native.set(0x1a6ac0, (out, source) => { putValue(out, text.get(source.value)); return out; });
native.set(0x1a1b30, value => { if (value.readU32() === 10) destructions++; value.writeU32(9); });
native.set(0x504f50, (instance, dsp, group, key, out) => {
  assert.equal(instance.value, editor.value);
  const object = tree.get(`${dsp}:${getValue(group)}`), name = getValue(key);
  if (!object || !Object.hasOwn(object, name)) return -1;
  putValue(out, object[name]); return 0;
});
native.set(0x5178c0, (instance, dsp, group, key, value, flags) => {
  assert.equal(instance.value, editor.value);
  writes.push({dsp, group: getValue(group), key: getValue(key), value: getValue(value), flags});
  if (refuse) return -4;
  if (!ignore) tree.get(`${dsp}:${getValue(group)}`)[getValue(key)] = getValue(value);
  return 0;
});
native.set(0x23cb50, () => { throw new Error('not used'); });
const api = install();

// a snapshot renamed: one undo step (the single-change flag), then HX Edit's views shown it (the refresh flag)
assert.equal(api.renameSnapshot(editor, 1, 'Crunch Rhy'), true);
assert.deepEqual(writes, [
  {dsp: -1, group: 'snapshot1', key: '@name', value: 'Crunch Rhy', flags: 0x80000000},
  {dsp: -1, group: 'snapshot1', key: '@name', value: 'Crunch Rhy', flags: 0x40000000}]);
assert.equal(api.peekGlobal(editor, 'snapshot1', '@name'), 'Crunch Rhy');
assert.equal(tree.get('-1:snapshot0')['@name'], 'Clean', 'only that snapshot');
// the same name again: nothing written
writes = [];
assert.equal(api.renameSnapshot(editor, 1, 'Crunch Rhy'), true);
assert.deepEqual(writes, []);
// what the Floor would refuse is refused before anything is written
for (const [index, name] of [[1, 'Eleven char'], [1, ''], [1, 'Café'], [1, 'tab\there'], [8, 'Lead'], [-1, 'Lead'], [1.5, 'Lead'], [1, null]]) {
  assert.throws(() => api.renameSnapshot(editor, index, name), /unsupported snapshot name/);
}
assert.throws(() => api.renameSnapshot(editor, 5, 'Lead'), /read was rejected/);    // a snapshot the preset does not have
assert.deepEqual(writes, []);
// HX Edit refuses the write: said so, and the refresh write is never sent
refuse = true;
assert.throws(() => api.renameSnapshot(editor, 0, 'Bright'), /refused the snapshot's name \(-4\)/);
assert.equal(writes.length, 1); refuse = false;
// HX Edit takes the write but the name does not change: said so
writes = []; ignore = true;
assert.throws(() => api.renameSnapshot(editor, 0, 'Bright'), /kept its old name/);
ignore = false;
// another editor object: nothing
editor.writeU32(0x1234); writes = [];
assert.throws(() => api.renameSnapshot(editor, 0, 'Bright'), /unsupported snapshot name/);
assert.deepEqual(writes, []); editor.writeU32(0xd63dfc);
assert.equal(constructions, destructions, 'every native string made for it is destroyed');
console.log('rename snapshot probe passed');
