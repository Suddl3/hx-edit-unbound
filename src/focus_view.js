'use strict';

// Focus Mode (HX Unbound menu): the selected block shown large in its scene, in a WebView2 pane
// over HX Edit's signal flow and edit panel (focus_view.py, focus_view.cs, focus_view.html).
// This script is the pane's eyes inside HX Edit 3.82 x86: while Focus Mode is on it reads the
// preset's blocks and the selected block's values from the edit buffer by name (target_binding
// peekValue: HX Edit's own getter, the one its parameter views use) and sends what changed.
// It reads only; nothing here writes to the preset or the device. A block picked in the pane's
// chain strip is selected by a click on that block in HX Edit's own chain (under the pane).
// (The notification handler 0x218a00 is hooked by nam_view and tone_view before this script installs, so its
// first bytes are already Frida's jump: it is guarded there, and by the launcher's check of the whole exe.)
const focusViewGuards = Object.freeze({
  '3b7e00': '558bec83ec08568b7508578bf9c70600',   // a widget's origin in the window (as nav_banner uses it)
});

// Where things sit on a DSP, in signal order. A block's place on its path is @position; @path 1 is the lower path.
const FOCUS_ENDS = Object.freeze(['inputA', 'inputB', 'split', 'join', 'outputA', 'outputB']);
const FOCUS_BLOCKS = 16;

// The preset as the pane draws it, from a reader peek(dsp, place, key). Pure: tests run it on a fake reader.
//   blocks: [{dsp, id, model, position, path, enabled, slot}] (slot: a NAM block's capture slot)
//   selected: {dsp, id} or null; values: the selected block's {parameter: value}
function focusSnapshot(peek, cursor, parameters, namEngines) {
  const blocks = [];
  for (const dsp of [0, 1]) {
    const places = [...FOCUS_ENDS, ...Array.from({length: FOCUS_BLOCKS}, (_, index) => 'block' + index)];
    for (const id of places) {
      const model = peek(dsp, id, '@model');
      if (typeof model !== 'string' || !model) continue;
      const block = {dsp, id, model};
      const position = peek(dsp, id, '@position'), path = peek(dsp, id, '@path');
      block.position = Number.isInteger(position) ? position : null;
      block.path = path === 1 ? 1 : 0;
      block.enabled = peek(dsp, id, '@enabled') !== false;
      if (namEngines.includes(model)) {
        const slot = peek(dsp, id, 'Index');
        block.slot = Number.isInteger(slot) ? slot : null;
      }
      blocks.push(block);
    }
  }
  let selected = null, values = {};
  const at = cursor && blocks.find(block => block.dsp === cursor.dsp && block.id === cursor.block);
  if (at) {
    selected = {dsp: at.dsp, id: at.id};
    for (const key of parameters[at.model] || []) {
      const value = peek(at.dsp, at.id, key);
      if (typeof value === 'number' || typeof value === 'boolean') values[key] = value;
    }
  }
  return {blocks, selected, values};
}

// Between full readings, only what a knob, a switch or a footswitch changes: each block's bypass (and a NAM
// block's capture slot) and the selected block's values. null when the blocks themselves are no longer the same
// (the selected block's model changed, or the cursor is on a block not seen yet): read everything again.
function focusValues(peek, blocks, cursor, parameters, namEngines) {
  const next = blocks.map(block => {
    const copy = {...block, enabled: peek(block.dsp, block.id, '@enabled') !== false};
    if (namEngines.includes(block.model)) {
      const slot = peek(block.dsp, block.id, 'Index');
      copy.slot = Number.isInteger(slot) ? slot : null;
    }
    return copy;
  });
  let selected = null, values = {};
  if (cursor && cursor.block) {
    const at = next.find(block => block.dsp === cursor.dsp && block.id === cursor.block);
    if (!at || peek(at.dsp, at.id, '@model') !== at.model) return null;
    selected = {dsp: at.dsp, id: at.id};
    for (const key of parameters[at.model] || []) {
      const value = peek(at.dsp, at.id, key);
      if (typeof value === 'number' || typeof value === 'boolean') values[key] = value;
    }
  }
  return {blocks: next, selected, values};
}

// Where to click HX Edit's own chain to select a block: its cell in the DSP's chain panel, low in the cell (on
// the name, clear of the bypass and delete buttons that show over the picture). A panel is ten cells wide
// (the input, eight blocks, the output) and two paths high. null for what has no cell of its own.
function focusChainPoint(box, block) {
  if (!box || !block || ![box.x, box.y, box.w, box.h].every(Number.isFinite)) return null;
  let column, row;
  if (block.id === 'inputA' || block.id === 'inputB') { column = 0; row = block.id === 'inputB' ? 1 : 0; }
  else if (block.id === 'outputA' || block.id === 'outputB') { column = 9; row = block.id === 'outputB' ? 1 : 0; }
  else if (/^block\d{1,2}$/.test(block.id) && Number.isInteger(block.position) && block.position >= 0 && block.position < 8) {
    column = block.position + 1; row = block.path === 1 ? 1 : 0;
  } else return null;
  return {x: Math.round(box.x + (column + .5) * box.w / 10), y: Math.round(box.y + (row + .8) * box.h / 2)};
}

// The pane's place: the main window below HX Edit's top row (preset, undo, DSP meter), down to the
// edit panel's bottom, across the whole window. sf/ed/main: {x, y, w, h} of the signal flow view
// ('sfvc'), the editor view ('edvw') and the window's root view ('main'), in client coordinates.
function focusPaneBounds(sf, ed, main) {
  if (![sf, ed, main].every(box => box && [box.x, box.y, box.w, box.h].every(Number.isFinite))) return null;
  const top = Math.max(0, sf.y - 6), bottom = Math.min(main.y + main.h, ed.y + ed.h);
  if (bottom - top < 300 || main.w < 600) return null;                 // a window too small for the pane
  return {x: main.x, y: top, w: main.w, h: bottom - top};
}

function installFocusView(options, parts) {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Focus Mode requires HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, hex] of Object.entries(focusViewGuards)) {
    const bytes = new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(hex.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error(`Focus Mode native byte guard failed at ${rva}`);
  }
  const {targetBinding, namView, toneView} = parts;
  const parameters = options.focusParameters || {}, namEngines = options.focusNamEngines || ['HD2_AmpNAMLite'];
  const widgetOrigin = new NativeFunction(base.add(0x3b7e00), 'pointer', ['pointer', 'pointer'], 'thiscall');
  const point = Memory.alloc(8);
  const SFVC = 0x73667663, EDVW = 0x65647677, MAIN = 0x6d61696e;
  // Values are read four times a second; the blocks themselves when HX Edit says something other than a value
  // changed, and every two seconds in any case.
  const POLL_MS = 250, FULL_MS = 2000;
  let on = false, timer = null, queued = false, queuedAt = 0, editor = NULL, lastState = '', lastBounds = '', reports = 6;
  let known = null, knownAt = 0, changed = true, wanted = null;

  function box(widget) {
    const geometry = widget.add(0x54).readPointer();
    widgetOrigin(widget, point);
    return {x: point.readS32(), y: point.add(4).readS32(),
            w: geometry.add(12).readS32() - geometry.add(4).readS32(), h: geometry.add(16).readS32() - geometry.add(8).readS32()};
  }
  function paneBounds() {
    // From the chain's own view up to the window's root view, by each view's id.
    let widget = namView.chainPanel(), sf = null, ed = null, main = null;
    for (let depth = 0; depth < 12 && widget && !widget.isNull(); depth++) {
      const geometry = widget.add(0x54).readPointer();
      if (geometry.isNull()) break;
      const id = geometry.readU32();
      if (id === SFVC) sf = box(widget);
      else if (id === EDVW) ed = box(widget);
      else if (id === MAIN) { main = box(widget); break; }
      widget = geometry.add(0x14).readPointer();
    }
    return focusPaneBounds(sf, ed, main);
  }
  function captures() {
    // The captures on the Floor, by slot: a NAM block's name and picture come from its slot.
    try { return namView.installedCaptures().map(capture => ({slot: capture.slot, name: capture.name, icon: capture.icon, gear: capture.gear})); }
    catch (_) { return []; }
  }
  function refresh(window) {
    queued = false;
    if (!on) return;
    try {
      const bounds = paneBounds();
      const place = JSON.stringify(bounds);
      if (place !== lastBounds) { lastBounds = place; send({type: 'focusBounds', window: window.toUInt32(), bounds}); }
      const cursor = toneView.cursorBlock();
      if (cursor && !cursor.editor.isNull()) editor = cursor.editor;
      if (editor.isNull()) { publish({blocks: [], selected: null, values: {}, captures: []}); return; }
      const began = Date.now(), peek = (dsp, place, key) => targetBinding.peekValue(editor, dsp, place, key);
      let state = !changed && known && began - knownAt < FULL_MS ? focusValues(peek, known, cursor, parameters, namEngines) : null;
      const full = !state;
      if (full) { state = focusSnapshot(peek, cursor, parameters, namEngines); knownAt = began; changed = false; }
      known = state.blocks;
      state.captures = state.blocks.some(block => block.slot !== undefined) ? captures() : [];
      if (reports > 0) { reports--; send({type: 'toneTrace', reason: 'focus-view', stage: full ? 'read' : 'read-values', ms: Date.now() - began, blocks: state.blocks.length, selected: !!state.selected}); }
      publish(state);
      if (wanted) select(wanted);
    } catch (error) {
      if (reports > 0) { reports--; send({type: 'toneTrace', reason: 'focus-view', stage: 'read-failed', error: String(error.message)}); }
    }
  }
  function select(target) {
    // A block picked in the pane's chain strip: a click on that block in HX Edit's own chain.
    wanted = null;
    const block = (known || []).find(item => item.dsp === target.dsp && item.id === target.id);
    const spot = block && focusChainPoint(namView.chainBox(block.dsp), block);
    const clicked = !!spot && namView.clickChainPoint(spot.x, spot.y);
    send({type: 'toneTrace', reason: 'focus-view', stage: clicked ? 'select' : 'select-skipped', dsp: target.dsp, block: target.id});
  }
  function publish(state) {
    const text = JSON.stringify(state);
    if (text === lastState) return;
    lastState = text;
    send({type: 'focusState', state});
  }
  function ask() {
    // Reads run on HX Edit's UI thread, one at a time.
    // (A request HX Edit has not run after two seconds, a busy or closing window, is asked again.)
    if (!on || (queued && Date.now() - queuedAt < 2000)) return;
    queued = namView.queueSidebarAction(refresh) === true;
    queuedAt = Date.now();
  }
  function set(value) {
    on = value === true;
    if (timer) { clearInterval(timer); timer = null; }
    lastState = ''; lastBounds = ''; queued = false; known = null; changed = true; wanted = null;
    if (on) { timer = setInterval(ask, POLL_MS); ask(); }
    send({type: 'toneTrace', reason: 'focus-view', stage: on ? 'on' : 'off'});
  }
  // A change in the editor (a knob turned here or on the Floor, another block picked, a preset loaded)
  // is read at once rather than at the next poll.
  // Anything but a plain value change (a block added, moved or replaced, a preset or snapshot loaded) means
  // the blocks are read again; a value change only the values.
  function eventName(value) {
    const data = value.add(4).readPointer();
    return data.isNull() ? '' : data.add(0x10).readPointer().readUtf8String();
  }
  const hook = Interceptor.attach(base.add(0x218a00), {
    onEnter(args) {
      if (!on) return;
      try { if (eventName(args[0]) !== 'EditBuffer_ParamChanged') changed = true; } catch (_) { changed = true; }
    },
    onLeave() { if (on) ask(); },
  });
  function listen() {
    recv('focusMode', message => {
      const value = message.payload || {};
      if (value.resend) { lastState = ''; lastBounds = ''; ask(); }
      else set(value.on === true);
      listen();
    });
  }
  function commands() {
    recv('focusCommand', message => {
      const value = message.payload || {};
      if (on && value.action === 'select' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && value.id.length < 16) {
        wanted = {dsp: value.dsp, id: value.id};
        queued = false; ask();
      }
      commands();
    });
  }
  listen(); commands();
  return { set, dispose() { set(false); hook.detach(); } };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { focusViewGuards, focusSnapshot, focusValues, focusChainPoint, focusPaneBounds, installFocusView };
}
