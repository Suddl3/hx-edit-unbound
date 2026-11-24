'use strict';

// HX Edit's menu row (File, Edit, Snapshots, Window, Help, Devices) away while one of our panes covers its screen,
// with its commands still working.
//
// HX Edit 3.82 x86 runs a menu command (WM_COMMAND: Save Preset 32779, Undo, Export, and its keys, which
// TranslateAccelerator turns into the same commands) only when it finds the command in its window's menu: the
// command handler at RVA 0x5b4740 calls the search 0x5b4200(GetMenu(hwnd), id) at 0x5b477c, once more for its other
// window at 0x5b4798, and drops the command when neither finds it. The search only looks for the id (item by item,
// into submenus); it does not ask whether the item is enabled.
// With the menu off the window (SetMenu(hwnd, NULL), window_frame.py) GetMenu gives NULL, so every command was
// dropped: seen live 2026-11-23, the Workbench's Save did nothing until the row was back.
//
// So while the row is away, those two searches are given the menu that was taken off (the launcher says which:
// "menuRow" {kept: handle}; the menu itself is never changed or freed here). HX Edit finds its commands as before.
// Nothing else is answered differently: HX Edit's own GetMenu for its window size (0x3748ab) and on WM_SHOWWINDOW
// (0x5b558e) see the window as it is. When HX Edit sets a menu itself (its Devices menu, 0x5b6039) the row is back
// until the launcher takes it off again, and that newer menu is the one kept.
const menuRowGuards = Object.freeze({
  '5b4200': '558bec83ec3053560f57c0c7',   // the search: push ebp; mov ebp, esp; sub esp, 0x30; ... (menu, command id)
  '5b477b': '50e87ffaffff',               // the handler: push eax (GetMenu(hwnd)); call 0x5b4200
  '5b4797': '50e863faffff',               // and for its other window: push eax; call 0x5b4200
});

function installMenuRow() {
  if (Process.arch !== 'ia32' || Process.pointerSize !== 4) throw new Error('Menu row requires HX Edit x86');
  const base = Process.mainModule.base;
  for (const [rva, hex] of Object.entries(menuRowGuards)) {
    const bytes = new Uint8Array(base.add(parseInt(rva, 16)).readByteArray(hex.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error(`Menu row native byte guard failed at ${rva}`);
  }
  const user = Process.getModuleByName('user32.dll');
  const isMenu = new NativeFunction(user.getExportByName('IsMenu'), 'int', ['pointer'], 'stdcall');
  // (the return addresses of the two calls: each call is 5 bytes after its push)
  const sites = [base.add(0x5b4781), base.add(0x5b479d)];
  let kept = NULL;
  const hook = Interceptor.attach(base.add(0x5b4200), {
    onEnter(args) {
      // Only a search of "no menu" from the command handler, and only while a menu is kept: the kept one instead.
      if (!args[0].isNull() || kept.isNull() || !sites.some(site => site.equals(this.returnAddress))) return;
      if (isMenu(kept)) args[0] = kept;
    },
  });
  function listen() {
    recv('menuRow', message => {
      const value = message.payload || {}, handle = Number(value.kept);
      kept = Number.isInteger(handle) && handle > 0 && handle <= 0xffffffff ? ptr(handle) : NULL;
      send({ type: 'menuRow', event: kept.isNull() ? 'none' : 'kept' });
      listen();
    });
  }
  listen();
  send({ type: 'menuRow', event: 'ready' });
  return { dispose() { hook.detach(); kept = NULL; } };
}
