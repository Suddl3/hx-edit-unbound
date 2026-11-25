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
# ... and the NAM library's Floor actions (stage 5 part 2), the library page's own: load / use a capture on the NAM block
# selected in HX Edit, preview one in User IR 128 there (end: put the block back), replace a taken slot.
SESSION_PAGES = ('level', 'library')
VERSION_KEYS = ('original', 'pedal', 'light16')         # nam_library.VERSIONS and the original
LIGHT_LAYERS = ('23', '20', '16', '14')                  # the older trainer's choices (library_card.html #layers)
LIGHT_QUALITIES = ('quick', 'standard', 'deep')
CAPTURE_ID = re.compile(r'[0-9a-f]{64}')


def checked_floor(value, entries):
    """The library page's Floor action as the session's action string, or None: load / use / pick a capture of the
    library, end the preview, or replace slot 1..128."""
    if not isinstance(value, dict):
        return None
    do, argument = value.get('do'), value.get('arg')
    if do in ('load', 'use', 'pick'):
        return f'{do}:{argument}' if isinstance(argument, str) and CAPTURE_ID.fullmatch(argument) and argument in entries else None
    if do == 'end':
        return 'end'
    if do == 'replace':
        return f'replace:{argument}' if isinstance(argument, int) and not isinstance(argument, bool) and 1 <= argument <= 128 else None
    # its versions (stage 5 part 3): the library page's own commands, for a capture of the library
    if do in ('listenStop', 'optimizeCancel', 'lightCancel'):
        return do
    key, capture = value.get('key'), argument
    if not (isinstance(capture, str) and CAPTURE_ID.fullmatch(capture) and capture in entries):
        return None
    if do in ('versionDefault', 'useVersion', 'listen') and key in VERSION_KEYS:
        return f'{do}:{capture}:{key}'
    if do == 'versionRemove' and key in VERSION_KEYS[1:]:
        return f'{do}:{capture}:{key}'
    if do == 'optimize' and key in VERSION_KEYS[1:]:
        return f'optimize:{capture}:{key}'
    if do == 'light' and isinstance(key, str):
        layers, _, quality = key.partition(':')
        if layers in LIGHT_LAYERS and quality in LIGHT_QUALITIES:
            return f'light:{capture}:{layers}:{quality}'
    return None
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


# The Workbench's NAM library (stage 5, part 1): the library on this PC, read and changed here, not in a session.
# Nothing here touches the Floor. A file or a folder is chosen in the pane's own dialog ("choose" -> "chosen").
LIBRARY_EDITS = ('gear', 'instrument', 'icon', 'iconDelete', 'remove', 'openSource')
CHOOSE = ('nam', 'namFolder', 'picture', 'export')
TONE3000_HOSTS = ('www.tone3000.com', 'tone3000.com')


def library_view(library):
    """What the Workbench's NAM library draws: each capture (nam_library.library_row), the pictures uploaded by the
    player (as data: URIs: the pane cannot reach the library's folder), the picture picker's groups and the choices."""
    import capture_icons
    import nam_library
    pictures = getattr(library, 'pictures', None)
    rows = [nam_library.library_row(key, value, pictures) for key, value in library.entries().items()]
    uploaded = nam_library.uploaded_pictures(pictures) if pictures else []
    return {'rows': rows,
            'pictures': {ident: nam_library.uploaded_data_uri(Path(pictures) / f'{ident}.png') for ident in uploaded},
            'groups': ([{'label': 'Your pictures', 'ids': uploaded[::-1], 'uploaded': True}] if uploaded else [])
                      + capture_icons.picker_groups(),
            'gears': dict(nam_library.GEARS), 'instruments': dict(nam_library.INSTRUMENTS)}


def checked_library(value, entries):
    """The page's library edit as (do, capture id, value), or None: a known edit, of a capture in the library."""
    import nam_library
    if not isinstance(value, dict) or value.get('do') not in LIBRARY_EDITS:
        return None
    do, identity, choice = value['do'], value.get('id'), value.get('value')
    if do == 'iconDelete':
        return (do, None, choice) if isinstance(choice, str) and nam_library.UPLOADED.fullmatch(choice) else None
    if not isinstance(identity, str) or identity not in entries:
        return None
    if do == 'gear':
        return (do, identity, choice) if choice in nam_library.GEARS else None
    if do == 'instrument':
        return (do, identity, choice or '') if choice in ('', None, *nam_library.INSTRUMENTS) else None
    if do == 'icon':
        return (do, identity, choice or '') if choice in ('', None) or (isinstance(choice, str) and len(choice) <= 40) else None
    if do == 'openSource':
        source = str((entries[identity] or {}).get('source') or '')
        from urllib.parse import urlsplit
        where = urlsplit(source)
        return (do, identity, source) if where.scheme == 'https' and where.netloc in TONE3000_HOSTS else None
    return do, identity, None


def checked_chosen(value, entries, temp_folder):
    """What the pane's own dialog chose ({kind, id, paths}), checked: (kind, capture id or None, [Path]), or None.
    nam: .nam files; namFolder: one folder; picture: the PNG the pane made in the temp folder; export: one folder."""
    if not isinstance(value, dict) or value.get('kind') not in CHOOSE:
        return None
    kind, identity, paths = value['kind'], value.get('id'), value.get('paths')
    if not isinstance(paths, list) or not paths or len(paths) > 500 or not all(isinstance(p, str) and p for p in paths):
        return None
    paths = [Path(p) for p in paths]
    if kind in ('picture', 'export') and (not isinstance(identity, str) or identity not in entries):
        return None
    if kind == 'nam':
        paths = [p for p in paths if p.suffix.lower() == '.nam' and p.is_file()]
    elif kind in ('namFolder', 'export'):
        paths = [p for p in paths[:1] if p.is_dir()]
    elif kind == 'picture':
        folder = Path(temp_folder).resolve()
        paths = [p for p in paths[:1] if p.is_file() and p.resolve().parent == folder and p.name.startswith('workbench-picture-')
                 and p.suffix.lower() == '.png']
    return (kind, identity if kind in ('picture', 'export') else None, paths) if paths else None


def import_files(library, paths, limit=2000):
    """Add the .nam files (a folder: every .nam in it and its subfolders) to the library, as the library window's
    Import does: nothing is converted, nothing goes on the Floor. {added, same, bad, more}.
    At most limit files: a folder's files are taken as the walk finds them and the walk stops there, so a huge folder
    (a drive, a synced cloud folder) does not hold the worker until all of it is walked; more: there were more files.
    A file larger than a capture can be (nam_library.MAX_NAM_FILE) is not read. (Review of PR #7.)"""
    from itertools import islice
    import nam_library
    stats = {'added': 0, 'same': 0, 'bad': [], 'more': False}
    files = []
    for path in paths:
        if len(files) > limit:
            break
        files += sorted(islice(path.rglob('*.nam'), limit + 1 - len(files))) if path.is_dir() else [path]
    stats['more'] = len(files) > limit
    for path in files[:limit]:
        try:
            if path.stat().st_size > nam_library.MAX_NAM_FILE:
                raise ValueError('larger than a NAM capture')
            data = path.read_bytes()
            nam_library.check_nam(data)
        except (OSError, ValueError):
            stats['bad'].append(path.name)
            continue
        new = library.add_data(data, path.name, source='file', notify=False)[1]
        stats['added' if new else 'same'] += 1
    library.changed()
    return stats


def usage_view(presets):
    """The presets this editor has seen use each IR slot (floor_memory presets(): only presets opened here), for the
    Floor slots view: [{setlist, preset, name, slots}] with the slots known; the others (not read) are left out."""
    rows = []
    for entry in presets if isinstance(presets, list) else []:
        if not (isinstance(entry, (list, tuple)) and len(entry) == 4 and isinstance(entry[3], list)):
            continue
        setlist, preset, name, slots = entry
        if all(isinstance(n, int) and not isinstance(n, bool) for n in (setlist, preset)) and isinstance(name, str):
            rows.append({'setlist': setlist, 'preset': preset, 'name': name[:48],
                         'slots': [s for s in slots if isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= 128]})
    return rows


def previews_view(previews, leftover=None):
    """The previews this editor put in User IR 128 (floor_memory previews(): {slot name: day}), for the page:
    [{name, when, onBlock}]. onBlock: the one floor_memory's leftover record says a block still plays (HX Edit closed
    during that preview; the next launch puts the block back): clearing it first would leave that block silent."""
    playing = leftover.get('name') if isinstance(leftover, dict) else None
    return [{'name': name, 'when': when, 'onBlock': name == playing} for name, when in (previews or {}).items()
            if isinstance(name, str) and name and isinstance(when, str)][-64:]


LAYOUT = 'workbenchLayout'             # settings.json: the Workbench's layout (Batch 4), kept from one launch to the next
# The layouts of the Workbench's own page (workbench_layout.js WORKBENCH_LAYOUTS; the page shows one only once it is
# built there). Classic, HX Edit's own screen, is not one of them: it is the Workbench switched off ("workbench": false),
# so coming back from it finds the layout chosen before.
LAYOUTS = ('workbench', 'classicplus', 'stage')


def layout_of(settings):
    """The layout kept in settings.json, or "workbench" (the default) for anything else."""
    found = settings.get(LAYOUT) if isinstance(settings, dict) else None
    return found if isinstance(found, str) and found in LAYOUTS else 'workbench'


def checked_layout(value):
    """A layout the page's chooser asked for, or None for anything that is not one."""
    return value if isinstance(value, str) and value in LAYOUTS else None


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
        self.usage = []                # usage_view: the presets seen using each slot (Batch 3, Floor slots)
        self.previews = []             # previews_view: the previews of ours in User IR 128
        self.prefs = prefs({})
        self.library = None
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

    def show_library(self, view):
        """The NAM library (library_view) for the page."""
        self.queue.put(('library', view if isinstance(view, dict) else {}))

    def show_prefs(self, kept):
        """The Workbench's kept choices (prefs) for the page."""
        self.queue.put(('prefs', kept if isinstance(kept, dict) else prefs({})))

    def show_usage(self, rows):
        """Which presets this editor has seen use each slot (usage_view), for the Floor slots view."""
        self.queue.put(('usage', rows if isinstance(rows, list) else []))

    def show_previews(self, rows):
        """The previews this editor put in User IR 128 (previews_view), for the Floor slots view's slot 128."""
        self.queue.put(('previews', rows if isinstance(rows, list) else []))

    def checked_clear(self, value):
        """The Floor slots view's Clear ({slots: [...]}), asked of the player there, as the command for focus_view.js,
        or None: only slots the page was shown in use (a capture, a plain IR, or what User IR 128 holds), none of them
        one the loaded preset's blocks use (HX Edit's own Clear refuses those too; focus_view.js checks again)."""
        state = self.state if isinstance(self.state, dict) else {}
        slots = value.get('slots') if isinstance(value, dict) else None
        if not isinstance(slots, list) or not 1 <= len(slots) <= 128 or len(set(map(repr, slots))) != len(slots):
            return None
        if any(isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= 128 for s in slots):
            return None
        used = {c.get('slot') for key in ('captures', 'irs') for c in state.get(key) or [] if isinstance(c, dict)}
        if state.get('slot128'):
            used.add(128)
        here = {b.get('slot') for b in state.get('blocks') or [] if isinstance(b, dict) and isinstance(b.get('slot'), int)}
        if not set(slots) <= used or set(slots) & here:
            return None
        return {'action': 'clear', 'slots': sorted(slots)}

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
        if kind == 'library':
            self.library = value
            if self.page_ready:
                self._write('P', {'type': 'library', 'library': value})
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
        if kind in ('usage', 'previews'):
            setattr(self, kind, value)
            if self.page_ready:
                self._write('P', {'type': kind, kind: value})
            return
        if kind == 'deviceLost':
            self.costs.lost(self.clock())
            self.trace({'type': 'workbench', 'event': 'dsp-device-lost'})
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
            self._write('P', {'type': 'usage', 'usage': self.usage})
            self._write('P', {'type': 'previews', 'previews': self.previews})
            if self.library is not None:
                self._write('P', {'type': 'library', 'library': self.library})
            self._show_costs()
        if kind in ('state', 'dsp'):
            # (the meter's figures and each path's block count, as the measuring sees them, for the trace)
            seen = [[dsp_costs._used(self.dsp, k), sum(dsp_costs._models(self.state, k).values())] for k in (0, 1)]
            if seen != self._seen:
                self._seen = seen
                self.trace({'type': 'workbench', 'event': 'dsp-seen', 'paths': seen})
            self._idle()

    def receive(self, value):
        # (every script message reaches the pane: one saying the Floor is not answering stops the measuring, on the
        # pane's own thread; dsp_costs.device_lost. Live check 2026-11-24 17:53.)
        if dsp_costs.device_lost(value):
            self.queue.put(('deviceLost', None))
        return super().receive(value)

    def _idle(self):
        # Each block's real DSP cost, from the path's meter as blocks come and go (dsp_costs).
        found = self.costs.observe(self.state, self.dsp, self.clock())
        for model, cost in found:
            self.trace({'type': 'workbench', 'event': 'dsp-cost', 'model': model, 'cost': cost})
        for model, cost in self.costs.held:
            self.trace({'type': 'workbench', 'event': 'dsp-cost-held', 'model': model, 'cost': cost, 'kept': self.costs.costs.get(model)})
        if found:
            self._show_costs()

    def _show_costs(self):
        # to the page, and to focus_view.js (the launcher posts them: its room checks then use them too)
        if self.page_ready:
            self._write('P', {'type': 'dspCosts', 'costs': self.costs.costs})
        self._act('costs', dict(self.costs.costs))
