"""The block picker's Guitar / Bass side, chosen by us, never changes the block's model. No device.

HX Edit's "cva!" handler (0x217120, from 0x2172eb) refills the model column for the new side and then
hands each row of the block's own model to 0x21a470, the same call a click on a model row makes: a
"@model" write and an undo step "Change Model". Seen live on preset 032 (Solo Lead OD). The replay
below plays that handler against tone_view.js's chooseSubcategory / keepBlockModel.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'


@unittest.skipUnless(shutil.which('node'), 'Node is required for the picker-side replay')
class PickerSideKeepsTheModelTests(unittest.TestCase):
    def test_our_side_choice_does_not_write_the_model_and_keeps_its_row_selected(self):
        view = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        start = view.index('  function chooseSubcategory(controller, value) {')
        side = view[start:view.index('  // grid list: add a tile', start)]
        self.assertIn('function keepBlockModel(args)', side)
        # The hook that applies it sits on the model picker's own model choice.
        hook = view[view.index('Interceptor.attach(base.add(0x21a470)'):]
        self.assertIn('keepBlockModel(args)', hook[:hook.index('});')])
        code = r'''
const assert=require('node:assert/strict');
const NULL={isNull:()=>true,equals:()=>false};
const ptr=value=>({isNull:()=>false,readPointer:()=>value,add:()=>ptr(value)});
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
let thread=1;const Process={getCurrentThreadId:()=>thread};
let listReports=10,menuSelectReady=null,choosingSide=false,sideThread=null;
const subcategoryChanged=0x21617663;
const writes=[];
// HX Edit's 0x21a470: returns at once without a model; otherwise the "@model" write (an undo step).
function pickModel(model){
  const args=[model];
  keepBlockModel(args);
  if(args[0]===NULL) return;
  writes.push(args[0]);
}
// HX Edit's "cva!" handler: the column refilled for the side (no selection), then the block's model re-chosen.
let elsewhere=null;   // a model chosen on another thread while ours runs (it must stay HX Edit's)
function menuSelect(m,value,event,redraw){
  assert.equal(event,subcategoryChanged);
  if(elsewhere){const was=thread;thread=2;pickModel(elsewhere);thread=was;}
  m.value=value;
  column.rows=value===2?['Cali Bass','SV Beast Nrm']:['Brit Plexi Brt','Solo Lead OD','Cali Rectifire','Cali Bass'];
  column.selected=-1;
  for(const label of column.rows) if(label==='Solo Lead OD') pickModel(label);
}
''' + side + r'''
// Our side (the block was selected, its category opens on All): no model write, its row selected again.
chooseSubcategory(controller,99);
assert.equal(menu.value,99);
assert.deepEqual(writes,[]);
assert.equal(column.rows[column.selected],'Solo Lead OD');
assert.equal(choosingSide,false);
// A side the block's model is not on: nothing written, nothing selected.
chooseSubcategory(controller,2);
assert.deepEqual(writes,[]);
assert.equal(column.selected,-1);
// The player's own pick in the dropdown stays HX Edit's (stock behaviour, as before).
column.rows=['Solo Lead OD'];column.selected=0;
menuSelect(menu,1,subcategoryChanged,1);
assert.deepEqual(writes,['Solo Lead OD']);
// Same side already shown: the menu is not touched at all.
menu.value=99;column.selected=0;
chooseSubcategory(controller,99);
assert.deepEqual(writes,['Solo Lead OD']);
// A model chosen on another thread during our side choice is left alone; after it, a click is HX Edit's.
elsewhere='Cali Rectifire';column.rows=['Brit Plexi Brt','Solo Lead OD','Cali Rectifire'];column.selected=1;
chooseSubcategory(controller,1);
assert.deepEqual(writes,['Solo Lead OD','Cali Rectifire']);
elsewhere=null;
pickModel('Brit Plexi Brt');
assert.deepEqual(writes,['Solo Lead OD','Cali Rectifire','Brit Plexi Brt']);
assert.equal(sideThread,null);
// A side choice that throws leaves nothing behind: the next click writes as HX Edit's own.
const keep=menuSelect;menuSelect=()=>{throw new Error('menu gone');};
assert.throws(()=>chooseSubcategory(controller,2),/menu gone/);
menuSelect=keep;
assert.equal(choosingSide,false);assert.equal(sideThread,null);
pickModel('Solo Lead OD');
assert.equal(writes.length,4);
'''
        run = subprocess.run(['node'], input=code, capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_the_hook_is_only_set_on_the_hx_edit_build_it_was_read_from(self):
        # (another build: no hook at all; our side choice may record "Change Model" there, as before the fix)
        view = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        self.assertIn("const keepModelGuards = { '21a470': '558bec6aff68????????64a100000000', '21a4a4': '8b7d0885ff0f84' };", view)
        hook = view[view.index('if (guardsMatch(keepModelGuards)) {'):]
        hook = hook[:hook.index("stage: 'model-keep-guard-failed'});")]
        self.assertIn('Interceptor.attach(base.add(0x21a470), {', hook)
        self.assertEqual(view.count('base.add(0x21a470)'), 1)
        # guardsMatch is the one the drop and the picker already use ('??': the relocated handler address)
        self.assertIn("return want === '??' || want === byte;", view)

    def test_a_stock_amp_picked_after_a_nam_block_leaves_no_step(self):
        # The page's select of a block just added at a "+" (or a click on it) makes HX Edit show the block's
        # category (0x21e500) and blockSide choose its remembered side: Solo Lead OD on 032 after a NAM block
        # ("subcategory 99" then an undo step, live 2026-11-24 16:46 and 18:56). No model write now.
        view = (ROOT / 'tone_view.js').read_text(encoding='utf-8')
        start = view.index('  const sideBlocks = new Map();')
        side = view[start:view.index('  // grid list: add a tile', start)]
        code = r'''
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
const send=()=>{};const Process={getCurrentThreadId:()=>1};
let listReports=10,menuSelectReady=null,choosingSide=false,sideThread=null;
const subcategoryChanged=0x21617663,writes=[];
function pickModel(model){const args=[model];keepBlockModel(args);if(args[0]===NULL)return;writes.push(args[0]);}
function menuSelect(m,value){m.value=value;column.selected=-1;for(const label of column.rows) if(label==='Solo Lead OD') pickModel(label);}
''' + side + r'''
blockSide(controller);                       // the amp selected: its side (All) shown, its row selected
assert.equal(menu.value,99);
assert.deepEqual(writes,[]);
assert.equal(column.rows[column.selected],'Solo Lead OD');
blockSide(controller);                       // the same block again (a reading, an Undo's reselect): nothing
assert.deepEqual(writes,[]);
menu.value=1;block='block4';                 // another amp, its side shown again: still no write
blockSide(controller);
assert.deepEqual(writes,[]);
'''
        run = subprocess.run(['node'], input=code, capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
