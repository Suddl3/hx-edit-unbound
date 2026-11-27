'use strict';
// Review R5 (bughunt 2026-11-27, snapshot_grid_writes_before_recall_completes): the Snapshot values grid's change to a
// snapshot that is not on. focus_view.js's own change(), gridPreset() and gridStep() run against a fake HX Edit whose
// snapshot recall lands only on a later tick of the device, as HX Edit's does (it reports the new snapshot some 150 ms
// after the recall). Readings come every 250 ms, as the pane's poll; refresh() is mirrored here only in what it does
// with a grid change: the change under way first, then the pane's requests while none is (test_workbench checks that
// production does the same).
// Usage: node snapshot_grid_probe.cjs [focus_view.js]. Before the fix (no gridStep) it runs the old handler and fails.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'src', 'focus_view.js'), 'utf8').split(String.fromCharCode(13)).join('');
function inner(name) {                                   // a function of installFocusView, or null when there is none
  const start = source.indexOf('\n  function ' + name + '(');
  if (start < 0) return null;
  return source.slice(start + 1, source.indexOf('\n  }\n', start) + 4);
}
function outer(name) {                                   // a function of the file itself
  const start = source.indexOf('\nfunction ' + name + '(');
  if (start < 0) return null;
  return source.slice(start + 1, source.indexOf('\n}\n', start) + 2);
}
const code = [inner('change'), inner('gridPreset') || 'function gridPreset() { return null; }',
  inner('gridStep') || 'function gridStep() {}', outer('focusSameValue') || '', outer('focusGridStep') || ''].join('\n');

// One run: setup(world) before the change asked, during(world, tick) on every tick. The device: `lag` ticks for a recall.
function run({asks, lag = 1, ticks = 40, during = () => {}, current = 0, values}) {
  const c = vm.createContext({});
  vm.runInContext(`
    let clock = 1000;
    const Date = {now: () => clock};
    const editor = {isNull: () => false, equals(other) { return other === this; }};
    let known = [{dsp: 0, id: 'block0'}], changed = false, current = ${current}, values = ${JSON.stringify(values)};
    let recalls = [], pending = [], setValues = [], notices = [], traces = [], header = {setlist: 1, preset: 30};
    let gridJob = null, writes = [];
    const GRID_LANDED_MS = 1000, GRID_LATEST_MS = 5000, lag = ${lag};
    const send = message => { if (message.type === 'dspNotice') notices.push(message.text); else traces.push(message.stage); };
    const endDrag = () => {}, finish = () => {};
    const namView = {presetHeader: () => header};
    const targetBinding = {
      peekGlobal: (e, group, key) => current,
      peekValue: (e, dsp, id, key) => values[current],
      recallSnapshot: (e, n) => { recalls.push(n); pending.push({n, due: lag}); },
      setValue: (e, dsp, id, key, value) => { setValues.push({snapshot: current, value}); values[current] = value; },
    };
    ${code}
    function refresh() {
      if (gridJob) gridStep();
      while (writes.length && !gridJob) change(writes.shift());
    }
    function device() {                                   // recalls land in order, each after lag ticks
      for (const recall of pending) recall.due--;
      while (pending.length && pending[0].due <= 0) current = pending.shift().n;
    }
  `, c);
  const world = code => vm.runInContext(code, c);
  for (const ask of asks) world(`writes.push(${JSON.stringify({action: 'snapValue', dsp: 0, id: 'block0', key: 'Drive', ...ask})})`);
  for (let tick = 0; tick < ticks; tick++) {
    during(world, tick);
    world('refresh(); clock += 250; device();');
  }
  return JSON.parse(world('JSON.stringify({values, current, recalls, setValues, notices, traces, gridJob, writes})'));
}

const results = [];
function check(name, fn) { fn(); results.push(name); }

check('a value set in another snapshot lands there once the recall has landed (R5)', () => {
  for (const lag of [1, 3]) {
    const d = run({asks: [{snapshot: 1, value: 7}], lag, values: [1, 2]});
    assert.deepEqual(d.values, [1, 7], `lag ${lag}: snapshot 1 kept its value, snapshot 2 got the new one`);
    assert.deepEqual(d.setValues, [{snapshot: 1, value: 7}], 'written once, on snapshot 2');
    assert.deepEqual(d.recalls, [1, 0]);
    assert.equal(d.current, 0, 'the snapshot that was on is back');
    assert.equal(d.gridJob, null);
    assert.deepEqual(d.notices, []);
  }
});

check('the snapshot that is on is written at once, with no recall', () => {
  const d = run({asks: [{snapshot: 0, value: 5}], values: [1, 2], ticks: 1});
  assert.deepEqual(d.values, [5, 2]);
  assert.deepEqual(d.recalls, []);
});

check('a second change waits for the first, and each lands in its own snapshot', () => {
  const d = run({asks: [{snapshot: 1, value: 7}, {snapshot: 2, value: 9}, {snapshot: 0, value: 4}], lag: 2, values: [1, 2, 3], ticks: 80});
  assert.deepEqual(d.values, [4, 7, 9]);
  assert.deepEqual(d.recalls, [1, 0, 2, 0]);
  assert.deepEqual(d.setValues.map(s => s.snapshot), [1, 2, 0]);
  assert.equal(d.current, 0);
});

check('another preset before the write: nothing written, nothing recalled into it', () => {
  const d = run({asks: [{snapshot: 1, value: 7}], values: [1, 2], during: (world, tick) => { if (tick === 2) world('header = {setlist: 1, preset: 31}'); }});
  assert.deepEqual(d.setValues, []);
  assert.deepEqual(d.recalls, [1]);
  assert.equal(d.gridJob, null);
  assert.equal(d.notices.length, 1);
});

check('a preset loaded again (HX Edit says so) before the write: nothing written', () => {
  const d = run({asks: [{snapshot: 1, value: 7}], values: [1, 2], during: (world, tick) => { if (tick === 2) world("if (gridJob) gridJob.moved = 'EditBuffer_DevicePresetChanged'"); }});
  assert.deepEqual(d.setValues, []);
  assert.deepEqual(d.recalls, [1]);
});

check('another editor (the device reconnected) before the write: nothing written', () => {
  const d = run({asks: [{snapshot: 1, value: 7}], values: [1, 2], during: (world, tick) => { if (tick === 2) world('if (gridJob) gridJob.editor = {}'); }});
  assert.deepEqual(d.setValues, []);
  assert.deepEqual(d.recalls, [1]);
});

check('a recall that never lands: nothing written, the snapshot that was on asked for again, said so', () => {
  const d = run({asks: [{snapshot: 1, value: 7}], values: [1, 2], lag: 1000});
  assert.deepEqual(d.setValues, []);
  assert.deepEqual(d.recalls, [1, 0]);
  assert.equal(d.gridJob, null);
  assert.ok(d.notices.some(text => /did not reach snapshot 2/.test(text)));
});

check('nothing else from the pane is taken while a change is under way', () => {
  let seen = null;
  run({asks: [{snapshot: 1, value: 7}, {snapshot: 0, value: 4}], values: [1, 2], lag: 1,
       during: (world, tick) => { if (tick === 2) seen = JSON.parse(world('JSON.stringify({writes: writes.length, setValues, current})')); }});
  assert.equal(seen.writes, 1, 'the second change still waits');
  assert.deepEqual(seen.setValues, [], 'nothing written while snapshot 2 settles');
});

console.log(JSON.stringify(results));
