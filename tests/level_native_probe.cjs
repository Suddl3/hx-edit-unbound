'use strict';
// Level presets' native actions (tone_view.js level*): the production function bodies, run with HX Edit's
// edit buffer replaced by a map (levelGet / levelSet) and the preset header by a plain value. No device.
// Code review 2026-11-27: R2 (an output B of its own), R3 (restore only into the prepared preset), R4 (an
// output Level on a pedal or MIDI is never replaced), and Apply only into the preset that was measured (R1).
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const tone = fs.readFileSync(path.join(__dirname, '..', 'src', 'tone_view.js'), 'utf8');
function fn(name) {
  const start = tone.indexOf('  function ' + name + '(');
  assert.ok(start >= 0, 'tone_view.js has no ' + name);
  const end = tone.indexOf('\n  }', start);
  return tone.slice(start, end + 4);
}
const names = ['levelGainController', 'levelSetGain', 'levelOutputs', 'levelSamePreset', 'levelExpect', 'levelOwns',
  'levelPlays', 'levelOwnOutputB', 'levelRefuseOutputB', 'levelRecord', 'levelHere', 'levelState',
  'levelRestoreSaved', 'levelAction'];
const functions = names.map(fn).join('\n');

function world() {
  const c = vm.createContext({});
  vm.runInContext(`
    const levelInputs = [[0, 'inputA'], [0, 'inputB'], [1, 'inputA'], [1, 'inputB']];
    const INTO_PATH_2 = [2, 3, 4], NO_INPUT = 0, USB_78 = 16, USB_12 = 10;
    const SNAPSHOTS_CONTROLLER = 19, GAIN_MIN = -120, GAIN_MAX = 20, OUTPUT_PARAMETERS = ['gain', 'pan'];
    let levelSaved = null, levelUndo = null, levelSavedAt = 0, active = null, connectionGeneration = 4;
    let header = {setlist: 2, preset: 30, name: 'Thirty'}, writes = [], refuse = () => false;
    const namView = {presetHeader: () => header};
    const values = new Map();
    const key = (d, g, k) => [d, g, k].join('/');
    function put(d, g, k, v) { values.set(key(d, g, k), v); }
    function levelGet(e, d, g, k) { return values.has(key(d, g, k)) ? values.get(key(d, g, k)) : null; }
    function levelGetTyped(e, d, g, k) { const value = levelGet(e, d, g, k); return value === null ? null : {type: 8, value}; }
    function levelSet(e, d, g, k, v, flags) {
      v = typeof v === 'object' && v !== null ? (v.float ?? v.int) : v;
      if (refuse(d, g, k, v)) return -1;
      writes.push({d, g, k, v}); put(d, g, k, v); return 0;
    }
    function levelEditor() { return {}; }
    function load(setlist, preset, name) { header = {setlist, preset, name}; }
    put(-1, 'global', '@current_snapshot', 0); put(-1, 'snapshot0', '@name', 'One'); put(-1, 'snapshot1', '@name', 'Two');
    put(-1, 'global', '@topology0', 'A'); put(-1, 'global', '@topology1', 'A');
    put(0, 'inputA', '@input', 1); put(0, 'inputB', '@input', 0); put(1, 'inputA', '@input', 0); put(1, 'inputB', '@input', 0);
    put(0, 'outputA', '@output', 1); put(1, 'outputA', '@output', 1); put(0, 'outputB', '@output', 1);
    put(0, 'outputA', 'gain', 0); put(1, 'outputA', 'gain', 0);
    ${functions}
  `, c);
  return c;
}
const run = (c, code) => vm.runInContext(code, c);
const json = (c, code) => JSON.parse(run(c, `JSON.stringify(${code})`));
const here = {setlist: 2, preset: 30, name: 'Thirty'};

// R2: lane B with an output of its own is refused before anything is written; with a mixer it is measured.
{
  const c = world();
  run(c, `put(-1, 'global', '@topology0', 'SAB')`);
  assert.throws(() => run(c, `levelAction({action: 'levelBegin', preset: ${JSON.stringify(here)}})`), /output of its own/);
  assert.throws(() => run(c, `levelAction({action: 'levelPrepare', outputs: false})`), /output of its own/);
  assert.throws(() => run(c, `levelAction({action: 'levelPrepare'})`), /output of its own/);
  assert.deepEqual(json(c, 'writes'), []);
  assert.equal(run(c, 'levelSaved'), null);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 1);
  // Apply refuses it too (the preset may have been changed after its scan).
  assert.throws(() => run(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2}, preset: ${JSON.stringify(here)}})`), /output of its own/);
  assert.deepEqual(json(c, 'writes'), []);
  // A path 2 with lane B on its own output but no signal (no input, not fed) does not matter.
  run(c, `put(-1, 'global', '@topology0', 'SABJ'); put(-1, 'global', '@topology1', 'AB')`);
  run(c, `levelAction({action: 'levelBegin', preset: ${JSON.stringify(here)}})`);
  assert.equal(json(c, 'levelSaved.preset').preset, 30);
}

// R3: the routing is put back only into the preset it was taken from (and over the same connection).
{
  const c = world();
  run(c, `levelAction({action: 'levelBegin', preset: ${JSON.stringify(here)}}); levelAction({action: 'levelPrepare'});`);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 16);
  assert.equal(json(c, `levelGet(null, 0, 'outputA', '@output')`), 10);
  assert.deepEqual(json(c, 'levelSaved.preset'), here);
  assert.equal(json(c, 'levelSaved.connection'), 4);
  // The player loads 031 (its own input 5, output 7) before the scan ends.
  run(c, `load(2, 31, 'Thirty-one'); put(0, 'inputA', '@input', 5); put(0, 'outputA', '@output', 7); writes = [];`);
  const reply = json(c, `levelAction({action: 'levelRestore'})`);
  assert.equal(reply.other, true);
  assert.equal(reply.kept.preset.preset, 30);
  assert.deepEqual(reply.kept.inputs, [[0, 'inputA', 1]]);
  assert.deepEqual(json(c, 'writes'), []);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 5);
  assert.equal(json(c, `levelGet(null, 0, 'outputA', '@output')`), 7);
  assert.equal(run(c, 'levelSaved'), null);         // no longer blocks Apply or Save in 031
}
{
  // The same in another setlist: preset 030 of setlist 3 is another preset.
  const c = world();
  run(c, `levelAction({action: 'levelBegin'}); levelAction({action: 'levelPrepare'});
          load(3, 30, 'Thirty'); put(0, 'inputA', '@input', 5); writes = [];`);
  assert.equal(json(c, `levelAction({action: 'levelRestore'})`).other, true);
  assert.deepEqual(json(c, 'writes'), []);
}
{
  // levelRecover's own record (in memory) is no different: nothing written into 031, the record handed back.
  const c = world();
  run(c, `levelAction({action: 'levelBegin'}); levelAction({action: 'levelPrepare'});
          load(2, 31, 'Thirty-one'); put(0, 'inputA', '@input', 5); put(0, 'outputA', '@output', 7); writes = [];`);
  const reply = json(c, `levelAction({action: 'levelRecover'})`);
  assert.equal(reply.other, true);
  assert.equal(reply.kept.preset.preset, 30);
  assert.deepEqual(json(c, 'writes'), []);
  // Back on 030 (still re-routed: it was saved that way), the kept record puts back only what is still re-routed.
  run(c, `load(2, 30, 'Thirty'); put(0, 'inputA', '@input', 16); put(0, 'outputA', '@output', 10);`);
  const back = json(c, `levelAction({action: 'levelRecover', ...${JSON.stringify(reply.kept)}})`);
  assert.equal(back.recovered, true);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 1);
  assert.equal(json(c, `levelGet(null, 0, 'outputA', '@output')`), 1);
}
{
  // A new device connection: the editor's record is not written blindly; the same preset's check puts back
  // only what is still re-routed.
  const c = world();
  run(c, `levelAction({action: 'levelBegin'}); levelAction({action: 'levelPrepare'}); connectionGeneration = 5;
          put(0, 'outputA', '@output', 3); writes = [];`);
  const reply = json(c, `levelAction({action: 'levelRecover'})`);
  assert.equal(reply.recovered, true);
  assert.deepEqual(json(c, 'writes').map(w => [w.g, w.k, w.v]), [['inputA', '@input', 1]]);   // output 3 left alone
}
{
  // The prepared preset itself: put back as before.
  const c = world();
  run(c, `levelAction({action: 'levelBegin'}); levelAction({action: 'levelPrepare'}); writes = [];`);
  assert.equal(json(c, `levelAction({action: 'levelRestore'})`).restored, true);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 1);
  assert.equal(json(c, `levelGet(null, 0, 'outputA', '@output')`), 1);
  assert.equal(run(c, 'levelSaved'), null);
}
{
  // A write refused halfway through preparing: the record made beforehand still puts back what did change.
  const c = world();
  run(c, `put(0, 'inputB', '@input', 2); refuse = (d, g, k, v) => g === 'inputB' && v === 16;`);
  assert.throws(() => run(c, `levelAction({action: 'levelPrepare', outputs: false})`), /inputB/);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 16);
  run(c, `refuse = () => false; levelAction({action: 'levelRestore'})`);
  assert.equal(json(c, `levelGet(null, 0, 'inputA', '@input')`), 1);
  assert.equal(json(c, `levelGet(null, 0, 'inputB', '@input')`), 2);
}

// R4: an output Level on EXP / MIDI (not Snapshots) is never replaced, so Undo has nothing it cannot put back.
{
  const c = world();
  run(c, `put(-1, 'controller', 'dsp0.outputA.gain.@controller', 1)`);
  assert.throws(() => run(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2}, home: 1, preset: ${JSON.stringify(here)}})`),
    /pedal or another controller/);
  assert.equal(json(c, `levelGet(null, -1, 'controller', 'dsp0.outputA.gain.@controller')`), 1);
  assert.deepEqual(json(c, 'writes'), []);
  assert.equal(run(c, 'levelUndo'), null);
  // On Snapshots already, or on none: applied as before.
  run(c, `put(-1, 'controller', 'dsp0.outputA.gain.@controller', 19)`);
  assert.deepEqual(json(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2}, home: 1, preset: ${JSON.stringify(here)}})`).visit, [1]);
}

// R1: Apply only into the preset that was measured.
{
  const c = world();
  assert.throws(() => run(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2, 2: -2}})`), /different preset/);
  assert.throws(() => run(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2, 2: -2}, preset: {setlist: 3, preset: 30}})`), /different preset/);
  assert.deepEqual(json(c, 'writes'), []);
  run(c, `levelAction({action: 'levelApplyPlan', trims: {1: -2}, home: 1, preset: ${JSON.stringify(here)}})`);
  run(c, `load(2, 31, 'Thirty-one'); writes = [];`);
  assert.throws(() => run(c, `levelAction({action: 'levelApplyHere', snapshot: 1, trim: -2})`), /different preset/);
  assert.throws(() => run(c, `levelAction({action: 'levelTie', dsp: 0, key: 'gain', controller: 19, preset: ${JSON.stringify(here)}})`), /different preset/);
  assert.deepEqual(json(c, 'writes'), []);
}

console.log('level native probe passed');
