'use strict';

// The Workbench's chain (workbench.html): each DSP drawn as a path of eight fixed places, lane B under lane A between
// the split and the mixer, from what focus_view.js reads (focusSnapshot's blocks). Pure: tests run it with node.
//
// How a preset keeps its routing (HX Edit's .hlx, the same names in the edit buffer):
//   a block: @position 0..7 (its place) and @path (0 lane A, 1 lane B);
//   split / join: @position, the gap the split or the mixer sits in (the split before place k, the mixer before
//     place k, 8 = after the last place); lane B runs over the places between them;
//   inputB: @input, where lane B takes its signal when the split was dragged down;
//   outputB: @output, where lane B goes when the mixer was dragged down;
//   global @topology0 / @topology1: the path's shape in one word: "A" one lane, "SABJ" a split and a mixer, "SAB" no
//     mixer (two outputs), "ABJ" no split (two inputs), "AB" two separate lanes. When it is there it decides; else
//     (an older reading) the shape is worked out from the blocks: a stock new preset keeps outputB at 1 with no lane B
//     at all, so outputB counts only on a path with a lane B and the mixer at the end.
//   outputA of path 1: 2, 3 or 4 sends it into path 2 (Path 2A, 2B or 2A+B).
const WORKBENCH_PLACES = 8;
const WORKBENCH_INTO_PATH_2 = Object.freeze({2: ['A'], 3: ['B'], 4: ['A', 'B']});

function workbenchName(list, code) {
  // A short name from HX Edit's own list ("Multi (Guitar, Aux, Variax)" -> "Multi").
  if (!Number.isInteger(code)) return '';
  const name = Array.isArray(list) && typeof list[code] === 'string' ? list[code] : code === 0 ? 'None' : 'Input ' + code;
  return name.replace(/\s*\(.*\)\s*$/, '').trim();
}

function workbenchShape(word) {
  // {laneB, split, join} from HX Edit's topology word, or null for a word it does not know.
  if (typeof word !== 'string' || !/^S?AB?J?$/.test(word) || (word.includes('J') && !word.includes('B')) || (word.startsWith('S') && !word.includes('B'))) return null;
  const laneB = word.includes('B');
  return {laneB, split: laneB && word.startsWith('S'), join: laneB && word.endsWith('J')};
}

function workbenchPaths(blocks, names = {}, topology = []) {
  const all = Array.isArray(blocks) ? blocks : [];
  const inputs = names.inputs || [], outputs = names.outputs || [];
  const find = (dsp, id) => all.find(block => block.dsp === dsp && block.id === id) || null;
  const first = find(0, 'outputA'), fed = first && WORKBENCH_INTO_PATH_2[first.output] || [];
  const paths = [];
  for (const dsp of [0, 1]) {
    // (a block named "pending": one the page shows where a change it asked for will put it, workbenchPending)
    const chain = all.filter(block => block.dsp === dsp && /^(block\d{1,2}|pending)$/.test(block.id) && Number.isInteger(block.position)
                                     && block.position >= 0 && block.position < WORKBENCH_PLACES);
    const a = Array(WORKBENCH_PLACES).fill(null), b = Array(WORKBENCH_PLACES).fill(null);
    for (const block of chain) (block.path === 1 ? b : a)[block.position] = block;
    const inputA = find(dsp, 'inputA'), inputB = find(dsp, 'inputB'), outputA = find(dsp, 'outputA'), outputB = find(dsp, 'outputB');
    const split = find(dsp, 'split'), join = find(dsp, 'join');
    const fromPath1 = dsp === 1 ? fed : [];
    const shape = workbenchShape((topology || [])[dsp]);
    const gap = (block, fallback) => block && Number.isInteger(block.position) ? Math.min(WORKBENCH_PLACES, Math.max(0, block.position)) : fallback;
    let laneB, ownInput, ownOutput, splitAt, joinAt;
    if (shape) {
      // HX Edit's own word for the shape (a block on lane B shows it in any case).
      // (a word with no lane B over a block on lane B, never seen: drawn as a split and a mixer)
      laneB = shape.laneB || b.some(Boolean);
      ownInput = shape.laneB && !shape.split;
      ownOutput = shape.laneB && !shape.join;
    } else {
      // Lane B is there with a block on it, or with an input of its own (the split dragged down, or path 1 sent into it).
      ownInput = !!inputB && (inputB.input > 0 || fromPath1.includes('B'));
      laneB = b.some(Boolean) || ownInput;
      ownOutput = laneB && !!outputB && outputB.output > 0 && gap(join, WORKBENCH_PLACES) >= WORKBENCH_PLACES;
    }
    splitAt = ownInput ? 0 : gap(split, 0);
    joinAt = ownOutput ? WORKBENCH_PLACES : gap(join, WORKBENCH_PLACES);
    // A block on lane B outside the split and the mixer (never seen; a preset may still say so): the lane takes it in.
    b.forEach((block, place) => { if (block) { splitAt = Math.min(splitAt, place); joinAt = Math.max(joinAt, place + 1); } });
    if (joinAt < splitAt) joinAt = splitAt;
    const inputName = block => {
      if (!block) return '';
      if (dsp === 1 && fromPath1.includes(block.id === 'inputB' ? 'B' : 'A')) return 'Path 1';
      return workbenchName(inputs, block.input);
    };
    paths.push({
      dsp,
      input: inputA ? {block: inputA, name: inputName(inputA)} : null,
      output: outputA ? {block: outputA, name: workbenchName(outputs, outputA.output)} : null,
      a,
      b: laneB ? b : null,
      // the places lane B runs over, and its own ends when it has them (else the split / the mixer node)
      from: laneB ? splitAt : null, to: laneB ? joinAt : null,
      split: laneB && !ownInput ? split : null,
      join: laneB && !ownOutput ? join : null,
      inputB: laneB && ownInput && inputB ? {block: inputB, name: inputName(inputB)} : null,
      outputB: laneB && ownOutput && outputB ? {block: outputB, name: workbenchName(outputs, outputB.output)} : null,
      empty: !chain.length,
    });
  }
  return paths;
}

function workbenchSplitNote(split, format) {
  // The words under the split: "evenly to lanes A and B", or its setting as HX Edit shows it.
  if (!split) return '';
  const values = split.values || {};
  if (split.model === 'HD2_AppDSPFlowSplitY') {
    const even = [values.BalanceA, values.BalanceB].every(value => typeof value !== 'number' || Math.abs(value - .5) < .005);
    return even ? 'evenly to lanes A and B' : 'A ' + format('BalanceA', values.BalanceA) + ', B ' + format('BalanceB', values.BalanceB);
  }
  if (split.model === 'HD2_AppDSPFlowSplitAB') return typeof values.RouteTo === 'number' ? format('RouteTo', values.RouteTo) : '';
  if (split.model === 'HD2_AppDSPFlowSplitXOver') return typeof values.Frequency === 'number' ? 'at ' + format('Frequency', values.Frequency) : '';
  if (split.model === 'HD2_AppDSPFlowSplitDyn') return typeof values.Threshold === 'number' ? 'over ' + format('Threshold', values.Threshold) : '';
  return '';
}

function workbenchNodeGaps(path, which) {
  // The gaps of lane A the split or the mixer of a drawn path (workbenchPaths) may go to, its own included: lane B's
  // blocks stay between the two (the split no later than the first, the mixer no earlier than after the last) and the
  // split stays before the mixer. [] when the path has no such node to move. (focus_view.checked_split checks again.)
  if (!path || !path.b || !(which === 'split' ? path.split : path.join)) return [];
  const used = path.b.map((block, place) => block ? place : null).filter(place => place !== null);
  const gaps = [];
  for (let k = 0; k <= WORKBENCH_PLACES; k++) {
    const ok = which === 'split' ? (!used.length || k <= Math.min(...used)) && k < path.to
                                 : (!used.length || k >= Math.max(...used) + 1) && k > path.from;
    if (ok) gaps.push(k);
  }
  return gaps;
}

function workbenchMixNote(join) {
  // The words under the mixer: each lane's level ("A 0.0 dB, B -3.0 dB").
  if (!join || !join.values) return '';
  const level = value => typeof value === 'number' ? (Math.round(value * 10) / 10).toFixed(1).replace('-', '−') + ' dB' : '?';
  return 'A ' + level(join.values['A Level']) + ', B ' + level(join.values['B Level']);
}

// The room a split's or a mixer's note has beside its node, inside the chain's own box (live check 2026-11-24: a
// split at a path's first place put its note out over Classic+'s sidebar). The split's note ends left of the split:
// it has the row from the grid's start to there, plus the path label's column (empty at lane B's line); the mixer's
// starts right of the mixer and has the rest of the row. Under 40 px the note is left out (the node's title has it).
const WORKBENCH_NOTE_GAP = 20, WORKBENCH_NOTE_LEAST = 40;
function workbenchNoteRoom(side, x, width, tag) {
  const room = Math.floor(side === 'split' ? x - WORKBENCH_NOTE_GAP + (tag || 0) : width - x - WORKBENCH_NOTE_GAP);
  return room >= WORKBENCH_NOTE_LEAST ? room : 0;
}

function workbenchPending(blocks, pending, namEngine) {
  // The chain as the page shows it while a change it asked for is on its way: HX Edit passes through other states
  // first (a moved block is briefly in neither place; an added capture first reads as a NAM block on IR slot 1), so the
  // change asked for is shown from the click until a reading has it. {blocks, settled}: settled when the reading
  // already shows the change (the page then forgets it; it also gives up after a few seconds: a change refused).
  const all = Array.isArray(blocks) ? blocks : [];
  if (!pending) return {blocks: all, settled: true};
  const chain = block => /^block\d{1,2}$/.test(block.id);
  const at = block => block.dsp === pending.dsp && chain(block) && block.position === pending.place && block.path === pending.lane;
  if (pending.action === 'move') {
    // (pending.block: the block as it was when it was dragged, for a reading that has it in neither place)
    // (pending.to: the other path's DSP, when the block goes there: HX Edit pastes a copy there, with a block name of
    // that path, and then removes the block from its own; settled once the copy is there and the block is gone)
    const to = Number.isInteger(pending.to) ? pending.to : pending.dsp, across = to !== pending.dsp;
    const there = b => b.dsp === to && chain(b) && b.position === pending.place && b.path === pending.lane;
    const block = all.find(b => b.dsp === pending.dsp && b.id === pending.id), was = block || pending.block;
    if (!was) return {blocks: all, settled: true};
    const arrived = all.some(b => b !== block && there(b) && b.model === was.model);
    if (across ? arrived && !(block && block.model === was.model) : arrived || (block && block.position === pending.place && block.path === pending.lane)) {
      return {blocks: all, settled: true};
    }
    const moved = {...was, dsp: to, position: pending.place, path: pending.lane, ...(across ? {id: 'pending'} : {})};
    const rest = all.filter(b => b !== block && !(across && there(b)));
    return {blocks: !across && block ? all.map(b => b === block ? moved : b) : rest.concat([moved]), settled: false};
  }
  if (pending.action === 'remove') {
    if (!all.some(b => b.dsp === pending.dsp && b.id === pending.id)) return {blocks: all, settled: true};
    return {blocks: all.filter(b => !(b.dsp === pending.dsp && b.id === pending.id)), settled: false};
  }
  if (pending.action === 'add') {
    // (a slot alone: a capture, on NAM's engine; a slot with a model: an IR block with that IR, as focus_view.js adds)
    const model = pending.slot && !pending.symbol ? namEngine : pending.symbol;
    const there = all.find(at);
    if (workbenchAdded(all, pending, namEngine)) return {blocks: all, settled: true};
    const shown = {dsp: pending.dsp, id: there ? there.id : 'pending', model, position: pending.place, path: pending.lane, enabled: true,
                   ...(pending.slot ? {slot: pending.slot} : {})};
    return {blocks: there ? all.map(b => b === there ? {...b, ...shown} : b) : all.concat([shown]), settled: false};
  }
  return {blocks: all, settled: true};
}

// ---- after an add, the new block is the picked one (Nick, 2026-11-24) -------------------------------------------
// The block an add asked for, once a reading shows it at its place with the model asked for (a capture: NAM's engine
// with that slot; an IR: the IR block with that IR), else null. The add is asked only on an empty place.
function workbenchAdded(blocks, add, namEngine) {
  if (!add) return null;
  const model = add.slot && !add.symbol ? namEngine : add.symbol;
  return (Array.isArray(blocks) ? blocks : []).find(b => b && b.dsp === add.dsp && /^block\d{1,2}$/.test(b.id) && b.position === add.place &&
    b.path === add.lane && b.model === model && (!add.slot || b.slot === add.slot)) || null;
}
// What the page waits for after it asked for an add: that place, what was asked, the block picked then and the preset.
// HX Edit can be slow to show a new block (a capture's slot or an IR is set once the block is there: 467b644), so it
// waits up to WORKBENCH_ADD_SELECT_MS; past that, or if the add was refused, nothing is picked.
const WORKBENCH_ADD_SELECT_MS = 6000;
const workbenchPresetKey = state => state && state.preset ? state.preset.setlist + ':' + state.preset.number : '';
function workbenchAddFollow(add, state, now) {
  return {dsp: add.dsp, lane: add.lane, place: add.place, symbol: add.symbol, slot: add.slot,
          was: state && state.selected ? {dsp: state.selected.dsp, id: state.selected.id} : null,
          preset: workbenchPresetKey(state), until: now + WORKBENCH_ADD_SELECT_MS};
}
// For each reading while it waits: {select: {dsp, id} | null, done}. The new block is picked once it is there, as a
// click on it picks it (one ask, no undo step of the page's own), unless HX Edit already has it selected. Nothing is
// picked, and the wait ends, when another block was picked meanwhile (by the player, here or on the Floor), another
// preset came up, or the time ran out. (A reading without the preset's header, as during an undo, is the same preset.)
function workbenchAddSelect(follow, state, namEngine, now) {
  if (!follow || !state) return {select: null, done: !follow};
  const sel = state.selected || null, key = workbenchPresetKey(state);
  const made = workbenchAdded(state.blocks, follow, namEngine);
  if (made && sel && sel.dsp === made.dsp && sel.id === made.id) return {select: null, done: true};
  // (a reading with nothing selected, as HX Edit may give while it adds, is not another pick)
  const was = follow.was, moved = !!sel && !(was && sel.dsp === was.dsp && sel.id === was.id);
  if ((key && follow.preset && key !== follow.preset) || moved || now > follow.until) return {select: null, done: true};
  return made ? {select: {dsp: made.dsp, id: made.id}, done: true} : {select: null, done: false};
}

// The steps made on the loaded preset since it came up, from HX Edit's undo position as it moves. That position is not
// a count: it is the index into HX Edit's ring of 33 undo records (editor+0x290 holds 33: 32 steps; a Levels scan ran
// it to 32 and on to 0, sweep 2026-11-24 23:35), and a preset load leaves it where it was (7@3:31, 7@3:32 in the sweep;
// HX Edit's history clear, editor vtable+0x20 -> 0x291b20, empties the records and keeps the index). So the change of
// each reading is taken round the ring (size), and a preset loaded starts at 0 steps. {preset, at, steps}; steps null
// when the position cannot be read. (A reading without the preset's header, as during an undo: the same preset.)
function workbenchOwnSteps(track, at, preset, size) {
  if (!Number.isInteger(at)) return {preset: preset || (track && track.preset) || '', at: null, steps: null};
  if (!preset && track) preset = track.preset;
  if (!track || track.preset !== preset || !Number.isInteger(track.at) || !Number.isInteger(track.steps)) return {preset, at, steps: 0};
  const ring = Number.isInteger(size) && size >= 2 ? size : null;
  let move = at - track.at;
  if (ring) { move = ((move % ring) + ring) % ring; if (move > ring / 2) move -= ring; }
  return {preset, at, steps: Math.max(0, track.steps + move)};
}

// Whether the bar offers Undo and Redo. HX Edit's own Edit-menu answers decide wherever they could be read (undo,
// redo: target_binding canUndo / canRedo; null when not read): HX Edit empties its own history on a preset load (live
// check 2026-11-25 00:55, `undo-can undo:false redo:false` straight after `preset 31`), so they never offer another
// preset's steps, and they keep the steps made on this preset before the Workbench first saw it (in Classic, in Focus
// Mode, before a layout switch or a relaunch of the pane: the review of 1d3675f). Only an answer that could not be
// read falls back on the steps the Workbench itself saw made on this preset (workbenchOwnSteps, workbenchRedo).
function workbenchUndoRedo(undo, redo, own, redoTrack) {
  return {undo: typeof undo === 'boolean' ? undo : !(own && own.steps === 0),
          redo: typeof redo === 'boolean' ? redo : !!(redoTrack && redoTrack.redo)};
}

// A block picked here shows as the picked one at once (Nick, 2026-11-25: "picking a block is not snappy"), drawn from
// what the page knows (its model, the catalog), before HX Edit's reading says it is selected. The page's pick holds
// until that reading comes (the pick is dropped then), and is dropped, showing HX Edit's own selection, when the block
// is gone, the time runs out, or HX Edit shows a block that is neither the one picked nor one it was on since (from:
// HX Edit's selection when the first of quick picks was made, and the picks made after it): the player picked
// elsewhere, on the Floor or in HX Edit. -> {pick (kept, or null), selected (what the page shows)}
const WORKBENCH_PICK_HOLD_MS = 2500;
function workbenchPicked(pick, selected, blocks, now) {
  if (!pick) return {pick: null, selected};
  const is = (a, b) => !!a && !!b && a.dsp === b.dsp && a.id === b.id;
  const there = (Array.isArray(blocks) ? blocks : []).some(b => is(b, pick));
  const before = (pick.from || []).some(f => is(f, selected));
  if (is(selected, pick) || !there || now > pick.until || (selected && !before)) return {pick: null, selected};
  return {pick, selected: {dsp: pick.dsp, id: pick.id}};
}
// The pick made now, over the one still held (quick clicks): what HX Edit may still show meanwhile is kept in from.
function workbenchPick(block, held, hxSelected, now) {
  const from = held ? held.from.concat([{dsp: held.dsp, id: held.id}]) : [hxSelected || null];
  return {dsp: block.dsp, id: block.id, from: from.filter(Boolean).slice(-6), until: now + WORKBENCH_PICK_HOLD_MS};
}

// A model or a capture asked for a block that is asked again before a reading shows the first (a double-click on a row,
// Nick's habit from Classic, where a double-click replaces): the same choice for the same block within
// WORKBENCH_SWAP_REPEAT_MS. Asked twice, HX Edit made it twice: two undo steps, and the first Undo seemed to do nothing.
const WORKBENCH_SWAP_REPEAT_MS = 1500;
// Rig on stage's pinned scene (Reveal B11: one scene for the preset) is frozen once the blocks shown belong to the
// preset: the same preset (key) and the same blocks and selection (sig) for WORKBENCH_SCENE_SETTLE_MS. On a switch the
// page could see the new preset's header while the old preset's blocks and selection still showed, and froze the old
// preset's scene under the new key (live 2026-11-26 00:5x: 032's "Studio Desk" on 031). track: {key, sig, since} or
// null; returns {settled, track}. Pure.
const WORKBENCH_SCENE_SETTLE_MS = 700;
function workbenchSceneSettled(track, key, sig, now) {
  if (!track || track.key !== key || track.sig !== sig) return {settled: false, track: {key, sig, since: now}};
  return {settled: now - track.since >= WORKBENCH_SCENE_SETTLE_MS, track};
}

// The side list across a layout switch (workbenchSwitch), and whether Classic+ opened it by itself (auto): Classic+
// always shows one and opens Presets when none is open; leaving Classic+, a list it opened by itself closes, one the
// player opened stays (live 2026-11-26: Presets stayed open beside Rig on stage after Classic+). Returns {view, auto}.
// Pure.
function workbenchSwitchSide(view, from, to, auto) {
  let v = {drawer: '', half: '', full: '', ...(view || {})};
  if (from === 'classicplus' && to !== 'classicplus' && auto && v.drawer === WORKBENCH_SIDE_FIRST) v = {...v, drawer: ''};
  const had = v.drawer, next = workbenchSwitch(v, to);
  const opened = to !== 'classicplus' ? false : from === 'classicplus' ? !!auto : !had && !!next.drawer;
  return {view: next, auto: opened};
}

// A click on a choice (the picker's card, Classic+'s row, the input/output chooser's tile): the second click on the
// same choice within WORKBENCH_DOUBLE_MS is its double-click. The first click lines the choice up and redraws the list,
// so the browser's own dblclick went to a new element and never fired (PR #9 review, P2). last: {key, at} or null;
// returns {double, last}: a double clears it (a third click starts afresh). Pure.
const WORKBENCH_DOUBLE_MS = 500;
function workbenchSecondClick(last, key, now) {
  if (last && last.key === key && now - last.at >= 0 && now - last.at <= WORKBENCH_DOUBLE_MS) return {double: true, last: null};
  return {double: false, last: {key, at: now}};
}

function workbenchSwapRepeat(asked, block, choice, now) {
  return !!asked && !!block && !!choice && asked.dsp === block.dsp && asked.id === block.id && now - asked.at < WORKBENCH_SWAP_REPEAT_MS &&
    (choice.symbol ? asked.symbol === choice.symbol : asked.slot === choice.slot);
}

function workbenchRedo(track, at, preset, redoing) {
  // Whether there is something to redo, from HX Edit's undo position (at: the steps that can be undone) as it
  // changes: an undo lowers it and leaves a step to redo; a new change raises it and leaves none, unless it is the
  // redo asked for (redoing). A preset loaded starts afresh. {preset, at, top, redo}; redo true when unknown.
  if (!Number.isInteger(at)) return {preset, at: null, top: null, redo: true};
  // (a reading without the preset's header, as while HX Edit reloads the preset's contents for an undo: the same preset)
  if (!preset && track) preset = track.preset;
  if (!track || track.preset !== preset || !Number.isInteger(track.at) || !Number.isInteger(track.top)) return {preset, at, top: at, redo: false};
  const top = Math.max(at > track.at && !redoing ? at : track.top, at);
  return {preset, at, top, redo: at < top};
}

// ---- what is open beside, under or over the chain ------------------------------------------------------------------
// The rule Nick agreed to (2026-11-23, research/modern-ui/play.js): what you use while editing stays beside the chain;
// a job of its own gets the full screen; an expand button switches between a thing's two sizes. The first size is the
// one the rail opens.
//   drawer: beside the chain (left of it); half: the lower half, in place of the block panel; full: the whole work
//   area, the chain shrunk to small tiles in the view's header. A drawer and a lower-half tool are never open together.
const WORKBENCH_SIZES = Object.freeze({
  presets: ['drawer', 'full'], captures: ['drawer'], irs: ['drawer'],
  look: ['half', 'full'], level: ['half', 'full'], library: ['full'], tone: ['full']});

// ---- the layouts (Batch 4): other arrangements of this same page --------------------------------------------------
// Every layout has the same tools, lists, dialogs and asks; a layout only decides where things sit and how the chain
// and the block's controls are drawn (Nick, 2026-11-24). The chosen one is the editor's own setting (settings.json
// "workbenchLayout", workbench.py); Classic (HX Edit's own screen) is not one of these: it switches the page off.
//   workbench: the rail of tools on the left, drawers beside the chain, a tool in the lower half, knobs underneath;
//   classicplus: HX Edit's own arrangement: a sidebar always there (Presets | Captures | IRs, its tools at its foot),
//     the chain across the top, the Edit area with the model list in place of the picker and the controls as sliders;
//   stage: the gear standing on the preset's scene, a glass rail and glass drawers over it, the block's dock below;
//     a tool that has a lower-half size elsewhere opens as its full view there (no lower half under a stage).
// built: offered in the chooser (a layout not built yet says "later" and cannot be picked).
const WORKBENCH_LAYOUTS = Object.freeze({workbench: {built: true}, classicplus: {built: true}, stage: {built: true}});
function workbenchLayoutOf(name) {
  // The layout a setting names, when it is one that is built; anything else is the Workbench.
  return typeof name === 'string' && Object.prototype.hasOwnProperty.call(WORKBENCH_LAYOUTS, name) && WORKBENCH_LAYOUTS[name].built ? name : 'workbench';
}
function workbenchSizes(layout) {
  // The sizes each thing has in a layout, its first the one the rail opens (WORKBENCH_SIZES in the Workbench).
  return layout === 'stage' ? {...WORKBENCH_SIZES, look: ['full'], level: ['full']} : WORKBENCH_SIZES;
}

function workbenchView(view, action, name, layout) {
  // The next {drawer, half, full} after an action: "rail" (a rail button: opens the thing in its first size, or closes
  // it when it is open there), "open" (the same without closing), "expand" (to its full view), "shrink" (back to its
  // other size), "back" (Back to the chain), "close" (that thing, wherever it is), "escape" (the full view, else the
  // lower half), "select" (a block picked in the chain: Levels gives way to the block's panel; Floor look stays and
  // follows it), "goto" (a small tile of a full view's header: everything over the chain closes).
  // layout: the Workbench's rules by default. In Classic+ the side list is the sidebar's tab, always there: its tab
  // never closes by a second click, and it stays beside a tool in the lower half (it is not beside the chain there).
  const v = {drawer: '', half: '', full: '', ...(view || {})};
  const sizes = workbenchSizes(layout)[name] || [], sidebar = layout === 'classicplus';
  const openFull = () => { v.full = name; if (v.half && v.half !== name) v.half = ''; };
  // One thing open at a time beside or under the chain (Nick, 2026-11-23: a side list and a lower-half tool open
  // together read as confusing): a side list closes the tool under the chain, and the other way round.
  const place = (size, thing) => { v[size] = thing; if (thing && !sidebar) v[size === 'drawer' ? 'half' : 'drawer'] = ''; };
  if (action === 'rail' || action === 'open') {
    const size = sizes[0], toggle = action === 'rail' && !(sidebar && size === 'drawer');
    if (size === 'drawer' || size === 'half') {
      if (v.full) { v.full = ''; place(size, name); } else place(size, toggle && v[size] === name ? '' : name);
    } else if (size === 'full') {
      if (toggle && v.full === name) v.full = ''; else openFull();
    }
  } else if (action === 'expand') {
    if (sizes.includes('full')) openFull();
  } else if (action === 'shrink') {
    const was = v.full, size = (workbenchSizes(layout)[was] || [])[0];
    v.full = '';
    if (size === 'drawer' || size === 'half') place(size, was);
  } else if (action === 'back') {
    v.full = '';
  } else if (action === 'close') {
    for (const size of ['drawer', 'half', 'full']) if (v[size] === name && !(sidebar && size === 'drawer')) v[size] = '';
  } else if (action === 'escape') {
    if (v.full) v.full = ''; else v.half = '';
  } else if (action === 'select') {
    if (v.half === 'level') v.half = '';
  } else if (action === 'goto') {
    v.full = ''; v.half = '';
  }
  return v;
}

function workbenchRailOn(view, name, layout) {
  // Whether a rail button is lit: what the full view shows, else what is open beside or under the chain. (Classic+'s
  // sidebar tabs: the tab shown, whatever else is open.)
  if (!view) return false;
  if (layout === 'classicplus' && (WORKBENCH_SIZES[name] || [])[0] === 'drawer') return view.drawer === name;
  return view.full ? view.full === name : view.drawer === name || view.half === name;
}

// What a switch of layout keeps (Batch 4): the preset, the selected block, a rename and the unsaved state are the
// page's own and never move; what is open moves to where the new layout has a place for it:
//   to Classic+: the side list shown (else WORKBENCH_SIDE_FIRST, the Presets tab), the lower half, the full view;
//   to the Workbench: a side list and a tool in the lower half are never open together there: the tool stays;
//   to the stage: a lower-half tool opens as its full view (the stage has no lower half), a side list stays.
const WORKBENCH_SIDE_FIRST = 'presets';
function workbenchSwitch(view, to) {
  const v = {drawer: '', half: '', full: '', ...(view || {})};
  const sizes = workbenchSizes(to);
  for (const size of ['drawer', 'half', 'full']) if (v[size] && !(sizes[v[size]] || []).includes(size)) {
    // (a thing with no such size in the new layout: its full view when it has one, else it closes)
    if (size !== 'full' && (sizes[v[size]] || []).includes('full') && !v.full) v.full = v[size];
    v[size] = '';
  }
  if (to === 'classicplus' && !v.drawer) v.drawer = WORKBENCH_SIDE_FIRST;
  if (to === 'workbench' && v.drawer && v.half) v.drawer = '';
  return v;
}

// Where things are drawn in a layout for a view: {rail: the rail's form ('rail' | 'side' | 'glass'), drawer: the side
// list shown ('' none), half, full, chain: the chain and the block's panel are shown, sidebar: Classic+'s sidebar}.
function workbenchPlaces(layout, view) {
  const v = {drawer: '', half: '', full: '', ...(view || {})}, plus = layout === 'classicplus', stage = layout === 'stage';
  return {
    rail: plus ? 'side' : stage ? 'glass' : 'rail',
    sidebar: plus,
    drawer: v.drawer && (plus || !v.full) ? v.drawer : '',
    half: !v.full && !stage ? v.half : '',
    full: v.full,
    chain: !v.full,
  };
}

// ---- Levels: from a scan to what Apply sets (the library page's own sums, library_card.html renderLevel) ------------
// rows: LevelFlow's measured rows ({preset, setlist, name, snapshot, snapshots, lufs, peak, level, varies, note});
// choice: {metric: 'lufs'|'peak', target: 'middle'|'custom'|'preset:<n>', custom, offsets: {key: {dB}}, skipped: [preset]}.
//   target for a row = target + its offset; change = that - loudness now (0 within the measuring wobble);
//   held (not applied): a note from the scan, more than 12 dB away, or a peak over -1 dBFS after the change.
// tone_preview / nam_level_flow check every change again before anything is applied.
const WORKBENCH_LEVEL_TRIM = 12, WORKBENCH_LEVEL_CEILING = -1;
const workbenchRound1 = v => Math.round(v * 10) / 10 + 0;
const workbenchLevelKey = row => [row.setlist ?? '', row.preset, row.name || '', row.snapshot].join(':');
function workbenchLevelOffset(choice, row) {
  const kept = (choice.offsets || {})[workbenchLevelKey(row)];
  return Number(kept && kept.dB) || 0;
}
function workbenchLevelTarget(rows, choice) {
  // {value, why}: the middle of the scan (each sound without its offset), as loud as a preset's main sound (its
  // group with the most snapshots), or the player's own number
  const metric = choice.metric === 'peak' ? 'peak' : 'lufs', count = row => (row.snapshots || [row.snapshot]).length;
  if (choice.target === 'custom') {
    const typed = Number(choice.custom);
    return choice.custom !== null && choice.custom !== '' && Number.isFinite(typed) ? {value: typed, why: 'your own level'} : {value: null, why: 'type a level'};
  }
  if (typeof choice.target === 'string' && choice.target.startsWith('preset:')) {
    const number = Number(choice.target.slice(7)), mine = rows.filter(row => row.preset === number && Number.isFinite(row[metric]));
    if (mine.length) {
      const main = mine.reduce((a, b) => count(b) > count(a) ? b : a);
      return {value: workbenchRound1(main[metric] - workbenchLevelOffset(choice, main)), why: 'as loud as ' + String(number).padStart(3, '0') + ' ' + (main.name || '')};
    }
  }
  const values = rows.map(row => row[metric] - workbenchLevelOffset(choice, row)).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return {value: null, why: 'the middle of what you scanned'};
  const m = values.length >> 1, median = values.length % 2 ? values[m] : (values[m - 1] + values[m]) / 2;
  return {value: Math.round(median * 2) / 2 + 0, why: 'the middle of what you scanned'};
}
function workbenchLevelPlan(rows, choice) {
  const metric = choice.metric === 'peak' ? 'peak' : 'lufs', target = workbenchLevelTarget(rows, choice).value;
  const skipped = new Set(choice.skipped || []);
  return rows.map(row => {
    const now = row[metric], offset = workbenchLevelOffset(choice, row);
    const after = target == null ? null : workbenchRound1(target + offset);
    let change = after == null || !Number.isFinite(now) ? null : workbenchRound1(after - now);
    if (change != null && Math.abs(change) <= (row.varies ? 1.0 : 0.5)) change = 0;   // (the edge counts as on target)
    let held = row.note || '';
    if (!held) {
      if (!Number.isFinite(change)) held = 'not measured';
      else if (Math.abs(change) > WORKBENCH_LEVEL_TRIM) held = 'more than ' + WORKBENCH_LEVEL_TRIM + ' dB away: check the sound itself';
      else if (Number.isFinite(row.peak) && row.peak + change > WORKBENCH_LEVEL_CEILING) {
        const p = row.peak + change; held = 'would peak at ' + (p > 0 ? '+' : p < 0 ? '−' : '') + Math.abs(p).toFixed(1) + ' dBFS';
      }
    }
    const output = Number.isFinite(row.level) && Number.isFinite(change) ? workbenchRound1(row.level + change) : null;
    return {...row, key: workbenchLevelKey(row), now, offset, after, change, held, output, use: !held && change !== 0 && !skipped.has(row.preset)};
  });
}
function workbenchLevelChanges(plan) {
  // What Apply sends: {preset: {snapshot: dB}} of the rows in use, a group of alike snapshots by its first one
  // (LevelFlow.apply keys its rows so and changes the whole group; another snapshot of it would be refused)
  const changes = {};
  for (const row of plan) if (row.use) (changes[row.preset] = changes[row.preset] || {})[row.snapshot] = row.change;
  return changes;
}

// ---- changes that are not saved ------------------------------------------------------------------------------------
// The loaded preset has changes that were not saved when HX Edit's undo position is no longer where it stood when the
// preset was loaded, or when a Save was last asked for here (mark: {key: "setlist:number", at}; the page keeps it).
// HX Edit keeps its undo position through a preset load and through a Save (seen live 2026-11-23), so the position
// alone says nothing. Without a mark for this preset, or a position that could be read, nothing counts as changed.
function workbenchUnsaved(undoAt, preset, mark) {
  if (!preset || typeof undoAt !== 'number' || !mark || mark.key !== preset || typeof mark.at !== 'number') return false;
  return undoAt !== mark.at;
}

// Right after a load HX Edit can add an undo step by itself (live check 2026-11-24 10:40: the block picker's side
// chosen for the new preset's selected block made a "Change Model" step; BACKLOG "fix-side-change-model"). For
// WORKBENCH_LOAD_SETTLE_MS after the load (mark.settle) such a step moves the mark with it, unless the page asked for a
// change of its own after the load (editAskedAt). A change made on the Floor itself in those 2.5 s is not counted.
const WORKBENCH_LOAD_SETTLE_MS = 2500;
function workbenchSettledMark(mark, key, undoAt, now, editAskedAt) {
  if (!mark || mark.key !== key || !mark.settle || now > mark.settle || typeof undoAt !== 'number' || undoAt === mark.at) return mark;
  if (editAskedAt && editAskedAt >= mark.settle - WORKBENCH_LOAD_SETTLE_MS) return mark;
  return {...mark, at: undoAt};
}

// A preview adds two undo steps of its own: the block to slot 128, and back to its own capture when it ends. When it
// ended so, with nothing else changed meanwhile (tone_view previewEnded: {from, to, at}: the position before it and
// after the step back), the preset is as it was: the mark moves from `from` to `to`. Only while the mark stood at
// `from` (the preset was unchanged when the preview began), only at exactly `to` (one step more is a real change), and
// only for WORKBENCH_PREVIEW_END_MS after it ended. (live check 2026-11-24 11:47: 032 kept the dot after End preview)
const WORKBENCH_PREVIEW_END_MS = 8000;
function workbenchPreviewMark(mark, key, undoAt, ended, now) {
  if (!mark || mark.key !== key || !ended || typeof ended.from !== 'number' || typeof ended.to !== 'number' ||
      typeof ended.at !== 'number' || now > ended.at + WORKBENCH_PREVIEW_END_MS) return mark;
  if (mark.at !== ended.from || undoAt !== ended.to) return mark;
  return {...mark, at: undoAt};
}

// ---- a Save while a preview plays ----------------------------------------------------------------------------------
// HX Edit's Save stores the edit buffer as it is: with a preview on, the NAM block on slot 128, which the preview's
// clean-up then empties (live check 2026-11-24 13:09, "Save, then load" offered during a preview). So the Workbench's
// Save first ends the preview and saves only once it has ended. Which preview plays, as the page sees it: 'library'
// (the library's own session: its End preview), 'tray' (a TONE3000 tone in the tray: its Stop preview), 'session'
// (HX Edit's script says one plays, neither of those shows it: nothing the page can end), or ''.
function workbenchPreviewOn(state, floor, tray) {
  const set = value => value !== null && value !== undefined;
  if (floor && set(floor.trial)) return 'library';
  if (tray && set(tray.trial) && Array.isArray(tray.tray) && tray.tray.some(item => item && item.state === 'ready' && item.trial === tray.trial)) return 'tray';
  if (state && state.previewing === true) return 'session';
  return '';
}
// Waiting for it to end (held: {since, until, offAt}): 'wait', 'save' or 'give-up' (not ended by `until`: no Save).
// Ended: saved once HX Edit's undo record has the step back (tone_view previewEnded.to, so the unsaved mark counts
// from there), or WORKBENCH_PREVIEW_STEP_MS after the preview went off without one (a capture the block moved on to).
const WORKBENCH_PREVIEW_END_WAIT_MS = 10000, WORKBENCH_PREVIEW_STEP_MS = 1500;
function workbenchSaveHold(held, now, on, undoAt, ended) {
  if (on) return {next: now > held.until ? 'give-up' : 'wait', offAt: 0};
  const offAt = held.offAt || now;
  const fresh = !!ended && typeof ended.at === 'number' && ended.at >= held.since && typeof ended.to === 'number';
  if (!fresh || undoAt === ended.to || now - offAt >= WORKBENCH_PREVIEW_STEP_MS) return {next: 'save', offAt};
  return {next: 'wait', offAt};
}

// ---- a name box of our own: a preset's name, a snapshot's ---------------------------------------------------------
// The Floor keeps 16 characters for a preset's name and 10 for a snapshot's, in its own font: the printable ASCII
// characters (space to "~"). What it would refuse is left out as it is typed, quietly; anything past the limit too.
const WORKBENCH_NAME_LIMITS = Object.freeze({preset: 16, snapshot: 10});
function workbenchNameTyped(text, limit) {
  return String(text == null ? '' : text).replace(/[^\x20-\x7e]/g, '').slice(0, limit);
}
// The name to send when Enter is pressed, or null when there is nothing to do: nothing left once the spaces at its
// end are gone, or the same name as now.
function workbenchNameDone(text, before, limit) {
  const name = workbenchNameTyped(text, limit).replace(/\s+$/, '');
  return name && name !== String(before == null ? '' : before).replace(/\s+$/, '') ? name : null;
}

// A preset's new name is kept pending until the next Save (Nick, 2026-11-24: HX Edit renames only the copy stored on
// the Floor, so the Workbench renames it right after HX Edit's Save): {key: "setlist:number", name}, for that preset
// only. Enter with the stored name again: nothing pending.
function workbenchPendingNamed(key, name, stored) {
  const clean = String(name == null ? '' : name).replace(/\s+$/, '');
  return !key || !clean || clean === String(stored == null ? '' : stored).replace(/\s+$/, '') ? null : {key, name: clean};
}
// The pending name of the preset loaded now (key), or null: a pending name never follows to another preset.
function workbenchPendingHere(pending, key) {
  return pending && key && pending.key === key ? pending : null;
}

// Whether to ask HX Edit's list back to the loaded preset's setlist (Batch 3; live check 2026-11-24 09:58: after Esc
// the list stayed on the setlist looked at, because the page asked only on a new state message, and an idle HX Edit
// sends none). s: {looking (the setlist looked at, or null), loaded, shown (the setlist HX Edit's list shows), now,
// askedAt, tries: {word, count}, force}. Asked when nothing looks elsewhere and the list shows another setlist: at once
// when forced (a way out: the list closed, the view left, "Back to", a load), else WORKBENCH_BACK_MS apart and
// WORKBENCH_BACK_TRIES times for the same pair. {ask, tries}.
const WORKBENCH_BACK_MS = 3000, WORKBENCH_BACK_TRIES = 5;
function workbenchBackAsk(s) {
  const tries = s.tries && typeof s.tries === 'object' ? s.tries : {word: '', count: 0};
  if (s.looking !== null && s.looking !== undefined) return {ask: false, tries};
  if (!Number.isInteger(s.loaded) || !Number.isInteger(s.shown) || s.shown === s.loaded) return {ask: false, tries};
  const word = s.shown + '>' + s.loaded, mine = word === tries.word ? tries : {word, count: 0};
  if (!s.force && ((s.askedAt && s.now - s.askedAt < WORKBENCH_BACK_MS) || mine.count >= WORKBENCH_BACK_TRIES)) return {ask: false, tries: mine};
  return {ask: true, tries: {word, count: mine.count + 1}};
}

// ---- setlists (Batch 3) ----------------------------------------------------------------------------------------------
// A setlist's own name as HX Edit's chooser holds it ("USER 1"), or "Setlist 3" while the names are not known.
function workbenchSetlistName(names, index) {
  const name = Array.isArray(names) && typeof names[index] === 'string' ? names[index].trim() : '';
  return name || (Number.isInteger(index) ? 'Setlist ' + (index + 1) : '');
}
// What the setlists' column says beside a setlist read this session: how many of its presets are in use ("New
// Preset" is an empty place), "empty", or '' when it was not read.
function workbenchSetlistCount(names) {
  if (!Array.isArray(names) || !names.length) return '';
  const used = names.filter(name => !/^new preset$/i.test(String(name || '').trim())).length;
  return used ? String(used) : 'empty';
}

// ---- the Floor's slots (Batch 3) -------------------------------------------------------------------------------------
// Every used slot of 1..127 (captures and plain IRs share them; 128 is the preview slot, shown apart), in order:
// {slot, name, kind: 'capture' | 'ir', icon, gear}. A slot listed twice keeps its capture.
// ---- the session's status line: each view its own --------------------------------------------------------------------
// Levels and the NAM library share one session, whose status text stays the last one said until another is: after
// Levels' "Undone: 1 preset(s) are back as they were." the Library showed it under Put on the Floor (sweep 2026-11-24).
// A text belongs to the page the session was on when it first came (page: 'level' or 'library'); the same text sent
// again later keeps its page. track: {text, page}.
function workbenchStatusOwner(track, text, page) {
  text = typeof text === 'string' ? text : '';
  return track && track.text === text ? track : {text, page};
}
// What one view shows of it: the text when it is that view's, else nothing.
const workbenchStatusFor = (track, page) => (track && track.page === page ? track.text : '');

// others: the slots holding a capture that is not one of the library's listed ones (state.otherCaptures): used too.
function workbenchSlotRows(captures, irs, others) {
  const rows = new Map();
  for (const c of Array.isArray(irs) ? irs : []) if (c && Number.isInteger(c.slot) && c.slot >= 1 && c.slot <= 127) rows.set(c.slot, {slot: c.slot, name: String(c.name || ''), kind: 'ir'});
  for (const c of Array.isArray(others) ? others : []) if (c && Number.isInteger(c.slot) && c.slot >= 1 && c.slot <= 127) rows.set(c.slot, {slot: c.slot, name: String(c.name || ''), kind: 'capture', icon: '', gear: ''});
  for (const c of Array.isArray(captures) ? captures : []) {
    if (c && Number.isInteger(c.slot) && c.slot >= 1 && c.slot <= 127) rows.set(c.slot, {slot: c.slot, name: String(c.name || ''), kind: 'capture', icon: c.icon || '', gear: c.gear || ''});
  }
  return [...rows.values()].sort((a, b) => a.slot - b.slot);
}
// The free slots of 1..last between the used ones, folded into ranges: [[from, to], ...].
function workbenchFreeRanges(used, last = 127) {
  const taken = new Set(used), ranges = [];
  let from = null;
  for (let slot = 1; slot <= last + 1; slot++) {
    const free = slot <= last && !taken.has(slot);
    if (free && from === null) from = slot;
    if (!free && from !== null) { ranges.push([from, slot - 1]); from = null; }
  }
  return ranges;
}
// The presets this editor has seen use a slot (usage: [{setlist, preset, name, slots}], floor_memory: only presets
// opened here), the loaded one left out (the page says "This preset" for it): [{setlist, preset, name}].
function workbenchSlotUsers(usage, slot, loaded) {
  return (Array.isArray(usage) ? usage : []).filter(u => u && Array.isArray(u.slots) && u.slots.includes(slot) &&
    !(loaded && u.setlist === loaded.setlist && u.preset === loaded.number)).map(u => ({setlist: u.setlist, preset: u.preset, name: u.name}));
}

// What the NAM library page and the Captures drawer say besides their captures (v0.7.2): trouble, the library's own
// problem this launch (workbench.library_problem: it could not be read, or found), said above the list and never
// replaced by "No captures yet"; empty, the line where no capture is listed (words: the list's own {empty, none}).
// total: the captures the list has, shown: those its search and filters leave.
function workbenchLibraryWords(lib, total, shown, words) {
  const problem = lib && typeof lib === 'object' && lib.problem && typeof lib.problem === 'object' ? lib.problem : null;
  const trouble = problem && typeof problem.text === 'string' ? problem.text : '';
  return {trouble, empty: shown ? '' : total ? words.none : trouble ? '' : words.empty};
}
// The firmware notice (workbench.firmware_notice: the Floor did not say which firmware it runs this launch), until its
// OK: '' when there is none, or it was dismissed (the same words).
function workbenchFirmwareNote(options, dismissed) {
  const text = options && typeof options === 'object' && typeof options.firmwareNotice === 'string' ? options.firmwareNotice : '';
  return text && text !== dismissed ? text : '';
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { workbenchSceneSettled, WORKBENCH_SCENE_SETTLE_MS, workbenchSwitchSide, workbenchSecondClick, WORKBENCH_DOUBLE_MS, workbenchName, workbenchShape, workbenchPaths, workbenchPending, workbenchRedo, workbenchOwnSteps, workbenchUndoRedo, workbenchSwapRepeat, WORKBENCH_SWAP_REPEAT_MS, workbenchPicked, workbenchPick, WORKBENCH_PICK_HOLD_MS, workbenchSplitNote, workbenchMixNote, workbenchNodeGaps,
                     WORKBENCH_NOTE_GAP, WORKBENCH_NOTE_LEAST, workbenchNoteRoom, WORKBENCH_SIZES,
                     workbenchAdded, WORKBENCH_ADD_SELECT_MS, workbenchPresetKey, workbenchAddFollow, workbenchAddSelect, workbenchView, workbenchRailOn, workbenchUnsaved,
                     WORKBENCH_LAYOUTS, workbenchLayoutOf, workbenchSizes, WORKBENCH_SIDE_FIRST, workbenchSwitch, workbenchPlaces, WORKBENCH_NAME_LIMITS, workbenchNameTyped, workbenchNameDone,
                     workbenchPendingNamed, workbenchPendingHere, WORKBENCH_LOAD_SETTLE_MS, workbenchSettledMark, WORKBENCH_PREVIEW_END_MS, workbenchPreviewMark, workbenchPreviewOn, WORKBENCH_PREVIEW_END_WAIT_MS, WORKBENCH_PREVIEW_STEP_MS, workbenchSaveHold, WORKBENCH_BACK_MS,

 WORKBENCH_BACK_TRIES, workbenchBackAsk, workbenchSetlistName, workbenchSetlistCount, workbenchSlotRows, workbenchFreeRanges, workbenchSlotUsers, workbenchStatusOwner, workbenchStatusFor,
                     workbenchLevelKey, workbenchLevelTarget, workbenchLevelPlan, workbenchLevelChanges, workbenchLibraryWords, workbenchFirmwareNote };
}
