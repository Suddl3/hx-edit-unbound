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
// Its window's first show is this same helper's call at 0x1a6039; just before it the window is made fully transparent
// (WS_EX_LAYERED, alpha 0: the pane inside it too), and it comes back as it was when the launcher says the pane's
// page is up ("startCover" {on: false}), or after 10 s at the latest. Classic as the saved layout: no cover.
const START_COVER_MS = 10000;

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
  const getLong = new NativeFunction(user.getExportByName('GetWindowLongW'), 'int', ['pointer', 'int'], 'stdcall');
  const setLong = new NativeFunction(user.getExportByName('SetWindowLongW'), 'int', ['pointer', 'int', 'int'], 'stdcall');
  const setLayered = new NativeFunction(user.getExportByName('SetLayeredWindowAttributes'), 'int', ['pointer', 'uint', 'uint8', 'uint'], 'stdcall');
  const redraw = new NativeFunction(user.getExportByName('RedrawWindow'), 'int', ['pointer', 'pointer', 'pointer', 'uint'], 'stdcall');
  const GWL_EXSTYLE = -20, WS_EX_LAYERED = 0x80000, LWA_ALPHA = 2;
  let cover = options.cover === true ? {wanted: true} : null;
  function uncover(why) {
    if (!cover || !cover.window) { if (cover) cover.wanted = false; return; }
    const {window, style, at} = cover;
    cover = null;
    try {
      setLayered(window, 0, 255, LWA_ALPHA);
      setLong(window, GWL_EXSTYLE, style);
      redraw(window, NULL, NULL, 0x0001 | 0x0004 | 0x0080 | 0x0100);   // INVALIDATE|ERASE|ALLCHILDREN|UPDATENOW
    } catch (_) { /* the window may be gone */ }
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
        // (the window's first show: transparent before it is drawn, until the pane's page is up)
        try {
          const style = getLong(args[0], GWL_EXSTYLE);
          setLong(args[0], GWL_EXSTYLE, style | WS_EX_LAYERED);
          setLayered(args[0], 0, 0, LWA_ALPHA);
          cover.window = args[0]; cover.style = style; cover.at = Date.now();
          send({ type: 'windowKeeper', event: 'cover-up' });
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
  });
  return { dispose() { uncover('dispose'); hook.detach(); } };
}
