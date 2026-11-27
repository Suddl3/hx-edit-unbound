"""Start the local HX Edit Unbound build and service the IR import converter."""

import argparse
import ctypes
from datetime import datetime
import json
import os
import re
from pathlib import Path
import tempfile
from threading import Event, Thread, Timer
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


def startup_line(firmware, library, primed, problem=None):
    """The one "startup" line of trace.log, so a launch that went wrong can be told apart afterwards: the Floor firmware
    for this launch (floor_firmware.detect) and where it came from (floor, remembered, configured or assumed), the
    library folder and how many captures it lists, the library index's result (floor_inventory.prime_library: indexed,
    how many refused, the first reason, timed out) and the library's trouble, if any (workbench.library_problem's kind).
    No capture names."""
    import floor_firmware
    line = {'type': 'startup', 'firmware': None, 'firmwareSource': None, 'library': None, 'entries': None,
            'primed': None, 'libraryProblem': None}
    if firmware is not None:
        line['firmware'] = firmware.describe()
        line['firmwareSource'] = floor_firmware.origin(firmware)
    try:
        line['library'] = str(library.folder)
        line['entries'] = len(library.entries())
    except Exception as error:                  # (said, not raised: this line never stops a launch)
        line['libraryError'] = str(error)[:200]
    if isinstance(primed, dict):
        refused = [item for item in primed.get('unsupported') or () if isinstance(item, dict)]
        line['primed'] = {'indexed': primed.get('indexed'), 'unsupported': len(refused),
                          'firstReason': str(refused[0].get('reason'))[:200] if refused else None,
                          'timedOut': bool(primed.get('timedOut'))}
    if isinstance(problem, dict):
        line['libraryProblem'] = problem.get('kind')
    return line


def remembered_captures(memory):
    """How many of the Floor's slots floor-memory.json last saw holding a capture (its content known), or 0."""
    try:
        return sum(1 for _, _, content in memory.slots() if content)
    except Exception:
        return 0


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
    primed = None               # the library index's result (prime_library), for the startup line and the Workbench
    if navigation:
        from floor_inventory import prime_library
        from navigation_host import NavigationHost
        from nam_sidebar import prepare_sidebar
        from uuid import uuid4
        # Fail before an editor/device session starts if its library presentation
        # cannot be built. Packaged builds include the matching compiled helper.
        prepare_sidebar()
        # Offline conversion precedes spawning HX Edit, never its native event callback.
        primed = prime_library(library, CONVERTER, Path(workspace) / 'library-index', timeout=120)
    # What this launch found, said rather than swallowed (v0.7.2): one "startup" line in trace.log; the Workbench says
    # when the library cannot be used (workbench.library_problem: not "No captures yet") and when the Floor did not say
    # which firmware it runs (workbench.firmware_notice). None of it ever stops a launch.
    firmware_note = None
    remembered = 0
    def library_trouble():
        try:
            from workbench import library_problem
            return library_problem(library, primed, remembered_captures(memory) if memory is not None else remembered)
        except Exception as error:
            trace({'type': 'startup', 'event': 'library-check-failed', 'error': str(error)[:200]})
            return None
    memory = None
    if floor_reference:
        try:
            from floor_memory import FloorMemory
            from workbench import firmware_notice
            remembered = remembered_captures(FloorMemory(library.folder))
            firmware_note = firmware_notice(FLOOR_SEEN, floor_firmware.asking(nam_catalog.load_settings()))
        except Exception as error:
            trace({'type': 'startup', 'event': 'firmware-check-failed', 'error': str(error)[:200]})
        try:
            trace(startup_line(FLOOR_SEEN, library, primed, library_trouble()))
        except Exception as error:
            print(f'Could not write the startup line: {error}')
    host = None
    preview = None
    sidebar = None
    meter = None
    focus = None
    workbench = None
    frame = None
    after_resume = []           # what runs once HX Edit is running (the Workbench, when it was left on)
    if navigation:
        # Classic's "Chain pictures" (Reveal B12): HX Edit's own model pictures unless "3D gear" was chosen, put in place
        # before HX Edit reads them (both sets are kept in the copy: nam_catalog.patch_model_art); the trial build's
        # launch comes here without main()
        try:
            nam_catalog.choose_model_art(exe.parent / 'res', nam_catalog.load_settings().get('chainModelArt') is True)
        except OSError as error:
            print(f'Chain pictures not changed: {error}')
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
            # (and the names this editor gave its own previews in User IR 128: a leftover of ours is replaced without
            # asking, anything else is asked about first; Batch 3)
            options.update(leftoverPreview=memory.preview(), rememberedSlots=memory.slots(), ownPreviews=list(memory.previews()),
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
            # HX Unbound options, as a first launch has them: HX Edit's own icons in Classic's chain (Reveal B12: Classic
            # feels like stock; "3D gear" is the other choice), large, with block names, no glow. A choice made in the
            # menu is kept in settings.json and wins from then on.
            options.update(chainArt=nam_catalog.load_settings().get('chainModelArt') is True,
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
                    import dsp_costs
                    # (the DSP costs it measured are dropped when the Floor answers with another firmware)
                    workbench = WorkbenchView(exe.parent / 'res', settings=nam_catalog.load_settings(), trace=trace,
                                              firmware=dsp_costs.firmware_of(FLOOR_SEEN))
                    workbench_start = setting_on(nam_catalog.load_settings())
                except Exception as error:
                    workbench = None
                    trace({'type': 'workbench', 'event': 'unavailable', 'error': str(error)})
            # Read-only research probes: only in a copy prepared with this marker file.
            options.update(namProbe=(exe.parent / 'res' / 'nam-probe.flag').is_file())
            before = '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in
                ('library_slot_state.js', 'automatic_slot_discovery.js', 'native_export_observer.js',
                 'nav_banner.js', 'target_binding.js', 'nam_sidebar.js', 'dsp_meter.js', 'window_keep.js', 'menu_row.js', 'menu_dark.js',
                 'setlists.js', 'focus_view.js')) + '\n'
            config = dict(request=uuid4().hex, repeat=True, automatic=True, requireHostMonitor=True)
            # Validate original native bytes before namView attaches to shared
            # entry points. The callback runs only after toneView exists and the
            # suspended editor resumes; installing it does not open the browser.
            initialize = ('\nconst navigationBanner = installNavigationBanner({openBrowser: (window, options) => toneView.openBrowser(window, options)});\n'
                          # The DSP meter is optional: a failed byte guard leaves the editor as it was.
                          "try { installDspMeter(); } catch (error) { send({type: 'dspMeter', event: 'unavailable', error: String(error.message)}); }\n"
                          # A reconnect leaves the window as the user has it (maximized stays maximized).
                          # (with a pane layout saved, HX Edit's own screen stays covered until the pane's page is up, J4)
                          f"try {{ installWindowKeeper({json.dumps({'cover': bool(workbench_start)})}); }} catch (error) {{ send({{type: 'windowKeeper', event: 'unavailable', error: String(error.message)}}); }}\n"
                          # HX Edit's menu row may be taken off its window only while this stands in for it (window_frame.py).
                          "try { installMenuRow(); } catch (error) { send({type: 'menuRow', event: 'unavailable', error: String(error.message)}); }\n"
                          # HX Edit's menu row drawn dark while a pane covers its screen (window_frame.py says when).
                          "try { installMenuDark(); } catch (error) { send({type: 'menuDark', event: 'unavailable', error: String(error.message)}); }\n")
            after = (f'\nconnectNativeExportLibrary({json.dumps(config)}, namView);'
                     '\nnamView.setLibraryOpener(window => toneView.openBrowser(window, {library:true, dockPanel:navigationBanner.dockPanel()}));'
                     '\ninstallNamSidebar(namView);'
                     # The Workbench's setlists (setlists.js): optional; a failed byte guard leaves them out.
                     "\nlet setlists = null; try { setlists = installSetlists(); } catch (error) { send({type: 'toneTrace', reason: 'setlists', stage: 'unavailable', error: String(error.message)}); }"
                     # Focus Mode is optional: a failed byte guard leaves the editor as it was.
                     f"\ntry {{ installFocusView({json.dumps(focus_options)}, {{targetBinding, namView, toneView, setlists}}); }}"
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
                elif name == 'checkSlots':
                    # Every permanent slot read back, ignoring what this PC remembers (nam_view checkAllSlots, R8).
                    if not detached.is_set():
                        script.post({'type': 'checkSlots', 'payload': {}})
                elif name == 'realNames':
                    # The catalog is renamed when the copy is prepared, so the choice applies from the next launch.
                    on = not nam_catalog.real_names_on()
                    nam_catalog.save_setting(nam_catalog.REAL_NAMES_KEY, on)
                    meter.set_real_names(on)
                    if workbench is not None:
                        workbench.show_options(menu_options())
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
                elif name.startswith('layout:'):
                    # Classic's chooser (Reveal B12): that layout, kept as the page's own chooser keeps it, and shown
                    from workbench import LAYOUT as LAYOUT_KEY, checked_layout as layout_choice
                    choice = layout_choice(name.split(':', 1)[1])
                    if choice:
                        nam_catalog.save_setting(LAYOUT_KEY, choice)
                        workbench_mode(True)
                        if workbench is not None:
                            workbench.show_options(menu_options())
                elif name in ('chainIcons', 'chainGear') and (name == 'chainGear') != chain_art[0]:
                    unbound_choice('chainArt')           # (the pair: one of the two, the same switch as the option)
                elif name == 'chainArt':
                    on = not chain_art[0]
                    chain_art[0] = on
                    nam_catalog.save_setting('chainModelArt', on)
                    try:                                 # (HX Edit's block list follows at the next launch; the chain at once)
                        nam_catalog.choose_model_art(exe.parent / 'res', on)
                    except OSError as error:
                        trace({'type': 'chainArt', 'event': 'pictures-failed', 'error': str(error)})
                    meter.set_chain_art(on)
                    if not detached.is_set():
                        script.post({'type': 'chainArt', 'payload': {'on': on}})
            # Focus Mode, on or off: the pane, the script that reads the blocks for it, and the menu's tick.
            # It starts off with every launch, and the page's own "Editor" button turns it off the same way.
            focus_on = [False]
            focus_seen = [False]        # Focus Mode shown at least once this launch (the TONE3000 open says so, S1)
            focus_missing = [False]     # its script did not install (a byte guard): the menu item says so
            # The Workbench, on or off (settings.json "workbench", kept from one launch to the next). It is shown while
            # it is on and Focus Mode is not: Focus Mode's "Editor" button comes back to it, and the two panes never
            # stand over each other. HX Edit's own toolbar items (the meter, the Unbound button) step aside for either.
            workbench_on = [False]
            # HX Edit's window frame while either pane covers its screen (window_frame.py): a dark title bar. Its menu
            # row stays unless settings.json "workbenchMenuBar" is false (the Workbench's menu has the switch). With
            # the row away HX Edit's window comes back one row taller at the next launch: the frame keeps the
            # window's size (settings.json "hxWindowSize") and gives it its height back.
            # The row goes only once menu_row.js said it stands in for it ("menuRow" ready, below): without that HX
            # Edit ignores its own Save. A failure there never stops a pane from showing.
            from window_frame import MENU_BAR, WINDOW_SIZE, WindowFrame
            def menu_bar_kept():
                return nam_catalog.load_settings().get(MENU_BAR) is not False
            def frame_kept(handle):
                if not detached.is_set():
                    script.post({'type': 'menuRow', 'payload': {'kept': handle}})
            def frame_dark(window, on):
                if not detached.is_set():
                    script.post({'type': 'menuDark', 'payload': {'window': int(window) & 0xffffffff, 'on': bool(on)}})
            frame = WindowFrame(trace=trace, on_kept=frame_kept, on_dark=frame_dark,
                                size=nam_catalog.load_settings().get(WINDOW_SIZE),
                                on_size=lambda size: nam_catalog.save_setting(WINDOW_SIZE, size))
            def layout_kept():
                # the Workbench's layout (Batch 4), settings.json "workbenchLayout"; the Workbench when it cannot be read
                try:
                    from workbench import layout_of
                    return layout_of(nam_catalog.load_settings())
                except Exception:
                    return 'workbench'
            def scene_pin_kept():
                # Rig on stage's scene pin (Reveal B11), settings.json "workbenchScenePin"; on when it cannot be read
                try:
                    from workbench import scene_pin_of
                    return scene_pin_of(nam_catalog.load_settings())
                except Exception:
                    return True
            def menu_options():
                # (firmwareNotice: the Floor did not say which firmware it runs this launch; one line on the page until OK)
                return {'level': bool(preview.level), 'menuRow': frame.menu_ok, 'menuBar': menu_bar_kept(), 'layout': layout_kept(),
                        'firmwareNotice': firmware_note, 'realNames': nam_catalog.real_names_on(),
                        'scenePin': scene_pin_kept()}
            def frame_show():
                try:
                    frame.apply(focus_on[0] or workbench_on[0], menu_bar_kept())
                except Exception as error:
                    trace({'type': 'windowFrame', 'event': 'failed', 'error': str(error)})
            def workbench_show():
                shown = workbench_on[0] and not focus_on[0]
                if not shown and preview is not None and preview.bounds_override is not None:
                    preview.place_over(None)             # (a tool over the Workbench goes back over HX Edit's own panel)
                    if workbench is not None:
                        workbench.set_raise(True)
                if workbench is not None:
                    if shown:                            # (the looks may have been changed in Focus Mode meanwhile)
                        workbench.show_look(nam_catalog.load_settings())
                    workbench.set_on(shown)
                meter.set_chain_option('focusMode', focus_on[0] or workbench_on[0])
                frame_show()
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
                if on:
                    focus_seen[0] = True                 # (for the TONE3000 open's trace, S1)
                # (S3: one pane over HX Edit's window all the way through: going back, the Workbench is shown before
                # Focus Mode goes; coming in, the Workbench stays until Focus Mode's page is up: its first use starts
                # its pane, and hiding the Workbench at once showed HX Edit's own screen for a moment)
                if not on:
                    workbench_show()
                if focus is not None:
                    if on:                               # the defaults may have been changed on the Floor look page meanwhile
                        focus.show_look(nam_catalog.load_settings())
                    focus.set_on(on)
                meter.set_chain_option('focusMode', on)
                if notice:
                    meter.receive({'type': 'dspNotice', 'text': notice})
                if not detached.is_set():
                    script.post({'type': 'focusMode', 'payload': {'on': on}})
                if on and focus is not None and not focus.page_ready:
                    def ready_then():                    # (once: the page's ready, or 4 s, whichever comes first)
                        if focus_on[0] and not ready_done[0]:
                            ready_done[0] = True
                            workbench_show()
                    ready_done = [False]
                    focus.on_ready = ready_then
                    Timer(4.0, ready_then).start()
                    trace({'type': 'focusView', 'event': 'waits-for-page'})
                elif on:
                    workbench_show()                     # out of Focus Mode's way
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
            def focus_look_save(view=None):
                view = view or focus                     # the pane that asked (Focus Mode or the Workbench)
                try:
                    import floor_store
                    from floor_memory import FloorMemory
                    path, store = floor_store.write_for(library, FloorMemory(library.folder),
                                                        nam_catalog.load_settings().get('floorLook'))
                except Exception as error:               # no library folder, a picture folder that has gone
                    trace({'type': 'focusView', 'event': 'look-save-failed', 'error': str(error)})
                    view.notice(f'The file for the Floor was not saved. {error}')
                    return
                trace({'type': 'focusView', 'event': 'look-saved', 'slots': len(store['nam']['slots'])})
                view.notice(f"Saved for the Floor: the default backgrounds and {len(store['nam']['slots'])} capture pictures. "
                             "It goes onto the Floor with its next picture update.")
            def pane_request(view, shown, name, value):
                # What either pane asks of HX Edit, each request checked by the pane's driver (focus_view.FocusView)
                # and only while that pane is shown. True when it was one of these.
                if name == 'select' and isinstance(value, dict) and value.get('dsp') in (0, 1) and isinstance(value.get('id'), str):
                    # A block clicked in the pane's chain: HX Edit selects it, and the pane follows.
                    if shown and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': {'action': 'select', 'dsp': value['dsp'], 'id': value['id'][:16]}})
                elif name in ('set', 'snapshot', 'preset', 'model', 'capture', 'add', 'remove', 'move', 'moveSplit', 'route', 'endpoint', 'assign', 'snapValue', 'splitType', 'ir', 'rename', 'setlist'):
                    # A knob, a switch or the bypass (inside the model's own range: view.checked_set), another snapshot,
                    # another preset of the loaded setlist (focus_view.js first closes a drag left open, then asks back:
                    # 'load'), or another model or a capture for the block the pane shows.
                    check = {'set': view.checked_set, 'snapshot': view.checked_snapshot, 'preset': view.checked_preset,
                             'model': view.checked_model, 'capture': view.checked_capture,
                             # the Workbench's changes to the chain: a block added, removed or moved (HX Edit's own entries)
                             'add': view.checked_add, 'remove': view.checked_remove, 'move': view.checked_move,
                             'moveSplit': view.checked_split, 'route': view.checked_route, 'assign': view.checked_assign,
                             'endpoint': view.checked_endpoint,              # (an input's or an output's place, R7)
                             'snapValue': view.checked_snap_value, 'splitType': view.checked_split_type,
                             'ir': view.checked_ir,
                             # the Workbench's name box: a snapshot's name in the edit buffer (one undo step)
                             'rename': view.checked_rename,
                             # the Workbench's setlists: another setlist looked at (HX Edit's list asked for its names)
                             'setlist': view.checked_look}[name]
                    command = check(value) if shown else None
                    if command and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': command})
                elif name in ('undo', 'redo'):
                    # HX Edit's own Undo / Redo (its Edit menu's entries, focus_view.js), as the pane's buttons ask them.
                    if shown and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': {'action': name}})
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
            def workbench_panel(value):
                # The Workbench's lower panel as the page measured it (its own pixels), in HX Edit's window: where a
                # tool's window goes instead of HX Edit's own panel. None when it is not a sensible rectangle.
                pane = workbench.bounds if isinstance(workbench.bounds, dict) else None
                if not pane or not isinstance(value, dict):
                    return None
                found = [value.get(key) for key in ('x', 'y', 'w', 'h')]
                if any(isinstance(n, bool) or not isinstance(n, (int, float)) for n in found):
                    return None
                x, y, w, h = (int(round(n)) for n in found)
                w, h = min(w, int(pane['w']) - x), min(h, int(pane['h']) - y)
                if x < 0 or y < 0 or w < 200 or h < 120:
                    return None
                return {'visible': True, 'x': int(pane['x']) + x, 'y': int(pane['y']) + y, 'w': w, 'h': h}
            def preview_free(then, keep_workbench=False):
                # TonePreview runs one session at a time (HX Edit's script allows one): the one open closes first,
                # as its own Close does, then `then` runs. keep_workbench: the Workbench's own session may stay.
                def wait():
                    alive = preview.thread is not None and preview.thread.is_alive()
                    if alive and not (keep_workbench and preview.workbench):
                        preview.close_window('workbench')
                        deadline = time.monotonic() + 8
                        while preview.thread is not None and preview.thread.is_alive() and time.monotonic() < deadline:
                            time.sleep(.05)
                    then()
                Thread(target=wait, daemon=True).start()
            def workbench_tool_closed():
                preview.on_presentation = None
                workbench.set_raise(True)
                workbench.tool_closed()                      # (the page closes the frame it sat in)
            def workbench_tool_presentation(mode):
                # TONE3000's own Pop out / Dock while it sits in the Workbench: popped out, the Workbench goes back to
                # the chain (the window plays on in its own window; the pane raises itself again, no child window
                # over it); docked, the page opens its view again around it.
                trace({'type': 'workbench', 'event': 'tool-presentation', 'mode': mode})
                workbench.set_raise(mode == 'floating')
                workbench.show_session('presentation', {'mode': mode})
            def workbench_action(name, value):
                if name == 'tool' and isinstance(value, dict) and value.get('name') in ('look', 'level', 'library', 'tone'):
                    # A tool from the Workbench's rail, over its lower panel (the Workbench stays): its window is placed
                    # there (TonePreview.place_over) and the pane stops raising itself above it until it closes.
                    place = workbench_panel(value)
                    trace({'type': 'workbench', 'event': 'tool', 'name': value['name'], 'place': place, 'pane': workbench.bounds})
                    if preview is None or place is None or (value['name'] == 'level' and not preview.level):
                        workbench_mode(False)                    # (as before: the tool opens on HX Edit's own screen)
                        if value['name'] == 'tone':
                            sidebar_action('catalog', '')
                        else:
                            unbound_choice(value['name'])
                        return
                    def open_tool():
                        preview.on_browser_closed = workbench_tool_closed
                        preview.on_presentation = workbench_tool_presentation if value['name'] == 'tone' else None
                        preview.place_over(place)
                        workbench.set_raise(False)
                        if value['name'] == 'tone':
                            # (placed over the Workbench's frame: the script needs no HX Edit pane for it; the layout
                            # and whether Focus Mode was shown go with it, for its trace: S1)
                            sidebar_action('catalog', f"workbench|layout={layout_kept()}|focus={int(focus_seen[0])}")
                        else:
                            unbound_choice(value['name'])
                    if preview.workbench_open():
                        preview_free(open_tool)              # (the Workbench's Levels session closes first)
                    else:
                        open_tool()
                    return
                if name == 'levels' and isinstance(value, dict):
                    # The Workbench's own Levels page (nam_level_flow.LevelFlow in a session without a window,
                    # TonePreview.WorkbenchSession): open, close, or one of the library page's own Level commands,
                    # which the session checks as it checks them from that page.
                    if preview is None or not preview.level or not workbench_on[0] or focus_on[0]:
                        return
                    do, argument = value.get('do'), value.get('arg')
                    page = value.get('page') if value.get('page') in SESSION_PAGES else 'level'
                    if do == 'open':
                        # (one session for either page: the NAM library's Floor actions run in it too)
                        if preview.workbench_open():
                            preview.workbench_action('levelOpen' if page == 'level' else 'library')
                        else:
                            preview_free(lambda: sidebar_action('workbench', page))
                    elif do == 'close':
                        if preview.workbench_open():
                            preview.close_window('workbench')
                    elif do in LEVEL_COMMANDS and (argument is None or (isinstance(argument, str) and len(argument) <= 20000)):
                        preview.workbench_action(do + (':' + argument if argument else ''))
                    elif library is not None and (action := checked_floor(value, library.entries())):
                        preview.workbench_action(action)
                    return
                if name == 'library' and isinstance(value, dict):
                    # The Workbench's NAM library: the library on this PC changed here (workbench.checked_library):
                    # a capture's kind, instrument or picture, an uploaded picture deleted, a capture removed, its
                    # TONE3000 page opened. Nothing touches the Floor.
                    if library is None or not workbench_on[0] or focus_on[0]:
                        return
                    if value.get('do') == 'view':
                        workbench.show_library(library_view(library, library_trouble()))
                        return
                    edit = checked_library(value, library.entries())
                    if edit is None:
                        return
                    do, identity, choice = edit
                    try:
                        if do == 'gear':
                            library.update(identity, gear=choice)
                        elif do == 'instrument':
                            library.set_instrument(identity, choice or None)
                        elif do == 'icon':
                            library.set_icon(identity, choice)
                        elif do == 'iconDelete':
                            library.remove_picture(choice)
                        elif do == 'remove':
                            library.remove(identity)
                        elif do == 'openSource':
                            os.startfile(choice)               # (a TONE3000 page, checked: in the player's browser)
                    except (OSError, ValueError, KeyError) as error:
                        workbench.notice(f'Library: {error}')
                    return
                if name == 'tray' and isinstance(value, dict):
                    # The Workbench's TONE3000 tray: Keep on this PC or Load on Floor for the profile previewing now,
                    # as the window's own card asks it (TonePreview.tone_action checks the shape; browse() the rest),
                    # or Stop preview (the window's own End preview).
                    trial, slot = value.get('trial'), value.get('slot')
                    if preview is not None and value.get('do') == 'end':
                        preview.tone_action('end')
                    elif preview is not None and value.get('do') in ('preview', 'retry', 'source'):
                        # the tray's Preview (the tone picked, again), Try again, View on TONE3000 (the bar's, U1)
                        preview.tone_action({'preview': 'auditionSelected', 'retry': 'retry', 'source': 'source'}[value['do']])
                    elif (preview is not None and value.get('do') == 'replace' and isinstance(value.get('slot'), int)
                          and not isinstance(value.get('slot'), bool) and 1 <= value['slot'] <= 128):
                        preview.tone_action(f"replace:{value['slot']}")                   # every slot taken: this one
                    elif (preview is not None and value.get('do') == 'profile' and isinstance(value.get('id'), int)
                          and not isinstance(value.get('id'), bool) and 0 < value['id'] < 10 ** 12):
                        preview.tone_action(f"model:{value['id']}")                       # the card's Profile list
                    elif (preview is not None and value.get('do') == 'target' and value.get('dsp') in (0, 1)
                          and not isinstance(value.get('dsp'), bool) and isinstance(value.get('id'), str)
                          and re.fullmatch(r'block\d{1,2}', value['id'])):
                        preview.tone_action(f"target:{value['dsp']}:{value['id']}")   # the tray's "Which block?"
                    elif preview is not None and isinstance(trial, int) and not isinstance(trial, bool):
                        if value.get('do') == 'keep':
                            preview.tone_action(f'keep:{trial}')
                        elif value.get('do') == 'save' and isinstance(slot, int) and not isinstance(slot, bool) and 1 <= slot <= 127:
                            preview.tone_action(f'save:{trial}:{slot}')
                    return
                if name == 'notice':
                    workbench.notice(value if isinstance(value, str) else '')   # (the pane's own word: a file it could not read)
                    return
                if name == 'chosen':
                    # The pane's own Windows dialog (focus_view.cs Choose; the page cannot send this): .nam files or a
                    # folder to import, a picture (made 256 px PNG by the pane), a folder to export a capture to.
                    if library is None:
                        return
                    chosen = checked_chosen(value, library.entries(), tempfile.gettempdir())
                    if chosen is None:
                        return
                    kind, identity, paths = chosen
                    def run_chosen():
                        try:
                            if kind in ('nam', 'namFolder'):
                                from tone_preview import import_summary
                                workbench.notice(import_summary(import_files(library, paths)))
                            elif kind == 'picture':
                                library.set_icon(identity, library.add_picture(paths[0].read_bytes()))
                                paths[0].unlink(missing_ok=True)
                            elif kind == 'export':
                                workbench.notice(f'Exported to {library.export(identity, paths[0])}')
                        except (OSError, ValueError, KeyError) as error:
                            workbench.notice(f'Library: {error}')
                    Thread(target=run_chosen, daemon=True).start()
                    return
                if name == 'prefs':
                    # The Workbench's own choices that outlive the page (the Levels page's target, metric, offsets):
                    # kept in settings.json, checked by workbench.prefs_after, never in the page.
                    prefs = prefs_after(nam_catalog.load_settings(), value)
                    if prefs is not None:
                        nam_catalog.save_setting(PREFS, prefs)
                        workbench.show_prefs(prefs)
                    return
                if name == 'clear':
                    # The Workbench's Floor slots: Clear, asked of the player on the page first (what is taken off, that
                    # Undo does not bring it back). workbench.checked_clear: only slots shown in use, none the loaded
                    # preset uses; focus_view.js clears them as HX Edit's own Clear does, and checks that again.
                    command = workbench.checked_clear(value) if workbench_on[0] and not focus_on[0] else None
                    if command and not detached.is_set():
                        script.post({'type': 'focusCommand', 'payload': command})
                    return
                if name == 'pin':
                    # A preset pinned or unpinned on the Presets view: kept in settings.json, never in the page.
                    pins = pins_after(nam_catalog.load_settings(), value)
                    if pins is not None:
                        nam_catalog.save_setting(PINS, pins)
                        workbench.show_pins(pins)
                    return
                if name == 'look':
                    # The Workbench's Floor look: the same looks and checks as Focus Mode's Change look (focus_view
                    # .look_change): a default (floorLook.assign, what the Floor shows) or this preset's own.
                    if workbench_on[0] and not focus_on[0]:
                        changed = workbench.changed_look(value, nam_catalog.load_settings())
                        for key, kept in changed.items():
                            nam_catalog.save_setting(key, kept)
                        if changed:
                            workbench.show_look(nam_catalog.load_settings())
                    return
                if name == 'lookSave':
                    # "Save for the Floor": the file the Floor's picture tool reads, as Focus Mode's and the old page's Save.
                    if workbench_on[0] and not focus_on[0]:
                        Thread(target=focus_look_save, args=(workbench,), daemon=True).start()
                    return
                if name == 'toolClose':
                    # The Workbench closed the frame a tool sat in (Close, Back to the chain, Esc, another tool's
                    # place): its window closes as its own Close does. (why: the view gave up waiting for it, R1)
                    if isinstance(value, dict) and value.get('why') == 'tone-not-open':
                        trace({'type': 'workbench', 'event': 'tool-not-open', 'name': 'tone'})
                    if preview is not None and preview.bounds_override is not None:
                        preview.close_window('workbench')
                    return
                if name == 'toolDock':
                    # The Workbench's TONE3000 button while its window is popped out: back into the view's frame.
                    place = workbench_panel(value)
                    if place is not None and preview is not None and preview.bounds_override is not None:
                        preview.place_over(place)
                        if preview.dock_tool():
                            workbench.set_raise(False)
                    return
                if name == 'toolFront':
                    # The chain's banner "Back to TONE3000" while the window is popped out: it comes forward.
                    if preview is not None:
                        preview.front_tool()
                    return
                if name == 'toolPlace':
                    # The Workbench was resized while a tool sits over its lower panel: the tool follows. hide: one of
                    # the page's top-bar menus is open over it (a window cannot be drawn under the page's menus, U5).
                    place = workbench_panel(value)
                    if place is not None and isinstance(value, dict) and value.get('hide') is True:
                        place = dict(place, visible=False)
                    if place is not None and preview is not None and preview.bounds_override is not None:
                        preview.place_over(place)
                    return
                if name == 'menuBar':
                    # The menu's "Show HX Edit's menu bar": kept in settings.json, the frame follows at once.
                    if isinstance(value, bool):
                        nam_catalog.save_setting(MENU_BAR, value)
                        frame_show()
                        workbench.show_options(menu_options())
                    return
                if name == 'layout':
                    # The logo menu's layout chooser (Batch 4): the page switches at once, the choice is kept in
                    # settings.json for the next launch (workbench.checked_layout). Classic is "menu" "classic" below.
                    choice = checked_layout(value)
                    if choice:
                        nam_catalog.save_setting(LAYOUT, choice)
                        workbench.show_options(menu_options())
                    return
                if name == 'scenePin':
                    # Rig on stage's pin (Reveal B11): one scene for the preset, or the picked block's; kept in settings.json
                    choice = checked_scene_pin(value)
                    if choice is not None:
                        nam_catalog.save_setting(SCENE_PIN, choice)
                        workbench.show_options(menu_options())
                    return
                if name == 'menu':
                    # The page's Editor | Focus switch and its Unbound menu. The tools are panels of HX Edit's own
                    # screen, which the pane would cover: the Workbench steps aside for them.
                    choice = workbench.checked_menu(value)
                    if choice == 'classic':
                        workbench_mode(False)
                    elif choice == 'focus':
                        focus_mode(True)
                    elif choice == 'checkSlots':         # (not a panel: the Workbench stays)
                        unbound_choice(choice)
                    elif choice == 'realNames':          # (a setting: the Workbench stays)
                        unbound_choice(choice)
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
                workbench.show_options(menu_options())
                from workbench import (LAYOUT, SCENE_PIN, checked_scene_pin, LEVEL_COMMANDS, PINS, PREFS, SESSION_PAGES, checked_chosen, checked_floor, checked_layout, checked_library, import_files,
                                       library_view, pinned, pins_after, prefs, prefs_after, previews_view, usage_view)
                workbench.show_pins(pinned(nam_catalog.load_settings()))
                workbench.show_prefs(prefs(nam_catalog.load_settings()))
                if memory is not None:
                    workbench.show_usage(usage_view(memory.presets()))
                    workbench.show_previews(previews_view(memory.previews(), memory.preview()))
                if preview is not None:
                    # the Workbench's own session (Levels): what it shows goes to the page; it says when it ends
                    preview.workbench_sink = workbench.show_session
                    preview.on_workbench_closed = lambda: workbench.show_session('closed', {})
                if library is not None:
                    # the NAM library for the Workbench's own view: now, and again whenever it changes
                    def library_changed():
                        try:
                            # (with what keeps it from being used, said in place of "No captures yet")
                            workbench.show_library(library_view(library, library_trouble()))
                        except (OSError, ValueError) as error:
                            trace({'type': 'workbench', 'event': 'library-view-failed', 'error': str(error)})
                    library.subscribe(library_changed)
                    library_changed()
                workbench.show_look(nam_catalog.load_settings())
                if workbench_start:
                    # (the start-up cover, J4: HX Edit's window comes back once the Workbench's page is up, at most
                    # 8 s here; the script's own limit is 10 s)
                    covered = [True]
                    def uncover(why):
                        if covered[0] and not detached.is_set():
                            covered[0] = False
                            trace({'type': 'windowKeeper', 'event': 'cover-release', 'why': why, 'layout': layout_kept()})
                            script.post({'type': 'startCover', 'payload': {'on': False, 'why': why}})
                    # (the pane's own dark window first, J4: its page does not load while the cover is over it)
                    workbench.on_shown = lambda: uncover('pane-shown')
                    workbench.on_ready = lambda: uncover('page-ready')
                    after_resume.append(lambda: workbench_mode(True, keep=False))
                    after_resume.append(lambda: Timer(8.0, lambda: uncover('launcher-timeout')).start())
            ir_dots = [options.get('irDots') is not False]
            chain_art = [options.get('chainArt') is True]
            chain_options = {'chainLarge': options.get('chainLarge') is True, 'chainNames': options.get('chainNames') is not False,
                             'chainGlow': options.get('chainGlow') is True}
            meter = DspMeter(trace=trace, on_choice=unbound_choice, icons=exe.parent / 'res' / 'icons_models')
            meter.set_ir_dots(ir_dots[0])
            meter.set_chain_art(chain_art[0])
            meter.set_real_names(nam_catalog.real_names_on())
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
                # (the Workbench's Floor slots: which presets use each slot, and our own previews in 128, as they change)
                if workbench is not None and payload.get('type') == 'presetUsage':
                    workbench.show_usage(usage_view(memory.presets()))
                if workbench is not None and payload.get('type') in ('previewOwned', 'tonePreviewState'):
                    workbench.show_previews(previews_view(memory.previews(), memory.preview()))
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
            if frame is not None and payload.get('type') == 'menuRow' and payload.get('event') in ('ready', 'unavailable'):
                # menu_row.js is in place (or its byte guard failed): only then may HX Edit's menu row be taken off
                frame.allow_menu(payload.get('event') == 'ready')
                frame_show()
                if workbench is not None:
                    workbench.show_options(menu_options())
            if frame is not None and payload.get('type') == 'focusBounds':
                # (HX Edit's window, as its script reports it with the pane's place: the frame follows what is shown)
                frame.set_window(payload.get('window'))
                frame_show()
            if host:
                host.receive(payload)
                if payload.get('type') == 'floorInventory':
                    preview.inventory_changed()
            if payload.get('type') == 'ready':
                ready.set()
            if payload.get('type') in {'toneTrace', 'navigationBanner', 'automaticSlotStatus', 'floorInventoryPresentation',
                                       'focusBounds',
                                       'dspMeterLayout', 'windowKeeper', 'menuRow', 'menuDark', 'presetUsage', 'pickerSide', 'favoritesRemoved',
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
                try:
                    # (HX Edit still open: its title bar and menu row as it made them, even when a pane's close above
                    # failed; review of PR #7)
                    if frame is not None:
                        frame.restore()
                finally:
                    if preview:
                        preview.close_diagnostics()


def prepared_workspace():
    """Where this launch's HX Edit copy is prepared: a new temporary folder under build/, or with HX_EDIT_COPY_DIR set
    (test launches) that one fixed folder, emptied first. A fixed folder keeps HX Edit's path the same from launch to
    launch, so a screen-control grant (computer use) given for one test launch still holds for the next."""
    fixed = os.environ.get('HX_EDIT_COPY_DIR')
    if not fixed:
        return tempfile.TemporaryDirectory(prefix='nam-', dir=ROOT / 'build', ignore_cleanup_errors=True)
    import contextlib
    import shutil

    @contextlib.contextmanager
    def fixed_folder(path):
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        yield str(path)

    return fixed_folder(Path(fixed).resolve())


def main():
    global FLOOR_SEEN
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
                        help='NAM Amp / Amp + cab / Pedal / Other categories in the block selector and the 3D gear '
                             'pictures (on with --navigation; kept so older commands still run).')
    parser.add_argument('--no-nam-category', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--unbound', action='store_true',
                        help='Everything on for a Floor with HX Unbound firmware: the same as --floor-reference '
                             '--navigation --nam-category (start.ps1 uses it).')
    args = parser.parse_args()
    # One launch with everything on (install check 2026-11-25: the documented --floor-reference --navigation left out
    # the NAM categories and the 3D gear set, so the Workbench showed HX Edit's own icons).
    if args.unbound:
        args.floor_reference = args.navigation = True
    if args.navigation and not args.no_nam_category:
        args.nam_category = True

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
    with prepared_workspace() as workspace:
        floor = None
        if args.floor_reference:
            import floor_firmware
            floor = floor_firmware.profile()
            # Ask the Floor itself (editor command 0x4f); without an answer, a profile set by hand, its last answer,
            # else the basic NAM firmware (floor_firmware.detect). "floorFirmwareAsk": false skips asking.
            # (kept for run_editor: what the Floor runs, where it came from for trace.log, and the Workbench's notice when
            # it did not answer; it was never set before v0.7.2, so run_editor always fell back to the copy's record)
            FLOOR_SEEN = floor = floor_firmware.detect(CONVERTER.parent)
            print(f'Floor firmware: {floor.describe()} ({floor.source})')
        exe = prepare_copy(workspace, scan_error, hx_nam=args.hx_nam, floor=floor)
        if args.navigation:
            from nav_resources import patch_navigation_resources, patch_library_navigation
            patch_navigation_resources(exe.parent)
            patch_library_navigation(exe.parent)
        if args.nam_category:
            from nam_catalog import choose_model_art, load_settings, patch_model_art, patch_nam_category
            patch_nam_category(exe.parent / 'res')
            # "Chain pictures" (Classic's chooser, Reveal B12): HX Edit's own icons unless "3D gear" was chosen
            # (settings.json "chainModelArt": true). HX Edit's block list and grid show the same set: it reads them from
            # its own picture files, so the chosen set goes into this launch's copy (both are kept there,
            # patch_model_art); a choice made while HX Edit runs changes the signal chain at once and the block list at
            # the next start. The Workbench and Focus Mode keep the 3D set either way (icons_models_3d).
            patch_model_art(exe.parent / 'res')
            choose_model_art(exe.parent / 'res', load_settings().get('chainModelArt') is True)
        run_editor(exe, workspace, device, profiles, firmware, floor_reference=args.floor_reference,
                   tone_window=args.tone_window, navigation=args.navigation)


if __name__ == '__main__':
    try:
        main()
    except ModuleNotFoundError as error:
        message(f'{error}\n\nInstall the launcher dependencies with: python -m pip install frida msgpack', 0x10)
    except Exception as error:
        message(error, 0x10)
