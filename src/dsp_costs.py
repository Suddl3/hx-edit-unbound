"""What one block really costs on the Floor, measured from its own DSP meter.

The Floor reports DSP per path only (dsp_meter.js: "used" of a 75 budget). HX Edit's per-model figure
(HelixModelDefs.bin) is an estimate that does not match it (a NAM A2 Lite: 36 of 75 there, much less on the meter).
So the Workbench watches the path: when a path has exactly one block more or fewer than its last steady reading,
the meter's next move is that block's cost. A model swapped for another counts too, once the old model's cost is
known. Nothing is asked of the device: these are the figures the meter reads anyway.

Saved in %LOCALAPPDATA%\\HX Edit NAM\\dsp-costs.json: {"costs": {key: used units}, "firmware": {...}}.

A NAM block's cost depends on the capture it plays, not only on its model: every capture is the one symbol
HD2_AmpNAMLite, and the live sweep of 2026-11-24 measured Jcm800 at 36.0 and Deluxe Reverb at 27.0 on the same Floor.
So a NAM block whose slot holds a capture of the library is keyed "<model>#<the capture's library id>" (the sha256 the
library keeps it by: the same capture in another slot is the same key, another capture in the same slot is not). Its
model's own figure follows the newest capture measured: it is the fallback for a capture not measured yet (cost_of),
and HX Edit's declared cost after it. A file from before this (model symbols only) loads as it was.
A block whose capture is not known for a moment (the slot check re-reads the slots after a chain change) is the same
block when only that changed: nothing is measured from it.
The costs are dropped when the Floor answers with another firmware than the one they were measured on (firmware_of:
its declared NAM and NAM Pedal costs, all its 0x4f answer says; review of PR #7).

A meter that has gone dead is not measured from (live check 2026-11-24 17:53: the Floor stopped answering after an
Undo, HX Edit's -8212 device timeout; the meter then read 0.0 on both paths while their blocks were still there,
and "path 1 has one block fewer, its meter 59.1 -> 0.0" saved 59.1 for HD2_AmpNAMLite):
  - a path whose meter drops to 0 while it still has blocks is dead (no block on the Floor costs nothing) until it
    reads above 0 again or has no blocks; a path with no reading is away;
  - HX Edit saying the device did not answer (device_lost) stops all measuring for LOST_QUIET seconds;
  - either way the last steady reading is dropped: the first reading after it is never compared with one from before.
And so one bad reading cannot change the file:
  - a block's cost is part of its path's total: never more than the total that had it, and less than it while other
    blocks share the path (bounded);
  - a figure more than confirm_gap away from the one kept is held, and kept only when a second measurement agrees
    with it (a Remove and its Undo measure twice).
"""
import json
import os
import re
from collections import Counter
from pathlib import Path

FILE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HX Edit NAM' / 'dsp-costs.json'
SETTLE = 5.0        # seconds any other reading must stay the same before it is the one to measure from
GIVE_UP = 30.0      # a change the meter never showed is dropped after this long (nothing is measured from it)
LOST_QUIET = 30.0   # after HX Edit said the device did not answer: nothing is measured or taken as steady for this long
AGREE = 1.0         # two measurements of one model this close agree


def confirm_gap(kept):
    """How far a new figure may be from the one kept and still replace it at once (else it waits for a second)."""
    return max(2.0, 0.15 * kept)


# HX Edit's answer when the device did not answer it in time (seen 2026-11-24 17:53 on an Undo, the Floor then gone)
DEVICE_ERRORS = ('-8212',)
_CODE = re.compile(r'\((-\d+)\)')
_CHAIN = re.compile(r'block\d{1,2}')
_CAPTURE = re.compile(r'[0-9a-f]{64}')
_KEY = re.compile(r'[A-Za-z0-9_]{3,64}(#[0-9a-f]{64})?')


def key_of(block, captures):
    """A block's key: its model, or "<model>#<capture id>" when its slot holds a capture of the library (captures:
    focus_view.js state.captures [{slot, id, ...}]). Only a NAM block's slot is in that list: an IR block's is an IR."""
    model = str(block.get('model'))
    slot = block.get('slot')
    if type(slot) is int and slot >= 1:
        for capture in captures:
            if isinstance(capture, dict) and capture.get('slot') == slot and _CAPTURE.fullmatch(str(capture.get('id') or '')):
                return model + '#' + capture['id']
    return model


def base(key):
    """The model of a key (a capture's key without its capture)."""
    return str(key).split('#', 1)[0]


def firmware_of(firmware):
    """What the costs are measured on: a floor_firmware.FloorFirmware the Floor itself answered with (source 'floor'),
    as {namCost, pedal, pedalCost}; None when the Floor did not say this launch (the costs are then kept as they are)."""
    if firmware is None or getattr(firmware, 'source', None) != 'floor':
        return None
    return {'namCost': firmware.nam_cost, 'pedal': bool(firmware.pedal), 'pedalCost': firmware.pedal_cost if firmware.pedal else None}


def device_lost(message):
    """Whether a message from the scripts says the Floor is not answering: a write or an undo refused with HX Edit's
    device timeout, the slot checker finding the device disconnected, or the DSP meter failing to read."""
    if not isinstance(message, dict):
        return False
    kind = message.get('type')
    if kind == 'toneTrace':
        found = _CODE.search(str(message.get('error') or ''))
        return bool(found) and found.group(1) in DEVICE_ERRORS
    if kind == 'automaticSlotStatus':
        return message.get('state') == 'disconnected'
    if kind == 'dspMeter':
        return message.get('event') == 'read-failed'
    return False


def _models(state, dsp):
    blocks = state.get('blocks') if isinstance(state, dict) else None
    captures = state.get('captures') if isinstance(state, dict) else None
    captures = captures if isinstance(captures, list) else []
    return Counter(key_of(b, captures) for b in blocks or [] if isinstance(b, dict) and b.get('dsp') == dsp and b.get('model'))


def _chain(state, dsp):
    """How many blocks of the chain (not an input, an output, the split or the mixer) a path has."""
    blocks = state.get('blocks') if isinstance(state, dict) else None
    return sum(1 for b in blocks or [] if isinstance(b, dict) and b.get('dsp') == dsp and _CHAIN.fullmatch(str(b.get('id'))))


def _preset(state):
    preset = state.get('preset') if isinstance(state, dict) else None
    return (preset.get('setlist'), preset.get('number')) if isinstance(preset, dict) else None


def _used(dsp, index):
    view = dsp[index] if isinstance(dsp, list) and len(dsp) > index else None
    used = view.get('used') if isinstance(view, dict) else None
    return float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) else None


def bounded(model, cost, total, shared):
    """(model, cost) when cost can be one block's share of a path whose meter read total, else None: more than 0,
    not more than the total, and less than it when other blocks were on the path with it."""
    if not 0 < cost <= 75 or cost > total or (shared and cost >= total):
        return None
    return model, cost


def difference(before, after):
    """(added, removed): the models one path gained and lost between two readings (Counters). A block that only
    gained or lost its capture's id (the same model, its capture known on one side only) is the same block."""
    added, removed = after - before, before - after
    for gone in list(removed.elements()):
        twin = next((key for key in added if base(key) == base(gone) and ('#' in key) != ('#' in gone)), None)
        if twin is not None:
            added[twin] -= 1
            removed[gone] -= 1
            added, removed = +added, +removed
    return added, removed


class DspCosts:
    def __init__(self, path=FILE, firmware=None):
        """firmware: what the Floor answered this launch (firmware_of), or None when it did not."""
        self.path = Path(path) if path else None
        self.costs = {}
        self.firmware = firmware
        self.dropped = False              # the file's costs were measured on another firmware: dropped at this start
        self._now = [None, None]          # per path: what it shows now {preset, models, used, since}
        self._settled = [None, None]      # per path: the last reading that stayed put {preset, models, chain, used}
        self._dead = [False, False]       # per path: its meter dropped to 0 while it had blocks
        self._quiet_until = None          # lost: no measuring until then
        self._held = {}                   # model: a figure far from the kept one, waiting for a second that agrees
        self.held = []                    # what the last observe held back [(model, cost)] (for the trace)
        was = None
        try:
            data = json.loads(self.path.read_text(encoding='utf-8')) if self.path else {}
            found, was = data.get('costs'), data.get('firmware')
            if isinstance(found, dict):
                self.costs = {str(k): round(float(v), 1) for k, v in found.items()
                              if _KEY.fullmatch(str(k)) and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 75}
        except (OSError, ValueError, AttributeError):
            self.costs = {}
        if firmware is None:
            self.firmware = was if isinstance(was, dict) else None      # (kept with the costs it belongs to)
        elif isinstance(was, dict) and was != firmware and self.costs:
            # measured on another firmware (a file from before this has none: its costs are taken as this one's)
            self.costs, self.dropped = {}, True
            self._save()

    def cost_of(self, key):
        """A key's measured cost: its own, else its model's (a capture not measured yet); None when neither is known."""
        return self.costs.get(key, self.costs.get(base(key)))

    def observe(self, state, dsp, now):
        """The chain (focus_view.js state) and the meter (dspLoad views) at time now. Returns what was measured
        [(model, cost)]; self.costs then has it, and the file is written."""
        found, self.held = [], []
        preset = _preset(state)
        quiet = self._quiet_until is not None and now < self._quiet_until
        for index in (0, 1):
            reading = {'preset': preset, 'models': _models(state, index), 'chain': _chain(state, index), 'used': _used(dsp, index)}
            last = self._now[index]
            if reading['used'] is None or not reading['chain'] or reading['used'] > 0:
                self._dead[index] = False
            if reading['used'] == 0 and reading['chain'] and last is not None and (last['used'] or 0) > 0:
                self._dead[index] = True              # dropped to 0 with its blocks still there: the meter, not a block
            if quiet or self._dead[index] or reading['used'] is None:
                # (told the device is gone, a dead meter or none: nothing to measure from, nothing kept from before;
                # while quiet not even the "since" of a reading, so the first steady one comes SETTLE after it)
                self._now[index] = None if quiet else {**reading, 'since': now}
                self._settled[index] = None
                continue
            current = self._now[index]
            if current is None or any(current[key] != reading[key] for key in reading):
                current = self._now[index] = {**reading, 'since': now}
            before = self._settled[index]
            if before == reading:
                continue
            measured = self._measure(before, reading)
            if measured == 'same':
                self._settled[index] = reading
                continue
            if measured == 'wait':
                if now - current['since'] >= GIVE_UP:
                    self._settled[index] = reading      # a change the meter never showed: start again from here
                continue                  # the blocks changed but the meter has not followed yet
            if measured:
                # The meter's first move after one block came or went: taken at once (a Remove then Undo a few
                # seconds later is two measurements), and the new reading is where the next one starts.
                self._settled[index] = reading
                found.append(measured)
                continue
            if now - current['since'] >= SETTLE:
                self._settled[index] = reading
        kept = []
        for model, cost in found:
            known, held = self.costs.get(model), self._held.pop(model, None)
            if known is None or abs(cost - known) <= confirm_gap(known) or (held is not None and abs(cost - held) <= AGREE):
                self.costs[model] = cost
                if base(model) != model:
                    self.costs[base(model)] = cost        # (the fallback for a capture not measured yet: the newest)
                kept.append((model, cost))
            else:
                self._held[model] = cost              # far from the kept figure: waits for a second measurement
                self.held.append((model, cost))
        if kept:
            self._save()
        return kept

    def lost(self, now):
        """HX Edit says the device is not answering: nothing measured for LOST_QUIET seconds, and the readings from
        before are forgotten (the first one after the device is back starts afresh)."""
        self._quiet_until = now + LOST_QUIET
        self._now = [None, None]
        self._settled = [None, None]

    def _measure(self, before, after):
        """(key, cost), 'wait' (the meter has not moved yet), 'same' (only a capture's id came or went) or None."""
        if not before or before['preset'] != after['preset'] or before['preset'] is None:
            return None
        if before['used'] is None or after['used'] is None:
            return None
        added, removed = difference(before['models'], after['models'])
        change = round(after['used'] - before['used'], 1)
        if sum(added.values()) + sum(removed.values()) == 0:
            # (only a capture's id came or went: the same blocks, taken as they are now when the meter agrees)
            return 'same' if change == 0 and before['models'] != after['models'] else None
        if change == 0:
            return 'wait'
        # (bounded by the path's total that had the block, and whether other blocks shared the path with it)
        if sum(added.values()) == 1 and not removed and change > 0:
            return bounded(next(iter(added)), change, after['used'], before['chain'] > 0)
        if sum(removed.values()) == 1 and not added and change < 0:
            return bounded(next(iter(removed)), -change, before['used'], after['chain'] > 0)
        if sum(added.values()) == 1 and sum(removed.values()) == 1:
            new, old = next(iter(added)), next(iter(removed))
            if old in self.costs:
                return bounded(new, round(self.costs[old] + change, 1), after['used'], after['chain'] > 1)
        return None

    def _save(self):
        if not self.path:
            return
        # (written beside it and then put in its place: a launcher stopped mid-write leaves the old file, not half of
        # one that the next launch cannot read; review of PR #7)
        part = self.path.with_name(self.path.name + '.part')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {'costs': self.costs, **({'firmware': self.firmware} if self.firmware else {})}
            part.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            os.replace(part, self.path)
        except OSError:
            pass
