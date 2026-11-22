'use strict';

// The Workbench's chain (workbench.html): each DSP drawn as a path of eight fixed places, lane B under lane A between
// the split and the mixer, from what focus_view.js reads (focusSnapshot's blocks). Pure: tests run it with node.
//
// How a preset keeps its routing (HX Edit's .hlx, the same names in the edit buffer):
//   a block: @position 0..7 (its place) and @path (0 lane A, 1 lane B);
//   split / join: @position, the gap the split or the mixer sits in (the split before place k, the mixer before
//     place k, 8 = after the last place); lane B runs over the places between them;
//   inputB: @input, 0 (None) unless the split was dragged down, when lane B has an input of its own;
//   outputB: @output, where lane B goes when the mixer was dragged down. A stock new preset keeps outputB at 1 with
//     no lane B at all, so it counts only on a path that has a lane B with the mixer at the end.
//   outputA of path 1: 2, 3 or 4 sends it into path 2 (Path 2A, 2B or 2A+B).
const WORKBENCH_PLACES = 8;
const WORKBENCH_INTO_PATH_2 = Object.freeze({2: ['A'], 3: ['B'], 4: ['A', 'B']});

function workbenchName(list, code) {
  // A short name from HX Edit's own list ("Multi (Guitar, Aux, Variax)" -> "Multi").
  if (!Number.isInteger(code)) return '';
  const name = Array.isArray(list) && typeof list[code] === 'string' ? list[code] : code === 0 ? 'None' : 'Input ' + code;
  return name.replace(/\s*\(.*\)\s*$/, '').trim();
}

function workbenchPaths(blocks, names = {}) {
  const all = Array.isArray(blocks) ? blocks : [];
  const inputs = names.inputs || [], outputs = names.outputs || [];
  const find = (dsp, id) => all.find(block => block.dsp === dsp && block.id === id) || null;
  const first = find(0, 'outputA'), fed = first && WORKBENCH_INTO_PATH_2[first.output] || [];
  const paths = [];
  for (const dsp of [0, 1]) {
    const chain = all.filter(block => block.dsp === dsp && /^block\d{1,2}$/.test(block.id) && Number.isInteger(block.position)
                                     && block.position >= 0 && block.position < WORKBENCH_PLACES);
    const a = Array(WORKBENCH_PLACES).fill(null), b = Array(WORKBENCH_PLACES).fill(null);
    for (const block of chain) (block.path === 1 ? b : a)[block.position] = block;
    const inputA = find(dsp, 'inputA'), inputB = find(dsp, 'inputB'), outputA = find(dsp, 'outputA'), outputB = find(dsp, 'outputB');
    const split = find(dsp, 'split'), join = find(dsp, 'join');
    const fromPath1 = dsp === 1 ? fed : [];
    // Lane B is there with a block on it, or with an input of its own (the split dragged down, or path 1 sent into it).
    const ownInput = !!inputB && (inputB.input > 0 || fromPath1.includes('B'));
    const used = b.some(Boolean);
    const laneB = used || ownInput;
    const gap = (block, fallback) => block && Number.isInteger(block.position) ? Math.min(WORKBENCH_PLACES, Math.max(0, block.position)) : fallback;
    let splitAt = ownInput ? 0 : gap(split, 0), joinAt = gap(join, WORKBENCH_PLACES);
    const ownOutput = laneB && !!outputB && outputB.output > 0 && joinAt >= WORKBENCH_PLACES;
    if (ownOutput) joinAt = WORKBENCH_PLACES;
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
      inputB: laneB && ownInput ? {block: inputB, name: inputName(inputB)} : null,
      outputB: laneB && ownOutput ? {block: outputB, name: workbenchName(outputs, outputB.output)} : null,
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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { workbenchName, workbenchPaths, workbenchSplitNote, workbenchMixNote };
}
