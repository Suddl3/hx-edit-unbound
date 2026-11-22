"""What one block really costs on the Floor, measured from its own DSP meter.

The Floor reports DSP per path only (dsp_meter.js: "used" of a 75 budget). HX Edit's per-model figure
(HelixModelDefs.bin) is an estimate that does not match it (a NAM A2 Lite: 36 of 75 there, much less on the meter).
So the Workbench watches the path: when a path settles with exactly one block more or fewer than before, the
change in its meter is that block's cost. A model swapped for another counts too, once the old model's cost is
known. Nothing is asked of the device: these are the figures the meter reads anyway.

Saved in %LOCALAPPDATA%\\HX Edit NAM\\dsp-costs.json: {"costs": {model symbol: used units}}.
"""
import json
import os
from collections import Counter
from pathlib import Path

FILE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HX Edit NAM' / 'dsp-costs.json'
SETTLE = 5.0        # seconds a path's blocks and its meter figure must stay the same before they are trusted
GIVE_UP = 30.0      # a change the meter never showed is dropped after this long (nothing is measured from it)


def _models(state, dsp):
    blocks = state.get('blocks') if isinstance(state, dict) else None
    return Counter(str(b.get('model')) for b in blocks or [] if isinstance(b, dict) and b.get('dsp') == dsp and b.get('model'))


def _preset(state):
    preset = state.get('preset') if isinstance(state, dict) else None
    return (preset.get('setlist'), preset.get('number')) if isinstance(preset, dict) else None


def _used(dsp, index):
    view = dsp[index] if isinstance(dsp, list) and len(dsp) > index else None
    used = view.get('used') if isinstance(view, dict) else None
    return float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) else None


def difference(before, after):
    """(added, removed): the models one path gained and lost between two readings (Counters)."""
    return after - before, before - after


class DspCosts:
    def __init__(self, path=FILE):
        self.path = Path(path) if path else None
        self.costs = {}
        self._now = [None, None]          # per path: what it shows now {preset, models, used, since}
        self._settled = [None, None]      # per path: the last reading that stayed put {preset, models, used}
        try:
            found = json.loads(self.path.read_text(encoding='utf-8')).get('costs') if self.path else None
            if isinstance(found, dict):
                self.costs = {str(k): round(float(v), 1) for k, v in found.items()
                              if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 75}
        except (OSError, ValueError, AttributeError):
            self.costs = {}

    def observe(self, state, dsp, now):
        """The chain (focus_view.js state) and the meter (dspLoad views) at time now. Returns what was measured
        [(model, cost)]; self.costs then has it, and the file is written."""
        found = []
        preset = _preset(state)
        for index in (0, 1):
            reading = {'preset': preset, 'models': _models(state, index), 'used': _used(dsp, index)}
            current = self._now[index]
            if current is None or any(current[key] != reading[key] for key in reading):
                self._now[index] = {**reading, 'since': now}
                continue
            if now - current['since'] < SETTLE:
                continue
            before = self._settled[index]
            if before == reading:
                continue
            measured = self._measure(before, reading)
            if measured == 'wait' and now - current['since'] < GIVE_UP:
                continue                  # the blocks changed but the meter has not followed yet
            self._settled[index] = reading
            if measured and measured != 'wait':
                found.append(measured)
        if found:
            for model, cost in found:
                self.costs[model] = cost
            self._save()
        return found

    def _measure(self, before, after):
        """(model, cost), 'wait' (the meter has not moved yet) or None (nothing to measure)."""
        if not before or before['preset'] != after['preset'] or before['preset'] is None:
            return None
        if before['used'] is None or after['used'] is None:
            return None
        added, removed = difference(before['models'], after['models'])
        change = round(after['used'] - before['used'], 1)
        if sum(added.values()) + sum(removed.values()) == 0:
            return None
        if change == 0:
            return 'wait'
        if sum(added.values()) == 1 and not removed and change > 0:
            return next(iter(added)), change
        if sum(removed.values()) == 1 and not added and change < 0:
            return next(iter(removed)), -change
        if sum(added.values()) == 1 and sum(removed.values()) == 1:
            new, old = next(iter(added)), next(iter(removed))
            if old in self.costs:
                cost = round(self.costs[old] + change, 1)
                return (new, cost) if 0 < cost <= 75 else None
        return None

    def _save(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({'costs': self.costs}, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        except OSError:
            pass
