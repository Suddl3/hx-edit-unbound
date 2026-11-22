'use strict';
// What Focus Mode's page (focus_view.html) and the Workbench's (workbench.html) both do with a block's controls: show a
// value as HX Edit shows it, and turn a knob or flip a switch as HX Edit's own sliders write it. Loaded by each page
// before its own script; it uses that page's `catalog`, `state` and `ask` (the page's top-level names).

// ---- values as HX Edit shows them (the rules are its own HelixControls.json, in the catalog) ----
function printf(format, x) {
  return String(format).replace(/%(\+?)(?:\.(\d+))?([fd%])/g, (_, plus, digits, type) => {
    if (type === '%') return '%';
    let text = type === 'd' ? String(Math.round(x)) : x.toFixed(digits ? +digits : 0);
    if (parseFloat(text) === 0) text = text.replace('-', '');
    return plus && parseFloat(text) >= 0 ? '+' + text : text;
  });
}
function positions(p) {
  const rules = catalog.controls[p.display] || {};
  return rules.isDiscrete && Array.isArray(rules.format) ? rules.format : null;
}
function shown(p, v) {
  const rules = catalog.controls[p.display] || {};
  if (v === undefined || v === null) return '';
  const names = positions(p);
  if (typeof v === 'boolean') return (names && names.length === 2 ? names : ['Off', 'On'])[v ? 1 : 0];
  if (names) return names[Math.round(v) - (typeof p.min === 'number' ? p.min : 0)] ?? String(v);
  const d = rules.minimumValue !== undefined && p.max > p.min
    ? rules.minimumValue + (v - p.min) / (p.max - p.min) * (rules.maximumValue - rules.minimumValue)
    : v * (rules.dspToDisplayScale || 1);
  let format = rules.formatUnits || rules.format || '%.1f', scale = 1;
  if (Array.isArray(rules.format)) {
    const range = rules.format.find(r => d >= r.lowerBound && d < r.upperBound) || rules.format[rules.format.length - 1];
    format = range.formatUnits || range.format; scale = range.unitsMultiplier || 1;
  }
  return printf(format, d * scale);
}
const wide = p => typeof p.min === 'number' && p.min > 0 && p.max / p.min >= 50;     // times and frequencies turn evenly by ratio
function turn(p, v) {                                                               // 0..1 position of the control
  if (typeof v !== 'number' || !(p.max > p.min)) return 0;
  const t = wide(p) && v > 0 ? Math.log(v / p.min) / Math.log(p.max / p.min) : (v - p.min) / (p.max - p.min);
  return Math.min(1, Math.max(0, t));
}

// ---- turning things: what the hand sets shows at once, and goes to HX Edit ----------------------------
// A drag is one "begin", its "move"s and one "end": HX Edit keeps that as a single step of its undo.
const held = new Map();                                   // value name -> {value, until}: shown until HX Edit has caught up
function valueOf(key) {
  const mine = held.get(key);
  if (mine && (mine.until === 0 || Date.now() < mine.until)) return mine.value;
  return state.values[key];
}
function setValue(block, key, value, phase) {
  held.set(key, {value, until: phase === 'begin' || phase === 'move' ? 0 : Date.now() + 600});
  ask('set', {dsp: block.dsp, id: block.id, key, value, phase});
}
const clamp = x => Math.min(1, Math.max(0, x));
function synced(p) { return !!(p.sync && valueOf(p.sync.switch) === true); }
const notes = () => (catalog.controls.sync_note || {}).format || [];
function text(p) {
  if (synced(p)) {
    const note = valueOf(p.sync.note);
    return typeof note === 'number' ? notes()[Math.round(note) - (p.sync.min || 0)] || '' : '';
  }
  return shown(p, valueOf(p.id));
}
// What a dial turns right now: its own value, or the note when it follows the tempo. Whole steps for a list
// of positions, a note or a whole-number value.
function turning(p) {
  if (synced(p)) return {key: p.sync.note, min: p.sync.min, max: p.sync.min + notes().length - 1, whole: true};
  return {key: p.id, min: p.min, max: p.max, whole: p.kind === 'steps' || p.whole === true};
}
function position(p) {
  const t = turning(p), v = valueOf(t.key);
  if (typeof v !== 'number') return 0;
  return t.whole ? clamp((v - t.min) / Math.max(1, t.max - t.min)) : turn(p, v);
}
function valueAt(p, x) {
  const t = turning(p); x = clamp(x);
  if (t.whole) return t.min + Math.round(x * (t.max - t.min));
  return wide(p) ? p.min * Math.pow(p.max / p.min, x) : p.min + x * (p.max - p.min);
}
function wireControl(el, p, block, redraw) {
  // A control of the page changes the block as HX Edit's sliders do: the '.lever' (a switch) flips with a click, the
  // '.dial' turns with a vertical drag, the wheel or the arrow keys, and goes back to its default with a double-click;
  // a '.sync' button makes a time follow the tempo. redraw(): the page shows what was set.
  const lever = el.querySelector('.lever'), dial = el.querySelector('.dial'), sync = el.querySelector('.sync');
  if (sync) sync.onclick = () => { setValue(block, p.sync.switch, !synced(p), 'single'); redraw(); };
  if (lever) {
    lever.onclick = () => {
      const now = valueOf(p.id);
      setValue(block, p.id, typeof now === 'number' ? (now === p.max ? p.min : p.max) : now !== true, 'single');
      redraw();
    };
    return;
  }
  let from = null, last = null, waiting = false, nudging = null;
  const push = (value, phase) => { last = value; setValue(block, turning(p).key, value, phase); redraw(); };
  // A press alone changes nothing (and a double-click is two of them): the drag begins with its first change.
  dial.onpointerdown = e => {
    if (e.button !== 0) return;
    try { dial.setPointerCapture(e.pointerId); } catch (_) { /* a pointer that is already gone */ }
    from = {y: e.clientY, x: position(p), moved: false}; last = valueAt(p, from.x); el.classList.add('live');
  };
  dial.onpointermove = e => {
    if (!from) return;
    const value = valueAt(p, from.x + (from.y - e.clientY) / (e.shiftKey ? 900 : 190));
    if (value === last) return;
    if (!from.moved) { from.moved = true; setValue(block, turning(p).key, last, 'begin'); }
    last = value; held.set(turning(p).key, {value, until: 0}); redraw();
    if (waiting) return;                                  // one message a frame is plenty
    waiting = true;
    requestAnimationFrame(() => { waiting = false; if (from) setValue(block, turning(p).key, last, 'move'); });
  };
  dial.onpointerup = dial.onpointercancel = () => {
    if (!from) return;
    const moved = from.moved;
    from = null; el.classList.remove('live');
    if (moved) push(last, 'end');
  };
  // The wheel and the arrow keys: a run of small steps is one drag for HX Edit's undo.
  const nudge = (direction, fine) => {
    const t = turning(p), step = t.whole ? 1 / Math.max(1, t.max - t.min) : fine ? .002 : .01;
    const value = valueAt(p, position(p) + direction * step);
    if (nudging === null) push(valueAt(p, position(p)), 'begin'); else clearTimeout(nudging);
    push(value, 'move');
    nudging = setTimeout(() => { nudging = null; push(last, 'end'); }, 350);
  };
  dial.onwheel = e => { e.preventDefault(); if (!from) nudge(e.deltaY < 0 ? 1 : -1, e.shiftKey); };
  dial.onkeydown = e => {
    if (['ArrowUp', 'ArrowRight'].includes(e.key)) nudge(1, e.shiftKey);
    else if (['ArrowDown', 'ArrowLeft'].includes(e.key)) nudge(-1, e.shiftKey);
    else return;
    e.preventDefault();
  };
  dial.ondblclick = () => { if (!synced(p) && typeof p.default === 'number') push(p.default, 'single'); };
}
