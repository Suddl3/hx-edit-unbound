"""The DSP costs measured from the Floor's meter (dsp_costs.py) when the Floor stops answering: live check 2026-11-24
17:51-17:55 on preset 032 (owner-trials/20261124-175132-02672395/trace.jsonl). After an add of a second NAM block
(path 1: 32.1 -> 59.1, HD2_AmpNAMLite 27.0) its Undo was refused with HX Edit's device timeout (-8212); the editor's
buffer took the block away but the meter stayed at 59.1, then read 0.0 on both paths, and "one block fewer, 59.1 ->
0.0" was saved as HD2_AmpNAMLite 59.1. No editor process, no device."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dsp_costs  # noqa: E402
import workbench  # noqa: E402
from test_focus_view import FakePane, resources  # noqa: E402

NAM = 'HD2_AmpNAMLite'
ENDS = ('HD2_AppDSPFlow1Input', 'HD2_AppDSPFlow2Input', 'HD2_AppDSPFlowOutput', 'HD2_AppDSPFlowOutput', 'HD2_AppDSPFlowSplitY', 'HD2_AppDSPFlowJoin')
ENDS_ID = ('inputA', 'inputB', 'outputA', 'outputB', 'split', 'join')
UNDO_REFUSED = {'type': 'toneTrace', 'reason': 'focus-view', 'stage': 'swap-failed', 'key': 'undo',
                'error': 'NAM target binding: undo was refused (-8212)'}


def chain(path1, path2=('HD2_Chorus', 'HD2_Reverb'), preset=32):
    """032 as the trace counts it: each path's input, output, split and mixer (6) and its blocks."""
    blocks = []
    for dsp, models in ((0, path1), (1, path2)):
        blocks += [{'dsp': dsp, 'id': i, 'model': m} for i, m in zip(ENDS_ID, ENDS)]
        blocks += [{'dsp': dsp, 'id': 'block%d' % k, 'model': m} for k, m in enumerate(models)]
    return {'preset': {'setlist': 3, 'number': preset}, 'blocks': blocks}


def meter(used1, used2):
    view = lambda used: None if used is None else {'load': used + 15, 'used': used, 'budget': 75}
    return [view(used1), view(used2)]


class DeadMeterTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / 'dsp-costs.json'
        self.costs = dsp_costs.DspCosts(self.file)
        self.costs.costs = {NAM: 27.0, 'HD2_DelaySimpleDelay': 3.3}          # the file as it was at 17:52:58

    def run_trace(self, steps):
        """steps: (seconds, path 1's blocks, meter 1, meter 2) or (seconds, message); readings every half second."""
        found = []
        for at, *rest in steps:
            if len(rest) == 1:
                if dsp_costs.device_lost(rest[0]):
                    self.costs.lost(at)
                continue
            blocks, used1, used2 = rest
            found += self.costs.observe(chain(blocks), meter(used1, used2), at)
        return found

    def trace_1753(self, *, told):
        before = ('HD2_DistKinkyBoost', NAM, NAM)          # 17:52:58: the second NAM block added (9 on path 1)
        after = ('HD2_DistKinkyBoost', NAM)                # 17:53:18: the Undo taken away in the editor's buffer
        steps = [(t / 2, before, 59.1, 31.1) for t in range(0, 14)]                  # steady at 59.1 / 31.1
        steps += [(20.0, UNDO_REFUSED)] if told else []
        steps += [(20.0 + t / 2, after, 59.1, 31.1) for t in range(0, 20)]           # 17:53:18: the meter stuck
        steps += [(30.0 + t / 2, after, 0.0, 0.0) for t in range(0, 40)]             # 17:53:28: both paths 0.0
        return steps

    def test_the_trace_of_17_53_saves_nothing_with_or_without_the_device_timeout(self):
        for told in (True, False):
            with self.subTest(told=told):
                self.setUp()
                self.assertEqual(self.run_trace(self.trace_1753(told=told)), [])
                self.assertEqual(self.costs.costs[NAM], 27.0)
                self.assertFalse(self.file.exists())                               # nothing written

    def test_after_the_power_cycle_the_first_readings_are_not_compared_with_those_from_before(self):
        steps = self.trace_1753(told=True)
        after = ('HD2_DistKinkyBoost', NAM)
        steps += [(1830.0, after, 0.0, 31.1), (1830.0, after, None, None)]          # 18:24:05: the Floor back, then no meter
        steps += [(1856.0 + t / 2, after, 32.1, 31.1) for t in range(0, 14)]          # 18:24:31: 032 read again
        self.assertEqual(self.run_trace(steps), [])
        # and the ordinary measuring works again: Nick's re-measure, a NAM block removed and its Undo
        again = [(1870.0, ('HD2_DistKinkyBoost',), 32.1, 31.1), (1871.0, ('HD2_DistKinkyBoost',), 5.1, 31.1)]
        again += [(1873.0, after, 5.1, 31.1), (1874.0, after, 32.1, 31.1)]
        self.assertEqual(self.run_trace(again), [(NAM, 27.0), (NAM, 27.0)])

    def test_a_dead_meter_is_a_path_that_drops_to_zero_with_its_blocks_still_there(self):
        # (one path alone, too; it comes back once it reads above 0 again, and must settle before it is measured from)
        steps = [(t / 2, ('HD2_DistKinkyBoost', NAM), 32.1, 31.1) for t in range(0, 14)]
        steps += [(10.0, ('HD2_DistKinkyBoost',), 32.1, 31.1), (11.0, ('HD2_DistKinkyBoost',), 0.0, 31.1)]
        self.assertEqual(self.run_trace(steps), [])
        self.assertTrue(self.costs._dead[0])
        self.assertIsNone(self.costs._settled[0])
        back = [(12.0, ('HD2_DistKinkyBoost',), 5.1, 31.1), (12.5, ('HD2_DistKinkyBoost', NAM), 32.1, 31.1)]   # not steady yet
        self.assertEqual(self.run_trace(back), [])
        self.assertFalse(self.costs._dead[0])

    def test_a_path_that_is_really_empty_reads_zero_and_is_still_measured(self):
        # the last block removed: its meter goes to 0 (an empty path), and an add into an empty path whose meter
        # follows a poll later (it still reads 0 with the block there: not dead, it never dropped)
        steps = [(t / 2, (NAM,), 27.0, 31.1) for t in range(0, 14)]
        steps += [(10.0, (), 27.0, 31.1), (11.0, (), 0.0, 31.1)]
        steps += [(12.0 + t / 2, (), 0.0, 31.1) for t in range(0, 14)]
        steps += [(20.0, (NAM,), 0.0, 31.1), (21.0, (NAM,), 0.0, 31.1), (22.0, (NAM,), 27.0, 31.1)]
        self.assertEqual(self.run_trace(steps), [(NAM, 27.0), (NAM, 27.0)])

    def test_a_cost_is_never_more_than_its_paths_total(self):
        self.assertEqual(dsp_costs.bounded(NAM, 27.0, 59.1, True), (NAM, 27.0))
        self.assertIsNone(dsp_costs.bounded(NAM, 59.1, 59.1, True))           # 17:53:28: the whole path, others still there
        self.assertEqual(dsp_costs.bounded(NAM, 27.0, 27.0, False), (NAM, 27.0))   # alone on its path: all of it
        self.assertIsNone(dsp_costs.bounded(NAM, 30.0, 27.0, False))
        self.assertIsNone(dsp_costs.bounded(NAM, 0.0, 27.0, False))
        self.assertIsNone(dsp_costs.bounded(NAM, 80.0, 90.0, False))

    def test_a_figure_far_from_the_kept_one_waits_for_a_second_that_agrees(self):
        self.costs.costs[NAM] = 59.1                                             # Nick's file now
        steps = [(t / 2, ('HD2_DistKinkyBoost', NAM), 32.1, 31.1) for t in range(0, 14)]
        steps += [(10.0, ('HD2_DistKinkyBoost',), 32.1, 31.1), (11.0, ('HD2_DistKinkyBoost',), 5.1, 31.1)]   # remove: 27.0
        self.assertEqual(self.run_trace(steps), [])
        self.assertEqual(self.costs.held, [(NAM, 27.0)])
        self.assertEqual(self.costs.costs[NAM], 59.1)
        undo = [(13.0, ('HD2_DistKinkyBoost', NAM), 5.1, 31.1), (14.0, ('HD2_DistKinkyBoost', NAM), 32.1, 31.1)]   # its Undo
        self.assertEqual(self.run_trace(undo), [(NAM, 27.0)])
        self.assertEqual(dsp_costs.DspCosts(self.file).costs[NAM], 27.0)
        # close to the kept figure: at once (a small move, max(2, 15%)); a far one that disagrees stays held
        self.assertEqual(dsp_costs.confirm_gap(27.0), 4.05)
        self.assertEqual(dsp_costs.confirm_gap(3.3), 2.0)

    def test_the_messages_that_say_the_floor_is_not_answering(self):
        lost = dsp_costs.device_lost
        self.assertTrue(lost(UNDO_REFUSED))
        self.assertTrue(lost({'type': 'automaticSlotStatus', 'state': 'disconnected', 'checked': 0, 'pending': None}))
        self.assertTrue(lost({'type': 'dspMeter', 'event': 'read-failed', 'error': 'access violation'}))
        self.assertFalse(lost({'type': 'toneTrace', 'reason': 'focus-view', 'stage': 'swap-failed', 'error': 'HX Edit refused (-3)'}))
        self.assertFalse(lost({'type': 'automaticSlotStatus', 'state': 'complete'}))
        self.assertFalse(lost({'type': 'workbench', 'event': 'dsp-seen'}))
        self.assertFalse(lost(None))

    def test_the_pane_stops_measuring_when_told_and_traces_what_it_held(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        clock = [100.0]
        view = workbench.WorkbenchView(resources(folder.name), process_factory=lambda *a, **k: FakePane(a), exe='FocusView.exe',
                                       costs_file=self.file, clock=lambda: clock[0])
        self.addCleanup(view.close)
        put, traced = [], []
        original = view.queue.put
        view.queue.put = lambda item, *a, **k: (put.append(item), original(item, *a, **k))
        view.trace = traced.append
        view.receive(UNDO_REFUSED)
        self.assertIn(('deviceLost', None), put)
        view._handle('deviceLost', None)
        self.assertEqual(view.costs._quiet_until, 100.0 + dsp_costs.LOST_QUIET)
        self.assertIn({'type': 'workbench', 'event': 'dsp-device-lost'}, traced)
        view.costs.held = [(NAM, 27.0)]
        view.costs.costs[NAM] = 59.1
        view.costs.observe = lambda *a: []
        view._idle()
        self.assertIn({'type': 'workbench', 'event': 'dsp-cost-held', 'model': NAM, 'cost': 27.0, 'kept': 59.1}, traced)


if __name__ == '__main__':
    unittest.main()
