"""Adding a NAM capture to a full preset (Nick, 2026-11-26 ~12:53, preset 006, owner-trials 20261126-121349-72343303).

P1: the picker's NAM tiles read 48% except Deluxe Reverb's 36%: a capture not measured yet took its model's figure,
which followed the newest capture measured (36 or 27 of 75), so the tiles changed from one day to another.
P2: a capture clicked for a "+" was refused by HX Edit (-8611, four times) and the page said only "HX Edit did not
make that change.": HX Edit admits a block while the meter's use, less the block replaced, plus the new model's own
catalog figure (a NAM block: 36 of 75, 48%) is at most 75; the page and focus_view.js counted the capture's measured
figure, or let it through.
"""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_workbench import run_js  # noqa: E402
from test_focus_view import run_js_source  # noqa: E402

NAM = 'HD2_AmpNAMLite'
DELUXE, JCM, NEW = '4' * 64, 'a' * 64, 'c' * 64


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def between(whole, start, end):
    at = whole.index(start)
    return whole[at:whole.index(end, at + len(start))]


class PageCostTests(unittest.TestCase):
    def page_costs(self, expression):
        page = text('workbench.html')
        piece = between(page, 'const costOf = key => {', '\n// The cost key of a capture')
        return run_js_source(
            'let costs = ' + json.dumps({NAM: 36, NAM + '#' + DELUXE: 27, NAM + '#' + JCM: 36, 'HD2_Chorus': 4.1}) + ';\n'
            'const catalog = {nam: ["' + NAM + '"], loads: {"' + NAM + '": 36, "HD2_Chorus": 4.5, "HD2_Lead": 25.5}};\n' + piece,
            expression)

    def test_p1_an_unmeasured_capture_costs_the_firmwares_declared_nam_figure(self):
        out = self.page_costs(f'[costOf("{NAM}#{DELUXE}"), costOf("{NAM}#{JCM}"), costOf("{NAM}#{NEW}"), costOf("{NAM}"),'
                              f' costOf("HD2_Chorus"), costOf("HD2_Lead"), admitOf("{NAM}"), admitOf("HD2_Chorus")]')
        self.assertEqual(out, [27, 36, 36, 36, 4.1, 25.5, 36, 4.5])
        # never another capture's figure: the model's measured one (27 now, the newest) is not used for a new capture
        out = self.page_costs(f'(costs["{NAM}"] = 27, [costOf("{NAM}#{NEW}"), costOf("{NAM}")])')
        self.assertEqual(out, [36, 36])

    def test_p2_whether_a_choice_fits_is_counted_as_hx_edit_counts_it(self):
        page = text('workbench.html')
        facts = between(page, 'function choiceFacts(block, space, item) {', '\n}\n')
        self.assertIn('need = admitOf(item.symbol);', facts)
        self.assertIn('need = isNam(block) ? 0 : admitOf(catalog.nam[0]);', facts)
        self.assertEqual(facts.count('full = !inUse && !!space && Number.isFinite(need) && need > space.left + 1e-6;'), 2)
        self.assertIn("'HX Edit needs ' + costText(need) + ' of DSP ' + (block.dsp + 1) + ' free for it, '", facts)
        rule = between(page, 'function pickRule(block, item, how) {', '\n}\n')
        self.assertLess(rule.index('if (f.full) { toast('), rule.index('pickCapture(block, item.capture);'))
        self.assertIn("toast(f.name + ' does not fit: ' + f.why + '. Remove or change a block on Path ' + (block.dsp + 1) + ' first.')", rule)


class ScriptRoomTests(unittest.TestCase):
    def test_p2_nicks_four_refusals_and_two_adds_by_hx_edits_rule(self):
        costs = {'admit': {NAM: 36, 'HD2_AmpArchetypeClean': 23.05, 'HD2_AmpLine6Litigator': 17},
                 'real': {NAM: 27, NAM + '#' + DELUXE: 27, 'HD2_AmpArchetypeClean': 23.0, 'HD2_AmpLine6Litigator': 17.0}}
        room = lambda used, now, then: run_js(['focus_view.js'], f'focusRoom({json.dumps({"used": used, "budget": 75})}, {json.dumps(costs)}, '
                                                                 f'{json.dumps(now)}, {json.dumps(then)}, 0)')
        self.assertIsNotNone(room(65.2, 'HD2_AmpArchetypeClean', NAM + '#' + DELUXE))   # 12:52:46, the swap: refused
        self.assertIsNotNone(room(42.2, None, NAM + '#' + DELUXE))                      # 12:53:08-56, the adds: refused
        self.assertIsNone(room(25.2, None, NAM + '#' + DELUXE))                         # 12:54:32: added
        self.assertIsNone(room(52.2, None, 'HD2_AmpLine6Litigator'))                    # 12:54:44: added
        script = text('focus_view.js')
        self.assertIn('const costsNow = () => ({admit: estimates, real: measured});', script)
        self.assertEqual(script.count('], costsNow(), '), 3)

    def test_p2_hx_edits_refusal_is_said_plainly(self):
        out = run_js(['focus_view.js'], '[focusRefusal({message: "NAM target binding: adding the block was rejected (-8611)"}, 0),'
                                        ' focusRefusal({message: "NAM target binding: adding the block was rejected (-8212)"}, 0),'
                                        ' focusRefusal("model change was rejected (-8611)", null)]')
        self.assertEqual(out, ['HX Edit refused it: not enough room on DSP 1 for that block by its own count. Remove or change a block on Path 1 first.',
                               None, 'HX Edit refused it: not enough room for that block by its own count. Remove or change a block first.'])
        script = text('focus_view.js')
        self.assertIn("const refused = ['add', 'capture', 'model'].includes(command.action) ? focusRefusal(error, command.dsp) : null;", script)
        self.assertIn("if (refused) send({type: 'dspNotice', text: refused});", script)


if __name__ == '__main__':
    unittest.main()
