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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { workbenchName, workbenchShape, workbenchPaths, workbenchPending, workbenchSplitNote, workbenchMixNote };
}
