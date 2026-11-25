"""The block picker's Guitar / Bass side, chosen by us, never changes the block's model. No device.

HX Edit's "cva!" handler (0x217120, from 0x2172eb) refills the model column for the new side and then
hands each row of the block's own model to 0x21a470, the same call a click on a model row makes: a
"@model" write and an undo step "Change Model". Seen live on preset 032 (Solo Lead OD).

caf0cec hooked 0x21a470 (Interceptor.attach) and dropped its argument during our side choice. Live
(2026-11-24 21:24, owner-trials/20261124-212410-3a9f2560) every pick of Solo Lead OD still added a step and
no "model-kept" line came: our side choice for a selected block runs in 0x21e500's onLeave (blockSide),
and Frida runs no hook for a call made inside another hook's onEnter / onLeave (Frida 17.5.2, tried on a
throwaway process: a hooked function called from onEnter or onLeave, through a NativeFunction, with
traps 'default' or 'all', never reached its hook; from inside an Interceptor.replace callback it did).
Now the three calls of 0x21a470 in that handler go through a stub that skips them while our flag is set
(installKeepModel). The replays below play the handler against chooseSubcategory / blockSide; the last
test runs installKeepModel over HX Edit.exe's own bytes and executes the patched calls (unicorn).
"""
from pathlib import Path
import faulthandler
import json
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
HX_EDIT = Path(os.environ.get('HX_EDIT_EXE', r'C:\Program Files (x86)\Line6\HX Edit\HX Edit.exe'))

try:
    import unicorn
    from unicorn import x86_const
except ImportError:  # pragma: no cover - the replay of the stub needs it
    unicorn = None


def view_text():
    return (ROOT / 'tone_view.js').read_text(encoding='utf-8').replace('\r\n', '\n')


def side_code(view, start_marker):
    start = view.index(start_marker)
    return view[start:view.index('  // grid list: add a tile', start)]


def node(code):
    run = subprocess.run(['node'], input=code, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if run.returncode != 0:
        raise AssertionError(run.stdout + run.stderr)
    return run.stdout


# HX Edit's handler as far as the side goes: each of the three calls of 0x21a470 is what the stub makes of it
# (flag set: skipped and counted; otherwise HX Edit's own call, a model write).
HANDLER = r'''
const writes=[];let flagByte=0;const siteCounts=[0,0,0];
keepModel={flag:{writeU8:value=>{flagByte=value;}},counts:[0,1,2].map(index=>({readU32:()=>siteCounts[index]}))};
function callSite(index,row){if(flagByte){siteCounts[index]++;return;}writes.push(row);}
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required for the picker-side replay')
class PickerSideKeepsTheModelTests(unittest.TestCase):
    def test_our_side_choice_does_not_write_the_model_and_keeps_its_row_selected(self):
        view = view_text()
        side = side_code(view, '  function chooseSubcategory(controller, value) {')
        # (no hook on 0x21a470: it would not run for our side choice from blockSide, see the docstring)
        self.assertNotIn('Interceptor.attach(base.add(0x21a470)', view)
        self.assertIn('  let keepModel = null;', view)
        kept_counts = next(line for line in view.split('\n') if line.startswith('  const keptCounts = '))
        node(r'''
const assert=require('node:assert/strict');
const NULL={isNull:()=>true,equals:()=>false};
// The model column: rows by label, one selected (a click on the block selects its model row).
const column={rows:['Brit Plexi Brt','Solo Lead OD','Cali Rectifire'],selected:1,isNull:()=>false};
const menu={value:1,isNull:()=>false};
const controller={add:offset=>({readPointer:()=>offset===0x58?column:NULL})};
const subcategoryMenu=()=>menu, subcategoryValue=()=>menu.value;
const base={add:()=>({readByteArray:()=>Uint8Array.from(Buffer.from('558bec56578bf1e8d4c500008b7d083b','hex')).buffer})};
const selectedRow=list=>list.selected<0?NULL:{isNull:()=>false,readUtf8String:()=>list.rows[list.selected]};
const rowIndex=(list,test)=>list.rows.findIndex(test);
const selectRow=(list,on,index,notify,scroll)=>{assert.equal(notify,0);list.selected=index;};
const sent=[],send=value=>sent.push(value);
let listReports=10,menuSelectReady=null,choosingSide=false,keepModel=null;
''' + kept_counts + HANDLER + r'''
const subcategoryChanged=0x21617663;
// HX Edit's "cva!" handler: the column refilled for the side (no selection), then the block's model re-chosen
// (0x21790b: an amp's category; 0x217802: a cab's).
function menuSelect(m,value,event,redraw){
  assert.equal(event,subcategoryChanged);
  m.value=value;
  column.rows=value===2?['Cali Bass','SV Beast Nrm']:['Brit Plexi Brt','Solo Lead OD','Cali Rectifire','Cali Bass'];
  column.selected=-1;
  for(const label of column.rows) if(label==='Solo Lead OD') callSite(1,label);
}
''' + side + r'''
// Our side (the block was selected, its category opens on All): no model write, its row selected again.
chooseSubcategory(controller,99);
assert.equal(menu.value,99);
assert.deepEqual(writes,[]);
assert.equal(column.rows[column.selected],'Solo Lead OD');
assert.equal(choosingSide,false);assert.equal(flagByte,0);
assert.deepEqual(sent.at(-1),{type:'toneTrace',reason:'nam-category',stage:'subcategory',value:99,kept:[0,1,0]});
// A side the block's model is not on: nothing written, nothing selected, nothing skipped.
chooseSubcategory(controller,2);
assert.deepEqual(writes,[]);
assert.equal(column.selected,-1);
assert.deepEqual(sent.at(-1).kept,[0,0,0]);
// The player's own pick in the dropdown stays HX Edit's (stock behaviour, as before), and so does a click
// on a model row (the column's "sbl!", 0x2179e3) with no side choice of ours running.
column.rows=['Solo Lead OD'];column.selected=0;
menuSelect(menu,1,subcategoryChanged,1);
assert.deepEqual(writes,['Solo Lead OD']);
callSite(2,'Brit Plexi Brt');
assert.deepEqual(writes,['Solo Lead OD','Brit Plexi Brt']);
// Same side already shown: the menu is not touched at all.
menu.value=99;column.selected=0;
chooseSubcategory(controller,99);
assert.deepEqual(writes,['Solo Lead OD','Brit Plexi Brt']);
// The column's own "sbl!" during our side choice (a selection HX Edit makes while refilling): kept too.
const plain=menuSelect;
menuSelect=(m,value,event)=>{plain(m,value,event);callSite(2,'Cali Bass');};
column.rows=['Brit Plexi Brt','Solo Lead OD'];column.selected=1;menu.value=1;
chooseSubcategory(controller,99);
menuSelect=plain;
assert.equal(writes.length,2);
assert.deepEqual(sent.at(-1).kept,[0,1,1]);
// A side choice that throws leaves nothing behind: the next click writes as HX Edit's own.
menuSelect=()=>{throw new Error('menu gone');};
assert.throws(()=>chooseSubcategory(controller,2),/menu gone/);
menuSelect=plain;
assert.equal(choosingSide,false);assert.equal(flagByte,0);
callSite(2,'Solo Lead OD');
assert.equal(writes.length,3);
// Not installed (another build): our side choice is HX Edit's as before, and the trace says so (kept null).
keepModel=null;menu.value=1;column.rows=['Solo Lead OD'];column.selected=0;
chooseSubcategory(controller,99);
assert.equal(writes.length,4);
assert.equal(sent.at(-1).kept,null);
''')

    def test_a_stock_amp_picked_after_a_nam_block_leaves_no_step(self):
        # The page's select of a block just added at a "+" (or a click on it) makes HX Edit show the block's
        # category (0x21e500) and blockSide choose its remembered side: Solo Lead OD on 032 after a NAM block
        # ("subcategory 99" then an undo step, live 2026-11-24 16:46, 18:56 and 21:24). No model write now.
        view = view_text()
        side = side_code(view, '  const sideBlocks = new Map();')
        kept_counts = next(line for line in view.split('\n') if line.startswith('  const keptCounts = '))
        node(r'''
const assert=require('node:assert/strict');
const NULL={isNull:()=>true,equals:()=>false};
const column={rows:['Brit Plexi Brt','Solo Lead OD','Cali Rectifire'],selected:1,isNull:()=>false};
const menu={value:1,isNull:()=>false};
const controller={add:offset=>({readPointer:()=>offset===0x58?column:NULL}),toString:()=>'picker'};
let block='block3';const position=()=>'0:'+block;
const subcategoryMenu=()=>menu, subcategoryValue=()=>menu.value, shownCategory=()=>'Amp';
const SIDED_CATEGORIES=new Set(['Amp','Amp+Cab','Preamp']),SIDE_ALL=99,rememberedSide=()=>99;
const base={add:()=>({readByteArray:()=>Uint8Array.from(Buffer.from('558bec56578bf1e8d4c500008b7d083b','hex')).buffer})};
const selectedRow=list=>list.selected<0?NULL:{isNull:()=>false,readUtf8String:()=>list.rows[list.selected]};
const rowIndex=(list,test)=>list.rows.findIndex(test);
const selectRow=(list,on,index,notify)=>{assert.equal(notify,0);list.selected=index;};
const sent=[],send=value=>sent.push(value);
let listReports=10,menuSelectReady=null,choosingSide=false,keepModel=null;
''' + kept_counts + HANDLER + r'''
const subcategoryChanged=0x21617663;
function menuSelect(m,value){m.value=value;column.selected=-1;for(const label of column.rows) if(label==='Solo Lead OD') callSite(1,label);}
''' + side + r'''
blockSide(controller);                       // the amp selected: its side (All) shown, its row selected
assert.equal(menu.value,99);
assert.deepEqual(writes,[]);
assert.equal(column.rows[column.selected],'Solo Lead OD');
assert.deepEqual(sent.at(-1).kept,[0,1,0]);
blockSide(controller);                       // the same block again (a reading, an Undo's reselect): nothing
assert.deepEqual(writes,[]);
menu.value=1;block='block4';                 // another amp, its side shown again: still no write
blockSide(controller);
assert.deepEqual(writes,[]);
''')

    def test_the_calls_are_only_patched_on_the_hx_edit_build_they_were_read_from(self):
        # (another build: nothing patched; our side choice may record "Change Model" there, as before the fix)
        view = view_text()
        self.assertIn('  const keepModelSites = [0x217802, 0x21790b, 0x2179e3];', view)
        guards = view[view.index('  const keepModelGuards = {'):]
        guards = guards[:guards.index('  };')]
        for rva, hexbytes in (('21a470', '558bec6aff68????????64a100000000'), ('21aab1', 'c20400'),
                              ('2172e3', '3bde0f854d06000081fa63766121'), ('2177ff', '568bcf'),
                              ('217908', '568bcf'), ('2179e0', '8bcf50')):
            self.assertIn("'%s': '%s'," % (rva, hexbytes), guards)
        install = view[view.index('  function installKeepModel() {'):]
        self.assertTrue(install.startswith('  function installKeepModel() {\n    if (!guardsMatch(keepModelGuards)) return null;'))
        hook = view[view.index('    try { keepModel = installKeepModel(); }'):]
        self.assertIn("stage: keepModel ? 'model-keep-ready' : 'model-keep-guard-failed'", hook[:hook.index('\n', 100)])
        self.assertIn("return want === '??' || want === byte;", view)

    @unittest.skipUnless(HX_EDIT.exists(), 'HX Edit.exe is not installed here')
    def test_the_guards_are_hx_edits_own_bytes(self):
        image = ExeImage(HX_EDIT)
        view = view_text()
        guards = view[view.index('  const keepModelGuards = {'):]
        guards = guards[:guards.index('  };')]
        import re
        for rva, hexbytes in re.findall(r"'([0-9a-f]+)': '([0-9a-f?]+)',", guards):
            have = image.read(int(rva, 16), len(hexbytes) // 2).hex()
            for index in range(0, len(hexbytes), 2):
                if hexbytes[index:index + 2] != '??':
                    self.assertEqual(have[index:index + 2], hexbytes[index:index + 2], (rva, have, hexbytes))
        for site in (0x217802, 0x21790b, 0x2179e3):                  # each a call of 0x21a470
            call = image.read(site, 5)
            self.assertEqual(call[0], 0xe8)
            self.assertEqual(site + 5 + int.from_bytes(call[1:], 'little', signed=True), 0x21a470)

    @unittest.skipUnless(HX_EDIT.exists() and unicorn is not None, 'needs HX Edit.exe and unicorn')
    def test_the_patched_calls_skip_only_while_the_flag_is_set(self):
        # installKeepModel run (node) over a copy of HX Edit.exe's handler at a relocated base, then the
        # patched calls executed (unicorn) with 0x21a470 standing in as "eax = row + 0x1000; ret 4".
        image = ExeImage(HX_EDIT)
        region_at, region_size = 0x217000, 0x4000
        region = image.read(region_at, region_size)
        view = view_text()
        install = view[view.index('  const keepModelSites = ['):view.index('  // grid list: add a tile')]
        guards_match = view[view.index('  function guardsMatch(guards) {'):]
        guards_match = guards_match[:guards_match.index('\n  }\n') + 4]
        base, page = 0x00c10000, 0x20000000
        out = json.loads(node(r'''
const mem=new Map();
class P{constructor(v){this.v=Number(BigInt.asUintN(32,BigInt(v)));}
 add(n){return new P(this.v+(n instanceof P?n.v:Number(n)));}
 toUInt32(){return this.v;} isNull(){return this.v===0;} equals(o){return o.v===this.v;}
 readU8(){return mem.get(this.v)??0;} writeU8(b){mem.set(this.v,b&255);}
 readS32(){let x=0;for(let i=3;i>=0;i--)x=x*256+(mem.get(this.v+i)??0);return x|0;}
 readU32(){return this.readS32()>>>0;}
 writeS32(x){x=x>>>0;for(let i=0;i<4;i++)mem.set(this.v+i,(x>>>(8*i))&255);}
 writePointer(p){this.writeS32(p.v);} readPointer(){return new P(this.readU32());}
 readByteArray(n){return Uint8Array.from({length:n},(_,i)=>mem.get(this.v+i)??0).buffer;}
 writeByteArray(a){a.forEach((b,i)=>mem.set(this.v+i,b));}}
const ptr=v=>new P(typeof v==='string'?(v.startsWith('0x')?parseInt(v,16):parseInt(v,10)):v),NULL=new P(0);
const base=new P(%d);
Buffer.from('%s','hex').forEach((b,i)=>mem.set(base.v+%d+i,b));
let allocs=0;
const Process={pageSize:4096,getModuleByName:()=>({getExportByName:()=>'VirtualAlloc'})};
function NativeFunction(){return()=>{allocs++;return new P(%d);};}
const Memory={patchCode:(at,size,write)=>write(at)};
''' % (base, region.hex(), region_at, page) + guards_match + install + r'''
const first=installKeepModel(),again=installKeepModel();   // loaded again into the same HX Edit: the same stubs
const dump=(at,n)=>Buffer.from(new P(at).readByteArray(n)).toString('hex');
console.log(JSON.stringify({first:{flag:first.flag.v,counts:first.counts.map(c=>c.v)},again:{flag:again.flag.v,counts:again.counts.map(c=>c.v)},
  allocs,page:dump(%d,4096),region:dump(base.v+%d,%d)}));
''' % (page, region_at, region_size)))
        self.assertEqual(out['allocs'], 1)
        self.assertEqual(out['first'], {'flag': page, 'counts': [page + 4, page + 8, page + 12]})
        self.assertEqual(out['again'], out['first'])
        patched = bytes.fromhex(out['region'])
        changed = [region_at + i for i in range(region_size) if patched[i] != region[i]]
        self.assertTrue(all(any(site <= at < site + 5 for site in (0x217802, 0x21790b, 0x2179e3)) for at in changed), changed)

        # (unicorn probes memory with an access violation it handles itself on Windows; faulthandler would print it)
        if faulthandler.is_enabled():
            faulthandler.disable()
            self.addCleanup(faulthandler.enable)
        emu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        emu.mem_map(base + region_at, region_size)
        emu.mem_write(base + region_at, patched)
        # 0x21a470 stands in: eax = [esp+4] + 0x1000; ret 4
        emu.mem_write(base + 0x21a470, bytes.fromhex('8b4424040500100000c20400'))
        emu.mem_map(page, 0x1000)
        emu.mem_write(page, bytes.fromhex(out['page']))
        emu.mem_map(0x30000000, 0x10000)
        cases = ((0x2177ff, 0x217807, x86_const.UC_X86_REG_ESI, 0),   # cva!, a cab's category
                 (0x217908, 0x217910, x86_const.UC_X86_REG_ESI, 1),   # cva!, the other categories
                 (0x2179e0, 0x2179e8, x86_const.UC_X86_REG_EAX, 2))   # sbl!, the column's selection
        for start, end, row_register, index in cases:
            for flag in (0, 1):
                with self.subTest(site=hex(start), flag=flag):
                    emu.mem_write(page, bytes([flag]))
                    count = int.from_bytes(emu.mem_read(page + 4 + 4 * index, 4), 'little')
                    emu.reg_write(x86_const.UC_X86_REG_ESP, 0x30008000)
                    emu.reg_write(x86_const.UC_X86_REG_EAX, 0)
                    emu.reg_write(x86_const.UC_X86_REG_ESI, 0)
                    emu.reg_write(row_register, 0x00abc000)
                    emu.reg_write(x86_const.UC_X86_REG_EDI, 0x00555000)
                    emu.emu_start(base + start, base + end, count=50)
                    self.assertEqual(emu.reg_read(x86_const.UC_X86_REG_ESP), 0x30008000)     # the row popped either way
                    self.assertEqual(emu.reg_read(x86_const.UC_X86_REG_ECX), 0x00555000)
                    after = int.from_bytes(emu.mem_read(page + 4 + 4 * index, 4), 'little')
                    if flag:
                        self.assertEqual(after, count + 1)                                  # skipped and counted
                        self.assertNotEqual(emu.reg_read(x86_const.UC_X86_REG_EAX), 0x00abd000)
                    else:
                        self.assertEqual(after, count)
                        self.assertEqual(emu.reg_read(x86_const.UC_X86_REG_EAX), 0x00abd000)  # HX Edit's own call, its row


class ExeImage:
    """HX Edit.exe's sections, read by RVA (no third-party PE reader)."""

    def __init__(self, path):
        self.data = Path(path).read_bytes()
        pe = int.from_bytes(self.data[0x3c:0x40], 'little')
        count = int.from_bytes(self.data[pe + 6:pe + 8], 'little')
        optional = int.from_bytes(self.data[pe + 20:pe + 22], 'little')
        at = pe + 24 + optional
        self.sections = []
        for _ in range(count):
            vsize, va, rawsize, raw = (int.from_bytes(self.data[at + 8 + 4 * i:at + 12 + 4 * i], 'little') for i in range(4))
            self.sections.append((va, max(vsize, rawsize), raw))
            at += 40

    def read(self, rva, size):
        for va, length, raw in self.sections:
            if va <= rva < va + length:
                return self.data[raw + rva - va:raw + rva - va + size]
        raise ValueError(hex(rva))


if __name__ == '__main__':
    unittest.main()
