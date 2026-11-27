"""R8 (review 2026-11-27): a remembered slot name is display, not proof of what the slot holds.

The review's reproduction (same_name_slot_accepts_stale_identity): slot 9 kept its name, Crunch, while another tool
replaced its content between launches. On the next launch the remembered content was put into the verification ledger
without a read, so Use on Floor could select a different sound than the library named. A remembered "not a library
capture" (contentId null) also skipped the read, and asking for the check again never read it.

These run the production functions (nam_view.js methods, the slot ledger, the slot-check coordinator) with native
access replaced by fakes. No device or editor is needed."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'


def _view_methods(*spans):
    view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
    return '\n'.join(view[view.index(start):view.index(end)] for start, end in spans)


def _run(code):
    run = subprocess.run(['node'], input=code, capture_output=True, text=True, encoding='utf-8', timeout=15)
    return run.returncode, run.stdout + run.stderr


@unittest.skipUnless(shutil.which('node'), 'Node is required for the slot-check replay')
class RememberedSlotIsNotProofTests(unittest.TestCase):
    def view_harness(self):
        ledger = (ROOT / 'library_slot_state.js').read_text(encoding='utf-8')
        ledger = ledger[:ledger.index('// Attach the verifier only')]
        methods = _view_methods(('    acceptRememberedSlot(slot) {', '    invalidateVerifiedSlots('),
                                ('    recordVerifiedSlot(', '    setDiscoveryLocked('),
                                ('    verifiedCaptureSlot(', '    modelSlot:'))
        return ledger + r'''
const assert=require('node:assert/strict'),sent=[],requests=[];
const send=message=>sent.push(message);
const OLD='a'.repeat(64),NEW='b'.repeat(64),CRUNCH_OLD='1'.repeat(64),CRUNCH_NEW='2'.repeat(64);
// Slot 9 was read on an earlier launch as the library's "Crunch" (content OLD). Since then another tool put a
// different capture there under the same name (content NEW). Slot 40 was remembered as a plain IR.
const rememberedSlots=new Map([[9,{name:'Crunch',contentId:OLD}],[40,{name:'Room IR',contentId:null}]]);
const slotNames=new Map([[9,'Crunch'],[40,'Room IR']]);
function forgetRememberedSlot(slot){if(rememberedSlots.delete(slot))send({type:'slotMemory',slot,forget:true});}
let inventoryDirty=false,inventoryState='unverified';
const emitInventory=()=>{},AUDITION_SLOT=128;
const slotLedger=createLibrarySlotLedger();
const payloadMetadata={[OLD]:{id:CRUNCH_OLD,name:'Crunch'},[NEW]:{id:CRUNCH_NEW,name:'Crunch (other)'}};
const irList=()=>({isNull:()=>false});
const getIrRow=()=>({isNull:()=>false,add:()=>({readU32:()=>1})});
const discoveryControls={requestVerification:options=>{requests.push(options);return true;}};
const api={
''' + methods + '\n};\n'

    def test_same_name_slot_is_not_accepted_as_verified_content(self):
        # The review's probe, against the fixed code: the startup pass still reads nothing (fast), but the old
        # content is not what Use on Floor trusts.
        code = self.view_harness() + r'''
assert.equal(api.acceptRememberedSlot(9),true,'the startup pass still skips the read (startup stays fast)');
assert.deepEqual(slotLedger.displayEntries(),[[9,OLD]],'the remembered capture is still shown at once');
assert.equal(api.verifiedCaptureSlot(CRUNCH_OLD),null,'a remembered name is not proof of the content');
assert.deepEqual(requests.at(-1)?.slots,[9],'Use on Floor asks for that slot to be read back');
// The read back finds what is really there.
assert.equal(api.recordVerifiedSlot(slotLedger.epoch(),9,NEW),true);
api.rememberSlot(9,'matched','Crunch',NEW);
assert.equal(api.verifiedCaptureSlot(CRUNCH_OLD),null,'the old capture is not on the Floor');
assert.equal(api.verifiedCaptureSlot(CRUNCH_NEW),9);
assert.deepEqual(sent.at(-1),{type:'slotMemory',slot:9,name:'Crunch',contentId:NEW},'memory learns the new content');
'''
        code_ok, output = _run(code)
        self.assertEqual(code_ok, 0, output)

    def test_a_read_that_finds_no_library_capture_drops_the_remembered_one(self):
        code = self.view_harness() + r'''
assert.equal(api.acceptRememberedSlot(9),true);
assert.equal(api.verifiedCaptureSlot(CRUNCH_OLD),null);
// The read back: an IR (or a capture this library does not have) under the same name.
api.rememberSlot(9,'unmatched-nam','Crunch');
assert.deepEqual(slotLedger.entries(),[],'nothing left that says slot 9 holds Crunch');
assert.deepEqual(slotLedger.displayEntries(),[]);
assert.deepEqual(sent.at(-1),{type:'slotMemory',slot:9,name:'Crunch',contentId:null});
'''
        code_ok, output = _run(code)
        self.assertEqual(code_ok, 0, output)

    def test_a_slot_read_on_this_connection_is_used_without_another_read(self):
        code = self.view_harness() + r'''
assert.equal(api.recordVerifiedSlot(slotLedger.epoch(),9,OLD),true);
assert.equal(api.verifiedCaptureSlot(CRUNCH_OLD),9);
assert.equal(requests.length,0,'no read asked for content already read on this connection');
// A reconnect discards proof; the recall then puts the memory back as display only.
slotLedger.invalidate(true);
assert.equal(api.acceptRememberedSlot(9),true);
assert.equal(api.verifiedCaptureSlot(CRUNCH_OLD),null);
assert.deepEqual(requests.at(-1)?.slots,[9]);
'''
        code_ok, output = _run(code)
        self.assertEqual(code_ok, 0, output)


@unittest.skipUnless(shutil.which('node'), 'Node is required for the slot-check replay')
class CheckReadsEverySlotTests(unittest.TestCase):
    def test_check_bypasses_memory_and_use_reads_only_its_slot(self):
        code = r'''
const assert=require('node:assert/strict');
const plans=[],states=[];let now=0;
const memory=new Map([[9,{name:'Crunch',contentId:'a'.repeat(64)}],[40,{name:'Room IR',contentId:null}]]);
const automatic=createAutomaticSlotDiscovery({now:()=>now,recallOnConnect:true,status:s=>states.push(s.state),
  prepare:p=>plans.push(p),export:()=>true,
  remembered:(slot,name)=>{const m=memory.get(slot);return !!m&&m.name===name;}});
const names=[[9,'Crunch'],[40,'Room IR'],[41,'Plate IR']];
memory.set(41,{name:'Plate IR',contentId:null});
const snap={device:0x210001,identity:'floor',signature:JSON.stringify(names),slots:names.map(n=>n[0]),slotSignatures:names,revision:0};
const tick=(dt=0)=>{now+=dt;automatic.tick(snap);};
function finish(status,contentId){const p=plans.at(-1);automatic.prepared({token:p.token,path:'E:\\x.wav'});tick();
  automatic.result({token:p.token,status,contentId});tick();}
// Connecting: everything remembered, nothing read.
automatic.host({generation:0,ready:true,present:true});tick();tick(1501);
assert.equal(plans.length,0);assert.equal(states.at(-1),'complete');
// An ordinary request (the NAM tab opening) still trusts memory for display: nothing read.
automatic.requestVerification({allowWhileBrowsing:true});tick();tick(1501);tick();
assert.equal(plans.length,0);
// Use on Floor for the capture remembered in slot 9: that slot alone is read back.
automatic.requestVerification({allowWhileBrowsing:true,slots:[9]});tick();tick(1501);
assert.deepEqual(plans.map(p=>p.slot),[9]);finish('matched','b'.repeat(64));
assert.equal(states.at(-1),'complete');assert.deepEqual(plans.map(p=>p.slot),[9]);
// The explicit Check: every slot is read, including the ones remembered as "not a library capture".
automatic.requestVerification({allowWhileBrowsing:true,fresh:true});tick();tick(1501);
finish('matched','b'.repeat(64));finish('unmatched-nam');finish('ir');
assert.deepEqual(plans.map(p=>p.slot),[9,9,40,41]);assert.equal(states.at(-1),'complete');
// After the Check, memory is used again for ordinary requests.
automatic.requestVerification({allowWhileBrowsing:true});tick();tick(1501);tick();
assert.deepEqual(plans.map(p=>p.slot),[9,9,40,41]);
// A fresh Check cancelled by the Floor's full refresh does not linger into the next pass.
automatic.requestVerification({fresh:true});automatic.invalidate();tick();tick(1501);tick();
assert.equal(automatic.inspect().fresh,false);assert.deepEqual(plans.map(p=>p.slot),[9,9,40,41]);
'''
        source = (ROOT / 'automatic_slot_discovery.js').read_text(encoding='utf-8')
        code_ok, output = _run(source + '\n' + code)
        self.assertEqual(code_ok, 0, output)


class RememberedSlotsInTheLibraryTests(unittest.TestCase):
    def test_rows_say_a_slot_is_remembered_until_it_is_read_back(self):
        import tempfile
        from nam_library import Library
        from nam_sidebar import sidebar_rows
        from test_floor_inventory import wav
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder, 'Crunch.nam')
            capture.write_text('{"metadata":{"gear_type":"amp"}}')
            library = Library(Path(folder, 'library'))
            identity = library.add(capture)
            converted = Path(folder, 'crunch.wav')
            converted.write_bytes(wav())
            content = library.register_payload(identity, converted)
            # Shown from memory at connect: the slot number, marked as remembered, Use on Floor still offered.
            self.assertTrue(library.set_slot_inventory({'epoch': 1, 'state': 'verified', 'entries': [[9, content]],
                                                        'remembered': [9]}))
            self.assertEqual(library.entries()[identity]['rememberedSlots'], [9])
            row, = sidebar_rows(library, can_load=True)
            self.assertEqual((row['deviceStatus'], row['verifiedSlots']), ('verified', [9]))
            self.assertIn('Remembered', row['locationDetail'])
            # Read back on this connection: no longer only remembered.
            self.assertTrue(library.set_slot_inventory({'epoch': 1, 'state': 'verified', 'entries': [[9, content]],
                                                        'verified': [[9, content]], 'remembered': []}))
            row, = sidebar_rows(library, can_load=True)
            self.assertEqual(row['locationDetail'], 'Capture content verified on this connection')
            # Older senders without the field are still accepted; a malformed one is refused.
            self.assertTrue(library.set_slot_inventory({'epoch': 2, 'state': 'verified', 'entries': [[9, content]]}))
            self.assertFalse(library.set_slot_inventory({'epoch': 3, 'state': 'verified', 'entries': [], 'remembered': ['9']}))


class CheckFloorSlotsMenuTests(unittest.TestCase):
    def test_check_floor_slots_reaches_the_slot_check_from_both_menus(self):
        from dsp_meter import DspMeter
        import workbench
        self.assertIn('checkSlots', DspMeter.CHOICES)
        self.assertEqual(workbench.WorkbenchView.checked_menu('checkSlots'), 'checkSlots')
        self.assertIn('Tuple.Create("Check Floor slots", "checkSlots")', (ROOT / 'NamLibrary.cs').read_text(encoding='utf-8'))
        self.assertIn("ask('menu', 'checkSlots')", (ROOT / 'workbench.html').read_text(encoding='utf-8'))
        launcher = (ROOT / 'start-hx-edit-nam.pyw').read_text(encoding='utf-8')
        self.assertIn("script.post({'type': 'checkSlots', 'payload': {}})", launcher)
        # The Workbench stays shown: Check Floor slots is not a panel of HX Edit's own screen.
        branch = launcher[launcher.index("choice = workbench.checked_menu(value)"):]
        self.assertLess(branch.index("elif choice == 'checkSlots'"), branch.index('elif choice:'))
        sidebar = (ROOT / 'nam_sidebar.js').read_text(encoding='utf-8')
        self.assertIn("recv('checkSlots'", sidebar)
        self.assertIn('namView.checkAllSlots', sidebar)


if __name__ == '__main__':
    unittest.main()
