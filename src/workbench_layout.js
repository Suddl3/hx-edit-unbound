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
    const model = pending.slot ? namEngine : pending.symbol;
    const there = all.find(at);
    if (there && there.model === model && (!pending.slot || there.slot === pending.slot)) return {blocks: all, settled: true};
    const shown = {dsp: pending.dsp, id: there ? there.id : 'pending', model, position: pending.place, path: pending.lane, enabled: true,
                   ...(pending.slot ? {slot: pending.slot} : {})};
    return {blocks: there ? all.map(b => b === there ? {...b, ...shown} : b) : all.concat([shown]), settled: false};
  }
  return {blocks: all, settled: true};
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

function workbenchView(view, action, name) {
  // The next {drawer, half, full} after an action: "rail" (a rail button: opens the thing in its first size, or closes
  // it when it is open there), "open" (the same without closing), "expand" (to its full view), "shrink" (back to its
  // other size), "back" (Back to the chain), "close" (that thing, wherever it is), "escape" (the full view, else the
  // lower half), "select" (a block picked in the chain: Levels gives way to the block's panel; Floor look stays and
  // follows it), "goto" (a small tile of a full view's header: everything over the chain closes).
  const v = {drawer: '', half: '', full: '', ...(view || {})};
  const sizes = WORKBENCH_SIZES[name] || [];
  const openFull = () => { v.full = name; if (v.half && v.half !== name) v.half = ''; };
  // One thing open at a time beside or under the chain (Nick, 2026-11-23: a side list and a lower-half tool open
  // together read as confusing): a side list closes the tool under the chain, and the other way round.
  const place = (size, thing) => { v[size] = thing; if (thing) v[size === 'drawer' ? 'half' : 'drawer'] = ''; };
  if (action === 'rail' || action === 'open') {
    const size = sizes[0], toggle = action === 'rail';
    if (size === 'drawer' || size === 'half') {
      if (v.full) { v.full = ''; place(size, name); } else place(size, toggle && v[size] === name ? '' : name);
    } else if (size === 'full') {
      if (toggle && v.full === name) v.full = ''; else openFull();
    }
  } else if (action === 'expand') {
    if (sizes.includes('full')) openFull();
  } else if (action === 'shrink') {
    const was = v.full, size = (WORKBENCH_SIZES[was] || [])[0];
    v.full = '';
    if (size === 'drawer' || size === 'half') place(size, was);
  } else if (action === 'back') {
    v.full = '';
  } else if (action === 'close') {
    for (const size of ['drawer', 'half', 'full']) if (v[size] === name) v[size] = '';
  } else if (action === 'escape') {
    if (v.full) v.full = ''; else v.half = '';
  } else if (action === 'select') {
    if (v.half === 'level') v.half = '';
  } else if (action === 'goto') {
    v.full = ''; v.half = '';
  }
  return v;
}

function workbenchRailOn(view, name) {
  // Whether a rail button is lit: what the full view shows, else what is open beside or under the chain.
  if (!view) return false;
  return view.full ? view.full === name : view.drawer === name || view.half === name;
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
function workbenchSlotRows(captures, irs) {
  const rows = new Map();
  for (const c of Array.isArray(irs) ? irs : []) if (c && Number.isInteger(c.slot) && c.slot >= 1 && c.slot <= 127) rows.set(c.slot, {slot: c.slot, name: String(c.name || ''), kind: 'ir'});
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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { workbenchName, workbenchShape, workbenchPaths, workbenchPending, workbenchRedo, workbenchSplitNote, workbenchMixNote, workbenchNodeGaps,
                     WORKBENCH_SIZES, workbenchView, workbenchRailOn, workbenchUnsaved, WORKBENCH_NAME_LIMITS, workbenchNameTyped, workbenchNameDone,
                     workbenchPendingNamed, workbenchPendingHere, WORKBENCH_BACK_MS, WORKBENCH_BACK_TRIES, workbenchBackAsk, workbenchSetlistName, workbenchSetlistCount, workbenchSlotRows, workbenchFreeRanges, workbenchSlotUsers,
                     workbenchLevelKey, workbenchLevelTarget, workbenchLevelPlan, workbenchLevelChanges };
}
