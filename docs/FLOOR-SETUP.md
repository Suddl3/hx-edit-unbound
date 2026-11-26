# Setup

Updated November 26, 2026.

## What you need

| | |
|---|---|
| Computer | Windows 10 or 11, 64-bit |
| HX Edit | The official **HX Edit 3.82** with its Line 6 driver, installed in its usual folder (`C:\Program Files (x86)\Line6\HX Edit`) |
| Python | 3.10 or newer, 64-bit ([python.org](https://www.python.org/downloads/windows/); tick "Add python.exe to PATH" or keep the `py` launcher) |
| Git | [git-scm.com](https://git-scm.com/download/win) |
| WebView2 Runtime | Already part of Windows 11; on Windows 10 it comes with Microsoft Edge |
| Helix Floor | [HX Unbound Floor](https://github.com/Suddl3/hx-unbound-floor) firmware for anything with NAM; see [Firmware](../README.md#firmware) |
| Optional | A [TONE3000](https://www.tone3000.com) account and its **Publishable Key** (TONE3000 → Settings → API Keys) for the TONE3000 browser |

HX Edit itself is never copied into this repository or changed: every launch makes its own working copy from your installed HX Edit.

## Install

In a folder of your choice:

```powershell
git clone https://github.com/Suddl3/hx-edit-unbound.git
cd hx-edit-unbound
.\setup.ps1
```

`setup.ps1` checks Windows, HX Edit 3.82, Python and Git, and says plainly what is missing. Then it:

1. puts the converter ([andreidevs/helix-lt-nam](https://github.com/andreidevs/helix-lt-nam) at a fixed commit) next to the editor folder;
2. makes the Python environment (`.venv`) with the packages the editor needs;
3. offers the art pack: the sharper gear pictures and scenes (about 210 MB, from [this release](https://github.com/Suddl3/hx-edit-unbound/releases/tag/gear-art-2026-11-22)), unzipped into `art\`;
4. asks once for your TONE3000 Publishable Key (it starts with `t3k_pub_`; never paste a Secret Key). Press Enter to skip.

Run it again any time: it skips what is done. Options: `-Art yes|no`, `-Key <key>|skip`.

If Windows says running scripts is disabled: `powershell -ExecutionPolicy Bypass -File .\setup.ps1`.

## Start

Close any other HX Edit, then:

```powershell
.\start.ps1
```

The first launch opens the Workbench. The first time you open the Library, every occupied User IR slot on the Floor is read back once (about half a second each); later launches skip slots whose name has not changed. A capture that is on the Floor but not yet in this PC's library shows as "IR slot n" until you import its `.nam` file.

TONE3000 opens at its sign-in page the first time: sign in with your own TONE3000 account.

## Update

Close HX Edit Unbound, then in the editor folder:

```powershell
git pull
.\setup.ps1
.\start.ps1
```

Coming from an older clone (folder `hx-edit-nam`, or the `floor` / `floor-navigation` branches): `git remote set-url origin https://github.com/Suddl3/hx-edit-unbound.git`, `git fetch`, `git checkout main`, then the three lines above. Your library and settings in `%LOCALAPPDATA%\HX Edit NAM` are kept.

## Good to know

- **User IR 128 is the preview slot.** A preview puts the tone there and takes it away again. Do not keep an IR of your own there.
- Your captures, recordings and settings live in `%LOCALAPPDATA%\HX Edit NAM` (the library in `NAM Library`, with `catalog.json`). Copy that folder to move your library to another PC.
- A Floor slot used by the open preset cannot be cleared until you leave the preset (Clear is greyed out, "Used by: This preset").
- Without the art pack the editor uses the smaller pictures kept in git (up to 256 px). Folders named in `settings.json` (`"focusArt": {"models", "captures", "scenes"}`) come before `art\`.
- The TONE3000 key is saved in `%LOCALAPPDATA%\HX Edit NAM\tone3000-publishable-key`. The `T3K_PUBLISHABLE_KEY` environment variable, if set, wins.
- Stock HX Edit's export/backup has omitted NAM data before. Keep your own copies of NAM presets.

## Without the scripts

`start.ps1` runs: `.venv\Scripts\pythonw.exe src\start-hx-edit-nam.pyw --unbound` (`--unbound` = `--floor-reference --navigation --nam-category`). The older command lines still work. The converter must sit next to the editor folder as `helix-lt-nam`.

## Versions

| Component | This release |
|---|---|
| Floor firmware | HX Unbound Floor's NAM A2 Lite block (HD2_AmpNAMLite, id 380) on Helix Floor 3.80.0 |
| Desktop | Windows HX Edit 3.82 (`HX Edit.exe` SHA-256 `f7faac4996164f9039c9ae3ca8d85cd135c5bceae8a511c8921a1244046cab66`) |
| Converter | andreidevs/helix-lt-nam at `c94834768546393420692794fdbb27c9cc31d718` (tools only; never flash LT firmware onto a Floor) |
| Python packages | frida 17.5.2, msgpack 1.2.4, numpy, sounddevice 0.5.6, soundfile 0.14.0 |
