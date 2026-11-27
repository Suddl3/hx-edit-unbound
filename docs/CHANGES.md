# What's new

## Unreleased

- **Remembered Floor slots are no longer taken on trust.** Slot numbers still show as soon as the Floor connects, but a slot this PC only remembers is read back before Use on Floor picks it, so a capture replaced by another tool under the same name can no longer play in place of the one the library names. **Check Floor slots** in the menu reads every slot again ([details](FLOOR-WORKFLOW.md#owner-decisions-november-13-supersede-the-points-they-touch-below)).

## November 27: v0.7.2

- **Problems at start-up are explained, not hidden.** If the editor cannot read your NAM library, the library page and the Captures drawer say why and that your captures are not lost, instead of "No captures yet". The library page shows the folder it reads.
- **Library missing, captures on the Floor**: if the library folder is empty but this PC remembers captures on your Floor, the editor says so.
- **Firmware notice**: if the Floor did not answer when the editor started (usual in the first minute after switching it on), one line says the editor is using the last known or basic firmware settings and to restart it in a minute. Before, it fell back to NAM at 48% and no NAM Pedal without a word.
- **Start-up line in trace.log**: the firmware found and where from, the library folder, how many captures it found and could open. No capture names.
- Fixes: the Floor's firmware answer now reaches the stored DSP costs; test runs no longer write into your own trace.log.
- **The 48% issue is fixed on the firmware side**: firmware from the [HX Unbound Floor builder](https://suddl3.github.io/hx-unbound-floor/) declares the NAM block at 43% of a DSP, and the editor follows it.
- Known: a few screens show NAM costs in the firmware's units ("32.5% of a DSP" for a block that uses 43%); while the library cannot be matched to the Floor, captures already there still offer "Put on the Floor".

## November 27: v0.7.1

- **Adding or swapping a NAM capture** is judged the way HX Edit judges it. A capture that has not been measured is shown at the firmware's own figure, captures that will not fit are marked full, and nothing is sent that HX Edit would refuse.
- **A plain message when there is no room**: how much the capture needs and how much is free, instead of "HX Edit did not make that change."
- **Known issue**: HX Edit counts a new NAM block at the firmware's declared 48% of a DSP, though a capture really uses about 36%. This stays until a firmware release lowers it ([details](FLOOR-WORKFLOW.md#status-november-26)).
- README: opens with the Workbench picking a NAM capture.

## November 26: the Workbench

- **The Workbench**, a modern editor over HX Edit, and **four layouts** (Workbench, Classic+, Rig on stage, Classic), chosen from the menu at the top left. The editor opens in the one you used last, and a first launch opens the Workbench. No flash of HX Edit's own screen at start-up.
- **One block picker**: every model in one list, NAM captures as their own category. A click lines a model up on the card, a double-click or Enter replaces, one click after "+" adds. Inputs and outputs get their own chooser.
- **TONE3000** in the Workbench: a "Plays on" row shows which NAM block a preview plays on (click another to move it). Pop it out into its own window and keep editing: a banner over the chain shows what is playing, with Stop, Keep and Load on Floor. NAM Pedal blocks are never used for a full capture.
- **Undo** follows HX Edit's own history, one step per choice, and steps over a finished preview.
- **Rig on stage**: a pin keeps one scene per preset, or lets the scene follow the selected block, with a soft change.
- **Classic** is closer to stock: HX Edit's own icons by default (the 3D gear is a choice), one UNBOUND menu for layouts, chain pictures and tools.
- **Install from a fresh clone**: `setup.ps1` once, then `start.ps1` ([Setup](FLOOR-SETUP.md)). The TONE3000 key is saved once.
- Dark title bars, the Unbound icon on every window, and HX Edit's bottom strip in the same dark gray.

## November 21

- **Focus** is now its own button on the toolbar: one click into Focus Mode. Its top bar chooses presets (arrows and a list) and snapshots, with undo, redo and DSP meters of its own, and a preset that comes up with nothing selected shows its first block.
- **Change look** in Focus Mode: the background and the picture of the block you are looking at, for this preset only; one background for a whole preset; and the defaults for every preset (the same ones as the Floor look page). The Floor shows the defaults until its firmware can read looks by preset.
- The **HX Unbound** menu holds the tools only; the options moved to a gear beside it, grouped by what they change. Options that depend on another one sit under it and are dimmed while it is off.

## November 20

- **Focus Mode**: the selected block shown large in its category's scene, with its own controls as knobs and switches, a strip of the chain to pick another block, and lists to change the block's model or its capture. Everything changes the real block, as HX Edit's own controls do, and undo works as usual. A small frame shows what the Floor's Focus View draws for the same block. See [Focus Mode](../README.md#focus-mode).
- Signal-chain pictures: 3D pictures, large pictures and block names under them (the options beside the HX Unbound menu).

## November 19

- **Drag and drop onto the chain**: captures from the NAM tab and the library window, and (with NAM categories) any model from the block picker. Dropping on a block replaces it, an empty cell adds one, between blocks inserts.
- **HX Edit's IR list**: the middle of a block now replaces it; NAM slots become NAM blocks and show in violet.
- **Block picker** (NAM categories): a click selects, double-click or Enter applies, the arrows only move the selection, and the model the block plays is shown in yellow.
- A NAM block is only made where the DSP has room.

These change how parts of HX Edit behave: see [how it behaves differently from stock HX Edit](FLOOR-WORKFLOW.md#how-classic-differs-from-stock-hx-edit).

## November 16

- **Level presets**, from the new **HX Unbound** menu button beside TONE3000: brings presets and snapshots to one output level. It measures each snapshot silently over USB with a short recording of your own playing (saved by guitar, reusable), suggests output-level changes toward one target, keeps intentional offsets (a lead +2 dB), then Applies with Undo. Only output levels change. [How it works](PRODUCT-VISION.md#level-presets-built-november-16).
- **HX Edit Unbound**: the project is now its own repository. While it runs, HX Edit's window is titled "HX Edit Unbound" and shows a violet-to-teal version of HX Edit's icon, so it is easy to tell apart from a stock HX Edit.
- A tidier repository: the app's code is in `src/`, the documents in `docs/`.

## November 14

- **Capture icons**: a gear picture for every NAM capture, picked from its name, in the NAM tab, the expanded library and the NAM model lists.
- **Change icon…**: choose another picture, go back to Automatic, or upload your own (and delete your uploads).
- **DSP meter** in HX Edit's toolbar: each DSP's use as the Floor reports it ("DSP 1 27/75"), turning yellow and red as a path fills up.
- **Your window stays put** when the Floor reconnects (maximized stays maximized).
- A tidier NAM tab: readable names when narrow, short dates, and Expand always opens the library.
- **Guitar / bass / both** per capture, with filters in both library views and an All / Guitar / Bass dropdown in every NAM category and in HX Edit's Amp and Preamp, which remembers your last side.
- A **NAM Cab** category in the block picker; favorites stay HX Edit's own (they work with NAM blocks, and go when their capture's slot is cleared).
- **Grid views**: capture pictures in the block picker's grid, and a grid view for the expanded library.
- Slot numbers show as soon as the Floor connects.
- **A warning before clearing a slot** that presets you have opened still use.

Details and what was tested: [Status, November 14](FLOOR-WORKFLOW.md#status-november-14).
