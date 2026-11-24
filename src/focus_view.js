'use strict';

// Focus Mode (HX Unbound menu): the selected block shown large in its scene, in a WebView2 pane
// over HX Edit's signal flow and edit panel (focus_view.py, focus_view.cs, focus_view.html).
// This script is the pane's eyes inside HX Edit 3.82 x86: while Focus Mode is on it reads the
// preset's blocks and the selected block's values from the edit buffer by name (target_binding
// peekValue: HX Edit's own getter, the one its parameter views use) and sends what changed.
// A block picked in the pane's chain strip is selected by a click on that block in HX Edit's own
// chain (under the pane). A knob, a switch or the bypass turned in the pane is one value of the
// selected block, written as HX Edit's own sliders write it (target_binding setValue): a drag is a
// begin, its changes and an end, so HX Edit undoes it in one step. A model or a capture chosen from
// the pane's list is set as HX Edit's own block picker sets it (target_binding setModel, setIndex),
// after checking the DSP has room. Nothing else is ever written.
// (The notification handler 0x218a00 is hooked by nam_view and tone_view before this script installs, so its
// first bytes are already Frida's jump: it is guarded there, and by the launcher's check of the whole exe.)
const focusViewGuards = Object.freeze({
  '3b7e00': '558bec83ec08568b7508578bf9c70600',   // a widget's origin in the window (as nav_banner uses it)
});

// Where things sit on a DSP, in signal order. A block's place on its path is @position; @path 1 is the lower path.
const FOCUS_ENDS = Object.freeze(['inputA', 'inputB', 'split', 'join', 'outputA', 'outputB']);
const FOCUS_BLOCKS = 16;
// HX Edit's IR blocks: their IR is a slot of the IR store, read as a NAM block's capture slot is (Index)
const FOCUS_IR_MODEL = /^HD2_ImpulseResponse\d{3,4}[A-Za-z]*$/;

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
      // Where an input takes its signal and an output sends it (HX Edit's input_type / output_type lists), and the
      // split's and the mixer's own settings: the Workbench draws the routing from them.
      const route = id.startsWith('input') ? peek(dsp, id, '@input') : id.startsWith('output') ? peek(dsp, id, '@output') : undefined;
      if (Number.isInteger(route)) block[id.startsWith('input') ? 'input' : 'output'] = route;
      if (id === 'split' || id === 'join') {
        const own = {};
        for (const key of parameters[model] || []) {
          const value = peek(dsp, id, key);
          if (typeof value === 'number' || typeof value === 'boolean') own[key] = value;
        }
        block.values = own;
      }
      if (namEngines.includes(model) || FOCUS_IR_MODEL.test(model)) {
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

// The selected block: the preset's own cursor (global "@cursor_dsp" / "@cursor_group", which HX Edit writes with every
// click on its chain, on either of its tabs, and when the Floor selects), else the edit panel's (toneView.cursorBlock).
// {dsp, block} or what the panel gave. Pure: tests run it.
// The block an add made, once a full reading shows it at its place. follow: {dsp, lane, place, model}: the model
// that was added (a capture: NAM's engine, found as any NAM engine; an IR: that IR block). Before, only a NAM engine
// was looked for, so an IR block that HX Edit was slow to show never got the IR dragged onto the chain (review of
// PR #7).
function focusAddMade(blocks, follow, namEngines) {
  const wanted = block => namEngines.includes(follow.model) ? namEngines.includes(block.model) : block.model === follow.model;
  return (blocks || []).find(block => block.dsp === follow.dsp && /^block\d{1,2}$/.test(block.id) && block.position === follow.place &&
                                      block.path === follow.lane && wanted(block)) || null;
}

function focusCursor(panel, dsp, group) {
  if ([0, 1].includes(dsp) && typeof group === 'string' && /^(block\d{1,2}|split|join|input[AB]|output[AB])$/.test(group)) {
    return {...(panel || {}), dsp, block: group};
  }
  return panel;
}

// Between full readings, only what a knob, a switch or a footswitch changes: each block's bypass (and a NAM
// block's capture slot) and the selected block's values. null when the blocks themselves are no longer the same
// (the selected block's model changed, or the cursor is on a block not seen yet): read everything again.
function focusValues(peek, blocks, cursor, parameters, namEngines) {
  const next = blocks.map(block => {
    const copy = {...block, enabled: peek(block.dsp, block.id, '@enabled') !== false};
    if (namEngines.includes(block.model) || FOCUS_IR_MODEL.test(block.model)) {
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

// Requests from the pane wait here until HX Edit's UI thread takes them. Of a drag's many changes to one
// value only the newest waits; a begin or an end is never dropped. Pure: tests run it.
function focusQueue(queue, command, limit = 32) {
  const same = item => item.dsp === command.dsp && item.id === command.id && item.key === command.key;
  if (command.phase === 'move') {
    const last = queue[queue.length - 1];
    if (last && last.phase === 'move' && same(last)) { queue[queue.length - 1] = command; return queue; }
  }
  if (queue.length >= limit) {
    const drop = queue.findIndex(item => item.phase === 'move');
    if (drop < 0) return queue;                                          // full of begins and ends: the new one is refused
    queue.splice(drop, 1);
  }
  queue.push(command);
  return queue;
}

// Whether a DSP has room for model `next` in place of model `now`, by the Floor's own figures (dsp_meter.js: what
// its blocks use of what they may). null when it fits or cannot be known; else the words for the user.
function focusRoom(view, loads, now, next, dsp) {
  if (!view || typeof view.used !== 'number' || typeof view.budget !== 'number') return null;
  const cost = Number(loads[next]);
  if (!Number.isFinite(cost)) return null;
  const after = Math.round((view.used - (Number(loads[now]) || 0) + cost) * 10) / 10;
  return after <= view.budget ? null : `DSP ${dsp + 1} has no room for that model (${after} of ${view.budget}).`;
}

// What moves a block's controls and how its snapshots differ (the Workbench's Bypass and controllers / Snapshot
// values tabs), from the preset's tree as HX Edit's own controller view reads it (target_binding peekTree):
//   controller "dsp0.block1.Gain.@controller" / "@min" / "@max" / "@cc" / "@snapshot_disable";
//   footswitch "dsp0.block1.@fs_index" / "@fs_customlabel" / "@fs_customcolor" / "@fs_momentary" / "@fs_enabled";
//   snapshot0..7 "blocks.dsp0.block1" (on or off) and "controllers.dsp0.block1.Gain.@value".
// Only what is there is kept. tree(group, key) -> a value or undefined. Pure: tests run it.
function focusAssign(tree, block, keys) {
  const at = `dsp${block.dsp}.${block.id}`, kept = value => value !== undefined && value !== null;
  const controls = {};
  for (const key of keys) {
    const found = {};
    for (const [name, field] of [['controller', '@controller'], ['min', '@min'], ['max', '@max'], ['cc', '@cc'], ['snapshotOff', '@snapshot_disable']]) {
      const value = tree('controller', `${at}.${key}.${field}`);
      if (kept(value)) found[name] = value;
    }
    if (Object.keys(found).length) controls[key] = found;
  }
  const footswitch = {};
  for (const [name, field] of [['index', '@fs_index'], ['label', '@fs_customlabel'], ['color', '@fs_customcolor'], ['ledColor', '@fs_ledcolor'],
                               ['momentary', '@fs_momentary'], ['enabled', '@fs_enabled'], ['cc', '@cc']]) {
    const value = tree('footswitch', `${at}.${field}`);
    if (kept(value)) footswitch[name] = value;
  }
  const snapshots = [];
  for (let s = 0; s < 8; s++) {
    const values = {};
    for (const key of keys) { const value = tree('snapshot' + s, `controllers.${at}.${key}.@value`); if (kept(value)) values[key] = value; }
    const on = tree('snapshot' + s, `blocks.${at}`);
    snapshots.push({...(kept(on) ? {on} : {}), values});
  }
  return {dsp: block.dsp, id: block.id, controls, footswitch, snapshots};
}

// The models' costs measured on the Floor's own meter (the Workbench's dsp_costs.py), each in place of HX Edit's
// estimate: {symbol: used units}, only plausible figures kept.
function focusMeasured(found) {
  const kept = {};
  if (!found || typeof found !== 'object') return kept;
  for (const [symbol, cost] of Object.entries(found).slice(0, 1000)) {
    if (/^[A-Za-z0-9_]{3,64}$/.test(symbol) && typeof cost === 'number' && Number.isFinite(cost) && cost > 0 && cost <= 75) kept[symbol] = cost;
  }
  return kept;
}

// The pane's place: the main window from its top (over HX Edit's own toolbar: the pane has its own, with the
// preset, the snapshot, undo and the DSP meters) down to the edit panel's bottom, across the whole window; HX
// Edit's status bar stays. sf/ed/main: {x, y, w, h} of the signal flow view ('sfvc'), the editor view ('edvw')
// and the window's root view ('main'), in client coordinates.
function focusFirstBlock(blocks) {
  // The block shown when a preset comes up with nothing selected: the first block of the chain in signal order
  // (path 1 before path 2; at the same place the upper lane first). Never an input, an output, the split or the
  // join. null for a preset with no blocks.
  const chain = (blocks || []).filter(block => /^block\d+$/.test(block.id) && Number.isInteger(block.position));
  chain.sort((a, b) => a.dsp - b.dsp || a.position - b.position || a.path - b.path);
  return chain.length ? {dsp: chain[0].dsp, id: chain[0].id} : null;
}
function focusCaptures(found, previous, inventory) {
  // The captures on the Floor for the pane's names and pictures. A change to the chain makes HX Edit announce a
  // new signal flow, which sends the whole slot list back to be checked (2-4 s): checked, it is empty meanwhile.
  // While that check runs (inventory.state 'refreshing'), a capture seen before stays on a slot the list still
  // shows (inventory.entries: [slot, contentId], kept through the check; a slot changed or deleted leaves it).
  const now = Array.isArray(found) ? found : [];
  if (!inventory || inventory.state !== 'refreshing' || !Array.isArray(previous) || !Array.isArray(inventory.entries)) return now;
  const have = new Set(now.map(c => c.slot)), shown = new Set(inventory.entries.map(entry => entry[0]));
  const kept = previous.filter(c => !have.has(c.slot) && shown.has(c.slot));
  return kept.length ? now.concat(kept).sort((a, b) => a.slot - b.slot) : now;
}
function focusPresetNames(names, preset) {
  // The setlist's preset names for the bar's list, only when HX Edit's list is the loaded preset's own setlist:
  // its row for the loaded preset must carry that preset's name (the sidebar can show another setlist, and a
  // name changed but not saved differs too). Otherwise null: the bar keeps its arrows and offers no list.
  if (!Array.isArray(names) || names.length !== 128 || !names.every(name => typeof name === 'string')) return null;
  if (!preset || !Number.isInteger(preset.number) || preset.number < 0 || preset.number > 127) return null;
  const clean = names.map(name => name.trim().slice(0, 32));
  return clean[preset.number] === String(preset.name || '').trim() ? clean : null;
}
// The Workbench's look at another setlist (Batch 3, setlists.js): once HX Edit's list has been asked for that
// setlist's names, its rows change when the Floor answers. The reading is taken once the rows have stood still for
// FOCUS_LOOK_SETTLE_MS and differ from what the list showed before (or at once when the list showed that setlist
// already: same). Rows that never change are not taken as the other setlist's (the ask may not have worked): failed
// after FOCUS_LOOK_SAME_MS, and "Try again" then reads them as they stand (the list shows that setlist by then); nothing
// usable after FOCUS_LOOK_GIVE_UP_MS: failed. Never another setlist's names under this one's.
// A slow first answer is not a failure (live check 2026-11-24 10:13: the first look after a launch took ~2.7 s, the
// later ones 0.6-0.9 s): FOCUS_LOOK_SAME_MS is 6 s, and a look called failed that way keeps being watched (watch) until
// FOCUS_LOOK_LATE_MS: rows that then change from what the list showed before, and settle, turn it into ok by itself.
// look: {setlist, at, before, last, lastAt, same, state: 'reading'}; names: the list's rows now (namView.presetNames).
const FOCUS_LOOK_SETTLE_MS = 500, FOCUS_LOOK_SAME_MS = 6000, FOCUS_LOOK_GIVE_UP_MS = 8000, FOCUS_LOOK_LATE_MS = 30000;
function focusLookStep(look, names, now) {
  if (!look || !(look.state === 'reading' || (look.state === 'failed' && look.watch))) return look;
  const usable = Array.isArray(names) && names.length >= 1 && names.length <= 128 && names.every(name => typeof name === 'string');
  const word = usable ? JSON.stringify(names) : null;
  const next = usable && word !== look.last ? {...look, last: word, lastAt: now} : look;
  if (usable && word === look.last && now - look.lastAt >= FOCUS_LOOK_SETTLE_MS && (look.same || word !== look.before)) {
    return {setlist: look.setlist, at: look.at, state: 'ok', names: names.map(name => name.trim().slice(0, 32))};
  }
  if (look.state === 'failed') return now - look.at > FOCUS_LOOK_LATE_MS ? {...next, watch: false} : next;   // (still watched)
  if (!usable && now - look.at > FOCUS_LOOK_GIVE_UP_MS) return {...next, state: 'failed', watch: true};
  if (usable && now - look.at >= FOCUS_LOOK_SAME_MS) return {...next, state: 'failed', unchanged: word === look.before, watch: true};
  return next;
}
function focusPaneBounds(sf, ed, main) {
  if (![sf, ed, main].every(box => box && [box.x, box.y, box.w, box.h].every(Number.isFinite))) return null;
  const top = Math.max(0, main.y), bottom = Math.min(main.y + main.h, ed.y + ed.h);
  if (bottom - top < 300 || main.w < 600) return null;                 // a window too small for the pane
  return {x: main.x, y: top, w: main.w, h: bottom - top};
}

// Research only (options.chainProbe, a copy with res/chain-probe.flag): the edit buffer's chain entries HX Edit itself
// calls go to the trace with their arguments and outcome, so a change made on HX Edit's own screen (its menu's
// "Restore Split", say) can be done the same way here. Reads only; changes nothing; a few hundred lines at most.
function focusChainProbe(base) {
  let budget = 900;
  // A Variant as the edit buffer passes them (target_binding decode): type at +0, the value at +8; a string is a
  // String object there (its representation at +4: length at +4, characters at +16). Else a bare String object.
  const chars = object => {
    const rep = object.add(4).readPointer(); if (rep.isNull()) return null;
    const length = rep.add(4).readU32(); if (length < 1 || length > 128) return null;
    const s = rep.add(16).readPointer().readUtf8String(length); return /^[\x20-\x7e]{1,128}$/.test(s) ? s : null;
  };
  const text = p => {
    try {
      const type = p.readU32();
      if (type === 10) return chars(p.add(8).readPointer());
      if (type === 4) return p.add(8).readS32();
      if (type === 5) return p.add(8).readU32();
      if (type === 8) return Math.round(p.add(8).readFloat() * 1e4) / 1e4;
      if (type === 11) return p.add(8).readU8() !== 0;
      return chars(p);
    } catch (_) { return null; }
  };
  const cell = p => { try { return {type: p.readU32(), value: p.add(8).readU32()}; } catch (_) { return null; } };
  const entries = {
    remove: [0x514bc0, a => ({dsp: a[0].toInt32(), item: text(a[1]), flags: a[2].toUInt32()})],
    add: [0x4ff300, a => ({dsp: a[0].toInt32(), item: text(a[1]), at: cell(a[2]), flags: a[3].toUInt32()})],
    move: [0x5123c0, a => ({dsp: a[0].toInt32(), item: text(a[1]), at: cell(a[2]), flags: a[3].toUInt32()})],
    paste: [0x513620, a => ({store: a[0].toInt32(), dsp: a[1].toInt32(), at: cell(a[2]), flags: a[3].toUInt32()})],
    write: [0x5178c0, a => ({dsp: a[0].toInt32(), group: text(a[1]), key: text(a[2]), value: text(a[3]) ?? cell(a[3]), flags: a[4].toUInt32()})],
  };
  for (const [name, [rva, read]] of Object.entries(entries)) {
    Interceptor.attach(base.add(rva), {
      onEnter(args) {
        this.seen = null;
        if (budget <= 0) return;
        try {
          const seen = read(args);
          // (a value write is kept only for the routing — the path's shape, its ends, positions, the cursor — and for
          // what the Bypass and controllers / Snapshot values tabs show: the controller, footswitch and snapshot sections)
          // (any write to the preset's own tree, dsp -1, is kept too)
          if (name === 'write' && seen.dsp !== -1 && !(typeof seen.key === 'string' && /^@(topology|input|output|position|path|cursor)/.test(seen.key)) &&
              !(typeof seen.group === 'string' && /^(controller|footswitch|snapshot[0-7])$/.test(seen.group)) &&
              !(typeof seen.key === 'string' && /@(controller|min|max|cc|snapshot_disable|fs_)/.test(seen.key))) return;
          this.seen = seen;
        } catch (_) { /* unreadable: not reported */ }
      },
      onLeave(result) {
        if (!this.seen || budget-- <= 0) return;
        send({type: 'toneTrace', reason: 'chain-probe', call: name, ...this.seen, result: result.toInt32()});
      },
    });
  }
  // The edit buffer's other entries a controller assignment may go through (not readers: +0x84/+0x88 run all the
  // time): each call with its first arguments as numbers and text, 25 per entry at most.
  const table = base.add(0x963dfc), plain = [0x8c, 0x90, 0x94, 0x98, 0x9c, 0xcc, 0xd0, 0xdc, 0xe0, 0xe4, 0xe8, 0xec, 0xf0, 0xf4, 0xf8, 0xfc,
    0x100, 0x104, 0x108, 0x10c, 0x110, 0x114, 0x118, 0x11c, 0x120, 0x124, 0x128, 0x12c, 0x130, 0x134, 0x138];
  const hooked = new Set(Object.values(entries).map(([rva]) => rva));
  for (const slot of plain) {
    const target = table.add(slot).readPointer(), rva = target.sub(base).toInt32();
    if (hooked.has(rva) || rva < 0x400000 || rva > 0x600000) continue;
    hooked.add(rva);
    let left = 60;
    try { Interceptor.attach(target, {
      onEnter(args) {
        if (left <= 0 || budget <= 0) { this.skip = true; return; }
        this.skip = false;
        const seen = [];
        for (let i = 0; i < 5; i++) { try { const t = text(args[i]); seen.push(t !== null ? t : args[i].toInt32()); } catch (_) { seen.push(null); } }
        this.seen = seen;
      },
      onLeave(result) {
        if (this.skip || left-- <= 0 || budget-- <= 0) return;
        send({type: 'toneTrace', reason: 'chain-probe', call: '+0x' + slot.toString(16), rva: '0x' + rva.toString(16), args: this.seen, result: result.toInt32()});
      },
    }); } catch (error) { send({type: 'toneTrace', reason: 'chain-probe', stage: 'not-hooked', slot: '+0x' + slot.toString(16), error: String(error.message)}); }
  }
  send({type: 'toneTrace', reason: 'chain-probe', stage: 'on'});
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
  const setlists = parts.setlists || null;      // setlists.js (the Workbench's setlists), when it installed
  if (options.chainProbe === true) {
    try { focusChainProbe(base); } catch (error) { send({type: 'toneTrace', reason: 'chain-probe', stage: 'failed', error: String(error.message)}); }
  }
  const parameters = options.focusParameters || {}, namEngines = options.focusNamEngines || ['HD2_AmpNAMLite'];
  const widgetOrigin = new NativeFunction(base.add(0x3b7e00), 'pointer', ['pointer', 'pointer'], 'thiscall');
  const point = Memory.alloc(8);
  const SFVC = 0x73667663, EDVW = 0x65647677, MAIN = 0x6d61696e;
  // Values are read four times a second; the blocks themselves when HX Edit says something other than a value
  // changed, and every two seconds in any case.
  const POLL_MS = 250, FULL_MS = 2000;
  let on = false, timer = null, queued = false, queuedAt = 0, editor = NULL, lastState = '', lastBounds = '', reports = 6, writeReports = 12;
  let known = null, knownAt = 0, changed = true, wanted = null, onFloor = [], assign = null, assignTraced = '';
  let header = {preset: null, snapshots: [], presets: null, tempo: null, topology: [null, null], setlists: null};   // the top bar's preset, snapshot names and preset list (full readings)
  // The Workbench's look at another setlist (focusLookStep), and a preset of another setlist asked of HX Edit's list.
  let looking = null, loadingIn = null;
  const LOAD_IN_MS = 5000;
  // The Workbench's Floor slots (Batch 3): what User IR 128 holds (its name, each full reading), and a Clear asked of
  // HX Edit until the slots read empty (CLEAR_MS at most).
  let slot128 = '', clearing = null;
  // A preset's stored copy renamed right after HX Edit's Save (setlists.js renamePreset), followed until HX Edit shows
  // the name (the loaded preset's header, or its row in HX Edit's list) or RENAME_PRESET_MS has passed: the outcome stays
  // in the state ("presetRename") for the page until the next one.
  let renaming = null;
  const RENAME_PRESET_MS = 8000;
  const CLEAR_MS = 8000;
  const CLEAR_REFUSED = {
    used: slots => `Slot ${slots.join(', ')} ${slots.length === 1 ? 'is' : 'are'} used by the loaded preset, so nothing was cleared. Load a preset that does not use ${slots.length === 1 ? 'it' : 'them'}, then clear again.`,
    unknown: () => 'The loaded preset could not be read just now, so nothing was cleared. Try again in a moment.',
    'not-ready': () => 'HX Edit\'s IR list is not ready, so nothing was cleared.',
    bad: () => 'Nothing was cleared.'};
  let namesWord = '';                                        // the last outcome of reading the preset list, for the trace
  let setlistsWord = '';                                     // the same for the setlists (setlists.js explain)
  // A preset that comes up with nothing selected gets its first block selected, a few tries per preset load and
  // never again once something has been selected in it (a cursor moved to an empty cell on purpose stays there).
  let pickKey = null, pickTries = 0;
  const PICK_TRIES = 3;
  function presetHeader() {
    // The loaded preset's number and name (nam_view reads HX Edit's own header) and its snapshots' names.
    let preset = null;
    try { const read = namView.presetHeader?.(); if (read) preset = {setlist: read.setlist, number: read.preset, name: read.name}; } catch (_) { preset = null; }
    const snapshots = [];
    const tempo = targetBinding.peekGlobal(editor, 'global', '@tempo');
    // Each path's routing as HX Edit keeps it: "A" one lane, "SABJ" split and mixer, "SAB" two outputs, "ABJ" two
    // inputs, "AB" two separate lanes (the Workbench draws the chain from it).
    const topology = [0, 1].map(dsp => { const word = targetBinding.peekGlobal(editor, 'global', '@topology' + dsp); return typeof word === 'string' ? word : null; });
    for (let index = 0; index < 8; index++) {
      const name = targetBinding.peekGlobal(editor, 'snapshot' + index, '@name');
      if (typeof name !== 'string') break;
      snapshots.push(name);
    }
    // The setlist's names, from HX Edit's own preset list (nam_view), when that list is this preset's setlist.
    let names = null;
    try { names = namView.presetNames?.() ?? 'no-reader'; } catch (error) { names = 'failed: ' + String(error.message).slice(0, 80); }
    const presets = focusPresetNames(names, preset);
    const word = presets ? 'ok' : Array.isArray(names) ? 'differs-' + names.length : String(names);
    if (word !== namesWord) {
      namesWord = word;
      send({type: 'toneTrace', reason: 'focus-view', stage: 'preset-names', result: word,
            ...(Array.isArray(names) && !presets && preset ? {row: String(names[preset.number]).slice(0, 40), name: preset.name} : {})});
    }
    // The Floor's setlists (setlists.js: the names HX Edit's own chooser holds) and the one its list shows.
    // A chooser still empty while HX Edit's Presets list has its rows (the Floor connected after HX Edit started, say)
    // is filled as HX Edit fills it (setlists.js askNames). How far the reading gets goes to the trace when it changes.
    let lists = null;
    try {
      const found = setlists && setlists.names();
      if (found) lists = {names: found, shown: setlists.shown()};
      else if (setlists && Array.isArray(names)) setlists.askNames();
    } catch (_) { lists = null; }
    if (setlists) {
      let word;
      try { word = setlists.explain(); } catch (error) { word = 'explain-failed: ' + String(error.message).slice(0, 60); }
      if (word !== setlistsWord) { setlistsWord = word; send({type: 'toneTrace', reason: 'focus-view', stage: 'setlists', result: word}); }
    }
    // (a preset's name can be renamed only when HX Edit's Librarian model is there and its guards held: setlists.js)
    let renameReady = false;
    try { renameReady = !!(setlists && setlists.canRename()); } catch (_) { renameReady = false; }
    return {preset, snapshots, presets, tempo: typeof tempo === 'number' && Number.isFinite(tempo) ? tempo : null, topology, setlists: lists, renameReady};
  }
  // Value writes from the pane, and the drag HX Edit has been told has begun (ended by us if the pane never does).
  const writes = [];
  let drag = null;
  const DRAG_IDLE_MS = 4000;
  // HX Edit's own sliders are shown what the pane has set (target_binding "refresh"), unless turned off.
  const notify = options.focusWriteNotify !== false;
  const estimates = options.focusLoads || {};
  let measured = {};          // {type: 'focusCommand', action: 'costs'}: what the Workbench has measured so far
  const costsNow = () => Object.assign({}, estimates, measured);
  const chainBlock = /^block\d{1,2}$/, modelSymbol = /^[A-Za-z0-9_]{3,64}$/;
  function swap(command) {
    // Another model, or a capture, for a block of the chain: refused with a word by the DSP meter when the DSP
    // has no room (HX Edit itself would answer with an error box).
    const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
    if (!block || !chainBlock.test(block.id) || editor.isNull()) { send({type: 'toneTrace', reason: 'focus-view', stage: 'swap-skipped'}); return; }
    endDrag('a model change');
    const isNam = namEngines.includes(block.model);
    const next = command.action === 'capture' ? (isNam ? block.model : namEngines[0]) : command.symbol;
    if (next !== block.model) {
      const full = focusRoom(typeof dspLoadsNow === 'undefined' ? null : dspLoadsNow[block.dsp], costsNow(), block.model, next, block.dsp);
      if (full) { send({type: 'dspNotice', text: full}); send({type: 'toneTrace', reason: 'focus-view', stage: 'swap-no-room'}); return; }
      targetBinding.setModel(editor, block.dsp, block.id, next);
    }
    // A NAM block's capture at once: left on slot 1 (a plain IR) it would silence the Floor (tone_view drop-replace).
    if (command.action === 'capture') {
      targetBinding.setIndex(editor, block.dsp, block.id, command.slot);
      finish(editor, block.dsp, block.id, 'Index', command.slot);
    }
    changed = true;
    send({type: 'toneTrace', reason: 'focus-view', stage: 'swap', action: command.action, to: next});
  }
  // The Workbench changes the chain itself: a block added on an empty place, removed, or moved to an empty place of
  // its own path (HX Edit's own entries: target_binding addModel, removeBlock, moveBlock; one undo step each). A capture
  // added is a NAM block whose slot is set as soon as HX Edit has put the block in the chain (until then the place
  // reads empty): left on slot 1, a plain IR, it would silence the Floor.
  let addFollow = null;
  let plainIrs = [];          // the Floor's plain IRs, read with each full reading (readIrs)
  let lastUndoWord = '';      // HX Edit's undo position and the preset, as last traced (the Workbench's redo button)
  const ADD_FOLLOW_MS = 3000;
  const occupied = (dsp, lane, place) => (known || []).some(block => block.dsp === dsp && chainBlock.test(block.id) && block.position === place && block.path === lane);
  function change(command) {
    if (editor.isNull()) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
    endDrag('a chain change');
    if (command.action === 'add') {
      if (occupied(command.dsp, command.lane, command.place)) { send({type: 'dspNotice', text: 'That place is no longer empty.'}); return; }
      // (a slot alone: a capture, on NAM's engine; a slot with an IR model: an IR block with that IR)
      const next = command.slot && !command.symbol ? namEngines[0] : command.symbol;
      const full = focusRoom(typeof dspLoadsNow === 'undefined' ? null : dspLoadsNow[command.dsp], costsNow(), null, next, command.dsp);
      if (full) { send({type: 'dspNotice', text: full}); send({type: 'toneTrace', reason: 'focus-view', stage: 'add-no-room'}); return; }
      if (command.slot) {
        // a capture: the block and its slot as one undo step (target_binding addCapture); its slot set later, as a
        // step of its own, only when the new block could not be found at once
        const made = targetBinding.addCapture(editor, command.dsp, command.lane, command.place, next, command.slot);   // (or an IR)
        if (made) {
          finish(editor, command.dsp, made, 'Index', command.slot);
          send({type: 'toneTrace', reason: 'focus-view', stage: 'add-capture-one-step', slot: command.slot});
        } else addFollow = {dsp: command.dsp, lane: command.lane, place: command.place, slot: command.slot, model: next, until: Date.now() + ADD_FOLLOW_MS};
      } else targetBinding.addModel(editor, command.dsp, command.lane, command.place, next);
    } else if (command.action === 'moveSplit') {
      // The split or the mixer to another gap of lane A (target_binding moveSplit: HX Edit's own move, one undo step).
      const node = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
      if (!node || node.position === command.place) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      targetBinding.moveSplit(editor, command.dsp, command.id, command.place);
    } else if (command.action === 'assign') {
      // The Bypass and controllers tab: a block's footswitch or a control's controller, as HX Edit's own tab writes
      // them (target_binding writeTree; focus_view.checked_assign has checked the field and the value).
      const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
      if (!block) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      const at = `dsp${block.dsp}.${block.id}`, fields = {
        fsIndex: ['footswitch', `${at}.@fs_index`, 'enum'], fsColor: ['footswitch', `${at}.@fs_customcolor`, 'enum'],
        fsLabel: ['footswitch', `${at}.@fs_customlabel`, 'text'], fsMomentary: ['footswitch', `${at}.@fs_momentary`, 'bool'],
        fsCc: ['footswitch', `${at}.@cc`, 'enum'], cc: ['controller', `${at}.${command.key}.@cc`, 'enum'],
        controller: ['controller', `${at}.${command.key}.@controller`, 'enum'], min: ['controller', `${at}.${command.key}.@min`, 'float'],
        max: ['controller', `${at}.${command.key}.@max`, 'float']};
      const [group, key, kind] = fields[command.field];
      targetBinding.writeTree(editor, group, key, command.value, kind);
    } else if (command.action === 'ir') {
      // The IRs drawer: another IR on an IR block (its Index, as HX Edit's IR picker writes it: one undo step)
      const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
      if (!block || !FOCUS_IR_MODEL.test(block.model) || block.slot === command.slot) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      targetBinding.setIndex(editor, block.dsp, block.id, command.slot);
      finish(editor, block.dsp, block.id, 'Index', command.slot);
    } else if (command.action === 'rename') {
      // The Workbench's name box in a snapshot's button: the snapshot's name in the edit buffer (target_binding
      // renameSnapshot: one undo step; Save keeps it, as any other change). A preset's name is not renamed here.
      targetBinding.renameSnapshot(editor, command.index, command.name);
    } else if (command.action === 'redo' || command.action === 'undo') {
      // HX Edit's own Undo / Redo (target_binding undo, redo: the Edit menu's entries), as the page's buttons ask
      if (command.action === 'undo') targetBinding.undo(editor); else targetBinding.redo(editor);
    } else if (command.action === 'splitType') {
      // The split's type (Split Y, A/B, Crossover, Dynamic): its model, written as HX Edit's panel writes a model.
      const node = (known || []).find(item => item.dsp === command.dsp && item.id === 'split');
      if (!node || node.model === command.symbol) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      targetBinding.setModel(editor, command.dsp, 'split', command.symbol);
    } else if (command.action === 'snapValue') {
      // The Snapshot values grid: a value (or the block's on/off) in another snapshot, the way HX Edit changes one:
      // that snapshot is recalled, the value written as a knob writes it, and the snapshot that was on comes back
      // (HX Edit has no write of its own into a snapshot that is not on; seen with the chain probe 2026-11-22).
      const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
      const now = targetBinding.peekGlobal(editor, 'global', '@current_snapshot');
      if (!block || !Number.isInteger(now)) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      const away = command.snapshot !== now;
      if (away) targetBinding.recallSnapshot(editor, command.snapshot);
      try {
        targetBinding.setValue(editor, block.dsp, block.id, command.key, command.value, 'single');
        finish(editor, block.dsp, block.id, command.key, command.value);
      } finally {
        if (away) targetBinding.recallSnapshot(editor, now);
      }
    } else if (command.action === 'route') {
      // Lane B's own input or output in place of the split or the mixer (HX Edit's Create Input: removeNode), or the
      // split or the mixer back (its Restore Split: restoreNode).
      if (command.back) targetBinding.restoreNode(editor, command.dsp, command.id);
      else targetBinding.removeNode(editor, command.dsp, command.id);
    } else {
      const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
      if (!block || !chainBlock.test(block.id)) { send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-skipped', action: command.action}); return; }
      if (command.action === 'remove') targetBinding.removeBlock(editor, block.dsp, block.id);
      else {
        // (to: the other path, when the block goes there)
        const to = command.to === undefined ? block.dsp : command.to;
        if (occupied(to, command.lane, command.place)) { send({type: 'dspNotice', text: 'That place is no longer empty.'}); return; }
        if (to === block.dsp) targetBinding.moveBlock(editor, block.dsp, block.id, command.lane, command.place);
        else {
          const full = focusRoom(typeof dspLoadsNow === 'undefined' ? null : dspLoadsNow[to], costsNow(), null, block.model, to);
          if (full) { send({type: 'dspNotice', text: full}); send({type: 'toneTrace', reason: 'focus-view', stage: 'move-no-room'}); return; }
          const meter = typeof dspLoadsNow === 'undefined' ? null : dspLoadsNow[to];
          const moved = targetBinding.moveAcross(editor, block.dsp, block.id, to, command.lane, command.place);
          // Pasted on lane A for lane B: moved down once the Floor's meter shows the block on that path (followDown)
          if (moved && moved.down) downFollow = {...moved, model: block.model, used: meter ? meter.used : null, at: Date.now()};
        }
      }
    }
    changed = true;
    send({type: 'toneTrace', reason: 'focus-view', stage: 'chain-' + command.action, dsp: command.dsp, to: command.to, lane: command.lane, place: command.place});
  }
  // A block moved to the other path's lane B was pasted on its lane A (target_binding moveAcross): it goes down once
  // the Floor has it, seen as that path's meter moving (a move sent before that never reached the Floor), or after
  // DOWN_LATEST_MS without a meter. Dropped when the block is no longer where it was pasted.
  let downFollow = null;
  const DOWN_SETTLE_MS = 400, DOWN_LATEST_MS = 4000;
  function followDown(blocks) {
    if (!downFollow) return;
    const follow = downFollow, now = Date.now();
    const meter = typeof dspLoadsNow === 'undefined' ? null : dspLoadsNow[follow.dsp];
    const arrived = meter && follow.used !== null && meter.used !== follow.used;
    if (now - follow.at < DOWN_SETTLE_MS || (!arrived && now - follow.at < DOWN_LATEST_MS)) return;
    downFollow = null;
    const made = blocks.find(block => block.dsp === follow.dsp && block.id === follow.down);
    if (!made || made.model !== follow.model || made.path !== 0 || made.position !== follow.from ||
        occupied(follow.dsp, follow.lane, follow.place)) { send({type: 'toneTrace', reason: 'focus-view', stage: 'move-down-dropped'}); return; }
    targetBinding.moveBlock(editor, follow.dsp, follow.down, follow.lane, follow.place);
    changed = true;
    send({type: 'toneTrace', reason: 'focus-view', stage: 'move-down', dsp: follow.dsp, place: follow.place, waited: now - follow.at, meter: !!arrived});
  }
  function followAdd(blocks) {
    // The capture's slot on the block just added, once a full reading shows it at its place.
    if (!addFollow) return;
    if (Date.now() > addFollow.until) { send({type: 'toneTrace', reason: 'focus-view', stage: 'add-follow-lost'}); addFollow = null; return; }
    const made = focusAddMade(blocks, addFollow, namEngines);
    if (!made) return;
    const follow = addFollow; addFollow = null;
    targetBinding.setIndex(editor, made.dsp, made.id, follow.slot);
    finish(editor, made.dsp, made.id, 'Index', follow.slot);
    changed = true;
    send({type: 'toneTrace', reason: 'focus-view', stage: 'add-capture-set', slot: follow.slot});
  }
  function finish(target, dsp, id, key, value) {
    // After a single change or a drag's end: the same value once more, for HX Edit's own views only.
    if (!notify) return;
    try { targetBinding.setValue(target, dsp, id, key, value, 'refresh'); }
    catch (error) { send({type: 'toneTrace', reason: 'focus-view', stage: 'refresh-failed', error: String(error.message)}); }
  }

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
  function captures(previous) {
    // The captures on the Floor, by slot: a NAM block's name and picture come from its slot (focusCaptures: kept
    // while HX Edit re-checks the slots after a chain change).
    try {
      const found = namView.installedCaptures().map(capture => ({slot: capture.slot, name: capture.name, icon: capture.icon, gear: capture.gear}));
      return focusCaptures(found, previous, namView.inventorySnapshot ? namView.inventorySnapshot() : null);
    }
    catch (_) { return previous || []; }
  }
  function readIrs(previous) {
    // The Floor's plain IRs (nam_view plainIrs: HX Edit's IR list without the captures' slots), for the Workbench's
    // IRs drawer; the last list while it cannot be read.
    try { const found = namView.plainIrs?.(); return Array.isArray(found) ? found : previous; }
    catch (_) { return previous; }
  }
  function endDrag(why) {
    if (!drag) return;
    const open = drag; drag = null;
    try { targetBinding.setValue(open.editor, open.dsp, open.id, open.key, open.value, 'end'); finish(open.editor, open.dsp, open.id, open.key, open.value); }
    catch (error) { send({type: 'toneTrace', reason: 'focus-view', stage: 'drag-end-failed', why, error: String(error.message)}); }
  }
  function write(command) {
    // One value of one block the pane shows, never anything else. A drag left open is closed first.
    const block = (known || []).find(item => item.dsp === command.dsp && item.id === command.id);
    const allowed = block && (command.key === '@enabled' || (parameters[block.model] || []).includes(command.key));
    if (!allowed || editor.isNull()) { send({type: 'toneTrace', reason: 'focus-view', stage: 'write-skipped', key: String(command.key).slice(0, 32)}); return; }
    const same = drag && drag.dsp === command.dsp && drag.id === command.id && drag.key === command.key;
    if (drag && !same) endDrag('another value');
    let phase = command.phase;
    if (phase === 'move' && !drag) phase = 'begin';                     // a change with no begin: begin with it
    if (phase === 'end' && !drag) phase = 'single';
    if (phase === 'begin' && same) phase = 'move';
    targetBinding.setValue(editor, command.dsp, command.id, command.key, command.value, phase);
    if (phase === 'begin' || phase === 'move') drag = {editor, dsp: command.dsp, id: command.id, key: command.key, value: command.value, at: Date.now()};
    else { drag = null; finish(editor, command.dsp, command.id, command.key, command.value); }
    if (writeReports > 0) { writeReports--; send({type: 'toneTrace', reason: 'focus-view', stage: 'write', key: command.key, phase}); }
  }
  function refresh(window) {
    queued = false;
    if (!on) return;
    while (writes.length) {
      const command = writes.shift();
      try {
        if (command.action === 'snapshot') {
          // Another snapshot: every value may differ after it.
          endDrag('a snapshot change');
          if (!editor.isNull()) targetBinding.recallSnapshot(editor, command.index);
          changed = true;
          send({type: 'toneTrace', reason: 'focus-view', stage: 'snapshot', index: command.index});
        } else if (command.action === 'look') {
          // The Workbench looks at another setlist: HX Edit's list is asked for its names (setlists.js look: nothing
          // is loaded). The list's rows are then followed until they have that setlist's names (focusLookStep).
          const before = namView.presetNames?.();
          const asked = setlists.look(command.setlist);
          looking = {setlist: command.setlist, at: Date.now(), before: JSON.stringify(before), last: '', lastAt: 0, same: !asked, state: 'reading'};
          changed = true;
          send({type: 'toneTrace', reason: 'focus-view', stage: 'look', setlist: command.setlist, asked});
        } else if (command.action === 'presetIn') {
          // A preset of the setlist HX Edit's list shows, loaded as a double-click in that list loads it (setlists.js
          // load); a drag left open is closed first. Said so when HX Edit has not loaded it within LOAD_IN_MS.
          endDrag('a preset change');
          setlists.load(command.setlist, command.number);
          loadingIn = {setlist: command.setlist, number: command.number, until: Date.now() + LOAD_IN_MS};
          changed = true;
          send({type: 'toneTrace', reason: 'focus-view', stage: 'preset-in', setlist: command.setlist, number: command.number});
        } else if (command.action === 'presetRename') {
          // The Workbench's pending name, asked right after HX Edit's own Save of that preset (the page's Save): the copy
          // stored on the Floor is renamed as HX Edit's list renames it (operation 3), then read back.
          renaming = {setlist: command.setlist, number: command.number, name: command.name, until: Date.now() + RENAME_PRESET_MS, state: 'asked'};
          setlists.renamePreset(command.setlist, command.number, command.name);
          changed = true;
          send({type: 'toneTrace', reason: 'focus-view', stage: 'preset-rename', setlist: command.setlist, number: command.number});
        } else if (command.action === 'clear') {
          // The Workbench's Floor slots: Clear, after the player said so there (nam_view clearSlotsChecked: HX Edit's
          // own Clear, never a slot the loaded preset uses). Followed until the slots read empty.
          const result = namView.clearSlotsChecked(command.slots);
          send({type: 'toneTrace', reason: 'focus-view', stage: 'clear', slots: command.slots, result});
          if (result.refused) send({type: 'dspNotice', text: (CLEAR_REFUSED[result.refused] || CLEAR_REFUSED.bad)(result.slots || [])});
          else clearing = {slots: result.cleared, until: Date.now() + CLEAR_MS};
          changed = true;
        } else if (command.action === 'preset') {
          // Another preset: a drag left open is closed on this preset first, then the launcher asks the Floor
          // for it (a Program Change, as a footswitch; HX Edit follows on its own).
          endDrag('a preset change');
          changed = true;
          send({type: 'focusPreset', number: command.number});
          send({type: 'toneTrace', reason: 'focus-view', stage: 'preset', number: command.number});
        } else if (['add', 'remove', 'move', 'moveSplit', 'route', 'assign', 'snapValue', 'splitType', 'redo', 'ir', 'undo', 'rename'].includes(command.action)) change(command);
        else if (command.action) swap(command); else write(command);
      }
      catch (error) {
        drag = null; changed = true;
        send({type: 'toneTrace', reason: 'focus-view', stage: command.action ? 'swap-failed' : 'write-failed', key: String(command.key || command.action).slice(0, 32), error: String(error.message)});
        if (['add', 'remove', 'move', 'moveSplit', 'route', 'assign', 'snapValue', 'splitType', 'redo', 'ir', 'undo', 'rename'].includes(command.action)) send({type: 'dspNotice', text: 'HX Edit did not make that change.'});
        // (a look that could not be asked: the page says that setlist could not be read; a load: said at once)
        if (command.action === 'look') looking = {setlist: command.setlist, at: Date.now(), state: 'failed'};
        if (command.action === 'presetIn') { loadingIn = null; send({type: 'dspNotice', text: 'HX Edit did not load that preset: ' + String(error.message)}); }
        if (command.action === 'presetRename' && renaming) renaming = {...renaming, state: 'failed', error: String(error.message).slice(0, 80)};
      }
    }
    if (drag && Date.now() - drag.at > DRAG_IDLE_MS) endDrag('idle');
    try {
      const bounds = paneBounds();
      const place = JSON.stringify(bounds);
      if (place !== lastBounds) { lastBounds = place; send({type: 'focusBounds', window: window.toUInt32(), bounds}); }
      const panelCursor = toneView.cursorBlock();
      if (panelCursor && !panelCursor.editor.isNull()) editor = panelCursor.editor;
      if (editor.isNull()) { publish({blocks: [], selected: null, values: {}, captures: [], preset: null, presets: null, snapshots: [], snapshot: null, undo: null}); return; }
      // (the selection as the preset itself keeps it, which follows every click on HX Edit's chain; the edit panel's
      // own, which the Workbench read before, stands still while HX Edit's Bypass/Controller Assign tab is open)
      const cursor = focusCursor(panelCursor, targetBinding.peekGlobal(editor, 'global', '@cursor_dsp'), targetBinding.peekGlobal(editor, 'global', '@cursor_group'));
      const began = Date.now(), peek = (dsp, place, key) => targetBinding.peekValue(editor, dsp, place, key);
      let state = !changed && known && began - knownAt < FULL_MS ? focusValues(peek, known, cursor, parameters, namEngines) : null;
      const full = !state;
      if (full) { state = focusSnapshot(peek, cursor, parameters, namEngines); knownAt = began; changed = false; }
      known = state.blocks;
      if (full && addFollow) { try { followAdd(known); } catch (error) { addFollow = null; send({type: 'toneTrace', reason: 'focus-view', stage: 'add-follow-failed', error: String(error.message)}); } }
      if (downFollow) {
        try { followDown(known); }
        catch (error) { downFollow = null; send({type: 'toneTrace', reason: 'focus-view', stage: 'move-down-failed', error: String(error.message)}); send({type: 'dspNotice', text: 'HX Edit did not move the block down to the parallel lane.'}); }
      }
      // The captures on the Floor, for the pane's list (looked up with each full reading), NAM block or not.
      if (full) {
        onFloor = captures(onFloor); header = presetHeader(); plainIrs = readIrs(plainIrs);
        try { slot128 = namView.slotName?.(128) || ''; } catch (_) { slot128 = ''; }
      }
      state.captures = onFloor;
      state.irs = plainIrs;
      state.preset = header.preset; state.presets = header.presets; state.snapshots = header.snapshots; state.tempo = header.tempo; state.topology = header.topology;
      state.setlists = header.setlists;
      state.slot128 = slot128 ? {name: slot128} : null;
      state.presetRenameReady = header.renameReady === true;
      if (renaming && renaming.state === 'asked') {
        // read back: the loaded preset's own name (when it is still that preset), or its row in HX Edit's list
        const here = header.preset && header.preset.setlist === renaming.setlist && header.preset.number === renaming.number;
        let row = null;
        try { if (setlists.shown() === renaming.setlist) { const rows = namView.presetNames?.(); if (Array.isArray(rows)) row = String(rows[renaming.number] ?? '').trim(); } } catch (_) { row = null; }
        if ((here && header.preset.name === renaming.name) || row === renaming.name) renaming = {...renaming, state: 'ok'};
        else if (Date.now() > renaming.until) renaming = {...renaming, state: 'failed', error: 'not seen'};
        if (renaming.state !== 'asked') send({type: 'toneTrace', reason: 'focus-view', stage: 'preset-rename-' + renaming.state, header: here ? header.preset.name : null, row});
      }
      state.presetRename = renaming ? {setlist: renaming.setlist, number: renaming.number, name: renaming.name, state: renaming.state} : null;
      if (clearing) {
        let left = clearing.slots;
        try { left = clearing.slots.filter(slot => !namView.slotEmpty(slot)); } catch (_) { left = clearing.slots; }
        if (!left.length) { send({type: 'toneTrace', reason: 'focus-view', stage: 'cleared', slots: clearing.slots}); clearing = null; changed = true; }
        else if (Date.now() > clearing.until) {
          send({type: 'dspNotice', text: `HX Edit did not clear slot ${left.join(', ')}.`});
          send({type: 'toneTrace', reason: 'focus-view', stage: 'clear-unseen', slots: left});
          clearing = null;
        }
      }
      state.clearing = clearing ? clearing.slots : null;
      if (looking && (looking.state === 'reading' || (looking.state === 'failed' && looking.watch))) {
        // (a look called failed is still watched for a while: late rows turn it into ok by themselves)
        let names = null;
        try { names = namView.presetNames?.(); } catch (_) { names = null; }
        const was = looking.state;
        looking = focusLookStep(looking, names, Date.now());
        if (looking.state !== was) send({type: 'toneTrace', reason: 'focus-view', stage: 'look-' + looking.state + (was === 'failed' ? '-late' : ''), setlist: looking.setlist, ms: Date.now() - looking.at});
      }
      state.looking = looking ? {setlist: looking.setlist, state: looking.state, ...(looking.names ? {names: looking.names} : {})} : null;
      if (loadingIn && header.preset && header.preset.setlist === loadingIn.setlist && header.preset.number === loadingIn.number) loadingIn = null;
      else if (loadingIn && Date.now() > loadingIn.until) {
        send({type: 'dspNotice', text: `HX Edit did not load preset ${String(loadingIn.number).padStart(3, '0')} of that setlist.`});
        send({type: 'toneTrace', reason: 'focus-view', stage: 'preset-in-unseen', setlist: loadingIn.setlist, number: loadingIn.number});
        loadingIn = null;
      }
      const snapshot = targetBinding.peekGlobal(editor, 'global', '@current_snapshot');
      state.snapshot = Number.isInteger(snapshot) ? snapshot : null;
      // Something to undo: HX Edit's own undo position (as tone_view reads it).
      // (undoAt: that position itself, for the Workbench's redo button)
      try { state.undoAt = editor.add(0x294).readS32(); state.undo = state.undoAt > 0; } catch (_) { state.undo = null; state.undoAt = null; }
      // Something to redo, as HX Edit's Edit menu asks it (target_binding canRedo); null when it cannot be read
      try { state.redo = targetBinding.canRedo(editor); } catch (_) { state.redo = null; }
      const undoWord = state.undoAt + '@' + (state.preset ? state.preset.setlist + ':' + state.preset.number : '-');
      if (undoWord !== lastUndoWord) { lastUndoWord = undoWord; send({type: 'toneTrace', reason: 'focus-view', stage: 'undo-at', at: undoWord}); }
      // The selected block's controllers, footswitch and snapshot values (focusAssign), read with each full reading
      // and kept between them; the first reading of each block goes to the trace (what HX Edit answered).
      const chosen = state.selected && state.blocks.find(b => b.dsp === state.selected.dsp && b.id === state.selected.id);
      if (chosen && full) {
        const began2 = Date.now();
        assign = focusAssign((group, key) => targetBinding.peekTree(editor, group, key), chosen, parameters[chosen.model] || []);
        const name = chosen.dsp + ':' + chosen.id + ':' + chosen.model;
        if (name !== assignTraced) {
          assignTraced = name;
          send({type: 'toneTrace', reason: 'focus-view', stage: 'assign-read', ms: Date.now() - began2, block: chosen.id, controls: assign.controls,
                footswitch: assign.footswitch, snapshots: assign.snapshots.map(s => ({on: s.on, n: Object.keys(s.values).length}))});
        }
      }
      if (!chosen) assign = null;
      state.assign = assign && chosen && assign.dsp === chosen.dsp && assign.id === chosen.id ? assign : null;
      if (reports > 0) { reports--; send({type: 'toneTrace', reason: 'focus-view', stage: full ? 'read' : 'read-values', ms: Date.now() - began, blocks: state.blocks.length, selected: !!state.selected}); }
      if (full) {
        const key = state.preset ? state.preset.setlist + ':' + state.preset.number : '';
        if (key !== pickKey) { pickKey = key; pickTries = 0; }
        if (state.selected) pickTries = PICK_TRIES;
        else if (key && !wanted && pickTries < PICK_TRIES) {
          const first = focusFirstBlock(state.blocks);
          if (first) { pickTries++; wanted = first; send({type: 'toneTrace', reason: 'focus-view', stage: 'first-block', dsp: first.dsp, block: first.id, attempt: pickTries}); }
        }
      }
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
    if (block && (block.id === 'split' || block.id === 'join')) {
      // (the split or the mixer: selected as HX Edit's own drop selects one, target_binding selectNode)
      targetBinding.selectNode(editor, block.dsp, block.id);
      changed = true;
      send({type: 'toneTrace', reason: 'focus-view', stage: 'select', dsp: target.dsp, block: target.id});
      return;
    }
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
    if (on && value !== true && drag) {
      // Turned off in the middle of a drag: HX Edit is told the drag has ended, on its own thread.
      const open = drag; drag = null; writes.length = 0;
      namView.queueSidebarAction(() => {
        try { targetBinding.setValue(open.editor, open.dsp, open.id, open.key, open.value, 'end'); finish(open.editor, open.dsp, open.id, open.key, open.value); } catch (_) { /* the block is gone */ }
      });
    }
    on = value === true;
    if (timer) { clearInterval(timer); timer = null; }
    lastState = ''; lastBounds = ''; queued = false; known = null; changed = true; wanted = null; onFloor = []; addFollow = null; downFollow = null;
    pickKey = null; pickTries = 0;
    header = {preset: null, snapshots: [], presets: null, tempo: null, topology: [null, null], setlists: null};
    looking = null; loadingIn = null; slot128 = ''; clearing = null; renaming = null;
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
      try {
        const name = eventName(args[0]);
        if (name !== 'EditBuffer_ParamChanged') changed = true;
        if (name === 'EditBuffer_DevicePresetChanged' || name === 'EditBuffer_TargetDeviceChanged') pickKey = null;   // a preset loaded, the same one too
      } catch (_) { changed = true; }
    },
    onLeave() { if (on) ask(); },
  });
  // Two panes read through this script: Focus Mode and the Workbench (workbench.html). It reads while either is
  // shown; a pane coming or going while the other stays shown keeps the reading going and sends it again.
  const wants = {focus: false, workbench: false};
  function want(pane, value) {
    wants[pane] = value === true;
    const next = wants.focus || wants.workbench;
    if (next && on) { lastState = ''; lastBounds = ''; queued = false; ask(); return; }
    set(next);
  }
  function listen() {
    recv('focusMode', message => {
      const value = message.payload || {};
      if (value.resend) { lastState = ''; lastBounds = ''; ask(); }
      else want(value.pane === 'workbench' ? 'workbench' : 'focus', value.on === true);
      listen();
    });
  }
  function commands() {
    recv('focusCommand', message => {
      const value = message.payload || {};
      if (value.action === 'costs') measured = focusMeasured(value.costs);
      else if (on && value.action === 'select' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && value.id.length < 16) {
        wanted = {dsp: value.dsp, id: value.id};
        queued = false; ask();
      } else if (on && value.action === 'set' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && value.id.length < 16 &&
                 typeof value.key === 'string' && value.key.length < 49 && ['single', 'begin', 'move', 'end'].includes(value.phase) &&
                 (typeof value.value === 'boolean' || Number.isFinite(value.value))) {
        focusQueue(writes, {dsp: value.dsp, id: value.id, key: value.key, value: value.value, phase: value.phase});
        queued = false; ask();
      } else if (on && value.action === 'snapshot' && Number.isInteger(value.index) && value.index >= 0 && value.index <= 7 && writes.length < 32) {
        writes.push({action: 'snapshot', index: value.index});
        queued = false; ask();
      } else if (on && setlists && value.action === 'look' && Number.isInteger(value.setlist) && value.setlist >= 0 && value.setlist <= 7 && writes.length < 32) {
        writes.push({action: 'look', setlist: value.setlist});
        queued = false; ask();
      } else if (on && setlists && value.action === 'presetIn' && Number.isInteger(value.setlist) && value.setlist >= 0 && value.setlist <= 7 &&
                 Number.isInteger(value.number) && value.number >= 0 && value.number <= 127 && writes.length < 32) {
        writes.push({action: 'presetIn', setlist: value.setlist, number: value.number});
        queued = false; ask();
      } else if (on && setlists && value.action === 'presetRename' && Number.isInteger(value.setlist) && value.setlist >= 0 && value.setlist <= 7 &&
                 Number.isInteger(value.number) && value.number >= 0 && value.number <= 127 && typeof value.name === 'string' &&
                 /^[\x20-\x7e]{1,16}$/.test(value.name) && writes.length < 32) {
        writes.push({action: 'presetRename', setlist: value.setlist, number: value.number, name: value.name});
        queued = false; ask();
      } else if (on && value.action === 'clear' && Array.isArray(value.slots) && value.slots.length >= 1 && value.slots.length <= 128 &&
                 value.slots.every(slot => Number.isInteger(slot) && slot >= 1 && slot <= 128) && new Set(value.slots).size === value.slots.length &&
                 !clearing && writes.length < 32) {
        writes.push({action: 'clear', slots: value.slots});
        queued = false; ask();
      } else if (on && value.action === 'preset' && Number.isInteger(value.number) && value.number >= 0 && value.number <= 127 && writes.length < 32) {
        writes.push({action: 'preset', number: value.number});
        queued = false; ask();
      } else if (on && [0, 1].includes(value.dsp) && typeof value.id === 'string' && chainBlock.test(value.id) && writes.length < 32 &&
                 ((value.action === 'model' && typeof value.symbol === 'string' && modelSymbol.test(value.symbol) && !namEngines.includes(value.symbol)) ||
                  (value.action === 'capture' && Number.isInteger(value.slot) && value.slot >= 1 && value.slot <= 127))) {
        writes.push({action: value.action, dsp: value.dsp, id: value.id, symbol: value.symbol, slot: value.slot});
        queued = false; ask();
      } else if (on && [0, 1].includes(value.dsp) && writes.length < 32 && (
                 (value.action === 'add' && [0, 1].includes(value.lane) && Number.isInteger(value.place) && value.place >= 0 && value.place <= 7 &&
                  ((typeof value.symbol === 'string' && modelSymbol.test(value.symbol) && !namEngines.includes(value.symbol) && value.slot === undefined) ||
                   ((value.symbol === undefined || (typeof value.symbol === 'string' && FOCUS_IR_MODEL.test(value.symbol))) && Number.isInteger(value.slot) && value.slot >= 1 && value.slot <= 127))) ||
                 (value.action === 'remove' && typeof value.id === 'string' && chainBlock.test(value.id)) ||
                 (value.action === 'move' && typeof value.id === 'string' && chainBlock.test(value.id) && [0, 1].includes(value.lane) &&
                  Number.isInteger(value.place) && value.place >= 0 && value.place <= 7 && (value.to === undefined || [0, 1].includes(value.to))))) {
        writes.push({action: value.action, dsp: value.dsp, id: value.id, lane: value.lane, place: value.place, symbol: value.symbol, slot: value.slot,
                     to: value.action === 'move' ? value.to : undefined});
        queued = false; ask();
      } else if (on && value.action === 'moveSplit' && [0, 1].includes(value.dsp) && ['split', 'join'].includes(value.id) &&
                 Number.isInteger(value.place) && value.place >= 0 && value.place <= 8 && writes.length < 32) {
        writes.push({action: 'moveSplit', dsp: value.dsp, id: value.id, place: value.place});
        queued = false; ask();
      } else if (on && value.action === 'assign' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && /^(block\d{1,2}|split|join|input[AB]|output[AB])$/.test(value.id) &&
                 ['fsIndex', 'fsColor', 'fsLabel', 'fsMomentary', 'fsCc', 'controller', 'cc', 'min', 'max'].includes(value.field) && writes.length < 32 &&
                 (value.key === undefined || (typeof value.key === 'string' && /^[A-Za-z0-9_ ]{1,48}$/.test(value.key))) &&
                 (typeof value.value === 'boolean' || Number.isFinite(value.value) || (typeof value.value === 'string' && /^[\x20-\x7e]{0,16}$/.test(value.value)))) {
        writes.push({action: 'assign', dsp: value.dsp, id: value.id, field: value.field, key: value.key, value: value.value});
        queued = false; ask();
      } else if (on && value.action === 'ir' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && chainBlock.test(value.id) &&
                 Number.isInteger(value.slot) && value.slot >= 1 && value.slot <= 127 && writes.length < 32) {
        writes.push({action: 'ir', dsp: value.dsp, id: value.id, slot: value.slot});
        queued = false; ask();
      } else if (on && value.action === 'rename' && value.what === 'snapshot' && Number.isInteger(value.index) && value.index >= 0 && value.index <= 7 &&
                 typeof value.name === 'string' && /^[\x20-\x7e]{1,10}$/.test(value.name) && writes.length < 32) {
        writes.push({action: 'rename', index: value.index, name: value.name});
        queued = false; ask();
      } else if (on && ['undo', 'redo'].includes(value.action) && writes.length < 32) {
        writes.push({action: value.action});
        queued = false; ask();
      } else if (on && value.action === 'splitType' && [0, 1].includes(value.dsp) && typeof value.symbol === 'string' &&
                 /^HD2_AppDSPFlowSplit(Y|AB|XOver|Dyn)$/.test(value.symbol) && writes.length < 32) {
        writes.push({action: 'splitType', dsp: value.dsp, symbol: value.symbol});
        queued = false; ask();
      } else if (on && value.action === 'snapValue' && [0, 1].includes(value.dsp) && typeof value.id === 'string' && chainBlock.test(value.id) &&
                 Number.isInteger(value.snapshot) && value.snapshot >= 0 && value.snapshot <= 7 && typeof value.key === 'string' && value.key.length < 49 &&
                 (typeof value.value === 'boolean' || Number.isFinite(value.value)) && writes.length < 32) {
        writes.push({action: 'snapValue', dsp: value.dsp, id: value.id, snapshot: value.snapshot, key: value.key, value: value.value});
        queued = false; ask();
      } else if (on && value.action === 'route' && [0, 1].includes(value.dsp) && ['split', 'join'].includes(value.id) && writes.length < 32) {
        writes.push({action: 'route', dsp: value.dsp, id: value.id, back: value.back === true});
        queued = false; ask();
      }
      commands();
    });
  }
  listen(); commands();
  return { set, dispose() { set(false); hook.detach(); } };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { focusViewGuards, focusSnapshot, focusValues, focusChainPoint, focusFirstBlock, focusPaneBounds, focusPresetNames, focusLookStep, focusQueue, focusRoom, focusMeasured, focusAssign, focusCursor, focusCaptures, focusAddMade, installFocusView };
}
