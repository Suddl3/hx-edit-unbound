'use strict';

// Leave HX Edit's window as the user has it when a device reconnects.
//
// HX Edit 3.82 x86 shows its editor window when a device connects: the routine around RVA 0x1a5b20
// calls the framework helper 0x60ccc0(hwnd, show = 1, activate = 1) at 0x1a6039, which runs
// ShowWindow(hwnd, SW_SHOWNORMAL) and then brings the window forward and focuses it. At startup that
// is what first shows the window. On a reconnect (the Floor switched off and on, a cable replugged)
// the window is already on screen, and SW_SHOWNORMAL takes it out of maximized; seen with a Floor
// power cycle, the only top-level window call HX Edit made. So, for that one call site only and only
// while the window is already visible, the helper gets a null window and returns at its own first
// check: no un-maximize, no move, no focus change. Startup and every other caller are untouched.
const windowKeepGuards = Object.freeze({
  '1a6034': '6a016a0153e8826c4600',      // push 1; push 1; push ebx; call 0x60ccc0 (relative)
  '60ccc0': '558bec568b750885f6745b56',  // the helper: hwnd = [ebp+8]; null -> return
});

// Start-up cover (J4, Nick 2026-11-25: "it flashes the classic version before loading the workbench version"): when
// the saved layout is one of the panes (the Workbench, Classic+, Rig on stage), HX Edit's own screen is never seen.
// Its window's first show is this same helper's call at 0x1a6039; just before it a plain dark window of ours (the
// panes' gray, #14161B) is put over it, owned by it (so it stays above it and goes with it), and kept over its client
// area until the launcher says the pane's page is up ("startCover" {on: false}), or 10 s at the latest. HX Edit's own
// window is left as it is: made transparent instead (5bd2592), the pane's WebView2 did not load its page until the
// cover came off, so it always ended on the 8 s timeout (live 2026-11-25 23:46/23:48). Classic saved: no cover.
const START_COVER_MS = 10000;
const START_COVER_GRAY = 0x001b1614;   // 0x00BBGGRR: #14161B, menu_dark's bar
// The window's frame at its first show too (Nick 2026-11-26: the title bar and the menu row were light for 3-4 s): the
// dark title bar and window_frame.py's caption, text and border colours (DWM attributes 20 or 19; 35, 36, 34), and
// menu_dark.js's dark row (menuDarkStart). The launcher's window_frame applies the same again once it has the window.
const START_FRAME = Object.freeze([[35, 0x001B1614], [36, 0x00D6CDC9], [34, 0x00382E2A]]);

function installWindowKeeper(options = {}) {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Window keeper requires HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, hex] of Object.entries(windowKeepGuards)) {
    const bytes = new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(hex.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error(`Window keeper native byte guard failed at ${rva}`);
  }
  const user = Process.getModuleByName('user32.dll');
  const isWindowVisible = new NativeFunction(user.getExportByName('IsWindowVisible'), 'int', ['pointer']);
  const api = (name, result, args) => new NativeFunction(user.getExportByName(name), result, args, 'stdcall');
  let cover = options.cover === true ? {wanted: true} : null;
  // (made only when a cover is wanted: the window class, then the window, on HX Edit's own UI thread)
  function makeCover(owner) {
    const kernel = Process.getModuleByName('kernel32.dll'), gdi = Process.getModuleByName('gdi32.dll');
    const getProc = new NativeFunction(kernel.getExportByName('GetProcAddress'), 'pointer', ['pointer', 'pointer'], 'stdcall');
    const moduleHandle = new NativeFunction(kernel.getExportByName('GetModuleHandleW'), 'pointer', ['pointer'], 'stdcall');
    const brush = new NativeFunction(gdi.getExportByName('CreateSolidBrush'), 'pointer', ['uint'], 'stdcall')(START_COVER_GRAY);
    const instance = moduleHandle(NULL), name = Memory.allocUtf16String('HXUnboundStartCover');
    const klass = Memory.alloc(48);                        // WNDCLASSEXW (x86)
    klass.writeU32(48);
    // (DefWindowProcW is forwarded to ntdll: GetProcAddress gives the function, as menu_dark.js takes it)
    klass.add(8).writePointer(getProc(user.base, Memory.allocAnsiString('DefWindowProcW')));
    klass.add(20).writePointer(instance);
    klass.add(28).writePointer(api('LoadCursorW', 'pointer', ['pointer', 'pointer'])(NULL, ptr(32512)));   // IDC_ARROW
    klass.add(32).writePointer(brush);
    klass.add(40).writePointer(name);
    api('RegisterClassExW', 'uint16', ['pointer'])(klass);   // (0 when already registered: the class is there all the same)
    const rect = Memory.alloc(16);
    api('GetWindowRect', 'int', ['pointer', 'pointer'])(owner, rect);
    const window = api('CreateWindowExW', 'pointer', ['uint', 'pointer', 'pointer', 'uint', 'int', 'int', 'int', 'int',
      'pointer', 'pointer', 'pointer', 'pointer'])(0x08000080, name, NULL, 0x90000000,            // NOACTIVATE|TOOLWINDOW; POPUP|VISIBLE
      rect.readS32(), rect.add(4).readS32(), rect.add(8).readS32() - rect.readS32(), rect.add(12).readS32() - rect.add(4).readS32(),
      owner, NULL, instance, NULL);
    if (window.isNull()) throw new Error('the cover window was not made');
    return {window, keep: [klass, name]};
  }
  // Over the owner's client area (its title bar and menu row stay visible): now, and while it is up (HX Edit may
  // maximize or move after its first show).
  function placeCover() {
    if (!cover || !cover.window) return;
    const client = Memory.alloc(16), corner = Memory.alloc(8);
    if (!api('GetClientRect', 'int', ['pointer', 'pointer'])(cover.owner, client)) return;
    corner.writeS32(0); corner.add(4).writeS32(0);
    api('ClientToScreen', 'int', ['pointer', 'pointer'])(cover.owner, corner);
    api('SetWindowPos', 'int', ['pointer', 'pointer', 'int', 'int', 'int', 'int', 'uint'])(cover.window, NULL,
      corner.readS32(), corner.add(4).readS32(), client.add(8).readS32(), client.add(12).readS32(), 0x0004 | 0x0010 | 0x4000);   // NOZORDER|NOACTIVATE|ASYNC
  }
  function darkFrame(window) {
    const result = {title: false, colours: 0, row: false};
    try {
      const dwm = Process.findModuleByName('dwmapi.dll') || Module.load('dwmapi.dll');
      const attribute = new NativeFunction(dwm.getExportByName('DwmSetWindowAttribute'), 'int', ['pointer', 'uint', 'pointer', 'uint'], 'stdcall');
      const value = Memory.alloc(4);
      value.writeU32(1);
      result.title = attribute(window, 20, value, 4) === 0 || attribute(window, 19, value, 4) === 0;
      for (const [which, colour] of START_FRAME) { value.writeU32(colour); if (attribute(window, which, value, 4) === 0) result.colours++; }
    } catch (_) { /* the frame stays as Windows draws it */ }
    try { if (typeof globalThis.menuDarkStart === 'function') { globalThis.menuDarkStart(window); result.row = true; } } catch (_) { }
    return result;
  }
  function uncover(why) {
    if (!cover || !cover.window) { if (cover) cover.wanted = false; return; }
    const {window, at, follow} = cover;
    cover = null;
    clearInterval(follow);
    try { api('PostMessageW', 'int', ['pointer', 'uint', 'pointer', 'pointer'])(window, 0x10, NULL, NULL); }   // WM_CLOSE: gone on its own thread
    catch (_) { /* the window may be gone */ }
    send({ type: 'windowKeeper', event: 'cover-down', why, ms: Date.now() - at });
  }
  function listenCover() {
    recv('startCover', message => {
      if (message.payload && message.payload.on === false) uncover(String(message.payload.why || 'launcher'));
      if (cover) listenCover();
    });
  }
  if (cover) listenCover();
  const reconnectShow = base.add(0x1a603e);   // return address of the call at 0x1a6039
  const hook = Interceptor.attach(base.add(0x60ccc0), {
    onEnter(args) {
      if (cover && cover.wanted && !cover.window && this.returnAddress.equals(reconnectShow) && !args[0].isNull() &&
          !isWindowVisible(args[0])) {
        // (the window's first show: our dark window goes over it first, until the pane's page is up)
        try {
          const frame = darkFrame(args[0]);                // (the title bar and the menu row dark before the first show)
          const made = makeCover(args[0]);
          Object.assign(cover, {window: made.window, owner: args[0], keep: made.keep, at: Date.now()});
          this.placeCover = true;
          cover.follow = setInterval(placeCover, 150);
          send({ type: 'windowKeeper', event: 'cover-up', frame });
          setTimeout(() => uncover('timeout'), START_COVER_MS);
        } catch (error) {
          cover = null;
          send({ type: 'windowKeeper', event: 'cover-failed', error: String(error.message) });
        }
        return;
      }
      if (!this.returnAddress.equals(reconnectShow) || args[0].isNull() || !isWindowVisible(args[0])) return;
      args[0] = NULL;
      send({ type: 'windowKeeper', event: 'kept' });
    },
    onLeave() {
      if (this.placeCover) placeCover();     // (shown now: the cover to its client area at once)
    },
  });
  return { dispose() { uncover('dispose'); hook.detach(); } };
}
