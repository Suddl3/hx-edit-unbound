"""Focus Mode: the selected block shown large in its scene, with its own controls.

A WebView2 pane (focus_view.cs, compiled to FocusView.exe) sits over HX Edit's signal flow and edit panel
and shows focus_view.html. This module builds what the page needs to draw any block, from HX Edit's own
files in the prepared copy's res folder, and drives the pane:

- HelixModelDefs.bin: every model's parameters (name, range, default, display type);
- HelixControls.json: how each display type is shown (format, units, the names of a switch's positions);
- HX_ModelCatalog.bin: the models' names, pictures, categories (with HX Edit's category colours) and the
  order of their parameters, which is also the order of the Floor's parameter pages;
- floor_store: the scene of each category, the same assignment the Floor look page sends to the Floor.

The live values come from focus_view.js (it reads the edit buffer inside HX Edit). Nothing here talks to
the device.
"""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import struct
import subprocess
from threading import Event, Thread
from urllib.parse import quote

import msgpack

import floor_store

ROOT = Path(__file__).resolve().parent
PAGE = 'focus_view.html'
# The page and its pictures are local folders served under these names (WebView2 virtual hosts).
HOSTS = {'app': 'app.focus.example', 'models': 'models.focus.example', 'full': 'full.focus.example',
         'captures': 'captures.focus.example', 'capturesfull': 'capturesfull.focus.example',
         'scenes': 'scenes.focus.example', 'plates': 'plates.focus.example'}
NAM_ENGINES = ('HD2_AmpNAMLite', 'HD2_AmpNAMPedal')
NAM_TINT = (0xB0, 0x70, 0xE0)          # nam_catalog.NAM_CATEGORY_COLOR: HX Edit shows NAM blocks in this colour
NEUTRAL = (0x98, 0x98, 0x98)
# A block's own switches that the page shows another way (bypass is the stomp switch) or not at all.
HIDDEN = ('@enabled', '@stereo', '@bypassvolume', '@type', '@model', '@position', '@path')
LABEL_KEYS = {label: key for key, label in floor_store.CATEGORY_LABELS.items()}
# The 800 x 480 backgrounds are already framed for the Floor: the gear's base is at 300 of 480.
SMALL_SCENE = {'w': 800, 'h': 480, 'focus': [0.5, 0.625], 'zoom': 1.0, 'gain': 1.0}


def _clean(value):
    """The msgpack files end every string with a NUL."""
    if isinstance(value, dict):
        return {_clean(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value.rstrip('\0') if isinstance(value, str) else value


def _control(controls, display):
    """A display type's rules, following aliases (comp_attack -> time_ms)."""
    spec, seen = controls.get(display) or {}, set()
    while isinstance(spec, dict) and 'alias' in spec and spec['alias'] not in seen:
        seen.add(spec['alias'])
        spec = controls.get(spec['alias']) or {}
    if not isinstance(spec, dict):
        return {}
    return {key: spec[key] for key in ('format', 'formatUnits', 'dspToDisplayScale', 'minimumValue', 'maximumValue',
                                       'isDiscrete') if key in spec}


def parameters(model, order, controls):
    """A model's controls, in the order HX Edit lists them: [{id, name, min, max, default, display, kind, sync}].

    order: the catalog's "params" for the model (None: the definition's own order). An entry that is a list,
    [{TempoSyncN}, {SyncSelectN}, {parameter}], is a time or rate control that can follow the tempo: one control
    with a Sync switch. kind: "knob" (a range), "switch" (two positions) or "steps" (a few named positions)."""
    known = {str(p.get('symbolicID', '')): p for p in model.get('params') or [] if isinstance(p, dict)}

    def usable(key):
        p = known[key]
        return not (p.get('stereo-only') or key.startswith(('SyncSelect', 'TempoSync')) or key in HIDDEN)

    keys = []
    for entry in order or []:
        try:
            if isinstance(entry, list):
                sync, note = next(iter(entry[0])), next(iter(entry[1]))
                key, label = next(iter(entry[2].items()))
                keys.append((key, label, (sync, note)))
            else:
                key, label = next(iter(entry.items()))
                keys.append((key, label, None))
        except (AttributeError, IndexError, StopIteration, TypeError):
            continue
    keys = [k for k in keys if k[0] in known and k[0] not in HIDDEN]
    listed = {k[0] for k in keys}
    keys += [(key, None, None) for key in known if key not in listed and usable(key)]
    result = []
    for key, label, sync in keys:
        p = known[key]
        spec = _control(controls, p.get('displayType', ''))
        positions = spec.get('format') if spec.get('isDiscrete') and isinstance(spec.get('format'), list) else None
        kind = 'switch' if p.get('valueType') == 2 or (positions and len(positions) == 2) else 'steps' if positions else 'knob'
        item = {'id': key, 'name': label or p.get('name') or key, 'min': p.get('min'), 'max': p.get('max'),
                'default': p.get('default'), 'display': p.get('displayType', ''), 'kind': kind}
        if sync and sync[0] in known and sync[1] in known:
            item['sync'] = {'switch': sync[0], 'note': sync[1], 'min': known[sync[1]].get('min', 1)}
        result.append(item)
    return result


def _tint(text):
    try:
        value = int(str(text), 16)
    except ValueError:
        return list(NEUTRAL)
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255]


def _png_size(path):
    with open(path, 'rb') as file:
        head = file.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    return struct.unpack('>II', head[16:24])


def _folder(value):
    path = Path(value) if isinstance(value, str) and value else None
    return path if path and path.is_dir() else None


def art_folders(resources, settings=None):
    """The folders the page's pictures come from: {name: folder}. Always: the prepared copy's model pictures
    (256 px), the capture pictures (128 px) and the Floor's backgrounds (800 x 480). Larger ones when this PC has
    them (settings.json "focusArt": {"models", "captures", "scenes"}, the same as JSON in HX_EDIT_FOCUS_ART, or the
    checkout's own full-size renders)."""
    art = (settings or {}).get('focusArt') if isinstance((settings or {}).get('focusArt'), dict) else {}
    try:                                           # a test build names this PC's folders without touching settings.json
        named = json.loads(os.environ.get('HX_EDIT_FOCUS_ART') or '{}')
        art = {**art, **named} if isinstance(named, dict) else art
    except ValueError:
        pass
    look = (settings or {}).get('floorLook') if isinstance((settings or {}).get('floorLook'), dict) else {}
    folders = {'app': ROOT, 'models': Path(resources) / 'icons_models', 'captures': ROOT / 'nam_capture_icons',
               'scenes': ROOT / 'focus_backgrounds' / 'backgrounds'}
    for name, choices in (('full', (art.get('models'), str(ROOT / 'helix_model_icons' / 'full'))),
                          ('capturesfull', (art.get('captures'), look.get('gearArt'))),
                          ('plates', (art.get('scenes'),))):
        found = next((folder for folder in map(_folder, choices) if folder), None)
        if found:
            folders[name] = found
    return {name: folder for name, folder in folders.items() if Path(folder).is_dir()}


def _url(host, name):
    return f'https://{HOSTS[host]}/{quote(name)}'


def scenes(folders):
    """{scene: {name, pictures: [urls, best first], w, h, focus, zoom, gain}}: where the gear stands in each."""
    try:
        styles = json.loads((ROOT / 'focus_backgrounds' / 'styles.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        styles = {}
    result = {}
    for entry in floor_store.scenes():
        ident, style = entry['id'], styles.get(entry['id']) if isinstance(styles.get(entry['id']), dict) else {}
        scene = {'name': entry['name'], 'pictures': [_url('scenes', f'{ident}.png')], **SMALL_SCENE}
        plate = folders.get('plates') and folders['plates'] / str(style.get('plate') or f'{ident}.png')
        if plate and plate.is_file():
            try:
                width, height = _png_size(plate)
            except (OSError, ValueError, struct.error):
                width = height = 0
            if width and height:
                focus = style.get('focus') if isinstance(style.get('focus'), list) and len(style['focus']) == 2 else [0.5, 0.56]
                scene.update(pictures=[_url('plates', plate.name), *scene['pictures']], w=width, h=height, focus=focus,
                             zoom=float(style.get('zoom', 1.0)), gain=float(style.get('gain', 1.0)))
                scene['small'] = {**SMALL_SCENE, 'picture': _url('scenes', f'{ident}.png')}
        result[ident] = scene
    return result


def assignment(settings=None):
    """Category -> scene, as the Floor look page has it (floor_store: the Floor tool's defaults until changed)."""
    look = (settings or {}).get('floorLook') if isinstance((settings or {}).get('floorLook'), dict) else {}
    chosen = look.get('assign') if isinstance(look.get('assign'), dict) else {}
    category = dict(floor_store.DEFAULT_ASSIGN['category'])
    category.update({key: value for key, value in (chosen.get('category') or {}).items()
                     if isinstance(key, str) and isinstance(value, str)})
    default = chosen.get('default') if isinstance(chosen.get('default'), str) else floor_store.DEFAULT_ASSIGN['default']
    return {'default': default, 'category': category}


def catalog(resources, settings=None):
    """Everything the page needs to draw any block of this copy of HX Edit.

    {"models": {symbol: {name, category, key, tint, pictures, scene, params}}, "controls": {display type: rules},
     "scenes": {...}, "captures": {"pictures": [url templates with {icon}]}, "nam": [NAM engine symbols]}"""
    resources = Path(resources)
    definitions = _clean(msgpack.unpackb((resources / 'HelixModelDefs.bin').read_bytes()))
    tree = _clean(msgpack.unpackb((resources / 'HX_ModelCatalog.bin').read_bytes()))
    controls = json.loads((resources / 'HelixControls.json').read_text(encoding='utf-8', errors='replace'))
    folders = art_folders(resources, settings)
    try:
        renders = json.loads((ROOT / 'helix_model_icons' / 'icons.json').read_text(encoding='utf-8')).get('icons') or {}
    except (OSError, ValueError):
        renders = {}
    assigned = assignment(settings)
    known_scenes = scenes(folders)

    def scene_for(key):
        scene = assigned['category'].get(key, assigned['default'])
        return scene if scene in known_scenes else assigned['default'] if assigned['default'] in known_scenes else None

    # A model's entry in the catalog: the first category that lists it (the NAM categories list the NAM block again).
    listed = {}
    for category in tree.get('categories') or []:
        name = str(category.get('name') or '')
        if name in ('Favorites', 'Connected Devices') or name.startswith('NAM '):
            continue
        for folder in [category, *(category.get('subcategories') or [])]:
            for entry in folder.get('models') or []:
                if isinstance(entry, dict) and entry.get('id'):
                    listed.setdefault(entry['id'], (category, entry))
    models, used = {}, set()
    for model in definitions:
        if not isinstance(model, dict) or not model.get('symbolicID'):
            continue
        symbol = model['symbolicID']
        category, entry = listed.get(symbol, ({}, {}))
        label = str(category.get('name') or '')
        key = LABEL_KEYS.get(label, '')
        nam = symbol in NAM_ENGINES
        if nam:
            label, key = 'NAM', 'amp'                     # the Floor files it under Amp: the same scene
        image = str(entry.get('image') or '')
        pictures = []
        render = renders.get(image) if isinstance(renders.get(image), dict) else None
        if render and 'full' in folders and (folders['full'] / Path(str(render.get('full'))).name).is_file():
            pictures.append(_url('full', Path(str(render['full'])).name))
        if image and not image.startswith('icon-') and (folders['models'] / image).is_file():
            pictures.append(_url('models', image))        # (the stock input/output pictures are strips of glyphs)
        params = parameters(model, entry.get('params'), controls)
        used.update(p['display'] for p in params)
        models[symbol] = {'name': str(entry.get('name') or model.get('name') or symbol).strip(), 'category': label, 'key': key,
                          'tint': list(NAM_TINT) if nam else _tint(category.get('color')) if category else list(NEUTRAL),
                          'pictures': pictures, 'scene': scene_for(key), 'params': params}
    used.add('sync_note')
    capture_pictures = [_url(host, '{icon}.png').replace('%7Bicon%7D', '{icon}')
                        for host in ('capturesfull', 'captures') if host in folders]
    return {'models': models, 'controls': {display: _control(controls, display) for display in sorted(used) if display},
            'scenes': known_scenes, 'captures': {'pictures': capture_pictures}, 'nam': list(NAM_ENGINES)}


def frida_options(models):
    """What focus_view.js needs: the value names to read for each model, and the NAM engines."""
    names = {}
    for symbol, model in models.items():
        keys = []
        for p in model['params']:
            keys.append(p['id'])
            if p.get('sync'):
                keys += [p['sync']['switch'], p['sync']['note']]
        names[symbol] = keys
    return {'focusParameters': names, 'focusNamEngines': list(NAM_ENGINES)}


def prepare_focus():
    """FocusView.exe, built beside the TONE3000 pane with the same WebView2 SDK (compiled once per source)."""
    from tone_browser import SDK_ASSETS, SDK_VERSION, browser_sdk
    source = ROOT / 'focus_view.cs'
    build = ROOT / 'build' / f'tone-browser-{SDK_VERSION}'
    exe = build / 'FocusView.exe'
    if exe.is_file() and (not source.is_file() or exe.stat().st_mtime_ns >= source.stat().st_mtime_ns):
        return exe
    build.mkdir(parents=True, exist_ok=True)
    if not all((build / Path(name).name).is_file() for name in SDK_ASSETS):
        with browser_sdk() as sdk:
            for name in SDK_ASSETS:
                (build / Path(name).name).write_bytes(sdk.read(name))
    compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET' / 'Framework' / 'v4.0.30319' / 'csc.exe'
    references = ['System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Web.Extensions.dll',
                  *(str(build / Path(name).name) for name in SDK_ASSETS[:2])]
    temporary = build / 'FocusView-new.exe'
    result = subprocess.run(
        [str(compiler), '/nologo', '/target:winexe', '/platform:x86', '/codepage:65001', f'/out:{temporary}',
         *(f'/reference:{assembly}' for assembly in references), str(source)],
        capture_output=True, text=True, errors='replace', timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise OSError(f'Could not build the Focus Mode pane.\n\n{result.stdout.strip()}')
    temporary.replace(exe)
    return exe


def pane_command(exe, parent, profile, folders):
    """FocusView.exe <parent window> <profile folder> <page url> <host=folder>…"""
    return [str(exe), str(int(parent)), str(profile), _url('app', PAGE),
            *(f'{HOSTS[name]}={folder}' for name, folder in folders.items())]


class FocusView:
    """The pane's process and what it shows. Lines to the pane: "P <json>" goes to the page as it is,
    "C <json>" is for the pane itself (its place, shown or hidden). Lines from it: {type: ready | action | error}.

    on_action(name, value): what the page asks for ("exit": back to the normal editor)."""

    def __init__(self, resources, *, settings=None, on_action=None, trace=None, process_factory=subprocess.Popen, exe=None):
        self.resources = Path(resources)
        self.settings = settings if isinstance(settings, dict) else {}
        self.on_action = on_action
        self.trace = trace or (lambda value: None)
        self.process_factory = process_factory
        self.exe = exe
        self.process = None
        self.on = False
        self.window = None
        self.bounds = None
        self.state = None
        self.page_ready = False
        self.failed = None
        self.queue = Queue()
        self.closed = Event()
        self._catalog = None
        self.worker = Thread(target=self._run, daemon=True)
        self.worker.start()

    def catalog(self):
        if self._catalog is None:
            self._catalog = catalog(self.resources, self.settings)
        return self._catalog

    def frida_options(self):
        return frida_options(self.catalog()['models'])

    def receive(self, value):
        """A message from focus_view.js. True when it was one of this pane's."""
        kind = value.get('type')
        if kind == 'focusBounds':
            self.queue.put(('bounds', (value.get('window'), value.get('bounds'))))
        elif kind == 'focusState':
            self.queue.put(('state', value.get('state')))
        else:
            return False
        return True

    def set_on(self, on):
        self.queue.put(('on', bool(on)))

    def close(self):
        self.closed.set()
        self.queue.put(('close', None))

    # -- the worker: the only thread that touches the pane's process ---------------------------------------------
    def _start(self):
        exe = self.exe or prepare_focus()
        profile = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HX Edit NAM' / 'Focus WebView'
        profile.mkdir(parents=True, exist_ok=True)
        command = pane_command(exe, self.window, profile, art_folders(self.resources, self.settings))
        self.process = self.process_factory(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf-8',
                                            errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        Thread(target=self._read, args=(self.process.stdout,), daemon=True).start()

    def _read(self, output):
        try:
            for line in output:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    self.queue.put(('pane', event))
        except (OSError, ValueError):
            pass
        self.queue.put(('pane', {'type': 'gone'}))

    def _write(self, prefix, value):
        if self.process is None or self.process.poll() is not None:
            return False
        try:
            self.process.stdin.write(prefix + ' ' + json.dumps(value, separators=(',', ':')) + '\n')
            self.process.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def _place(self):
        bounds = self.bounds if isinstance(self.bounds, dict) else None
        self._write('C', {'visible': bool(self.on and bounds), **({key: int(bounds[key]) for key in ('x', 'y', 'w', 'h')} if bounds else {})})

    def _show_state(self):
        if self.page_ready and self.state is not None:
            self._write('P', {'type': 'state', 'state': self.state})

    def _handle(self, kind, value):
        if kind == 'on':
            self.on = value
            if value:
                self.failed = None
            self._place()
            self._show_state()
        elif kind == 'bounds':
            window, bounds = value
            if isinstance(window, int) and window:
                self.window = window
            self.bounds = bounds if isinstance(bounds, dict) else None
            if self.on and self.process is None and self.window and self.bounds and not self.failed:
                try:
                    self._start()
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    self.failed = str(error)
                    self.trace({'type': 'focusView', 'event': 'start-failed', 'error': self.failed})
                    self._act('failed', self.failed)
            self._place()
        elif kind == 'state':
            self.state = value
            self._show_state()
        elif kind == 'pane':
            event = value.get('type')
            if event == 'ready':                       # the page has loaded: what it draws with, then what to draw
                self.page_ready = True
                self._write('P', {'type': 'catalog', 'catalog': self.catalog()})
                self._place()
                self._show_state()
                self.trace({'type': 'focusView', 'event': 'ready'})
            elif event == 'action':
                self._act(str(value.get('name') or ''), value.get('value'))
            elif event == 'error':
                self.failed = str(value.get('text') or 'The Focus Mode pane failed.')
                self.trace({'type': 'focusView', 'event': 'error', 'error': self.failed})
                self._act('failed', self.failed)
            elif event == 'gone':
                self.process, self.page_ready = None, False
                if self.on and not self.closed.is_set():
                    self._act('failed', self.failed or 'The Focus Mode pane closed.')

    def _act(self, name, value):
        if self.on_action:
            try:
                self.on_action(name, value)
            except Exception as error:               # the pane keeps running whatever the launcher does
                self.trace({'type': 'focusView', 'event': 'action-failed', 'error': str(error)})

    def _run(self):
        while not self.closed.is_set():
            try:
                kind, value = self.queue.get(timeout=.5)
            except Empty:
                continue
            if kind == 'close':
                break
            try:
                self._handle(kind, value)
            except Exception as error:
                self.trace({'type': 'focusView', 'event': 'worker-failed', 'error': str(error)})
        if self.process is not None:
            self._write('C', {'close': True})
            try:
                self.process.wait(timeout=2)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.process.kill()
                except OSError:
                    pass
