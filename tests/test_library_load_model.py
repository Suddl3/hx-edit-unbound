"""Library Use / Put on the Floor read the selected block's model through namView.presetTree() (tone_view boundModel).

presetTree() returned readCurrentPreset's raw wrapper {tree: {...}} although it is documented (and read) as the tree
itself, so boundModel always found no model and every library load failed with "Could not read the model of the
selected block" (seen on a Helix Floor, 2026-11-27)."""
import json
import re
import subprocess
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'


def run_node(script):
    return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)


class PresetTreeShape(unittest.TestCase):
    def setUp(self):
        view = (SRC / 'nam_view.js').read_text(encoding='utf-8')
        self.line = re.search(r'^\s*presetTree: (.+),\s*$', view, re.M).group(1)
        tone = (SRC / 'tone_view.js').read_text(encoding='utf-8')
        self.bound = tone[tone.index('  function boundModel()'):tone.index('  function pickModel(')]

    def test_presetTree_returns_the_tree_and_boundModel_reads_the_model(self):
        result = run_node('''
          let next = null;
          const readCurrentPreset = (lenient, raw) => next;
          const presetTree = ''' + self.line + ''';
          const namView = {presetTree};
          const active = {block: 'block0', controller: {add: k => ({readS32: () => (k === 0x80 ? 0 : -1)})}};
        ''' + self.bound + '''
          const out = [];
          next = {tree: {dsp0: {block0: {'@model': 'HD2_AmpNAMLite'}}}};
          out.push(Object.keys(presetTree()), boundModel());
          next = {reason: 'preset-changing'};
          out.push(presetTree(), boundModel());
          console.log(JSON.stringify(out));
        ''')
        self.assertEqual(result, [['dsp0'], 'HD2_AmpNAMLite', {'reason': 'preset-changing'}, None])


if __name__ == '__main__':
    unittest.main()
