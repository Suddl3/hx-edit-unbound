"""The Workbench: a modern view of the regular editor, in the same kind of pane as Focus Mode.

A WebView2 pane (FocusView.exe, focus_view.cs) over HX Edit's toolbar, signal flow and edit panel shows workbench.html:
a top bar (preset, save, snapshots, undo, tempo, Editor | Focus, the Unbound menu), both paths of the chain with lane B
between the split and the mixer, the selected block's controls, and a picker for its model or capture. HX Edit's own
screen stays underneath, untouched, so switching the Workbench off is instant.

Everything it reads and writes goes through Focus Mode's own script and checks (focus_view.js, focus_view.FocusView):
the same reading of the preset, the same click on HX Edit's chain to select a block, the same writes. This module only
adds what the page draws with on top of Focus Mode's catalog. Nothing here talks to the device.
"""
import json
import re
import time
from pathlib import Path

import dsp_costs
import focus_view

SETTING = 'workbench'                  # settings.json: the Workbench is on (shown at launch) unless false or missing
# The kinds of NAM capture a model category offers as its own "Captures" tab (the names are focus_view.NAM_KINDS);
# every capture is under "All captures" in any case.
CAPTURE_TABS = {'Amp': ('NAM Amp', 'NAM Amp + cab'), 'Preamp': ('NAM Amp',), 'Cab': ('NAM Cab',),
                'Distortion': ('NAM Pedal',), 'Dynamics': ('NAM Pedal',)}
# The Unbound menu's choices that the launcher's own menu also has (dsp_meter.DspMeter.CHOICES): its tools open on HX
# Edit's own screen (they are panels of it, which the pane would cover), so the Workbench steps aside for them.
TOOLS = ('level', 'look', 'library')


def route_names(resources):
    """HX Edit's own names for where an input takes its signal and an output sends it (HelixControls.json input_type,
    output_type): {"inputs": [...], "outputs": [...]}, by the number the preset keeps."""
    try:
        controls = json.loads((Path(resources) / 'HelixControls.json').read_text(encoding='utf-8', errors='replace'))
    except (OSError, ValueError):
        controls = {}
    names = {}
    # (and the footswitch LED colours, for the Bypass and controllers tab: HelixControls.json footswitchLED)
    for key, kind in (('inputs', 'input_type'), ('outputs', 'output_type'), ('ledColors', 'footswitchLED')):
        found = (controls.get(kind) or {}).get('format') if isinstance(controls.get(kind), dict) else None
        names[key] = [str(name) for name in found] if isinstance(found, list) else []
    return names


def extras(resources):
    """What the Workbench draws with beyond Focus Mode's catalog: each model's DSP cost (HelixModelDefs.bin, the units
    of the Floor's own meter), the input and output names, and which capture kinds each category offers."""
    return {'loads': focus_view.model_loads(resources), **route_names(resources),
            'captureTabs': {name: list(kinds) for name, kinds in CAPTURE_TABS.items()}}


PINS = 'presetPins'                    # settings.json: the pinned presets, "setlist:number" (the Presets view's stars)
SETLISTS, PRESETS = 8, 128             # a Helix Floor's setlists and presets in each


def pinned(settings):
    """The pinned presets kept in settings.json, each "setlist:number"; anything else there is left out."""
    found = settings.get(PINS) if isinstance(settings, dict) else None
    keep = []
    for key in found if isinstance(found, list) else []:
        parts = key.split(':') if isinstance(key, str) else []
        if len(parts) == 2 and all(p.isdigit() for p in parts) and int(parts[0]) < SETLISTS and int(parts[1]) < PRESETS:
            key = f'{int(parts[0])}:{int(parts[1])}'
            if key not in keep:
                keep.append(key)
    return keep


def pins_after(settings, value):
    """The pins once the page's {setlist, number, on} is applied, or None for a request that is not one."""
    if not isinstance(value, dict):
        return None
    setlist, number, on = value.get('setlist'), value.get('number'), value.get('on')
    if any(isinstance(n, bool) or not isinstance(n, int) for n in (setlist, number)) or not isinstance(on, bool):
        return None
    if not (0 <= setlist < SETLISTS and 0 <= number < PRESETS):
        return None
    key, pins = f'{setlist}:{number}', pinned(settings)
    return pins + ([] if key in pins else [key]) if on else [k for k in pins if k != key]


# The Workbench's own Levels page: the library page's Level commands it may send into its session (tone_preview
# browse() checks each one's argument as it does from that page).
LEVEL_COMMANDS = ('levelOpen', 'levelScan', 'levelApply', 'levelUndo', 'levelGuitar', 'levelGuitarRemove', 'levelCancel')
PREFS = 'workbenchPrefs'               # settings.json: the page's choices that outlive it (the Levels page's)
LEVEL_KEY = re.compile(r'[^:]{0,4}:\d{1,3}:[^\n]{0,40}:\d{1,2}')


def prefs(settings):
    """The Workbench's kept choices, as settings.json has them, anything malformed left out:
    {"levels": {"metric": "lufs"|"peak", "target": "middle"|"custom"|"preset:<n>", "custom": float|None,
     "snapshots": "all"|"4"|"1", "signal": str, "offsets": {"setlist:preset:name:snapshot": {"dB", "when"}}}}"""
    found = settings.get(PREFS) if isinstance(settings, dict) else None
    levels = found.get('levels') if isinstance(found, dict) and isinstance(found.get('levels'), dict) else {}
    kept = {'metric': 'peak' if levels.get('metric') == 'peak' else 'lufs',
            'target': levels['target'] if isinstance(levels.get('target'), str) and re.fullmatch(r'middle|custom|preset:\d{1,3}', levels['target']) else 'middle',
            'custom': float(levels['custom']) if isinstance(levels.get('custom'), (int, float)) and not isinstance(levels.get('custom'), bool)
                      and -60 <= levels['custom'] <= 0 else None,
            'snapshots': levels['snapshots'] if levels.get('snapshots') in ('all', '4', '1') else 'all',
            'signal': levels['signal'][:64] if isinstance(levels.get('signal'), str) else '',
            'offsets': {}}
    offsets = levels.get('offsets') if isinstance(levels.get('offsets'), dict) else {}
    for key, value in list(offsets.items())[:2000]:
        if not isinstance(key, str) or not LEVEL_KEY.fullmatch(key) or not isinstance(value, dict):
            continue
        db = value.get('dB')
        if isinstance(db, (int, float)) and not isinstance(db, bool) and db and -12 <= db <= 12:
            kept['offsets'][key] = {'dB': round(float(db), 1), 'when': str(value.get('when') or '')[:40]}
    return {'levels': kept}


def prefs_after(settings, value):
    """The kept choices once the page's {"levels": {...}} replaces them, or None for a request that is not one."""
    if not isinstance(value, dict) or not isinstance(value.get('levels'), dict):
        return None
    return prefs({PREFS: {'levels': value['levels']}})


def setting_on(settings):
    """Whether the Workbench is shown at launch: only once it has been switched on (settings.json "workbench": true)."""
    return isinstance(settings, dict) and settings.get(SETTING) is True


class WorkbenchView(focus_view.FocusView):
    """The Workbench's pane: Focus Mode's driver with workbench.html. on: shown (the launcher hides it while Focus Mode
    is shown, so the two panes never fight over the top place)."""
    PAGE_NAME = 'workbench.html'
    PROFILE = 'Workbench WebView'

    def __init__(self, resources, *, costs_file=dsp_costs.FILE, clock=time.monotonic, **options):
        self.options = {}
        self.pins = []
        self.prefs = prefs({})
        self.costs = dsp_costs.DspCosts(costs_file)
        self.clock = clock
        self._seen = None
        super().__init__(resources, **options)

    def catalog(self):
        if self._catalog is None:
            self._catalog = {**focus_view.catalog(self.resources, self.settings), **extras(self.resources)}
        return self._catalog

    def show_options(self, options):
        """The Unbound menu's state for the page ({"level": the Level tool is in this build, ...})."""
        self.queue.put(('options', dict(options) if isinstance(options, dict) else {}))

    @staticmethod
    def checked_menu(value):
        """A choice from the page's Unbound menu, or None: "classic" (HX Edit's own screen), "focus" (Focus Mode), or a
        tool of the launcher's own menu."""
        return value if value in ('classic', 'focus', *TOOLS) else None

    def show_pins(self, pins):
        """The pinned presets ("setlist:number") for the page."""
        self.queue.put(('pins', [str(k) for k in pins] if isinstance(pins, list) else []))

    def show_prefs(self, kept):
        """The Workbench's kept choices (prefs) for the page."""
        self.queue.put(('prefs', kept if isinstance(kept, dict) else prefs({})))

    def show_session(self, kind, data):
        """What the Workbench's own session shows (TonePreview.WorkbenchSession): "status" with the Level view, or
        "closed" when the session has ended. Only what JSON carries."""
        try:
            data = json.loads(json.dumps(data if isinstance(data, dict) else {}, default=str))
        except (TypeError, ValueError):
            data = {}
        self.queue.put(('session', {'kind': str(kind), 'data': data}))

    def tool_closed(self):
        """The tool's window over the page closed by itself (its own Close, Esc): the page closes its frame."""
        self.queue.put(('toolClosed', None))

    def _handle(self, kind, value):
        if kind == 'toolClosed':
            if self.page_ready:
                self._write('P', {'type': 'toolClosed'})
            return
        if kind == 'prefs':
            self.prefs = value
            if self.page_ready:
                self._write('P', {'type': 'prefs', 'prefs': value})
            return
        if kind == 'session':
            if self.page_ready:
                self._write('P', {'type': 'session', **value})
            return
        if kind == 'pins':
            self.pins = value
            if self.page_ready:
                self._write('P', {'type': 'pins', 'pins': value})
            return
        if kind == 'options':
            self.options = value
            if self.page_ready:
                self._write('P', {'type': 'options', 'options': value})
            return
        super()._handle(kind, value)
        if kind == 'pane' and isinstance(value, dict) and value.get('type') == 'ready':
            self._write('P', {'type': 'options', 'options': self.options})
            self._write('P', {'type': 'pins', 'pins': self.pins})
            self._write('P', {'type': 'prefs', 'prefs': self.prefs})
            self._show_costs()
        if kind in ('state', 'dsp'):
            # (the meter's figures and each path's block count, as the measuring sees them, for the trace)
            seen = [[dsp_costs._used(self.dsp, k), sum(dsp_costs._models(self.state, k).values())] for k in (0, 1)]
            if seen != self._seen:
                self._seen = seen
                self.trace({'type': 'workbench', 'event': 'dsp-seen', 'paths': seen})
            self._idle()

    def _idle(self):
        # Each block's real DSP cost, from the path's meter as blocks come and go (dsp_costs).
        found = self.costs.observe(self.state, self.dsp, self.clock())
        for model, cost in found:
            self.trace({'type': 'workbench', 'event': 'dsp-cost', 'model': model, 'cost': cost})
        if found:
            self._show_costs()

    def _show_costs(self):
        # to the page, and to focus_view.js (the launcher posts them: its room checks then use them too)
        if self.page_ready:
            self._write('P', {'type': 'dspCosts', 'costs': self.costs.costs})
        self._act('costs', dict(self.costs.costs))
