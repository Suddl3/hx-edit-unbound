"""Put on the Floor while the Library stays open (live sweep 2026-11-24, owner-trials/20261124-222512-2717b7e9):
the capture was written to User IR 29 at 23:38:14 and the row stayed at "Going to slot 29..." for two minutes. The
trace: workflow-paused (the load), verification-paused (HX Edit: slot 29 changed), verification-requested (the load's
setWorkflowBusy(false) resumed it, the Library being shown), then verification-paused again (slot 29's later
notifications: renamed, the profile registered) and nothing resumed it until the Library was closed. Each slot
invalidation clears the coordinator's "allowed while browsing". Now a slot change re-allows the check while the
Library is shown and no load runs (nam_view resumeLibraryCheck, called by library_slot_state's invalidate)."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'

SEQUENCE = r'''
const assert=require('node:assert/strict');let now=0;const plans=[],exports=[],states=[];
const s=createAutomaticSlotDiscovery({now:()=>now,prepare:p=>plans.push(p),export:p=>{exports.push(p.slot);return true;},
 status:v=>states.push(v.state)});
let snap={device:0x210001,identity:'x',signature:'9',slots:[9],slotSignatures:[[9,'A']],revision:1};
function tick(dt=0){now+=dt;s.tick(snap);}
function finish(){const p=plans.at(-1);s.prepared({token:p.token,path:'E:\\fresh.wav'});tick();s.result({token:p.token,status:'matched'});tick();}
// nam_view's flags and its rule (resumeLibraryCheck / setWorkflowBusy(false)): the Library shown, no load under way
let libraryBrowsing=false,workflowBusy=false;
const rule=()=>{if(libraryBrowsing&&!workflowBusy)s.resumeRequestedVerification({allowWhileBrowsing:true});};
const invalidate=slots=>{s.invalidate(slots);if(RESUME && Array.isArray(slots))rule();};
s.host({generation:0,ready:true,present:true});
s.setSessionActive(true);                                           // the Library's session
libraryBrowsing=true;s.requestVerification({allowWhileBrowsing:true});tick();tick(1501);finish();
assert.deepEqual(exports,[9]);
// Put on the Floor: the load's workflow, slot 29 written
workflowBusy=true;s.pauseForWorkflow();
snap={...snap,signature:'9,29',slots:[9,29],slotSignatures:[[9,'A'],[29,'N']]};
invalidate([29]);                                                   // Librarian_HelixIRChanged
for(let i=0;i<8;i++)tick(250);
assert.equal(plans.length,1,'no check while the load runs');
workflowBusy=false;rule();                                          // the load ends (setWorkflowBusy(false))
invalidate([29]);                                                   // Librarian_HelixIRRenamed
invalidate([29]);                                                   // the profile registered
for(let i=0;i<8;i++)tick(250);                                      // (2 s: the check starts 1.5 s after a change)
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required for native JavaScript replay')
class LibraryCheckWhileOpenTests(unittest.TestCase):

    def node(self, code):
        source = (ROOT / 'automatic_slot_discovery.js').read_text(encoding='utf-8')
        run = subprocess.run(['node'], input=source + '\n' + code, capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_the_sweep_sequence_stayed_paused_without_the_resume(self):
        self.node('const RESUME=false;' + SEQUENCE + r'''
for(let i=0;i<480;i++)tick(250);                                    // two minutes with the Library open
assert.equal(plans.length,1,'slot 29 waits for the Library to close');assert.deepEqual(exports,[9]);
assert.equal(states.at(-1),'verification-paused');
''')

    def test_with_the_resume_slot_29_is_checked_while_the_library_stays_open(self):
        self.node('const RESUME=true;' + SEQUENCE + r'''
assert.equal(plans.at(-1).slot,29);finish();
assert.deepEqual(exports,[9,29]);assert.deepEqual(s.inspect().done,[9,29]);
// a TONE3000 session (the Library not shown) still pauses it
libraryBrowsing=false;snap={...snap,signature:'9,29,30',slots:[9,29,30],slotSignatures:[[9,'A'],[29,'N'],[30,'T']]};
invalidate([30]);for(let i=0;i<480;i++)tick(250);
assert.equal(plans.at(-1).slot,29);assert.deepEqual(exports,[9,29]);assert.equal(states.at(-1),'verification-paused');
''')

    def test_the_wrapper_and_the_rule_are_in_the_scripts(self):
        state = (ROOT / 'library_slot_state.js').read_text(encoding='utf-8')
        self.assertIn('automatic.invalidate(slots);', state)
        self.assertIn('if(Array.isArray(slots))namView.resumeLibraryCheck?.();', state)
        view = (ROOT / 'nam_view.js').read_text(encoding='utf-8')
        self.assertIn('resumeLibraryCheck() {', view)
        self.assertIn('if (libraryBrowsing && !workflowBusy) discoveryControls?.resumeRequestedVerification({allowWhileBrowsing:true});', view)
        self.assertIn('if (!busy && wasBusy && libraryBrowsing) discoveryControls?.resumeRequestedVerification({allowWhileBrowsing:true});', view)


if __name__ == '__main__':
    unittest.main()
