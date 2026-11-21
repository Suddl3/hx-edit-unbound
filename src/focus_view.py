"""Focus Mode: the selected block shown large in its scene, with its own controls.

A WebView2 pane (focus_view.cs, compiled to FocusView.exe) sits over HX Edit's signal flow and edit panel
and shows focus_view.html. This module builds what the page needs to draw any block, from HX Edit's own
files in the prepared copy's res folder, and drives the pane:

- HelixModelDefs.bin: every model's parameters (name, range, default, display type);
- HelixControls.json: how each display type is shown (format, units, the names of a switch's positions);
- HX_ModelCatalog.bin: the models' names, pictures, categories (with HX Edit's category colours) and the
  order of their parameters, which is also the order of the Floor's parameter pages;
- floor_store: the scene of each category, the same assignment the Floor look page sends to the Floor;
- settings.json "presetLooks": what a preset changes in that (its own background, a block's background or picture).

The live values come from focus_view.js (it reads the edit buffer inside HX Edit). Nothing here talks to
the device.
"""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import struct
import subprocess
from threading import Event, Thread
from urllib.parse import quote

import msgpack

import capture_icons
import floor_store

ROOT = Path(__file__).resolve().parent
PAGE = 'focus_view.html'
# The page and its pictures are local folders served under these names (WebView2 virtual hosts).
HOSTS = {'app': 'app.focus.example', 'models': 'models.focus.example', 'full': 'full.focus.example',
         'captures': 'captures.focus.example', 'capturesfull': 'capturesfull.focus.example',
         'scenes': 'scenes.focus.example', 'plates': 'plates.focus.example'}
NAM_ENGINES = ('HD2_AmpNAMLite', 'HD2_AmpNAMPedal')
NAM_TINT = (0xB0, 0x70, 0xE0)          # nam_catalog.NAM_CATEGORY_COLOR: HX Edit shows NAM blocks in this colour
# The kinds of NAM capture, as the block picker's NAM categories file them by a capture's gear (tone_view.js
# captureGroup; the names are nam_catalog.NAM_CATEGORY_GROUPS). A gear in none of them is "NAM Other".
NAM_KINDS = (('NAM Amp', ('amp', 'preamp')), ('NAM Amp + cab', ('amp-cab', 'amp-pedal-cab')), ('NAM Cab', ('cab',)),
             ('NAM Pedal', ('pedal', 'pedal-amp')), ('NAM Other', ()))
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
        if p.get('valueType') == 0:
            item['whole'] = True                         # whole numbers only (a slot, a number of semitones)
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


# ---- looks: one background per kind of block (the defaults), and what a preset changes ----------------------------
# settings.json "presetLooks": {"<setlist>:<preset>": {"name": the preset's name when its look was chosen,
#   "scene": one background for the whole preset (optional),
#   "blocks": {<model symbol> or "slot:<capture slot>": {"scene": ..., "picture": ...}}}}
# The most specific choice wins: the block's own in this preset, then the preset's, then the default for its kind.
# A block is known by its model (a NAM block by its capture slot), not by its place in the chain: the Floor can look
# that up, and it stays with the block when the chain is rearranged.
LOOKS_KEY = 'presetLooks'
PRESET_KEY = re.compile(r'(\d{1,2}):(\d{1,3})')
SCENE_ID = re.compile(r'[a-z0-9_]{1,40}')
SLOT_KEY = re.compile(r'slot:(\d{1,3})')
MODEL_KEY = re.compile(r'[A-Za-z0-9_]{1,64}')
PICTURE_ID = re.compile(r'(?:model|capture):[A-Za-z0-9_. -]{1,80}')


def _block_key(key):
    if not isinstance(key, str):
        return False
    slot = SLOT_KEY.fullmatch(key)
    return 1 <= int(slot[1]) <= 128 if slot else bool(MODEL_KEY.fullmatch(key))


def _choice(value):
    """A block's own look as it is kept: {"scene"?, "picture"?}, each only if well formed."""
    value = value if isinstance(value, dict) else {}
    kept = {}
    if isinstance(value.get('scene'), str) and SCENE_ID.fullmatch(value['scene']):
        kept['scene'] = value['scene']
    if isinstance(value.get('picture'), str) and PICTURE_ID.fullmatch(value['picture']):
        kept['picture'] = value['picture']
    return kept


def preset_looks(settings=None):
    """The looks chosen for presets, as settings.json keeps them; anything malformed is left out."""
    stored = (settings or {}).get(LOOKS_KEY)
    looks = {}
    for key, value in stored.items() if isinstance(stored, dict) else ():
        where = PRESET_KEY.fullmatch(key) if isinstance(key, str) else None
        if not where or int(where[1]) > 31 or int(where[2]) > 127 or not isinstance(value, dict):
            continue
        blocks = value.get('blocks') if isinstance(value.get('blocks'), dict) else {}
        entry = {'name': str(value.get('name') or '')[:32],
                 'blocks': {block: _choice(choice) for block, choice in blocks.items() if _block_key(block) and _choice(choice)}}
        if isinstance(value.get('scene'), str) and SCENE_ID.fullmatch(value['scene']):
            entry['scene'] = value['scene']
        if 'scene' in entry or entry['blocks']:
            looks[f'{int(where[1])}:{int(where[2])}'] = entry
    return looks


def look_view(settings=None):
    """What the page's Change look panel works with: the defaults in force, the Floor tool's own defaults (for the
    "Default" marks and for putting them back), the kinds of block, and every preset's look."""
    return {'assign': assignment(settings),
            'factory': {'default': floor_store.DEFAULT_ASSIGN['default'], 'category': dict(floor_store.DEFAULT_ASSIGN['category'])},
            'categories': [[key, label] for key, label in floor_store.CATEGORY_LABELS.items()],
            'presets': preset_looks(settings)}


def look_change(settings, change, preset, scenes, pictures, models):
    """One change asked for in the Change look panel, as the settings.json keys to save ({} when it is refused).

    preset: the loaded preset {setlist, number, name} (HX Edit's own header), which a preset's or a block's change
    must name. scenes / pictures / models: what this editor has (the catalog's), so nothing unknown is kept.
      {"scope": "block", "preset": {setlist, number}, "key": model or "slot:n", "scene": id | None}   (or "picture")
      {"scope": "preset", "preset": {...}, "scene": id | None}     one background for the whole preset, or none
      {"scope": "preset", "preset": {...}, "clear": True}          back on the defaults
      {"scope": "preset", "preset": {...}, "adopt": True}          a look kept under another name here is this preset's
      {"scope": "default", "category": kind or "default", "scene": id}
      {"scope": "default", "reset": True}"""
    settings = settings if isinstance(settings, dict) else {}
    if not isinstance(change, dict):
        return {}
    scope = change.get('scope')

    def scene(value):
        return value if isinstance(value, str) and SCENE_ID.fullmatch(value) and value in scenes else None

    if scope == 'default':
        look = dict(settings.get('floorLook')) if isinstance(settings.get('floorLook'), dict) else {}
        if change.get('reset') is True:
            look.pop('assign', None)
            return {'floorLook': look}
        chosen, kind = scene(change.get('scene')), change.get('category')
        if not chosen or (kind != 'default' and kind not in floor_store.CATEGORY_LABELS):
            return {}
        now = assignment(settings)
        if kind == 'default':
            now['default'] = chosen
        else:
            now['category'][kind] = chosen
        look['assign'] = floor_store.assignment(now, list(scenes))
        return {'floorLook': look}

    if scope not in ('block', 'preset') or not isinstance(preset, dict) or not isinstance(change.get('preset'), dict):
        return {}
    setlist, number = preset.get('setlist'), preset.get('number')
    if type(setlist) is not int or type(number) is not int or not 0 <= setlist <= 31 or not 0 <= number <= 127:
        return {}
    if change['preset'].get('setlist') != setlist or change['preset'].get('number') != number:
        return {}                                      # asked for a preset that is no longer the loaded one
    name = str(preset.get('name') or '')[:32]
    looks = preset_looks(settings)
    key = f'{setlist}:{number}'
    kept = looks.get(key)
    if scope == 'preset' and change.get('adopt') is True:
        if not kept or kept['name'] == name:
            return {}
        kept['name'] = name
        return {LOOKS_KEY: looks}
    if scope == 'preset' and change.get('clear') is True:
        if key not in looks:
            return {}
        del looks[key]
        return {LOOKS_KEY: looks}
    # A look kept under another name was another preset's (this number has been written over or the presets moved).
    entry = kept if kept and kept['name'] == name else {'name': name, 'blocks': {}}
    if scope == 'preset':
        if 'scene' not in change or (change['scene'] is not None and not scene(change['scene'])):
            return {}
        if change['scene'] is None:
            entry.pop('scene', None)
        else:
            entry['scene'] = change['scene']
    else:
        block = change.get('key')
        slot = SLOT_KEY.fullmatch(block) if isinstance(block, str) else None
        if not _block_key(block) or (not slot and block not in models):
            return {}
        own = dict(entry['blocks'].get(block) or {})
        touched = False
        if 'scene' in change:
            if change['scene'] is not None and not scene(change['scene']):
                return {}
            touched = True
            own.pop('scene', None) if change['scene'] is None else own.update(scene=change['scene'])
        if 'picture' in change:
            if change['picture'] is not None and change['picture'] not in pictures:
                return {}
            touched = True
            own.pop('picture', None) if change['picture'] is None else own.update(picture=change['picture'])
        if not touched:
            return {}
        if own:
            entry['blocks'][block] = own
        else:
            entry['blocks'].pop(block, None)
    if 'scene' in entry or entry['blocks']:
        looks[key] = entry
    else:
        looks.pop(key, None)
    return {LOOKS_KEY: looks}


def catalog(resources, settings=None):
    """Everything the page needs to draw any block of this copy of HX Edit.

    {"models": {symbol: {name, category, key, tint, pictures, picture, scene, params}}, "controls": {display type: rules},
     "scenes": {...}, "captures": {"pictures": [url templates with {icon}]}, "nam": [NAM engine symbols],
     "pictures": {picture id: {name, group, urls}}: every picture a block can be given in place of its own (the models'
     renders as "model:<HX Edit's picture file>", the capture pictures as "capture:<id>"),
     "nam_kinds": [{name, gears}]: the kinds of NAM capture, in the block picker's order (the last takes the rest)}"""
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
    models, used, gallery = {}, set(), {}
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
        title = str(entry.get('name') or model.get('name') or symbol).strip()
        own = f'model:{image}' if pictures and PICTURE_ID.fullmatch(f'model:{image}') else None
        if own and not nam:
            gallery.setdefault(own, {'name': title, 'group': label, 'urls': pictures})
        models[symbol] = {'name': title, 'category': label, 'key': key,
                          'tint': list(NAM_TINT) if nam else _tint(category.get('color')) if category else list(NEUTRAL),
                          'pictures': pictures, 'picture': own, 'scene': scene_for(key), 'params': params,
                          # what HX Edit can bypass has an "@enabled" switch of its own (an input or an output has none)
                          'bypass': any(isinstance(p, dict) and p.get('symbolicID') == '@enabled' for p in model.get('params') or [])}
    used.add('sync_note')
    # The models a block can be changed to, as HX Edit's own picker groups them. A stereo folder lists the mono
    # models again (a block keeps being mono or stereo), so only folders with models of their own are kept; "All"
    # repeats the folders beside it. Inputs, outputs, splits and merges are not models of a block.
    lists = []
    for category in tree.get('categories') or []:
        name = str(category.get('name') or '')
        if name in ('None', 'Favorites', 'Connected Devices', 'Input', 'Output', 'Split', 'Merge') or name.startswith('NAM '):
            continue
        shelves, seen = [], set()
        for folder in category.get('subcategories') or [category]:
            if str(folder.get('name') or '') == 'All' and len(category.get('subcategories') or []) > 1:
                continue
            symbols = [entry['id'] for entry in folder.get('models') or []
                       if isinstance(entry, dict) and entry.get('id') in models and entry.get('name')
                       and entry['id'] not in NAM_ENGINES and entry['id'] not in seen]
            seen.update(symbols)                           # (a model listed again under Stereo is the same model)
            if symbols:
                shelves.append({'name': str(folder.get('name') or '') if folder is not category else '', 'models': symbols})
        if shelves:
            lists.append({'name': name, 'tint': _tint(category.get('color')), 'folders': shelves})
    capture_pictures = [_url(host, '{icon}.png').replace('%7Bicon%7D', '{icon}')
                        for host in ('capturesfull', 'captures') if host in folders]
    try:
        icons = capture_icons.known_icons()
    except (OSError, ValueError, KeyError):
        icons = ()
    for icon in icons if capture_pictures else ():
        gallery[f'capture:{icon}'] = {'name': icon.replace('_', ' ').capitalize(), 'group': 'NAM',
                                      'urls': [url.replace('{icon}', quote(icon)) for url in capture_pictures]}
    return {'models': models, 'controls': {display: _control(controls, display) for display in sorted(used) if display},
            'scenes': known_scenes, 'captures': {'pictures': capture_pictures}, 'nam': list(NAM_ENGINES), 'lists': lists,
            'pictures': gallery, 'nam_kinds': [{'name': name, 'gears': list(gears)} for name, gears in NAM_KINDS]}


def model_loads(resources):
    """{model: DSP load} as HX Edit counts it (HelixModelDefs.bin), for checking a DSP's room before a model is changed."""
    try:
        definitions = _clean(msgpack.unpackb((Path(resources) / 'HelixModelDefs.bin').read_bytes()))
    except (OSError, ValueError, msgpack.exceptions.ExtraData):
        return {}
    return {model['symbolicID']: float(model['load']) for model in definitions
            if isinstance(model, dict) and model.get('symbolicID') and isinstance(model.get('load'), (int, float))}


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


def write_notify(settings=None):
    """Whether HX Edit's own sliders are shown a value set in the pane (a second write for its views only; on
    unless settings.json has "focusWriteNotify": false, which leaves exactly a stock slider's write)."""
    return (settings or {}).get('focusWriteNotify') is not False


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
        self._pictures = {}
        self.dsp = None
        self.look = look_view(self.settings)             # the defaults and every preset's look (show_look after a change)
        self.worker = Thread(target=self._run, daemon=True)
        self.worker.start()

    def catalog(self):
        if self._catalog is None:
            self._catalog = catalog(self.resources, self.settings)
        return self._catalog

    def frida_options(self):
        return {**frida_options(self.catalog()['models']), 'focusWriteNotify': write_notify(self.settings),
                'focusLoads': model_loads(self.resources)}

    def receive(self, value):
        """A message from focus_view.js. True when it was one of this pane's."""
        kind = value.get('type')
        if kind == 'focusBounds':
            self.queue.put(('bounds', (value.get('window'), value.get('bounds'))))
        elif kind == 'focusState':
            self.queue.put(('state', value.get('state')))
        elif kind == 'dspLoad':                          # the DSP meter's figures (dsp_meter.js), for the pane's own meters
            self.queue.put(('dsp', list(value.get('dsp') or [None, None])[:2]))
        elif kind == 'focusPreset':                      # focus_view.js is ready for the preset the page chose
            self.queue.put(('load', value.get('number')))
        elif kind == 'dspNotice':                        # a refusal the DSP meter would show: it is hidden under the pane
            if not self.on:
                return False
            self.notice(value.get('text'))
        else:
            return False
        return True

    def show_look(self, settings=None):
        """The looks as settings.json has them now, to the page (after a change here or on the Floor look page)."""
        self.queue.put(('look', look_view(settings)))

    def changed_look(self, value, settings=None):
        """The page's Change look request as the settings.json keys to save ({}: refused): look_change, for the preset
        HX Edit has loaded and with only the scenes, pictures and models this editor has."""
        state = self.state if isinstance(self.state, dict) else {}
        found = self.catalog()
        return look_change(settings, value, state.get('preset'), found['scenes'], found['pictures'], found['models'])

    def notice(self, text):
        """A line for the page to show for a moment (something asked for in the pane did not happen)."""
        if isinstance(text, str) and text.strip():
            self.queue.put(('notice', text.strip()[:200]))

    def set_on(self, on):
        self.queue.put(('on', bool(on)))

    def with_pictures(self, state):
        """The state with a picture for every capture: its own when it has one of the pack's, else the one the library
        picks from its name and gear (capture_icons.pick), as the NAM tab and the chain do."""
        captures = state.get('captures') if isinstance(state, dict) else None
        if not isinstance(captures, list):
            return state
        known = set(capture_icons.known_icons())
        for capture in captures:
            if not isinstance(capture, dict) or capture.get('icon') in known:
                continue
            key = (str(capture.get('name') or ''), str(capture.get('gear') or ''))
            if key not in self._pictures:
                try:
                    self._pictures[key] = capture_icons.pick(key[0], key[1] or None)
                except (OSError, ValueError, KeyError, IndexError):
                    self._pictures[key] = ''
            capture['icon'] = self._pictures[key]
        return state

    def _block(self, value):
        state = self.state if isinstance(self.state, dict) else {}
        if not isinstance(value, dict):
            return None
        return next((b for b in state.get('blocks') or [] if isinstance(b, dict) and b.get('dsp') == value.get('dsp')
                     and b.get('id') == value.get('id')), None)

    def checked_snapshot(self, value):
        """The page's request to recall a snapshot, as the command for focus_view.js, or None: one of the preset's
        snapshots, by its place (0 = snapshot 1)."""
        state = self.state if isinstance(self.state, dict) else {}
        count = len(state.get('snapshots') or [])
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < min(count, 8):
            return None
        return {'action': 'snapshot', 'index': value}

    def checked_preset(self, value):
        """The page's request for another preset of the loaded setlist, as the command for focus_view.js, or None:
        'previous' or 'next' of the loaded one (around the ends, as the Floor's own footswitches), or a preset's
        number from the list the page was given."""
        state = self.state if isinstance(self.state, dict) else {}
        preset = state.get('preset') if isinstance(state.get('preset'), dict) else {}
        now = preset.get('number')
        if isinstance(now, bool) or not isinstance(now, int) or not 0 <= now <= 127:
            return None
        if value == 'previous':
            number = (now - 1) % 128
        elif value == 'next':
            number = (now + 1) % 128
        elif isinstance(value, int) and not isinstance(value, bool) and isinstance(state.get('presets'), list):
            number = value
            if not 0 <= number < len(state['presets']) or number > 127 or number == now:
                return None
        else:
            return None
        return {'action': 'preset', 'number': number}

    def checked_model(self, value):
        """The page's request to change a block's model, as the command for focus_view.js, or None: only a block
        of the chain (not an input, an output, the split or the join), and only a model HX Edit's picker offers."""
        block = self._block(value)
        symbol = value.get('symbol') if isinstance(value, dict) else None
        if not block or not str(block.get('id', '')).startswith('block') or not isinstance(symbol, str):
            return None
        offered = {s for group in self.catalog()['lists'] for folder in group['folders'] for s in folder['models']}
        if symbol not in offered or symbol == block.get('model'):
            return None
        return {'action': 'model', 'dsp': block['dsp'], 'id': block['id'], 'symbol': symbol}

    def checked_capture(self, value):
        """The page's request to put a capture on a block, or None: a capture that is on the Floor (by its slot), on a
        block of the chain. A NAM block changes capture; another block becomes a NAM block with that capture."""
        block = self._block(value)
        slot = value.get('slot') if isinstance(value, dict) else None
        state = self.state if isinstance(self.state, dict) else {}
        on_floor = {c.get('slot') for c in state.get('captures') or [] if isinstance(c, dict)}
        if (not block or not str(block.get('id', '')).startswith('block') or isinstance(slot, bool) or not isinstance(slot, int)
                or not 1 <= slot <= 127 or slot not in on_floor):
            return None
        return {'action': 'capture', 'dsp': block['dsp'], 'id': block['id'], 'slot': slot}

    def checked_set(self, value):
        """The page's request to set a value, as the command for focus_view.js, or None when it is not one of the
        selected kind: a control of that block's model (kept inside its range), its tempo switch or note, or its
        bypass. {dsp, id, key, value, phase}."""
        state = self.state if isinstance(self.state, dict) else {}
        if not isinstance(value, dict) or value.get('phase') not in ('single', 'begin', 'move', 'end'):
            return None
        block = next((b for b in state.get('blocks') or [] if isinstance(b, dict) and b.get('dsp') == value.get('dsp')
                      and b.get('id') == value.get('id')), None)
        model = self.catalog()['models'].get(block.get('model')) if block else None
        key, new = value.get('key'), value.get('value')
        if not model or not isinstance(key, str) or isinstance(new, str) or new is None:
            return None
        command = {'action': 'set', 'dsp': block['dsp'], 'id': block['id'], 'key': key, 'phase': value['phase']}
        if key == '@enabled':
            return {**command, 'value': bool(new)} if model.get('bypass') and isinstance(new, bool) else None
        if key == 'Index' and block.get('model') in NAM_ENGINES:
            return None                                                          # a capture is chosen from the list
        for p in model['params']:
            sync = p.get('sync') or {}
            if key == sync.get('switch'):
                return {**command, 'value': bool(new)} if isinstance(new, bool) else None
            if key == sync.get('note'):
                notes = self.catalog()['controls'].get('sync_note', {}).get('format') or []
                low = sync.get('min', 1)
                if isinstance(new, bool) or not isinstance(new, (int, float)) or not notes:
                    return None
                return {**command, 'value': int(min(max(round(new), low), low + len(notes) - 1))}
            if key != p['id']:
                continue
            low, high = p.get('min'), p.get('max')
            if isinstance(low, bool) or isinstance(high, bool):                  # a switch
                return {**command, 'value': bool(new)} if isinstance(new, bool) else None
            if isinstance(new, bool) or not isinstance(new, (int, float)) or new != new:
                return None
            if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
                return None
            new = min(max(new, low), high)
            return {**command, 'value': int(round(new)) if p.get('whole') else float(new)}
        return None

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

    def _show_dsp(self):
        if self.page_ready and self.dsp is not None:
            self._write('P', {'type': 'dsp', 'dsp': self.dsp})

    def _show_look(self):
        if self.page_ready and self.look is not None:
            self._write('P', {'type': 'look', 'look': self.look})

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
            self.state = self.with_pictures(value)
            self._show_state()
        elif kind == 'dsp':
            self.dsp = value
            self._show_dsp()
        elif kind == 'look':
            self.look = value
            self._show_look()
        elif kind == 'load':
            if self.on and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127:
                self._act('load', value)
        elif kind == 'notice':
            if self.on and self.page_ready:
                self._write('P', {'type': 'notice', 'text': value})
        elif kind == 'pane':
            event = value.get('type')
            if event == 'ready':                       # the page has loaded: what it draws with, then what to draw
                self.page_ready = True
                self._write('P', {'type': 'catalog', 'catalog': self.catalog()})
                self._show_look()
                self._place()
                self._show_state()
                self._show_dsp()
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
