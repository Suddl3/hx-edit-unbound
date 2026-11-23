"""Start the local HX Edit Unbound build and service the IR import converter."""

import argparse
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from threading import Event, Thread
import time


ROOT = Path(__file__).resolve().parent
# helix-lt-nam's converter: inside a built package (beside src), else beside the repository folder
FLOOR_SEEN = None   # the Floor's firmware profile for this launch (floor_firmware.detect), set by the launcher
CONVERTER = next((base / 'helix-lt-nam' / 'tools' / 'nam2ir.py' for base in (ROOT.parent, ROOT.parent.parent)
                  if (base / 'helix-lt-nam' / 'tools' / 'nam2ir.py').is_file()),
                 ROOT.parent.parent / 'helix-lt-nam' / 'tools' / 'nam2ir.py')
TITLE = 'HX Edit Unbound'
TRACE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HX Edit NAM' / 'trace.log'


def editor_window():
    """The visible HX Edit main window ("HX Edit - <device>", or "HX Edit Unbound - <device>"), or None.

    Notices from this background process opened behind HX Edit when they had no owner; owned by
    the editor's window they always open in front of it.
    """
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []
    buffer = ctypes.create_unicode_buffer(256)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):     # GW_OWNER: top level
            user32.GetWindowTextW(hwnd, buffer, 256)
            if buffer.value.startswith(('HX Edit - ', 'HX Edit Unbound - ')):   # Unbound: NamLibrary.cs UnboundLook
                found.append(hwnd)
                return False
        return True
    try:
        user32.EnumWindows(visit, 0)
    except OSError:
        return None
    return found[0] if found else None


def message(text, flags):
    # MB_SETFOREGROUND (0x10000): bring the notice forward when this process may.
    return ctypes.windll.user32.MessageBoxW(editor_window(), str(text), TITLE, flags | 0x10000)


def level_di(exe):
    """Where a build says NAM's input file is (res/nam-level.flag), one more place Level looks for it."""
    flag = exe.parent / 'res' / 'nam-level.flag'
    try:
        path = Path(flag.read_text(encoding='utf-8').strip())
    except OSError:
        return None
    return path if path.suffix.lower() == '.wav' and path.is_file() else None


def trace(payload):
    """Append editor diagnostics to TRACE; they hold no capture or preset names."""
    line = json.dumps({'time': datetime.now().isoformat(timespec='seconds'), **payload})
    print(line)
    try:
        TRACE.parent.mkdir(parents=True, exist_ok=True)
        with TRACE.open('a', encoding='utf-8') as log:
            log.write(line + '\n')
    except OSError:
        pass


def ask_firmware():
    """Ask which NAM firmware the unit runs (Enter: the last answer) and keep it in settings.json: it sets
    the NAM blocks of HX Edit's catalog and the import modes. Cancel keeps the last answer."""
    import nam_modes
    from nam_catalog import nam_layers, nam_pedal, save_setting
    current = 'pedal' if nam_pedal() else 'layers' if nam_layers() else 'plain'
    try:
        key = nam_modes.choose_firmware(current)
    except OSError as error:                      # no task dialog: keep the last answer
        print(f'Could not ask for the firmware: {error}')
        return current
    key = key or current
    save_setting('namPedal', key == 'pedal')
    save_setting('namLayers', key in ('pedal', 'layers'))
    return key


def choose_and_train(payload, workspace):
    """The files to convert for an import: as chosen, or with the captures replaced by trained copies
    (the mode chooser, on a firmware with the lighter NAM blocks and an import that asks). None: cancelled."""
    from nam_catalog import nam_layers, nam_pedal
    files = list(payload['files'])
    captures = [f for f in files if f.lower().endswith('.nam')]
    if not (payload.get('ask') and captures and nam_layers()):
        return files
    import nam_modes
    owner = int(payload.get('owner') or 0)
    key = nam_modes.choose_mode([Path(c).stem for c in captures], owner, nam_pedal())
    if key is None:
        return None
    if key == 'original':
        return files
    trained = nam_modes.train(captures, key, workspace, CONVERTER.with_name('nam_refine.py'), owner)
    if trained is None:
        return None
    swap = dict(zip(captures, trained))
    return [swap.get(f, f) for f in files]


def drag_favorite_path():
    """The file a model dragged from the block picker is written to (tone_view dragFavorite)."""
    import tempfile
    folder = Path(tempfile.gettempdir()) / 'HX Edit Unbound'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / 'picker-drag.fav'


def run_editor(exe, workspace, device, profiles, firmware='plain', *, floor_reference=False,
               tone_window='embedded', navigation=False, client_id='', library=None):
    from functools import partial
    import nam_modes
    from nam_catalog import ir_parameters, save_setting, sidebar_width
    from nam_convert import convert_batch, stage_tone_import, validate_import
    from nam_library import Library
    from tone_preview import TonePreview
    from tone_browser import ToneBrowser
    from floor_reference import FLOOR_REFERENCE_OPTIONS
    from floor_capture import validate_floor_capture_files
    import floor_firmware
    import nam_catalog

    # The Floor firmware this copy's catalog was built for (floor_firmware.py): the NAM Pedal block and pedal files.
    # What the Floor itself runs, when the launcher asked it (FLOOR_SEEN, floor_firmware.detect): a NAM Pedal version
    # is offered only when this copy's catalog has the block and the Floor has it too.
    built = floor_firmware.recorded(exe.parent / 'res')
    running = FLOOR_SEEN or built
    floor_pedal = floor_reference and built.pedal and running.pedal
    if navigation and not floor_reference:
        raise ValueError('Navigation requires the Floor reference profile.')
    library = library if library is not None else Library()
    if (exe.parent / 'res' / 'icons_models' / 'NAMCAP_green_screamer.png').is_file():
        library.publish_pictures(exe.parent / 'res' / 'icons_models')   # uploads reach the NAM model lists
    if navigation:
        from floor_inventory import prime_library
        from navigation_host import NavigationHost
        from nam_sidebar import prepare_sidebar
        from uuid import uuid4
        # Fail before an editor/device session starts if its library presentation
        # cannot be built. Packaged builds include the matching compiled helper.
        prepare_sidebar()
        # Offline conversion precedes spawning HX Edit, never its native event callback.
        prime_library(library, CONVERTER, Path(workspace) / 'library-index', timeout=120)
    host = None
    preview = None
    sidebar = None
    meter = None
    memory = None
    focus = None
    workbench = None
    after_resume = []           # what runs once HX Edit is running (the Workbench, when it was left on)
    pid = device.spawn([str(exe)], cwd=str(exe.parent))
    try:
        session = device.attach(pid)
        detached = Event()
        ready = Event()
        errors = []
        session.on('detached', lambda *_: detached.set())
        imports = (ROOT / 'nam_import.js').read_text(encoding='utf-8')
        view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        tone = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        options = dict(FLOOR_REFERENCE_OPTIONS) if floor_reference else {}
        before, initialize, after = '', '', ''
        if navigation:
            options.update(navigation=True, nativeDiscovery=True, payloadMetadata=library.payload_metadata())
            # A preview left on a block by a closed editor, and the slots already read back.
            from floor_memory import FloorMemory
            memory = FloorMemory(library.folder)
            options.update(leftoverPreview=memory.preview(), rememberedSlots=memory.slots(),
                           presetUsage=memory.presets(), pickerSides=memory.sides(),
                           favoriteSlots=memory.favorites(), favoriteLooks=memory.looks())
            # The NAM block category exists in this copy's catalog (nam_catalog.patch_nam_category).
            options.update(namCategory=(exe.parent / 'res' / 'icons_category' / 'FX_HX_Category_NAM_Amp.png').is_file())
            # A NAM block's DSP load as this copy's catalog declares it (for the room check before adding one).
            options.update(namLoad=floor_firmware.recorded(exe.parent / 'res').nam_load,
                           modelLoads=nam_catalog.model_loads(exe.parent / 'res'),
                           # Dragging a model from the block picker: its @type, and where its one-block favorite goes.
                           modelTypes=nam_catalog.model_types(exe.parent / 'res'),
                           dragFavorite=str(drag_favorite_path()))
            # HX Unbound menu: "Mark NAM slots in the IR list" (on unless turned off).
            options.update(irDots=nam_catalog.load_settings().get('irNamDots') is not False)
            # HX Unbound options, as a first launch has them: 3D pictures on, large, with block names, no glow. A choice
            # made in the menu is kept in settings.json and wins from then on.
            options.update(chainArt=nam_catalog.load_settings().get('chainModelArt') is not False,
                           chainArtFiles=nam_catalog.chain_art_files(exe.parent / 'res'),
                           # HX Unbound menu: "Large pictures in the signal chain" (off unless turned on).
                           chainLarge=nam_catalog.load_settings().get('chainLarge') is not False,
                           # HX Unbound menu: "Block names under large pictures" (on unless turned off).
                           chainNames=nam_catalog.load_settings().get('chainNames') is not False,
                           # HX Unbound options: "Glow behind them" (off unless turned on).
                           chainGlow=nam_catalog.load_settings().get('chainGlow') is True)
            # HX Unbound menu: "Focus Mode" (focus_view.py). What its script reads for each model comes from this
            # copy's own model files; without them the editor starts as usual and the menu item says so.
            focus_options = {}
            try:
                from focus_view import FocusView
                focus = FocusView(exe.parent / 'res', settings=nam_catalog.load_settings(), trace=trace)
                focus_options = focus.frida_options()
                # Research only (a copy prepared with this marker file): HX Edit's own chain changes go to the trace.
                focus_options['chainProbe'] = (exe.parent / 'res' / 'chain-probe.flag').is_file()
            except Exception as error:
                focus = None
                trace({'type': 'focusView', 'event': 'unavailable', 'error': str(error)})
            # The Workbench (workbench.py): a modern view of the regular editor in the same kind of pane, reading and
            # writing through Focus Mode's script and checks; without Focus Mode it is not offered.
            workbench_start = False
            if focus is not None:
                try:
                    from workbench import WorkbenchView, setting_on
                    workbench = WorkbenchView(exe.parent / 'res', settings=nam_catalog.load_settings(), trace=trace)
                    workbench_start = setting_on(nam_catalog.load_settings())
                except Exception as error:
                    workbench = None
                    trace({'type': 'workbench', 'event': 'unavailable', 'error': str(error)})
            # Read-only research probes: only in a copy prepared with this marker file.
            options.update(namProbe=(exe.parent / 'res' / 'nam-probe.flag').is_file())
            before = '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in
                ('library_slot_state.js', 'automatic_slot_discovery.js', 'native_export_observer.js',
                 'nav_banner.js', 'target_binding.js', 'nam_sidebar.js', 'dsp_meter.js', 'window_keep.js',
                 'focus_view.js')) + '\n'
            config = dict(request=uuid4().hex, repeat=True, automatic=True, requireHostMonitor=True)
            # Validate original native bytes before namView attaches to shared
            # entry points. The callback runs only after toneView exists and the
            # suspended editor resumes; installing it does not open the browser.
            initialize = ('\nconst navigationBanner = installNavigationBanner({openBrowser: (window, options) => toneView.openBrowser(window, options)});\n'
                          # The DSP meter is optional: a failed byte guard leaves the editor as it was.
                          "try { installDspMeter(); } catch (error) { send({type: 'dspMeter', event: 'unavailable', error: String(error.message)}); }\n"
                          # A reconnect leaves the window as the user has it (maximized stays maximized).
                          "try { installWindowKeeper(); } catch (error) { send({type: 'windowKeeper', event: 'unavailable', error: String(error.message)}); }\n")
            after = (f'\nconnectNativeExportLibrary({json.dumps(config)}, namView);'
                     '\nnamView.setLibraryOpener(window => toneView.openBrowser(window, {library:true, dockPanel:navigationBanner.dockPanel()}));'
                     '\ninstallNamSidebar(namView);'
                     # Focus Mode is optional: a failed byte guard leaves the editor as it was.
                     f"\ntry {{ installFocusView({json.dumps(focus_options)}, {{targetBinding, namView, toneView}}); }}"
                     " catch (error) { send({type: 'toneTrace', reason: 'focus-view', stage: 'unavailable', error: String(error.message)}); }")
        script = session.create_script(
            f"{before}{view}\n{imports}\n{tone}\n{initialize}const namView = installNamView({json.dumps(profiles)}, {sidebar_width()}, {json.dumps(ir_parameters(exe.parent / 'res'))}, {json.dumps(options)});"
            f"\nconst targetBinding = {'installTargetBinding()' if navigation else 'null'};"
            f"\nconst toneView = installToneView({json.dumps(nam_modes.tiles(firmware))}, {json.dumps(options)}, targetBinding);{after}\nsend({{ type: 'ready' }});"
        )
        if navigation:
            host = NavigationHost(script, workspace, library, detached)
        preview = TonePreview(script, workspace, CONVERTER, detached, message, library=library,
                              client_id=client_id, browser_factory=partial(ToneBrowser, mode=tone_window),
                              payload_callback=(lambda _: host.metadata_changed()) if host else None,
                              trace_callback=trace if navigation else None,
                              optimize=bool(navigation and (exe.parent / 'res' / 'nam-optimize.flag').is_file()),
                              pedal_block=bool(navigation and floor_pedal),
                              nam_load=running.nam_load if floor_reference else 36.0,
                              pedal_load=running.pedal_load if floor_reference else 7.5,
                              level=bool(navigation), level_di=level_di(exe) if navigation else None)
        if navigation:
            from nam_sidebar import NamSidebar
            def sidebar_action(action, identity):
                if not detached.is_set():
                    script.post({'type': 'namSidebarAction', 'payload': {'action': action, 'id': identity}})
            sidebar = NamSidebar(script, library, detached, action_handler=sidebar_action, trace=trace)
            preview.sidebar_status = sidebar.status
            preview.drop_handler = sidebar.drop       # the library window's drag onto the chain
            preview.native_drag_handler = sidebar.native_drag
            from dsp_meter import DspMeter
            # The HX Unbound menu button (beside the TONE3000 button): Level presets (in builds that have
            # them), the Floor look and the NAM library.
            def unbound_choice(name):
                if name == 'level' and preview.level:
                    sidebar_action('level', '')
                elif name == 'look':
                    sidebar_action('look', '')
                elif name == 'library':
                    sidebar_action('expand', '')
                elif name == 'irDots':
                    on = not ir_dots[0]
                    ir_dots[0] = on
                    nam_catalog.save_setting('irNamDots', on)
                    meter.set_ir_dots(on)
                    if not detached.is_set():
                        script.post({'type': 'irDots', 'payload': {'on': on}})
                elif name in ('chainLarge', 'chainNames', 'chainGlow'):
                    on = not chain_options[name]
                    chain_options[name] = on
                    nam_catalog.save_setting(name, on)
                    meter.set_chain_option(name, on)
                    if not detached.is_set():
                        script.post({'type': 'chainOption', 'payload': {'name': name, 'on': on}})
                elif name == 'focusMode':
                    focus_mode(not focus_on[0])
                elif name == 'workbench':
                    workbench_mode(True)
                elif name == 'chainArt':
                    on = not chain_art[0]
                    chain_art[0] = on
                    nam_catalog.save_setting('chainModelArt', on)
                    meter.set_chain_art(on)
                    if not detached.is_set():
                        script.post({'type': 'chainArt', 'payload': {'on': on}})
            # Focus Mode, on or off: the pane, the script that reads the blocks for it, and the menu's tick.
            # It starts off with every launch, and the page's own "Editor" button turns it off the same way.
            focus_on = [False]
            focus_missing = [False]     # its script did not install (a byte guard): the menu item says so
            # The Workbench, on or off (settings.json "workbench", kept from one launch to the next). It is shown while
            # it is on and Focus Mode is not: Focus Mode's "Editor" button comes back to it, and the two panes never
            # stand over each other. HX Edit's own toolbar items (the meter, the Unbound button) step aside for either.
            workbench_on = [False]
            def workbench_show():
                shown = workbench_on[0] and not focus_on[0]
                if workbench is not None:
                    workbench.set_on(shown)
                meter.set_chain_option('focusMode', focus_on[0] or workbench_on[0])
                if not detached.is_set():
                    script.post({'type': 'focusMode', 'payload': {'pane': 'workbench', 'on': shown}})
            def workbench_mode(on, notice=None, keep=True):
                if on and (workbench is None or focus_missing[0]):
                    on, notice = False, 'The Workbench is not available in this copy.'
                workbench_on[0] = on
                if keep:
                    nam_catalog.save_setting('workbench', on)
                workbench_show()
                if notice:
                    meter.receive({'type': 'dspNotice', 'text': notice})
            def focus_mode(on, notice=None):
                if on and (focus is None or focus_missing[0]):
                    on, notice = False, 'Focus Mode is not available in this copy.'
                focus_on[0] = on
                if focus is not None:
                    if on:                               # the defaults may have been changed on the Floor look page meanwhile
                        focus.show_look(nam_catalog.load_settings())
                    focus.set_on(on)
                meter.set_chain_option('focusMode', on)
                if notice:
                    meter.receive({'type': 'dspNotice', 'text': notice})
                if not detached.is_set():
                    script.post({'type': 'focusMode', 'payload': {'on': on}})
                workbench_show()                         # back on the Workbench when it is on, or out of Focus Mode's way
            def focus_load(number, view=None):
                view = view or focus                     # the pane that asked (Focus Mode or the Workbench)
                try:
                    import nam_level
                    nam_level.load_preset(number)
                except Exception as error:               # no MIDI port, or it is busy: said in the pane
                    trace({'type': 'focusView', 'event': 'preset-load-failed', 'number': number, 'error': str(error)})
                    view.notice(f'Preset {number:03d} did not load. {error}')
                    return
                for _ in range(30):                      # HX Edit follows within a moment when the Floor took it
                    time.sleep(.1)
                    preset = (view.state or {}).get('preset') if isinstance(view.state, dict) else None
                    if isinstance(preset, dict) and preset.get('number') == number:
                        return
                if view.on:
                    trace({'type': 'focusView', 'event': 'preset-load-unseen', 'number': number})
                    view.notice(f'The Floor did not load preset {number:03d}. Check MIDI PC Receive in its Global Settings.')
            def focus_look_save():
                try:
                    import floor_store
                    from floor_memory import FloorMemory
                    path, store = floor_store.write_for(library, FloorMemory(library.folder),
                                                        nam_catalog.load_settings().get('floorLook'))
                except Exception as error:               # no library folder, a picture folder that has gone
                    trace({'type': 'focusView', 'event': 'look-save-failed', 'error': str(error)})
                    focus.notice(f'The file for the Floor was not saved. {error}')
                    return
                trace({'type': 'focusView', 'event': 'look-saved', 'slots': len(store['nam']['slots'])})
                focus.notice(f"Saved for the Floor: the default backgrounds and {len(store['nam']['slots'])} capture pictures. "
                             "It goes onto the Floor with its next picture update.")
            def pane_request(view, shown, name, value):
                # What either pane asks of HX Edit, each request checked by the pane's driver (focus_view.FocusView)
                # and only while that pane is shown. True when it was one of these.
                if name == 'select' and isinstance(value, dict) and value.get('dsp') in (0, 1) and isinstance(value.get('id'), str):
                    # A block clicked in the pane's chain: HX Edit selects it, and the pane follows.
                    if shown and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': {'action': 'select', 'dsp': value['dsp'], 'id': value['id'][:16]}})
                elif name in ('set', 'snapshot', 'preset', 'model', 'capture', 'add', 'remove', 'move', 'moveSplit', 'route', 'assign', 'snapValue', 'splitType'):
                    # A knob, a switch or the bypass (inside the model's own range: view.checked_set), another snapshot,
                    # another preset of the loaded setlist (focus_view.js first closes a drag left open, then asks back:
                    # 'load'), or another model or a capture for the block the pane shows.
                    check = {'set': view.checked_set, 'snapshot': view.checked_snapshot, 'preset': view.checked_preset,
                             'model': view.checked_model, 'capture': view.checked_capture,
                             # the Workbench's changes to the chain: a block added, removed or moved (HX Edit's own entries)
                             'add': view.checked_add, 'remove': view.checked_remove, 'move': view.checked_move,
                             'moveSplit': view.checked_split, 'route': view.checked_route, 'assign': view.checked_assign,
                             'snapValue': view.checked_snap_value, 'splitType': view.checked_split_type}[name]
                    command = check(value) if shown else None
                    if command and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': command})
                elif name == 'redo':
                    # HX Edit's own Redo (its Edit menu's entry, focus_view.js 'redo'), as the pane's Redo button asks it.
                    if shown and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': {'action': 'redo'}})
                elif name == 'load':
                    # The preset is loaded as a footswitch or the Level tool loads it (a MIDI Program Change over
                    # USB); HX Edit follows on its own. Nothing is saved; what was not saved in the preset left
                    # behind is lost, as with HX Edit's own preset list.
                    if shown and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127:
                        Thread(target=focus_load, args=(value, view), daemon=True).start()
                else:
                    return False
                return True
            def focus_action(name, value):
                if name == 'exit':
                    focus_mode(False)
                elif name == 'failed':
                    focus_mode(False, 'Focus Mode could not start.')
                elif focus is not None and pane_request(focus, focus_on[0], name, value):
                    pass
                elif name == 'look':
                    # Change look in the pane: a block's or a preset's own look (settings.json presetLooks), or a
                    # default (floorLook.assign, the same one the Floor look page edits). Checked by focus_view.
                    if focus is not None and focus_on[0]:
                        changed = focus.changed_look(value, nam_catalog.load_settings())
                        for key, kept in changed.items():
                            nam_catalog.save_setting(key, kept)
                        if changed:
                            focus.show_look(nam_catalog.load_settings())
                elif name == 'lookSave':
                    # "Save for the Floor": the file the Floor's picture tool reads, as Save on the Floor look page.
                    if focus is not None and focus_on[0]:
                        Thread(target=focus_look_save, daemon=True).start()
            def workbench_action(name, value):
                if name == 'menu':
                    # The page's Editor | Focus switch and its Unbound menu. The tools are panels of HX Edit's own
                    # screen, which the pane would cover: the Workbench steps aside for them.
                    choice = workbench.checked_menu(value)
                    if choice == 'classic':
                        workbench_mode(False)
                    elif choice == 'focus':
                        focus_mode(True)
                    elif choice:
                        workbench_mode(False)
                        unbound_choice(choice)
                elif name == 'failed':
                    workbench_mode(False, 'The Workbench could not start.', keep=False)
                elif name == 'costs':
                    # Each model's DSP as the Floor's meter measured it (workbench.py, dsp_costs.py): focus_view.js
                    # checks room with them in place of HX Edit's estimates. Taken from the driver's own record, not
                    # from the request (the page's own requests come this way too).
                    if not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': {'action': 'costs', 'costs': dict(workbench.costs.costs)}})
                else:
                    pane_request(workbench, workbench_on[0] and not focus_on[0], name, value)
            if focus is not None:
                focus.on_action = focus_action
            if workbench is not None:
                workbench.on_action = workbench_action
                workbench.show_options({'level': bool(preview.level)})
                if workbench_start:
                    after_resume.append(lambda: workbench_mode(True, keep=False))
            ir_dots = [options.get('irDots') is not False]
            chain_art = [options.get('chainArt') is True]
            chain_options = {'chainLarge': options.get('chainLarge') is True, 'chainNames': options.get('chainNames') is not False,
                             'chainGlow': options.get('chainGlow') is True}
            meter = DspMeter(trace=trace, on_choice=unbound_choice, icons=exe.parent / 'res' / 'icons_models')
            meter.set_ir_dots(ir_dots[0])
            meter.set_chain_art(chain_art[0])
            for name, on in chain_options.items():
                meter.set_chain_option(name, on)
            meter.set_chain_option('focusMode', False)

        def on_message(event, _data):
            if event['type'] == 'error':
                errors.append(event.get('description', 'IR import hook failed.'))
                trace({'type': 'nativeScriptError', 'description': errors[-1],
                       'stack': event.get('stack', ''), 'line': event.get('lineNumber')})
                ready.set()
                return
            payload = event.get('payload', {})
            if memory:
                memory.receive(payload)
            if sidebar:
                sidebar.receive(payload)
            if meter:
                meter.receive(payload)
            if focus:
                focus.receive(payload)
            if workbench:
                workbench.receive(payload)
                if payload.get('reason') == 'focus-view' and payload.get('stage') == 'unavailable':
                    focus_missing[0] = True
            if host:
                host.receive(payload)
                if payload.get('type') == 'floorInventory':
                    preview.inventory_changed()
            if payload.get('type') == 'ready':
                ready.set()
            if payload.get('type') in {'toneTrace', 'navigationBanner', 'automaticSlotStatus', 'floorInventoryPresentation',
                                       'focusBounds',
                                       'dspMeterLayout', 'windowKeeper', 'presetUsage', 'pickerSide', 'favoritesRemoved',
                                       'libraryConnectionGuard', 'librarySlotEvidenceResult'}:
                trace(payload)
            if payload.get('type') == 'irExportObservation' and payload.get('stage') in {'invalidated', 'discarded', 'slot-changed'}:
                # Structural diagnostics only: no capture names, paths or tokens.
                trace({'type': 'slotVerificationEvent', 'stage': payload.get('stage'),
                       'reason': payload.get('reason'), 'slot': payload.get('slot')})
            if payload.get('type') == 'floorInventory':
                trace({'type': 'floorInventory', 'epoch': payload.get('epoch'),
                       'state': payload.get('state'), 'verifiedSlots': len(payload.get('entries', []))})
            if payload.get('type') == 'sidebarWidth':
                try:
                    save_setting('sidebarWidth', int(payload['width']))
                except (OSError, TypeError, ValueError, KeyError) as error:
                    print(f'Could not save the sidebar width: {error}')
            if payload.get('type') in {'toneStart', 'toneBounds', 'toneReply', 'toneDismiss', 'toneTarget', 'toneFocus', 'toneAction'}:
                preview.receive(payload)
            if payload.get('type') in {'convert', 'validateImport', 'stageTone'}:
                try:
                    if payload['type'] == 'convert':
                        # The Floor reference has only the original engine. A
                        # different editor's saved LT training preference must
                        # not silently alter this profile's imports.
                        files = list(payload['files']) if floor_reference else choose_and_train(payload, workspace)
                        result = {'cancelled': True} if files is None else \
                            {'files': convert_batch(files, workspace, CONVERTER)}
                        if floor_reference and files is not None:
                            validate_floor_capture_files(result['files'], floor_pedal)
                        for index, file in enumerate(payload['files'] if files is not None else []):
                            if file.lower().endswith('.nam'):
                                try:
                                    identity = library.add(file)
                                    if host:
                                        library.register_payload(identity, result['files'][index])
                                        host.metadata_changed()
                                except (OSError, ValueError) as error:
                                    print(f'Could not add {file} to the NAM library: {error}')
                    elif payload['type'] == 'stageTone':
                        if floor_reference:
                            validate_floor_capture_files([payload['file']], floor_pedal)
                        staged = stage_tone_import(payload['file'], workspace, audition=payload['audition'])
                        result = {'file': str(staged)}
                    else:
                        if floor_reference:
                            validate_floor_capture_files(payload['files'], floor_pedal)
                        imported = validate_import(payload['files'], payload['firstSlot'],
                                                   set(payload['occupied']), payload['namOnly'])
                        result = {'profiles': imported}
                except Exception as error:
                    result = {'error': str(error)}
                if not detached.is_set():
                    script.post({'type': 'converted', 'payload': result})

        script.on('message', on_message)
        script.load()
        if not ready.wait(5) or errors:
            raise RuntimeError(errors[0] if errors else 'HX Edit did not initialize the IR import hook.')
        if host:
            host.start()
        device.resume(pid)
        for step in after_resume:
            step()
        detached.wait()
        if preview.thread:
            preview.thread.join(timeout=2)
    except BaseException:
        try:
            device.kill(pid)
        except Exception:
            pass
        raise
    finally:
        try:
            if host:
                host.close()
        finally:
            try:
                if sidebar:
                    sidebar.close()
                if meter:
                    meter.close()
                if focus:
                    focus.close()
                if workbench:
                    workbench.close()
            finally:
                if preview:
                    preview.close_diagnostics()


def main():
    import frida
    from nam_catalog import prepare_copy
    from nam_inventory import HX_NAM_DEVICES, scan_profiles
    from floor_reference import require_plain_catalog, startup_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lt-nam', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--hx-nam', choices=HX_NAM_DEVICES, help='Confirm the device runs NAM A2 Lite on preset ID 555.')
    parser.add_argument('--floor-reference', action='store_true',
                        help='Original Floor A2 Lite profile: native editor USB only and preview slot 128 reserved.')
    parser.add_argument('--tone-window', choices=('embedded', 'floating'), default='embedded',
                        help='TONE3000 browser presentation; floating leaves the native controls visible.')
    parser.add_argument('--navigation', action='store_true',
                        help='Experimental Floor header browser and verified native slot discovery.')
    parser.add_argument('--nam-category', action='store_true',
                        help='Experimental: NAM Amp / Amp + cab / Pedal / Other categories in the block selector.')
    args = parser.parse_args()

    if args.navigation and not args.floor_reference:
        parser.error('--navigation requires --floor-reference')
    if args.nam_category and not args.navigation:
        parser.error('--nam-category requires --navigation')

    if args.floor_reference:
        from nam_catalog import nam_layers, nam_pedal
        require_plain_catalog(layers=nam_layers(), pedal=nam_pedal())
        if args.hx_nam:
            parser.error('--floor-reference and --hx-nam are mutually exclusive')

    device = frida.get_local_device()
    if any(p.name.lower() in {'hx edit.exe', 'hx edit nam.exe'} for p in device.enumerate_processes()):
        raise RuntimeError('Close the open HX Edit window, then start HX Edit Unbound again.')
    if not CONVERTER.is_file():
        raise FileNotFoundError('Keep the helix-lt-nam checkout next to this editor\'s folder for the built-in converter.')

    profiles, scan_error = startup_profiles(floor_reference=args.floor_reference,
        scan=scan_profiles, converter_directory=CONVERTER.parent, hx_nam=args.hx_nam)

    firmware = 'plain' if args.hx_nam or args.floor_reference else ask_firmware()
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nam-', dir=ROOT / 'build', ignore_cleanup_errors=True) as workspace:
        floor = None
        if args.floor_reference:
            import floor_firmware
            floor = floor_firmware.profile()
            # Ask the Floor itself (editor command 0x4f); without an answer, a profile set by hand, its last answer,
            # else the basic NAM firmware (floor_firmware.detect). "floorFirmwareAsk": false skips asking.
            floor = floor_firmware.detect(CONVERTER.parent)
            print(f'Floor firmware: {floor.describe()} ({floor.source})')
        exe = prepare_copy(workspace, scan_error, hx_nam=args.hx_nam, floor=floor)
        if args.navigation:
            from nav_resources import patch_navigation_resources, patch_library_navigation
            patch_navigation_resources(exe.parent)
            patch_library_navigation(exe.parent)
        if args.nam_category:
            from nam_catalog import load_settings, patch_model_art, patch_nam_category
            patch_nam_category(exe.parent / 'res')
            # "3D pictures of the gear" (on unless turned off): HX Edit's block list and grid show the renders too. HX Edit
            # reads those from its own picture files, so they go into this launch's copy; turning the option on or off
            # changes the signal chain at once and the block list at the next start.
            if load_settings().get('chainModelArt') is not False:
                patch_model_art(exe.parent / 'res')
        run_editor(exe, workspace, device, profiles, firmware, floor_reference=args.floor_reference,
                   tone_window=args.tone_window, navigation=args.navigation)


if __name__ == '__main__':
    try:
        main()
    except ModuleNotFoundError as error:
        message(f'{error}\n\nInstall the launcher dependencies with: python -m pip install frida msgpack', 0x10)
    except Exception as error:
        message(error, 0x10)
