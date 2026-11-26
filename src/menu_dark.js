'use strict';

// HX Edit's menu row (File, Edit, Snapshots, Window, Help, Devices) drawn dark while one of our panes covers its
// screen. The row stays on the window, so HX Edit's commands, its keys and its saved window size are untouched
// (taking the row off broke both: window_frame.py).
//
// Windows draws a themed window's menu row through two messages its window procedure may answer itself:
// WM_UAHDRAWMENU (0x91, the row's background) and WM_UAHDRAWMENUITEM (0x92, one item), each with the device context
// to draw into. HX Edit leaves both to DefWindowProcW, which draws them light. While "dark" is on (the launcher says
// so: "menuDark" {window, on}), DefWindowProcW for HX Edit's main window is watched: those two are drawn here in the
// panes' colours and the call goes on as WM_NULL, so Windows draws nothing over them; after WM_NCPAINT and
// WM_NCACTIVATE the light line Windows leaves under the row is painted over. Every other message, every other
// window, and everything while "dark" is off pass through untouched.
// The drop-down menus are Windows' own popups: they follow uxtheme's app mode (ordinals 135 SetPreferredAppMode and
// 136 FlushMenuThemes, as other dark Win32 apps use them), set to dark with the row and back to the default with it.
// Where that is not available the drop-downs stay light. Tried on Windows 11 build 10.0.26200 (2026-11-23, trace
// 20261123-220202-cd3f5079: "popups" true, File's drop-down dark); the ordinals are undocumented and could go in a
// later Windows: then the drop-downs stay light (GetProcAddress finds nothing, or the call does nothing).
const MENU_DARK = Object.freeze({ bar: 0x001b1614, hot: 0x00332925, ink: 0x00d6cdc9, off: 0x006c605a });   // 0x00BBGGRR: the panes' panel, a raised row, ink, faint

function installMenuDark() {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Dark menu row requires HX Edit x86');
  const user = Process.getModuleByName('user32.dll'), gdi = Process.getModuleByName('gdi32.dll'), kernel = Process.getModuleByName('kernel32.dll');
  const api = (module, name, result, args) => new NativeFunction(module.getExportByName(name), result, args, 'stdcall');
  const getProcAddress = api(kernel, 'GetProcAddress', 'pointer', ['pointer', 'pointer']);
  // (DefWindowProcW is forwarded to ntdll: GetProcAddress gives the function HX Edit's own calls reach)
  const defWindowProc = getProcAddress(user.base, Memory.allocAnsiString('DefWindowProcW'));
  if (defWindowProc.isNull()) throw new Error('Dark menu row: DefWindowProcW not found');
  const getMenu = api(user, 'GetMenu', 'pointer', ['pointer']);
  const getMenuBarInfo = api(user, 'GetMenuBarInfo', 'int', ['pointer', 'int', 'int', 'pointer']);
  const getMenuItemInfo = api(user, 'GetMenuItemInfoW', 'int', ['pointer', 'uint', 'int', 'pointer']);
  const getWindowRect = api(user, 'GetWindowRect', 'int', ['pointer', 'pointer']);
  const getClientRect = api(user, 'GetClientRect', 'int', ['pointer', 'pointer']);
  const mapWindowPoints = api(user, 'MapWindowPoints', 'int', ['pointer', 'pointer', 'pointer', 'uint']);
  const getWindowDC = api(user, 'GetWindowDC', 'pointer', ['pointer']);
  const releaseDC = api(user, 'ReleaseDC', 'int', ['pointer', 'pointer']);
  const fillRect = api(user, 'FillRect', 'int', ['pointer', 'pointer', 'pointer']);
  const drawText = api(user, 'DrawTextW', 'int', ['pointer', 'pointer', 'int', 'pointer', 'uint']);
  const redrawWindow = api(user, 'RedrawWindow', 'int', ['pointer', 'pointer', 'pointer', 'uint']);
  const drawMenuBar = api(user, 'DrawMenuBar', 'int', ['pointer']);
  const systemParameters = api(user, 'SystemParametersInfoW', 'int', ['uint', 'uint', 'pointer', 'uint']);
  const createSolidBrush = api(gdi, 'CreateSolidBrush', 'pointer', ['uint']);
  const createFont = api(gdi, 'CreateFontIndirectW', 'pointer', ['pointer']);
  const selectObject = api(gdi, 'SelectObject', 'pointer', ['pointer', 'pointer']);
  const setTextColor = api(gdi, 'SetTextColor', 'uint', ['pointer', 'uint']);
  const setBkMode = api(gdi, 'SetBkMode', 'int', ['pointer', 'int']);

  let window = NULL, dark = false, brushes = null, font = NULL, reported = false;
  // (a drawing that failed falls back to Windows' own, light; it is said once, so a regression shows in the trace
  // without a message for every repaint; review of PR #7)
  function failed(where, error) {
    if (reported) return;
    reported = true;
    try { send({ type: 'menuDark', event: 'draw-failed', where, error: String(error && error.message || error) }); } catch (_) { }
  }
  // (made once, at the first dark row; all drawing is on HX Edit's own window thread)
  const tools = () => brushes || (brushes = { bar: createSolidBrush(MENU_DARK.bar), hot: createSolidBrush(MENU_DARK.hot) });
  function menuFont() {
    // Windows' own menu font: NONCLIENTMETRICSW (504 bytes on x86), lfMenuFont at 224
    if (font.isNull()) { const metrics = Memory.alloc(504); metrics.writeU32(504); if (systemParameters(0x29, 504, metrics, 0)) font = createFont(metrics.add(224)); }
    return font;
  }
  const rect = Memory.alloc(16), other = Memory.alloc(16), bar = Memory.alloc(32), info = Memory.alloc(48), text = Memory.alloc(2 * 260);

  function drawBar(uah) {
    // UAHMENU {hmenu, hdc, flags}: the whole row, where GetMenuBarInfo says it is (screen -> window coordinates)
    const hdc = uah.add(4).readPointer();
    bar.writeU32(32);
    if (!getMenuBarInfo(window, -3, 0, bar) || !getWindowRect(window, other)) return false;   // OBJID_MENU
    const left = other.readS32(), top = other.add(4).readS32();
    rect.writeS32(bar.add(4).readS32() - left); rect.add(4).writeS32(bar.add(8).readS32() - top);
    rect.add(8).writeS32(bar.add(12).readS32() - left); rect.add(12).writeS32(bar.add(16).readS32() - top + 1);   // (and the line under it)
    return fillRect(hdc, rect, tools().bar) !== 0;
  }
  function drawItem(uah) {
    // UAHDRAWMENUITEM {DRAWITEMSTRUCT dis (48 bytes: itemState at 16, rcItem at 28), UAHMENU um (hmenu at 48, hdc at 52),
    // UAHMENUITEM umi (iPosition at 60)}
    const state = uah.add(16).readU32(), item = uah.add(28), menu = uah.add(48).readPointer(), hdc = uah.add(52).readPointer();
    info.writeU32(48); info.add(4).writeU32(0x40); info.add(36).writePointer(text); info.add(40).writeU32(256); text.writeU16(0);   // MIIM_STRING
    if (!getMenuItemInfo(menu, uah.add(60).readS32(), 1, info)) return false;
    const hot = (state & 0x41) !== 0, off = (state & 0x06) !== 0;      // selected or hot; greyed or disabled
    if (!fillRect(hdc, item, hot ? tools().hot : tools().bar)) return false;
    const mine = menuFont(), before = mine.isNull() ? NULL : selectObject(hdc, mine);
    setBkMode(hdc, 1);                                                 // TRANSPARENT
    setTextColor(hdc, off ? MENU_DARK.off : MENU_DARK.ink);
    // DT_CENTER | DT_VCENTER | DT_SINGLELINE, and no underlines unless Alt showed them (ODS_NOACCEL -> DT_HIDEPREFIX)
    drawText(hdc, text, -1, item, 0x25 | ((state & 0x100) ? 0x100000 : 0));
    if (!before.isNull()) selectObject(hdc, before);
    return true;
  }
  function drawLine() {
    // The one-pixel line Windows leaves between the row and the client area
    if (getMenu(window).isNull() || !getClientRect(window, rect) || !getWindowRect(window, other)) return;
    mapWindowPoints(window, NULL, rect, 2);
    const left = rect.readS32() - other.readS32(), top = rect.add(4).readS32() - other.add(4).readS32(), right = rect.add(8).readS32() - other.readS32();
    rect.writeS32(left); rect.add(4).writeS32(top - 1); rect.add(8).writeS32(right); rect.add(12).writeS32(top);
    const hdc = getWindowDC(window);
    if (hdc.isNull()) return;
    fillRect(hdc, rect, tools().bar);
    releaseDC(window, hdc);
  }
  const hook = Interceptor.attach(defWindowProc, {
    onEnter(args) {
      this.line = false;
      if (!dark || !args[0].equals(window)) return;
      const message = args[1].toUInt32();
      try {
        if (message === 0x91) { if (drawBar(args[3])) args[1] = NULL; }          // drawn here: Windows' own drawing is skipped (WM_NULL)
        else if (message === 0x92) { if (drawItem(args[3])) args[1] = NULL; }
        else if (message === 0x85 || message === 0x86) this.line = true;          // WM_NCPAINT, WM_NCACTIVATE: the line, afterwards
      } catch (error) { failed('row', error); }                                   // (anything unexpected: Windows draws it, light)
    },
    onLeave() {
      if (!this.line) return;
      try { drawLine(); } catch (error) { failed('line', error); }
    },
  });
  function appMode(on) {
    // The drop-downs: uxtheme's app mode, where this Windows has it
    try {
      const theme = Process.getModuleByName('uxtheme.dll');
      const setMode = getProcAddress(theme.base, ptr(135)), flush = getProcAddress(theme.base, ptr(136));
      if (setMode.isNull() || flush.isNull()) return false;
      new NativeFunction(setMode, 'int', ['int'], 'stdcall')(on ? 2 : 0);      // SetPreferredAppMode: ForceDark, or Default
      new NativeFunction(flush, 'void', [], 'stdcall')();                      // FlushMenuThemes
      return true;
    } catch (_) { return false; }
  }
  function setDark(handle, on, why) {
    window = Number.isInteger(handle) && handle > 0 && handle <= 0xffffffff ? ptr(handle) : NULL;
    const changed = on !== dark;
    dark = on && !window.isNull();
    let popups = null;
    if (changed) popups = appMode(dark);
    if (!window.isNull()) {
      // (the row and the frame again, in the new colours: RDW_INVALIDATE | RDW_FRAME)
      try { drawMenuBar(window); redrawWindow(window, NULL, NULL, 0x0401); } catch (error) { failed('redraw', error); }
    }
    send({ type: 'menuDark', event: dark ? 'dark' : 'plain', ...(popups === null ? {} : { popups }), ...(why ? { why } : {}) });
  }
  function listen() {
    recv('menuDark', message => {
      const value = message.payload || {};
      setDark(Number(value.window), value.on === true);
      listen();
    });
  }
  listen();
  // (the start-up cover, window_keep.js: the row dark from HX Edit's window's first show, before the launcher has found
  // the window; J4, Nick 2026-11-26 "Darken it too")
  globalThis.menuDarkStart = window => setDark(window.toUInt32(), true, 'start-cover');
  send({ type: 'menuDark', event: 'ready' });
  return { dispose() { hook.detach(); dark = false; } };
}
