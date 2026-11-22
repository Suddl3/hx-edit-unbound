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
    for key, kind in (('inputs', 'input_type'), ('outputs', 'output_type')):
        found = (controls.get(kind) or {}).get('format') if isinstance(controls.get(kind), dict) else None
        names[key] = [str(name) for name in found] if isinstance(found, list) else []
    return names


def extras(resources):
    """What the Workbench draws with beyond Focus Mode's catalog: each model's DSP cost (HelixModelDefs.bin, the units
    of the Floor's own meter), the input and output names, and which capture kinds each category offers."""
    return {'loads': focus_view.model_loads(resources), **route_names(resources),
            'captureTabs': {name: list(kinds) for name, kinds in CAPTURE_TABS.items()}}


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
        self.costs = dsp_costs.DspCosts(costs_file)
        self.clock = clock
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

    def _handle(self, kind, value):
        if kind == 'options':
            self.options = value
            if self.page_ready:
                self._write('P', {'type': 'options', 'options': value})
            return
        super()._handle(kind, value)
        if kind == 'pane' and isinstance(value, dict) and value.get('type') == 'ready':
            self._write('P', {'type': 'options', 'options': self.options})
            self._show_costs()
        if kind in ('state', 'dsp'):
            self._idle()

    def _idle(self):
        # Each block's real DSP cost, from the path's meter as blocks come and go (dsp_costs).
        found = self.costs.observe(self.state, self.dsp, self.clock())
        for model, cost in found:
            self.trace({'type': 'workbench', 'event': 'dsp-cost', 'model': model, 'cost': cost})
        if found:
            self._show_costs()

    def _show_costs(self):
        if self.page_ready:
            self._write('P', {'type': 'dspCosts', 'costs': self.costs.costs})
