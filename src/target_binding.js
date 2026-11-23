'use strict';

// HX Edit 3.82 x86 typed EditBuffer API. It addresses a DSP/block/parameter,
// independently of the currently selected parameter widget. See BOUND-TARGET.md.
const targetBindingGuards = Object.freeze({
  '504f50': '558bec6aff',
  '504f78': '8bf9897df08b751483cbffc745a40900',
  '5178c0': '558bec6aff',
  '5178e8': '8bf9897de88b4d188bc12500000040c7',
  '1a6ac0': '558bec6aff',
  '1a1b30': '568bf18b0683c0f683f8047714ff2485',
  '23cb50': '558bec6aff',
});

function targetBindingRestoreAllowed(binding, observed, options) {
  return !!binding && binding.valid === true && !!observed && !!options
    && options.context === binding.context && options.originalSlot === binding.originalSlot
    && Number.isInteger(binding.originalSlot) && binding.originalSlot >= 1 && binding.originalSlot <= 127
    && options.expectedSlot === 128 && observed.slot === 128
    && observed.engine === binding.engine && observed.valueType === binding.valueType;
}

function installTargetBinding(options = {}) {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Target binding requires HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, expected] of Object.entries(targetBindingGuards)) {
    const actual = Array.from(new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(expected.length / 2)),
      b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== expected) throw new Error(`Target binding native byte guard failed at ${rva}`);
  }
  const method = (rva, type, args) => new NativeFunction(base.add(rva), type, ['pointer', ...args], 'thiscall');
  const constructString = method(0x1a6ac0, 'pointer', ['pointer']);
  const destroyVariant = method(0x1a1b30, 'void', []);
  const readValue = method(0x504f50, 'int', ['int', 'pointer', 'pointer', 'pointer']);
  const writeValue = method(0x5178c0, 'int', ['int', 'pointer', 'pointer', 'pointer', 'uint']);
  const sliderValue = method(0x23cb50, 'pointer', ['pointer']);
  const engines = new Set(options.supportedEngines || ['HD2_AmpNAMLite']);
  const bindings = new WeakMap();
  function fail(reason) { throw new Error(`NAM target binding: ${reason}`); }
  function emptyVariant() {
    const result = Memory.alloc(16);
    result.writeByteArray(new Uint8Array(16));
    result.writeU32(9); // native null/opaque pointer value
    return result;
  }
  function string(text) {
    const result = emptyVariant();
    constructString(result, Memory.allocUtf8String(text));
    return result;
  }
  function nativeString(object) {
    if (object.isNull()) fail('missing native string');
    const representation = object.add(4).readPointer();
    if (representation.isNull()) return '';
    const length = representation.add(4).readU32();
    if (length > 256) fail('native string exceeds identity bound');
    const data = representation.add(16).readPointer();
    if (length && data.isNull()) fail('invalid native string');
    return length ? data.readUtf8String(length) : '';
  }
  function decode(value) {
    const type = value.readU32();
    if (type === 4 || type === 1) return { type, value: value.add(8).readS32() };   // (1: as HX Edit writes @controller)
    if (type === 5) return { type, value: value.add(8).readU32() };
    if (type === 8) return { type, value: value.add(8).readFloat() };
    // (6 / 7: a 64-bit number, as a snapshot keeps a list setting's choice, a wave shape say: seen 2026-11-22 as
    // "kind 7". A small whole number is that; anything else is read as a double.)
    if (type === 6 || type === 7) {
      const whole = (type === 6 ? value.add(8).readS64() : value.add(8).readU64()).toNumber();
      return { type, value: Number.isSafeInteger(whole) && Math.abs(whole) < 1e9 ? whole : value.add(8).readDouble() };
    }
    if (type === 10) return { type, value: nativeString(value.add(8).readPointer()) };
    if (type === 11) return { type, value: value.add(8).readU8() !== 0 };   // a switch (@enabled, Polarity, …)
    fail(`unsupported native parameter type ${type}`);
  }
  function editorReady(editor) {
    if (editor.isNull() || !editor.readPointer().equals(base.add(0x963dfc))) return false;
    const table = editor.readPointer();
    return table.add(0x7c).readPointer().equals(base.add(0x5178c0))
      && table.add(0x88).readPointer().equals(base.add(0x504f50))
      && table.add(0xdc).readPointer().equals(base.add(0x51aaf0));
  }
  function internal(binding, context) {
    const state = bindings.get(binding);
    if (!state || binding.valid !== true || context !== state.context) fail('expired context');
    if (Process.getCurrentThreadId() !== state.thread) fail('not on the captured UI thread');
    if (!editorReady(state.editor)) fail('editor instance changed');
    return state;
  }
  function parameter(state, name) {
    let block = null, key = null;
    const value = emptyVariant();
    try {
      block = string(state.blockName); key = string(name);
      const result = readValue(state.editor, state.dsp, block, key, value);
      if (result < 0) fail(`read was rejected (${result})`);
      return decode(value);
    } finally {
      destroyVariant(value);
      if (key) destroyVariant(key);
      if (block) destroyVariant(block);
    }
  }
  function observed(state) {
    const model = parameter(state, '@model');
    const value = parameter(state, state.parameter);
    if (model.type !== 10 || !engines.has(model.value)) fail('block is no longer a supported NAM engine');
    if (![4, 5, 8].includes(value.type) || !Number.isInteger(value.value) || value.value < 1 || value.value > 128) {
      fail('native slot value is not an integer in 1–128');
    }
    return { slot: value.value, valueType: value.type, engine: model.value };
  }
  function capture(controller, model, config) {
    if (!config || config.context === undefined || !Number.isInteger(config.slot) || config.slot < 1 || config.slot > 127) {
      fail('capture requires a permanent original slot and context');
    }
    if (controller.isNull() || !controller.readPointer().equals(base.add(0x8d948c))) fail('unknown model selector');
    if (model.isNull() || !model.readPointer().equals(base.add(0x8e942c))) fail('unknown Model slider');
    if (model.add(0x104).readU8() !== 0) fail('global parameter cannot be bound as a block');
    const editor = controller.add(0x34).readPointer();
    if (!editorReady(editor)) fail('unsupported edit buffer');
    const dsp = controller.add(0x80).readS32(), blockName = nativeString(controller.add(0x84));
    const name = nativeString(model.add(0xf8));
    // The patched NAM engine inherits the stock IR model's Index parameter.
    // Never bind a different numeric slider merely because its value matches.
    if (![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName) || name !== 'Index') {
      fail('unsupported block or parameter identity');
    }
    const state = { editor, dsp, blockName, parameter: name, context: config.context,
      thread: Process.getCurrentThreadId(), originalSlot: config.slot };
    const current = observed(state);
    const value = emptyVariant();
    let slider;
    try { sliderValue(model, value); slider = decode(value); }
    finally { destroyVariant(value); }
    // The slider's valueType=0 emits signed integers, while the stored variant
    // may retain an unsigned numeric tag. Identity is the same integral slot;
    // preserve the edit buffer's own tag when restoring it later.
    if (current.slot !== config.slot || ![4, 5, 8].includes(slider.type) || slider.value !== config.slot) {
      fail('selected slider and addressed block disagree');
    }
    state.engine = current.engine; state.valueType = current.valueType;
    const binding = { valid: true, dsp, blockName, parameter: name, engine: current.engine,
      originalSlot: config.slot, context: config.context };
    bindings.set(binding, state);
    return binding;
  }
  function read(binding, config) {
    const state = internal(binding, config?.context);
    const current = observed(state);
    if (current.engine !== state.engine || current.valueType !== state.valueType) fail('bound block changed');
    return current;
  }
  function restore(binding, originalSlot, config) {
    const state = internal(binding, config?.context);
    const current = observed(state);
    if (!targetBindingRestoreAllowed({ ...state, valid: binding.valid }, current,
      { ...config, originalSlot })) fail('preview ownership or original value changed');
    let block = null, key = null;
    const value = emptyVariant();
    try {
      block = string(state.blockName); key = string(state.parameter);
      value.writeU32(state.valueType);
      if (state.valueType === 8) value.add(8).writeFloat(state.originalSlot);
      else value.add(8).writeU32(state.originalSlot);
      // Same typed call/flag used by HXParameterViewController for a single cva!
      // edit outside a slider gesture. No cursor or parameter-widget mutation.
      const result = writeValue(state.editor, state.dsp, block, key, value, 0x80000000);
      if (result < 0) fail(`restore was rejected (${result})`);
    } finally {
      destroyVariant(value);
      if (key) destroyVariant(key);
      if (block) destroyVariant(block);
    }
    // This acknowledges acceptance of the native edit, not completion. HX Edit
    // can dispatch its parameter notification after this call unwinds. The
    // preview lifecycle must poll read() (and the visible Model when selected)
    // before releasing128. Never make a successful API return stand in for it.
    return true;
  }
  function release(binding) {
    if (binding) { binding.valid = false; bindings.delete(binding); }
    // No native pointers to temporary strings are retained between calls.
  }
  function peekSlot(editor, dsp, blockName) {
    // The capture slot of any NAM block, read from the edit buffer. Read-only and unbound: for
    // presentation (which icon a block shows), never for an edit. null when it is not a NAM block
    // or cannot be read on this thread.
    try {
      if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName)) return null;
      const state = {editor, dsp, blockName, parameter: 'Index'};
      const model = parameter(state, '@model');
      if (model.type !== 10 || !engines.has(model.value)) return null;
      const value = parameter(state, 'Index');
      return [4, 5, 8].includes(value.type) && Number.isInteger(value.value) && value.value >= 1 && value.value <= 128 ?
        value.value : null;
    } catch (_) { return null; }
  }
  function peekModel(editor, dsp, blockName) {
    // Any block's model symbol and Index (an IR block's slot), read from the edit buffer.
    // Read-only, for noticing an IR block that plays a NAM capture's slot. null when unreadable.
    try {
      if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName)) return null;
      const state = {editor, dsp, blockName, parameter: 'Index'};
      const model = parameter(state, '@model');
      if (model.type !== 10 || typeof model.value !== 'string') return null;
      let index = null;
      try {                                    // a block with no Index (most models) still has a model
        const value = parameter(state, 'Index');
        if ([4, 5, 8].includes(value.type) && Number.isInteger(value.value)) index = value.value;
      } catch (_) { index = null; }
      return {model: model.value, index};
    } catch (_) { return null; }
  }
  // Focus Mode: any value of a block, an input, an output, the split or the join, read from the edit
  // buffer by its name in HX Edit's model definitions ("Drive", "@enabled", "@model", …). Read-only.
  // A number, a string or a boolean; undefined when the block or the value is not there.
  const placePattern = /^(?:block\d{1,2}|input[AB]|output[AB]|split|join)$/, keyPattern = /^@?[A-Za-z0-9_ ]{1,48}$/;
  function peekValue(editor, dsp, blockName, key) {
    try {
      if (!editorReady(editor) || ![0, 1].includes(dsp) || !placePattern.test(blockName) || !keyPattern.test(key)) return undefined;
      return parameter({editor, dsp, blockName}, key).value;
    } catch (_) { return undefined; }
  }
  // Focus Mode's top bar: a value of the preset itself, read as Level presets reads it (dsp -1): the group
  // "global" ("@current_snapshot") or "snapshot0".."snapshot7" ("@name"). Read-only; undefined when it is not there.
  const groupPattern = /^(?:global|snapshot[0-7])$/;
  function peekGlobal(editor, group, key) {
    try {
      if (!editorReady(editor) || !groupPattern.test(group) || !keyPattern.test(key)) return undefined;
      return parameter({editor, dsp: -1, blockName: group}, key).value;
    } catch (_) { return undefined; }
  }
  // The Workbench's Bypass and controllers / Snapshot values tabs: the preset's own tree, as HX Edit's controller
  // view reads it (0x1b72cd: dsp -1, the group "controller", the key "dsp0.block1.Gain.@controller"), and the same
  // for "footswitch" and "snapshot0".."snapshot7" (the sections of a preset file). Read-only; undefined when not there.
  const treePattern = /^(?:controller|footswitch|snapshot[0-7])$/, pathPattern = /^[A-Za-z0-9_ .@+-]{1,120}$/;
  function peekTree(editor, group, key) {
    try {
      if (!editorReady(editor) || !treePattern.test(group) || !pathPattern.test(key)) return undefined;
      return parameter({editor, dsp: -1, blockName: group}, key).value;
    } catch (error) {
      // (there, but of a kind decode does not read yet: said so, for the trace)
      const kind = /unsupported native parameter type (\d+)/.exec(String(error.message));
      return kind ? {unsupportedType: Number(kind[1])} : undefined;
    }
  }
  // Recalls a snapshot (0..7) as HX Edit's own snapshot control and Level presets do: "@current_snapshot" of
  // "global", one write with the single-change flag. Nothing is saved.
  function recallSnapshot(editor, index) {
    if (!editorReady(editor) || !Number.isInteger(index) || index < 0 || index > 7) fail('unsupported snapshot');
    const current = parameter({editor, dsp: -1, blockName: 'global'}, '@current_snapshot');
    if (![4, 5].includes(current.type)) fail('unexpected snapshot value');
    let group = null, name = null;
    const variant = emptyVariant();
    try {
      group = string('global'); name = string('@current_snapshot');
      variant.writeU32(current.type); variant.add(8).writeU32(index);
      const result = writeValue(editor, -1, group, name, variant, WRITE_FLAGS.single);
      if (result < 0) fail(`snapshot recall was rejected (${result})`);
    } finally {
      destroyVariant(variant);
      if (name) destroyVariant(name);
      if (group) destroyVariant(group);
    }
    return true;
  }
  // The Workbench's Bypass and controllers tab: a value of the preset's "controller" or "footswitch" section written
  // as HX Edit's own Bypass/Controller Assign tab writes it (seen with the chain probe 2026-11-22): +0x7c, dsp -1,
  // flags 0, e.g. ("controller", "dsp0.block1.Drive.@controller", Variant{1, 1}) for EXP Pedal 1, a float 0..1 for
  // "@min" / "@max", ("footswitch", "dsp0.block0.@fs_index", Variant{1, N}), "@fs_customcolor", "@fs_customlabel".
  // The value keeps the kind HX Edit already has there; where nothing is there yet, kind says: 'enum' (Variant type 1,
  // as HX Edit writes @controller and @fs_index), 'float', 'bool' or 'text'.
  const writePattern = /^(?:controller|footswitch)$/;
  function writeTree(editor, group, key, value, kind) {
    if (!editorReady(editor) || !writePattern.test(group) || !pathPattern.test(key) || !['enum', 'float', 'bool', 'text'].includes(kind)) fail('unsupported tree value');
    let type = {enum: 1, float: 8, bool: 11, text: 10}[kind];
    // (an 'enum' is always written as HX Edit writes it, type 1, whatever a reading of it says)
    if (kind !== 'enum') {
      try { const now = parameter({editor, dsp: -1, blockName: group}, key); if ([4, 5, 8, 10, 11].includes(now.type)) type = now.type; } catch (_) { /* not there yet */ }
    }
    let groupName = null, keyName = null, variant = null;
    try {
      groupName = string(group); keyName = string(key);
      if (type === 10) {
        if (typeof value !== 'string' || value.length > 32) fail('unsupported text');
        variant = string(value);
      } else {
        variant = emptyVariant(); variant.writeU32(type);
        if (type === 8) { if (!Number.isFinite(value)) fail('unsupported number'); variant.add(8).writeFloat(value); }
        else if (type === 11) variant.add(8).writeU8(value ? 1 : 0);
        else { if (!Number.isInteger(value)) fail('unsupported whole number'); variant.add(8).writeS32(value); }
      }
      const result = writeValue(editor, -1, groupName, keyName, variant, 0);
      if (result < 0) fail(`HX Edit refused to change ${key} (${result})`);
    } finally {
      if (variant) destroyVariant(variant);
      if (keyName) destroyVariant(keyName);
      if (groupName) destroyVariant(groupName);
    }
    return true;
  }
  // Focus Mode: a value of a block written as HX Edit's own parameter view writes it (0x229c47 -> the setter
  // 0x5178c0). The flags are the ones seen on a stock slider (listened to on the Floor editor, 2026-11-20):
  // a single change 0x80000000; a drag = begin 0x80000001 (the value as it is), each change 0x80000003,
  // end 0x80000002 (the last value): HX Edit keeps a whole drag as one step of its undo.
  // A slider's own write leaves HX Edit's parameter views as they are (the slider already shows the value), so
  // after a write from elsewhere they showed the old value. HX Edit's undo writes with 0x40000000: the views
  // follow such a write, and it is not kept for undo (both seen on the Floor editor, 2026-11-20; with both bits
  // set nothing was kept for undo either). So "refresh" is a second write of the value just set, with that flag
  // alone: HX Edit's own sliders show it, and the step kept for undo is the slider-style write before it.
  // The stored value's own type is kept (a float, a whole number or a switch). Never a model, a place or a name.
  const WRITE_FLAGS = Object.freeze({single: 0x80000000, begin: 0x80000001, move: 0x80000003, end: 0x80000002,
                                     refresh: 0x40000000});
  const fixedKeys = new Set(['@model', '@position', '@path', '@type', '@stereo']);
  function setValue(editor, dsp, blockName, key, value, phase) {
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !placePattern.test(blockName) || !keyPattern.test(key) ||
        fixedKeys.has(key) || !Object.hasOwn(WRITE_FLAGS, phase)) fail('unsupported value write');
    const current = parameter({editor, dsp, blockName}, key);
    if (current.type === 11 ? typeof value !== 'boolean' : !([4, 5, 8].includes(current.type) && Number.isFinite(value))) {
      fail('value does not fit the stored type');
    }
    let block = null, name = null;
    const variant = emptyVariant();
    try {
      block = string(blockName); name = string(key);
      variant.writeU32(current.type);
      if (current.type === 8) variant.add(8).writeFloat(value);
      else if (current.type === 11) variant.add(8).writeU8(value ? 1 : 0);
      else if (current.type === 4) variant.add(8).writeS32(Math.round(value));
      else variant.add(8).writeU32(Math.max(0, Math.round(value)));
      const result = writeValue(editor, dsp, block, name, variant, WRITE_FLAGS[phase]);
      if (result < 0) fail(`write was rejected (${result})`);
    } finally {
      destroyVariant(variant);
      if (name) destroyVariant(name);
      if (block) destroyVariant(block);
    }
    return true;
  }
  function setIndex(editor, dsp, blockName, slot) {
    // A NAM block's capture slot, written as restore() writes it (one undo step), keeping the
    // stored value's own type. Only for a supported NAM engine and a permanent slot.
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName) ||
        !Number.isInteger(slot) || slot < 1 || slot > 127) fail('unsupported block or slot');
    const state = {editor, dsp, blockName, parameter: 'Index'};
    const model = parameter(state, '@model');
    if (model.type !== 10 || !engines.has(model.value)) fail('not a NAM block');
    const current = parameter(state, 'Index');
    if (![4, 5, 8].includes(current.type)) fail('unexpected slot value');
    let block = null, key = null;
    const value = emptyVariant();
    try {
      block = string(blockName); key = string('Index');
      value.writeU32(current.type);
      if (current.type === 8) value.add(8).writeFloat(slot); else value.add(8).writeU32(slot);
      const result = writeValue(editor, dsp, block, key, value, 0x80000000);
      if (result < 0) fail(`write was rejected (${result})`);
    } finally {
      destroyVariant(value);
      if (key) destroyVariant(key);
      if (block) destroyVariant(block);
    }
    return true;
  }
  // What the block picker itself does when a model row is chosen (0x21a470): a block's model
  // changes through the editor's parameter write (vtbl+0x7c = 0x5178c0, "@model"); an empty cell
  // gets a block through vtbl+0xa8 = 0x4ff300(dsp, &Variant(symbol), &Variant{5, (row<<16)|col},
  // flags). One undo step each, and HX Edit fills the defaults itself: far quicker than pasting a
  // favorite. Symbols only of HX Edit's models.
  const symbolPattern = /^[A-Za-z0-9_]{3,64}$/;
  function setModel(editor, dsp, blockName, symbol) {
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName) || !symbolPattern.test(symbol)) {
      fail('unsupported block or model');
    }
    let block = null, key = null, value = null;
    try {
      block = string(blockName); key = string('@model'); value = string(symbol);
      const result = writeValue(editor, dsp, block, key, value, 0x80000000);
      if (result < 0) fail(`model change was rejected (${result})`);
    } finally {
      if (value) destroyVariant(value);
      if (key) destroyVariant(key);
      if (block) destroyVariant(block);
    }
    return true;
  }
  function addModel(editor, dsp, row, col, symbol) {
    if (!editorReady(editor) || ![0, 1].includes(dsp) || ![0, 1].includes(row) || !Number.isInteger(col) ||
        col < 0 || col > 15 || !symbolPattern.test(symbol)) fail('unsupported cell or model');
    const entry = editor.readPointer().add(0xa8).readPointer();
    if (!entry.equals(base.add(0x4ff300))) fail('unexpected editor add-block entry');
    const add = new NativeFunction(entry, 'int', ['pointer', 'int', 'pointer', 'pointer', 'uint'], 'thiscall');
    let value = null;
    const cell = emptyVariant();
    try {
      value = string(symbol);
      cell.writeU32(5); cell.add(8).writeU32(((row << 16) | col) >>> 0);
      const result = add(editor, dsp, value, cell, 0x80000000);
      if (result < 0) fail(`adding the block was rejected (${result})`);
    } finally {
      if (value) destroyVariant(value);
    }
    return true;
  }
  // The Workbench: a block removed or moved as HX Edit itself does it, through the edit buffer's own entries beside
  // add (research/modern-ui/STAGE2-FINDINGS.md, read from HX Edit.exe 3.82 on disk). Remove is vtbl+0xb0 = 0x514bc0
  // (dsp, &Variant(block name), flags): what HX Edit's block picker calls when "None" is chosen (0x21a565). Move is
  // vtbl+0xa0 = 0x5123c0 (dsp, &Variant(block name), &Variant{5, (lane<<16)|place}, flags): what its chain's drag
  // calls (0x412932). Flags 0x80000000, a user's action: one undo step each. Only a block of the chain, never an
  // input, an output, the split or the join, and only when the entry is the one studied.
  function editorEntry(editor, slot, rva, what) {
    const entry = editor.readPointer().add(slot).readPointer();
    if (!entry.equals(base.add(rva))) fail(`unexpected editor ${what} entry`);
    return entry;
  }
  function removeBlock(editor, dsp, blockName) {
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName)) fail('unsupported block');
    const remove = new NativeFunction(editorEntry(editor, 0xb0, 0x514bc0, 'remove-block'), 'int', ['pointer', 'int', 'pointer', 'uint'], 'thiscall');
    let name = null;
    try {
      name = string(blockName);
      const result = remove(editor, dsp, name, 0x80000000);
      if (result < 0) fail(`removing the block was rejected (${result})`);
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  function moveBlock(editor, dsp, blockName, row, col) {
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !/^block\d{1,2}$/.test(blockName) || ![0, 1].includes(row) ||
        !Number.isInteger(col) || col < 0 || col > 7) fail('unsupported block or place');
    const move = new NativeFunction(editorEntry(editor, 0xa0, 0x5123c0, 'move-block'), 'int', ['pointer', 'int', 'pointer', 'pointer', 'uint'], 'thiscall');
    let name = null;
    const cell = emptyVariant();
    try {
      name = string(blockName);
      cell.writeU32(5); cell.add(8).writeU32(((row << 16) | col) >>> 0);
      const result = move(editor, dsp, name, cell, 0x80000000);
      if (result < 0) fail(`moving the block was rejected (${result})`);
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  function removeNode(editor, dsp, which) {
    // Lane B's own input or output, as HX Edit's split / mixer menu "Create Input" / "Create Output" (shortcut Del)
    // makes it: its menu's clear (0x41b224), the remove entry (+0xb0 = 0x514bc0) on "split" (-> 0x4d66b0) or "join"
    // (-> 0x4d5cf0). Flags 0x80000000, as the menu: one undo step. (The way back is an add: restoreNode. A second
    // removal, or one on "inputB" / "outputB", is refused: -4, seen 2026-11-22.)
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !['split', 'join'].includes(which)) fail('unsupported routing item');
    const remove = new NativeFunction(editorEntry(editor, 0xb0, 0x514bc0, 'remove-block'), 'int', ['pointer', 'int', 'pointer', 'uint'], 'thiscall');
    let name = null;
    try {
      name = string(which);
      const result = remove(editor, dsp, name, 0x80000000);
      if (result < 0) fail(`HX Edit refused to change lane B's routing (${result})`);
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  function restoreNode(editor, dsp, which) {
    // The split or the mixer back in place of lane B's own input or output, as HX Edit's menu "Restore Split" /
    // "Restore Merge" does it (seen with the chain probe 2026-11-22): the add entry (+0xa8 = 0x4ff300) with the item
    // "split" at place 0 or "join" at place 8 of lane A; add hands those to 0x484970 / 0x483e40. One undo step.
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !['split', 'join'].includes(which)) fail('unsupported routing item');
    const add = new NativeFunction(editorEntry(editor, 0xa8, 0x4ff300, 'add-block'), 'int', ['pointer', 'int', 'pointer', 'pointer', 'uint'], 'thiscall');
    let name = null;
    const cell = emptyVariant();
    try {
      name = string(which);
      cell.writeU32(5); cell.add(8).writeU32(which === 'split' ? 0 : 8);
      const result = add(editor, dsp, name, cell, 0x80000000);
      if (result < 0) fail(`HX Edit refused to put the ${which === 'join' ? 'mixer' : 'split'} back (${result})`);
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  function selectNode(editor, dsp, which) {
    // The split or the mixer selected in HX Edit (its settings then show, as a block's do): "@cursor_dsp" and then
    // "@cursor_group" of "global", as HX Edit's chain drop selects a split or a mixer it has just moved (0x41324f:
    // +0x80, which is +0x7c with flags 0: no undo step). Nothing of the preset changes.
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !['split', 'join'].includes(which)) fail('unsupported split or mixer');
    const current = parameter({editor, dsp: -1, blockName: 'global'}, '@cursor_dsp');
    if (![4, 5].includes(current.type)) fail('unexpected cursor value');
    let group = null, key = null, name = null;
    const number = emptyVariant();
    try {
      group = string('global'); key = string('@cursor_dsp');
      number.writeU32(current.type); number.add(8).writeU32(dsp >>> 0);
      let result = writeValue(editor, -1, group, key, number, 0);
      if (result < 0) fail(`selecting the path was rejected (${result})`);
      destroyVariant(key); key = string('@cursor_group'); name = string(which);
      result = writeValue(editor, -1, group, key, name, 0);
      if (result < 0) fail(`selecting the ${which === 'join' ? 'mixer' : 'split'} was rejected (${result})`);
    } finally {
      destroyVariant(number);
      if (name) destroyVariant(name);
      if (key) destroyVariant(key);
      if (group) destroyVariant(group);
    }
    return true;
  }
  function moveSplit(editor, dsp, which, gap) {
    // The split or the mixer to another gap of lane A (0 = before place 1, 8 = after place 8): the same move entry
    // (+0xa0 = 0x5123c0) with the item "split" or "join". For those it reads only the place of the target cell and
    // hands it to the split's or the mixer's own code (0x4c8800 / 0x4c7d60, static study 2026-11-22), as HX Edit's
    // chain drag does (0x4131b2 checks for them after a drop). Flags 0x80000000: one undo step.
    if (!editorReady(editor) || ![0, 1].includes(dsp) || !['split', 'join'].includes(which) || !Number.isInteger(gap) ||
        gap < 0 || gap > 8) fail('unsupported split, mixer or gap');
    const move = new NativeFunction(editorEntry(editor, 0xa0, 0x5123c0, 'move-block'), 'int', ['pointer', 'int', 'pointer', 'pointer', 'uint'], 'thiscall');
    let name = null;
    const cell = emptyVariant();
    try {
      name = string(which);
      cell.writeU32(5); cell.add(8).writeU32(gap >>> 0);
      const result = move(editor, dsp, name, cell, 0x80000000);
      if (result < 0) fail(`moving the ${which === 'join' ? 'mixer' : 'split'} was rejected (${result})`);
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  function blockCells(editor, dsp) {
    // The blocks of a path as the edit buffer has them now: [{name, path, position}].
    const found = [];
    for (let k = 0; k < 32; k++) {
      const name = 'block' + k;
      if (!peekModel(editor, dsp, name)) continue;
      const lane = peekValue(editor, dsp, name, '@path'), place = peekValue(editor, dsp, name, '@position');
      if (Number.isInteger(lane) && Number.isInteger(place)) found.push({name, path: lane, position: place});
    }
    return found;
  }
  function moveAcross(editor, fromDsp, blockName, toDsp, row, col) {
    // A block to an empty place of the other path, as HX Edit's own drag between the paths does it: the block is
    // copied to the drag's own store (store 2, not the clipboard: +0xb8, as the chain's drag start 0x416de7), pasted
    // on the other path (+0xc4 with 0x100, as the chain's drop of a block from the other path 0x412af1), and
    // removed from its own (+0xb0, as the drag's end 0x41200b), the paste and the removal as one undo step (+0xd4
    // opens it, +0xd8 closes it with the outcome, as the drop does). Nothing is changed when the paste is refused.
    if (!editorReady(editor) || ![0, 1].includes(fromDsp) || ![0, 1].includes(toDsp) || fromDsp === toDsp ||
        !/^block\d{1,2}$/.test(blockName) || ![0, 1].includes(row) || !Number.isInteger(col) || col < 0 || col > 7) fail('unsupported block or place');
    const copy = new NativeFunction(editorEntry(editor, 0xb8, 0x5034b0, 'copy-block'), 'int', ['pointer', 'int', 'int', 'pointer'], 'thiscall');
    const canPaste = new NativeFunction(editorEntry(editor, 0xc8, 0x500320, 'can-paste'), 'int', ['pointer', 'int', 'int', 'pointer', 'uint'], 'thiscall');
    const paste = new NativeFunction(editorEntry(editor, 0xc4, 0x513620, 'paste'), 'int', ['pointer', 'int', 'int', 'pointer', 'uint'], 'thiscall');
    const remove = new NativeFunction(editorEntry(editor, 0xb0, 0x514bc0, 'remove-block'), 'int', ['pointer', 'int', 'pointer', 'uint'], 'thiscall');
    const open = new NativeFunction(editorEntry(editor, 0xd4, 0x4ffa80, 'undo-open'), 'int', ['pointer', 'uint'], 'thiscall');
    const close = new NativeFunction(editorEntry(editor, 0xd8, 0x5044b0, 'undo-close'), 'int', ['pointer', 'int'], 'thiscall');
    let name = null;
    const cell = emptyVariant();
    try {
      name = string(blockName);
      cell.writeU32(5); cell.add(8).writeU32(((row << 16) | col) >>> 0);
      let result = copy(editor, 2, fromDsp, name);
      if (result < 0) fail(`copying the block was rejected (${result})`);
      // Lane B of a path that has only lane A: HX Edit's paste refuses it (seen 2026-11-22, -4), a move within a
      // path does not. Then the block is pasted on an empty place of lane A (its own place first) and moved down
      // there, as a drag within that path moves it.
      let via = null;
      result = canPaste(editor, 2, toDsp, cell, 0);
      if (result < 0 && row === 1) {
        const taken = blockCells(editor, toDsp).map(b => b.path + ':' + b.position);
        for (const place of [col, 0, 1, 2, 3, 4, 5, 6, 7]) {
          if (taken.includes('0:' + place)) continue;
          cell.add(8).writeU32(place >>> 0);
          if (canPaste(editor, 2, toDsp, cell, 0) >= 0) { via = place; result = 0; break; }
        }
      }
      if (result < 0) fail(`the other path refused the block (${result})`);
      const model = peekModel(editor, fromDsp, blockName), before = via === null ? [] : blockCells(editor, toDsp).map(b => b.name);
      open(editor, 0x80000000);
      try {
        result = paste(editor, 2, toDsp, cell, 0x100);
        // The paste with 0x100 takes the block from its own path itself (seen 2026-11-22: a removal after it was
        // refused, -4, and closing the undo step with that lost it). Removed here only if it is still there.
        const left = result >= 0 ? peekModel(editor, fromDsp, blockName) : null;
        if (left && model && left.model === model.model) result = remove(editor, fromDsp, name, 0);
      } finally {
        close(editor, result);
      }
      if (result < 0) fail(`moving the block to the other path was rejected (${result})`);
      // Pasted on lane A for lane B: the caller moves it down later (moveBlock), once the Floor has the block. Moved
      // down at once, inside the paste's undo step or right after it, HX Edit had it on lane B but the Floor never
      // got the move (seen twice on 2026-11-22: the Floor kept it on lane A). {down: its name now, lane, place}.
      if (via !== null) {
        const made = blockCells(editor, toDsp).find(b => !before.includes(b.name) && b.path === 0 && b.position === via);
        if (!made) fail('the block reached the other path but could not be found there');
        return {down: made.name, dsp: toDsp, from: via, lane: 1, place: col};
      }
    } finally {
      if (name) destroyVariant(name);
    }
    return true;
  }
  return { capture, read, restore, release, peekSlot, peekModel, peekValue, peekGlobal, peekTree, writeTree, recallSnapshot, setValue, setIndex, setModel, addModel,
           removeBlock, moveBlock, moveAcross, moveSplit, selectNode, removeNode, restoreNode };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { targetBindingGuards, targetBindingRestoreAllowed, installTargetBinding };
}
