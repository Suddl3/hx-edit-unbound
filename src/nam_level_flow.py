"""The Level page's work, off the page's own loop: scan presets, apply a standard, undo.

command(action, **data) talks to HX Edit (tone_view.js level actions) and raises on an error reply;
changed() is called, from any thread, whenever view() has something new for the page. One job runs
at a time (a scan, an Apply or an Undo); each puts the Floor back on the preset and snapshot the
player started on.

Scan: each chosen preset is loaded (MIDI Program Change, nam_level.load_preset) unless it is the
current one, its routing is switched for measuring (input USB 7/8, outputs USB 1/2: silent on the amp),
every chosen snapshot is recalled and measured, and the routing is put back. Nothing is saved.

Apply: one change per snapshot (the page sends them; the standard and the suggested changes are
worked out on the page from the measurements). The current preset alone is changed, not saved,
as before. Several presets are each changed and saved (HX Edit's own Save Preset), since loading the
next one would drop unsaved changes; what each had before is kept in nam_level.RECORDS for Undo.
"""

from datetime import datetime
from pathlib import Path
import re
from threading import Event, Lock, Thread
import time
from uuid import uuid4

import nam_level


class LevelError(Exception):
    pass


SNAPSHOTS_CONTROLLER = 19


def identity(preset):
    """Which preset something belongs to: {setlist, preset, name} (a preset header, or a measured row).
    The same number in another setlist is another preset."""
    preset = preset or {}
    return {'setlist': preset.get('setlist'), 'preset': preset.get('preset'), 'name': preset.get('name') or ''}


def same_preset(header, ident):
    """Whether HX Edit's preset header is that preset: the same setlist and number, and the same name
    when both have one (another preset put in that place)."""
    now, ident = identity(header), identity(ident)
    return (isinstance(now['setlist'], int) and now['setlist'] == ident['setlist'] and
            now['preset'] == ident['preset'] and
            (not now['name'] or not ident['name'] or now['name'].strip() == ident['name'].strip()))


def describe(ident):
    # (no setlist number: HX Edit counts setlists from 0 in the header, the Floor from 1)
    return f'preset {ident.get("preset") or 0:03d}' + (f' "{ident["name"]}"' if ident.get('name') else '')


def scanned_snapshots(snapshots, mode='all'):
    """The snapshots a scan measures: 'all', or 1 to n (4: the usual four footswitches; 1: presets that
    do not use snapshots). Whether an unnamed snapshot is in use cannot be told from the preset, so the
    player chooses, and All is the default: nothing is missed."""
    if mode == 'all':
        return list(snapshots)
    return [s for s in snapshots if s.get('number', 9) <= int(mode)]


def alike_rows(rows):
    """One preset's measured snapshots, those that measured the same (loudness and peak within 0.1 dB, the
    same output Level) as one row: {'snapshot': first, 'snapshots': [...]}."""
    merged = []
    for row in sorted(rows, key=lambda r: r['snapshot']):
        twin = next((m for m in merged if row['lufs'] is not None and m['lufs'] is not None and
                     abs(m['lufs'] - row['lufs']) <= 0.1 and abs((m['peak'] or 0) - (row['peak'] or 0)) <= 0.1 and
                     m.get('level') == row.get('level') and not m['note'] and not row['note']), None)
        if twin is None:
            merged.append(dict(row, snapshots=list(row.get('snapshots') or [row['snapshot']])))
        else:
            twin['snapshots'] += row.get('snapshots') or [row['snapshot']]
            twin['snapNames'] = twin.get('snapNames', []) + row.get('snapNames', [])
    return merged


class LevelFlow:
    SETTLE = 0.35     # s after a snapshot recall (HX Edit reports it ~150 ms later)
    LOADED = 0.6      # s after a preset load is seen, for its blocks to settle

    def __init__(self, command, changed, *, di, meter_factory=None, load_preset=None,
                 restore_file=nam_level.INTERRUPTED, records_file=nam_level.RECORDS,
                 guitar_file=nam_level.GUITAR_FILE, guitars_file=None, history_file=None, nam_input=None,
                 sleep=time.sleep, clock=time.monotonic):
        self.command, self.changed = command, changed
        # di: where a build keeps NAM's input file (one more place to look); nam_input(): finds it.
        self.di = di
        folder = Path(guitar_file).parent
        self.guitars_file = Path(guitars_file) if guitars_file else folder / nam_level.GUITARS_FILE.name
        self.history_file = Path(history_file) if history_file else folder / nam_level.HISTORY_FILE.name
        self.takes = folder / 'level-guitars'
        self.nam_input = nam_input or (lambda: nam_level.nam_input([di] if di else []))
        self._nam = (None, -1e9)          # (found, when looked): the page asks often, the disk is read seldom
        self.scanned_with = None           # the test signal's name, for "last leveled with" on Apply
        self.meter_factory = meter_factory or nam_level.Meter
        self.load_preset = load_preset or nam_level.load_preset
        self.restore_file, self.records_file, self.guitar_file = restore_file, records_file, guitar_file
        self.sleep, self.clock = sleep, clock
        self.lock = Lock()
        self.cancelled = Event()
        self.closed = Event()
        self.worker = None
        self.watcher = None
        self._view = {'running': None, 'progress': '', 'fraction': None, 'rows': [], 'skipped': {}, 'message': '', 'error': None,
                      'current': None, 'presets': [], 'undo': None}

    # ---- the page's view --------------------------------------------------------------------------
    def view(self):
        with self.lock:
            view = {key: (list(value) if isinstance(value, list) else value) for key, value in self._view.items()}
        guitars = self.guitars()
        view['guitars'] = [{k: g.get(k) for k in ('id', 'name', 'peak', 'when')} for g in guitars['guitars']]
        view['lastGuitar'] = guitars['last']
        view['nam'] = self._nam_found()
        view['leveled'] = nam_level.load_history(self.history_file)
        records = nam_level.load_records(self.records_file)
        view['undo'] = None if not records else {
            'presets': [entry.get('preset', {}).get('preset') for entry in records['presets']],
            'saved': bool(records.get('saved')), 'when': records.get('when')}
        return view

    def guitars(self):
        return nam_level.load_guitars(self.guitars_file, self.guitar_file)

    NAM_LOOK = 10.0   # s between looks for NAM's input file

    def _nam_found(self):
        found, when = self._nam
        now = time.monotonic()
        if now - when >= self.NAM_LOOK:
            found = self.nam_input() is not None
            self._nam = (found, now)
        return found

    def _update(self, **values):
        with self.lock:
            self._view.update(values)
        self.changed()

    @property
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    # ---- opening the page -------------------------------------------------------------------------
    def open(self, presets=None):
        """The current preset and its snapshots (nothing changes), after putting right a measurement
        that was cut short. presets: [[number, name]] of the setlist, for choosing several."""
        state = self.command('levelState')
        note = ''
        if not self.busy:
            note = self.recover(state.get('prepared'))
            if note:
                state = self.command('levelState')
        self._current(state)
        self._update(presets=presets or [], message=note + 'Choose a standard, then Scan.', error=None)
        if self.watcher is None:
            self.watcher = Thread(target=self._watch, daemon=True)
            self.watcher.start()

    def _current(self, state):
        current = {'preset': state.get('preset'), 'snapshot': state.get('snapshot'),
                   'snapshots': state.get('snapshots') or []}
        setlist = (state.get('preset') or {}).get('setlist')
        with self.lock:
            same = self._view.get('current') == current
            # Measurements belong to the setlist they were made in: another setlist's preset 030 is
            # another preset, so they go (a scan there starts afresh).
            stale = isinstance(setlist, int) and not self.busy and any(
                row.get('setlist') != setlist for row in self._view['rows'])
        if stale:
            self._update(rows=[], skipped={})
        if not same:
            self._update(current=current)

    WATCH = 1.5       # s between looks at which preset HX Edit is on, while the page is open and idle

    def _watch(self):
        # The page follows HX Edit: a preset chosen on the Floor or in HX Edit shows at once.
        while not self.closed.wait(self.WATCH):
            if self.busy:
                continue
            try:
                state = self.command('levelState')
            except Exception:              # HX Edit busy or gone: look again later
                continue
            if state.get('preset') and not self.busy:
                self._current(state)

    def recover(self, prepared=False):
        """Put back the routing a cut-short measurement left behind (this preset only); a note or ''."""
        saved = nam_level.interrupted(self.restore_file)
        if not saved and not prepared:
            return ''
        reply = self.command('levelRecover', **{k: v for k, v in (saved or {}).items() if k != 'ties'})
        if reply.get('kept') and not saved:
            self._keep(reply['kept'])                 # the editor's record, of another preset: kept on disk
        if reply.get('other'):
            return ''                                 # another preset: kept for when it comes back
        if (saved or {}).get('ties') and reply.get('recovered'):
            self._put_back(saved['ties'], saved.get('preset'))   # the output Level per snapshot, as it was
        nam_level.forget_inputs(self.restore_file)
        return ('Measuring was cut short last time; the routing is back as it was (not saved). '
                if reply.get('recovered') else '')

    # ---- jobs -------------------------------------------------------------------------------------
    def _start(self, name, target, *args):
        if self.busy:
            raise LevelError('Level is busy; wait for it or Cancel.')
        self.cancelled.clear()
        self._update(running=name, error=None, progress='', fraction=None)
        self.worker = Thread(target=self._run, args=(name, target, args), daemon=True)
        self.worker.start()

    def _run(self, name, target, args):
        message, error = '', None
        try:
            message = target(*args)
        except Exception as failure:          # reported on the page; the routing was already put back
            error = str(failure) or failure.__class__.__name__
            message = {'scan': 'Scan stopped: ', 'apply': 'Apply stopped: ', 'undo': 'Undo stopped: ',
                       'guitar': 'Measuring your guitar stopped: '}[name] + error
        self._update(running=None, progress='', fraction=None, message=message, error=error)

    def cancel(self):
        self.cancelled.set()

    def close(self, wait=15.0):
        self.closed.set()
        self.cancel()
        if self.worker is not None:
            self.worker.join(timeout=wait)

    def scan(self, presets, snapshots='all', signal=None):
        """presets: preset numbers of the current setlist (the current one when empty); snapshots: 'all'
        or 1 to n (scanned_snapshots); signal: a saved guitar's id (the last one when None) or 'nam'."""
        count = 'all' if snapshots == 'all' else max(1, min(8, int(snapshots)))
        numbers = [int(n) for n in presets if 0 <= int(n) <= 127] if presets else []
        self._start('scan', self._scan, numbers, count, self._signal(signal))

    def apply(self, changes, target=None):
        """changes: {preset number: {snapshot: dB}}, checked against the measurements; target: {value,
        metric} the page levelled to, for each preset's "last leveled" note."""
        clean, who = {}, {}
        rows = {(row['preset'], row['snapshot']): row for row in self.view()['rows']}
        for preset, snaps in changes.items():
            for snapshot, change in snaps.items():
                row = rows.get((int(preset), int(snapshot)))   # a row: one snapshot, or several alike
                if row is None or row.get('lufs') is None:
                    raise LevelError(f'Preset {int(preset):03d} snapshot {snapshot} has not been measured.')
                # The preset it was measured in: its setlist and number (and name), never the number alone.
                ident = identity(row)
                if not isinstance(ident['setlist'], int):
                    raise LevelError(f'Preset {int(preset):03d} was measured without its setlist; scan it again.')
                if who.setdefault(int(preset), ident) != ident:
                    raise LevelError(f'Preset {int(preset):03d} was measured twice, differently; scan it again.')
                change = round(float(change), 1) + 0.0
                reason = nam_level.check_change(change, row.get('peak'))
                if reason:
                    raise LevelError(f'Preset {int(preset):03d} snapshot {snapshot}: {reason}.')
                if change:
                    for number in row.get('snapshots') or [row['snapshot']]:
                        clean.setdefault(int(preset), {})[int(number)] = change
        if len({ident['setlist'] for ident in who.values()}) > 1:
            raise LevelError('These measurements come from more than one setlist; scan again.')
        if not clean:
            raise LevelError('Nothing to change: every ticked snapshot already meets the standard.')
        self._start('apply', self._apply, clean, target, {n: who[n] for n in clean})

    def measure_guitar(self, seconds=10.0, name=''):
        """The player plays for `seconds` after a 3-2-1 countdown: two typical seconds become a saved
        guitar's test signal, with its peak at the Floor's input. A name already saved is recorded again."""
        self._start('guitar', self._guitar, seconds, name)

    def remove_guitar(self, ident):
        """Delete a saved guitar and its recording (presets it levelled keep their levels)."""
        if self.busy:
            raise LevelError('Level is busy; wait for it or Cancel.')
        data = self.guitars()
        guitar = next((g for g in data['guitars'] if g['id'] == ident), None)
        if guitar is None:
            raise LevelError('That recording is already gone.')
        file = Path(guitar['file'])
        if file.parent == self.takes or file.name == nam_level.TAKE_FILE.name:   # only its own take
            try:
                file.unlink()
            except OSError:
                pass
        data['guitars'] = [g for g in data['guitars'] if g['id'] != ident]
        if data['last'] == ident:
            data['last'] = data['guitars'][-1]['id'] if data['guitars'] else None
        nam_level.save_guitars(data, self.guitars_file)
        self._update(message=f'Deleted the recording "{guitar["name"]}".', error=None)

    COUNTDOWN = 3

    def _guitar(self, seconds, name=''):
        data = self.guitars()
        name = nam_level.guitar_name(name, data['guitars'])
        same = next((g for g in data['guitars'] if g['name'].lower() == name.lower()), None)
        ident = same['id'] if same else 'g' + uuid4().hex[:10]
        self.takes.mkdir(parents=True, exist_ok=True)
        take = self.takes / f'{ident}-{uuid4().hex[:6]}.wav'
        meter = self.meter_factory(None)
        done = Event()
        try:
            self._update(progress='Getting ready…', fraction=None)
            ready = meter.ready()
            if not ready.get('ok'):
                raise LevelError(ready.get('error') or 'The Floor\'s audio is not available.')
            for count in range(self.COUNTDOWN, 0, -1):
                if self.cancelled.is_set():
                    return 'Recording cancelled; nothing was kept.'
                self._update(progress=f'Get ready to play… {count}')
                self.sleep(1.0)

            def started():           # the measurer has begun recording: count the seconds down
                began = time.monotonic()

                def tick():
                    while not done.wait(0.25):
                        gone = time.monotonic() - began
                        self._update(progress=f'Recording: play now… {max(0, int(seconds - gone + 0.99))} s left',
                                     fraction=min(1.0, gone / seconds))
                self._update(progress=f'Recording: play now… {int(seconds)} s left', fraction=0.0)
                Thread(target=tick, daemon=True).start()
            result = meter.guitar_level(seconds, keep=take, started=started)
        finally:
            done.set()
            meter.close()
        if not result.get('ok'):
            raise LevelError(result.get('error') or 'Nothing came in.')
        guitar = {'id': ident, 'name': name, 'peak': float(result['peak']),
                  'when': datetime.now().isoformat(timespec='seconds'), 'file': str(take)}
        if same and Path(same['file']) != take:
            try:
                Path(same['file']).unlink()
            except OSError:
                pass
        data['guitars'] = [g for g in data['guitars'] if g['id'] != ident] + [guitar]
        data['last'] = ident
        nam_level.save_guitars(data, self.guitars_file)
        return (f'Recorded "{name}". Scans with it play two seconds of your playing, as you played it '
                f'(it peaks at {result["peak"]:.1f} dBFS). It stays on this PC.')

    def _signal(self, signal):
        """(file, start, peak) of the test signal and its name: a saved guitar (its id), played as
        recorded; 'nam', NAM's input file at the last guitar's level (or a humbucker's, none recorded)."""
        data = self.guitars()
        if signal == 'nam':
            path = self.nam_input()
            if path is None:
                raise LevelError('NAM\'s input file was not found on this PC.')
            last = next((g for g in data['guitars'] if g['id'] == data['last']), None)
            return path, nam_level.NAM_START, float(last['peak']) if last else nam_level.DEFAULT_PEAK, 'NAM input file'
        guitar = next((g for g in data['guitars'] if g['id'] == signal), None) or \
            next((g for g in data['guitars'] if g['id'] == data['last']), None)
        if guitar is None:
            raise LevelError('Record your guitar first: scans use your own playing as the test signal.')
        if data['last'] != guitar['id']:
            data['last'] = guitar['id']
            nam_level.save_guitars(data, self.guitars_file)
        return Path(guitar['file']), 0.0, None, guitar['name']

    def undo(self):
        if not nam_level.load_records(self.records_file):
            raise LevelError('Nothing to undo.')
        self._start('undo', self._undo)

    def _shift(self, preset, trims, sign):
        """After an Apply (sign 1) or its Undo (-1): the rows show the level the preset now has, and
        what was applied, so the same change is not offered twice."""
        with self.lock:
            rows = []
            for row in self._view['rows']:
                change = trims.get(row['snapshot']) if row['preset'] == preset else None
                if change and row.get('lufs') is not None:
                    row = dict(row, lufs=round(row['lufs'] + sign * change, 2),
                               peak=round(row['peak'] + sign * change, 2) if row.get('peak') is not None else None,
                               level=round(row['level'] + sign * change, 1) if row.get('level') is not None else None)
                    row['applied'] = round((row.get('applied') or 0) + sign * change, 1) or None
                rows.append(row)
            self._view['rows'] = rows

    # ---- steps ------------------------------------------------------------------------------------
    def _here(self):
        # Right after a recall or a routing change the preset header can read empty for a moment.
        for attempt in range(8):
            state = self.command('levelState')
            if state.get('preset'):
                return state
            self.sleep(0.25)
        raise LevelError('HX Edit has not reported the current preset yet.')

    def _goto(self, number, settle=True, setlist=None):
        """The preset `number` loaded (from this setlist), its levelState. settle False: at once (a scan
        silences it straight away and lets it settle afterwards). setlist: the setlist it must be in (a
        preset change loads by number, within whichever setlist HX Edit is on): another one stops here,
        before anything is loaded or changed."""
        def check(state):
            now = (state.get('preset') or {}).get('setlist')
            if setlist is not None and now != setlist:
                raise LevelError(f'HX Edit is on another setlist now, not the one preset {number:03d} was '
                                 'measured in; nothing more was changed. Go back to that setlist, or scan again.')
            return state
        state = check(self._here())
        if state['preset'].get('preset') == number:
            return state
        self.load_preset(number)
        deadline = self.clock() + 8
        while self.clock() < deadline:
            self.sleep(0.25)
            state = self.command('levelState')
            if (state.get('preset') or {}).get('preset') == number:
                if settle:
                    self.sleep(self.LOADED)
                return check(self._here())
        raise LevelError(f'Preset {number:03d} did not load.')

    def _home(self, start):
        """Back to the preset and snapshot the player started on."""
        preset, snapshot = (start.get('preset') or {}).get('preset'), start.get('snapshot')
        setlist = (start.get('preset') or {}).get('setlist')
        if setlist is not None and (self._here().get('preset') or {}).get('setlist') != setlist:
            return      # the player chose another setlist: the same number there is another preset
        if preset is not None:
            self._goto(preset, setlist=setlist)
        if snapshot:
            self.command('levelRecall', snapshot=snapshot)
            self.sleep(self.SETTLE)

    LANDED = 1.0      # s on a snapshot before its Level is written

    def _land(self, number):
        """Recall a snapshot and give it a full second to land (its values arrive well after HX Edit
        reports the new snapshot number)."""
        self.command('levelRecall', snapshot=number)
        start = self.clock()
        while True:
            self.sleep(0.1)
            if self.clock() - start >= self.LANDED and self.command('levelState').get('snapshot') == number:
                return
            if self.clock() - start > 5.0:
                raise LevelError(f'HX Edit did not reach snapshot {number}.')

    def _visit(self, number, action, **data):
        self._land(number)
        return self.command(action, snapshot=number, **data)

    AGREE = 0.5       # dB: two readings this close are one steady sound
    MOST = 4          # readings of a sound that moves on its own (its loudness changes by itself)
    PAUSE = 0.7       # s between readings, for delay and reverb tails of the last one to fade

    def _readings(self, meter, source, progress):
        """One snapshot's loudness: two readings; when they differ by more than AGREE (a sound that
        moves on its own: modulation, delays), up to MOST, and the middle one counts. The highest peak
        counts (headroom). 'spread': how far the readings were apart."""
        results = []
        while True:
            if results:
                self.sleep(self.PAUSE)
            self._update(progress=progress + (f', reading {len(results) + 1}' if results else '') + '…')
            result = meter.measure(start=source[0], peak=source[1])
            if not result.get('ok'):
                return result              # silent, or the signal never arrived: the caller decides
            results.append(result)
            values = sorted(r['lufs'] for r in results)
            if len(results) >= 2 and (values[-1] - values[0] <= self.AGREE or len(results) >= self.MOST):
                break
            if self.cancelled.is_set():
                break
        values = sorted(r['lufs'] for r in results)
        middle = values[len(values) // 2] if len(values) % 2 else (values[len(values) // 2 - 1] + values[len(values) // 2]) / 2
        return dict(results[0], lufs=round(middle, 2), peak=max(r['peak'] for r in results),
                    spread=round(values[-1] - values[0], 2), readings=len(results))

    def _ties(self, number, numbers, own):
        """The final outputs whose Level or Pan is on a controller, with every snapshot's value, read
        before the scan re-routes them (which drops the controller): [{dsp, controllers, values: {n:
        {key: {type, value}}}}]. own: the player's preset, which gets them back afterwards; a controller
        other than Snapshots (a pedal, MIDI) could not be put back, so that preset is not scanned. In every
        preset an output Level on such a controller is refused: Apply would replace it with Snapshots."""
        ties = [tie for tie in self.command('levelTies').get('ties') or [] if tie.get('controllers')]
        if not ties:
            return []
        for tie in ties:
            for key, controller in tie['controllers'].items():
                if controller != SNAPSHOTS_CONTROLLER and (own or key == 'gain'):
                    raise LevelError(f'Preset {number:03d}: its output {"Level" if key == "gain" else "Pan"} '
                                     'is on a pedal or another controller (not Snapshots). Level would lose '
                                     'that, so it leaves this preset alone.')
        for tie in ties:
            tie['values'] = {}
        for snapshot in numbers:
            self._update(progress=f'Reading the output level of {number:03d}, snapshot {snapshot}…')
            self._land(snapshot)
            read = {tie['dsp']: tie for tie in self.command('levelTies').get('ties') or []}
            for tie in ties:
                tie['values'][snapshot] = read.get(tie['dsp'], {}).get('values') or {}
        return ties

    def _put_back(self, ties, preset=None):
        """The output Level / Pan back on Snapshots, with each snapshot's own value (after levelRestore).
        preset: the preset they were read in; HX Edit refuses them on any other."""
        mine = {'preset': identity(preset)} if preset else {}
        for tie in ties:
            for key, controller in tie['controllers'].items():
                self.command('levelTie', dsp=tie['dsp'], key=key, controller=controller, **mine)
        snapshots = sorted({int(n) for tie in ties for n in tie['values']})
        for snapshot in snapshots:
            self._update(progress=f'Putting the output level of snapshot {snapshot} back…')
            self._land(snapshot)
            for tie in ties:
                values = tie['values'].get(snapshot) or tie['values'].get(str(snapshot)) or {}
                for key in tie['controllers']:
                    value = values.get(key)
                    if isinstance(value, dict) and isinstance(value.get('value'), (int, float)):
                        self.command('levelPut', dsp=tie['dsp'], key=key, snapshot=snapshot, value=value, **mine)

    def _keep(self, state, ties=()):
        """HX Edit's measuring record (a levelBegin / levelPrepare reply's 'saved') on disk, for putting the
        routing back if this is cut short."""
        try:
            nam_level.remember_inputs(state or {}, self.restore_file, ties=ties)
        except OSError:
            pass

    def _end(self, own, ties, ident, failure=None):
        """After measuring a preset: the routing back as it was (the player's own preset), or HX Edit's
        record dropped (another one: loading the next preset drops its measuring routing, unsaved).
        HX Edit writes the old routing only into the preset it came from; when another preset is on now,
        the record stays on disk for that preset (recover). failure: what stopped the measuring; it stays
        the error when putting back fails as well."""
        try:
            if not own:
                self.command('levelDrop')
                nam_level.forget_inputs(self.restore_file)
                return
            reply = self.command('levelRestore', preset=ident)
            if reply.get('other'):
                if not nam_level.interrupted(self.restore_file) and reply.get('kept'):
                    self._keep({'preset': reply['kept'].get('preset'), 'saved': reply['kept']}, ties)
                self.recover()        # the same preset after a reconnection: what is still re-routed
                if nam_level.interrupted(self.restore_file):
                    raise LevelError(f'HX Edit left {describe(ident)} while it was being measured. Its '
                                     'routing was not written into the preset now loaded; it is put back '
                                     'when Level opens on that preset again (if it was saved that way).')
                return
            if ties:
                self._put_back(ties, ident)
            nam_level.forget_inputs(self.restore_file)
        except Exception as cleanup:
            if failure is None:
                raise
            raise LevelError(f'{str(failure) or failure.__class__.__name__} (Putting the routing back failed too: '
                             f'{cleanup}. Check the preset\'s input and output in HX Edit.)') from failure

    def _save(self, preset):
        before = self._here().get('savedAt') or 0
        for attempt in range(8):
            try:
                self.command('levelSave', preset=preset)
                break
            except Exception as failure:      # the header can read empty for a moment after an edit
                if 'different preset' not in str(failure) or attempt == 7:
                    raise
                self.sleep(0.25)
        deadline = self.clock() + 10
        while self.clock() < deadline:
            self.sleep(0.25)
            if (self.command('levelState').get('savedAt') or 0) > before:
                return
        raise LevelError(f'HX Edit did not confirm saving preset {preset.get("preset", 0):03d}.')

    def _scan(self, numbers, count, source):
        signal, at, peak, label = source   # the test signal: its file, where it starts, its level, its name
        self.scanned_with = label
        start = self._here()
        here = start['preset']['preset']
        setlist = start['preset'].get('setlist')    # the presets chosen are this setlist's
        # The current preset last: the others are left by loading the next one (which drops the
        # measuring routing, unsaved), so only the player's own preset needs its routing put back, at
        # the very end. Nothing plays between presets but the moment a preset takes to load.
        numbers = sorted(numbers or [here], key=lambda n: (n == here, n))
        total, done, rows, skipped = len(numbers) * (count if isinstance(count, int) else 8), 0, [], {}
        began = None                     # when the first snapshot was measured: for "about n min left"
        self._update(skipped={}, fraction=0.0)
        self._update(rows=[])
        meter = self.meter_factory(signal)
        try:
            for number in numbers:
                if self.cancelled.is_set():
                    break
                state = self._goto(number, settle=False, setlist=setlist)
                own = number == here
                every = [s['number'] for s in state.get('snapshots') or []]
                ident = identity(state['preset'])
                # What measuring will change, kept (in HX Edit and on disk) before anything is changed.
                # HX Edit refuses here, before the test signal is routed, a preset Level cannot measure
                # silently (a lane B with an output of its own).
                begun = self.command('levelBegin', preset=ident)
                ties = []
                try:
                    self._keep(begun)
                    # The guitar is silenced at once (input USB 7/8); the outputs are re-routed only after
                    # a just-loaded preset has settled and an output on a controller (Level per snapshot)
                    # has had every snapshot's value read (right after a load its controllers read as
                    # none: Floor, November 16, 030).
                    self.command('levelPrepare', outputs=False, preset=ident)
                    self.sleep(self.LANDED)
                    chosen = scanned_snapshots(state.get('snapshots') or [], count)
                    numbers_chosen = [s['number'] for s in chosen]
                    # the player's own preset gets every snapshot's Level back, so all of them are read
                    ties = self._ties(number, every if own else numbers_chosen, own)
                    prepared = self.command('levelPrepare', preset=ident)    # now the outputs: USB 1/2 only
                    self._keep(prepared, ties if own else [])
                    # Re-routed, the output holds one Level for every snapshot now: each measurement is
                    # put right by that snapshot's own Level (the output Level is a plain gain).
                    flat = {tie['dsp']: tie for tie in self.command('levelTies').get('ties') or []}
                    preset = state.get('preset') or {'preset': number}
                    snapshots = chosen
                    names = {s['number']: s.get('name', '') for s in snapshots}
                    left = [n for n in every if n not in names]
                    if left:
                        skipped[preset['preset']] = left
                        self._update(skipped=dict(skipped))
                    # Every snapshot is measured. Reading what a snapshot holds right after recalling it
                    # is not reliable (HX Edit reports the new snapshot before its values arrive, more
                    # so in a big preset: Floor, November 16), so nothing is compared beforehand;
                    # snapshots that measure the same are shown as one row afterwards.
                    groups = [[n] for n in names]
                    total += len(groups) - (count if isinstance(count, int) else 8)
                    mine = []
                    for group in groups:
                        if self.cancelled.is_set():
                            break
                        done += 1
                        first = group[0]
                        label = names[first] or f'snapshot {first}'
                        self._update(progress=f'Measuring {preset["preset"]:03d} {preset.get("name", "")}, '
                                              f'{label} ({done} of about {total})…',
                                     fraction=min(1.0, (done - 1) / max(1, total)))
                        # A full second on the snapshot first: in a big preset its sound takes that long to
                        # land (at 0.35 s, 005's snapshots measured 1.5-3 dB apart from run to run).
                        self._land(first)
                        if began is None:
                            began = self.clock()
                        left = ''
                        if done > 1:
                            seconds = (self.clock() - began) / (done - 1) * (total - done + 1)
                            left = f' · about {max(1, round(seconds / 60))} min left' if seconds >= 90 else \
                                f' · about {max(5, int(round(seconds / 5.0)) * 5)} s left'
                        result = self._readings(meter, (at, peak), f'Measuring {preset["preset"]:03d} '
                                                f'{preset.get("name", "")}, {label} ({done} of {total}{left})')
                        # Seconds after the recall now: the output Level read here is this snapshot's.
                        after = self.command('levelState', gain=True)
                        if not same_preset(after.get('preset'), ident):
                            raise LevelError(f'HX Edit left {describe(ident)} while it was being measured.')
                        if after.get('snapshot') != first:
                            raise LevelError(f'HX Edit left snapshot {first} while it was being measured.')
                        level = after.get('gain')
                        correction = 0.0
                        for tie in ties[:1]:
                            own_level = ((tie['values'].get(first) or {}).get('gain') or {}).get('value')
                            flat_level = (((flat.get(tie['dsp']) or {}).get('values') or {}).get('gain') or {}).get('value')
                            if isinstance(own_level, (int, float)) and isinstance(flat_level, (int, float)):
                                correction, level = own_level - flat_level, own_level
                        if result.get('ok') and correction:
                            result = dict(result, lufs=round(result['lufs'] + correction, 2),
                                          peak=round(result['peak'] + correction, 2))
                        spread = result.get('spread') or 0.0
                        row = {'preset': preset['preset'], 'name': preset.get('name', ''), 'setlist': preset.get('setlist'),
                               'snapshot': first, 'snapshots': group, 'snapName': names[first],
                               'snapNames': [names[n] for n in group],
                               'lufs': result.get('lufs') if result.get('ok') else None,
                               'peak': result.get('peak') if result.get('ok') else None,
                               'note': '' if result.get('ok') else result.get('error', 'Not measured'),
                               'level': round(level, 1) + 0.0 if isinstance(level, (int, float)) else None,
                               # how far its readings were apart, when it moves on its own (dB)
                               'varies': round(spread / 2, 1) if spread > self.AGREE else None}
                        if not result.get('ok') and not result.get('silent'):
                            raise LevelError(result.get('error') or 'Measuring failed.')
                        mine.append(row)
                        self._update(rows=sorted(rows + mine, key=lambda r: (r['preset'], r['snapshot'])),
                                     fraction=min(1.0, done / max(1, total)))
                    rows += alike_rows(mine)
                    self._update(rows=sorted(rows, key=lambda r: (r['preset'], r['snapshot'])))
                except BaseException as failure:
                    self._end(own, ties, ident, failure)
                    raise
                self._end(own, ties, ident)
        finally:
            meter.close()
            self._home(start)
        measured = sum(1 for row in rows if row['lufs'] is not None)
        presets = len({row['preset'] for row in rows})
        if self.cancelled.is_set():
            return f'Cancelled. {measured} sound(s) measured; nothing was changed.'
        return (f'Measured {measured} different sound(s) in {presets} preset(s). '
                'Check the levels, then Apply; nothing has been changed yet.')

    def _apply(self, changes, target=None, who=None):
        """changes: {preset number: {snapshot: dB}}; who: {preset number: identity} of the measured presets
        (apply()). Each preset is checked to be that one (setlist, number, name) before it is changed or
        saved. Cancel stops before the next preset; what was done stays done, and Undo has it."""
        who = who or {}
        missing = [n for n in sorted(changes) if n not in who]
        if missing:
            raise LevelError(f'Preset {missing[0]:03d} has no measurement to apply; scan it again.')
        levels = {}
        for row in self.view()['rows']:
            for number in row.get('snapshots') or [row['snapshot']]:
                levels.setdefault(row['preset'], {})[number] = row.get('level')
        start = self._here()
        setlist = who[next(iter(changes))]['setlist']
        if start['preset'].get('setlist') != setlist:
            raise LevelError('These measurements were made in another setlist than the one HX Edit is on now; '
                             'nothing was changed. Go back to that setlist, or scan again.')
        home = start['preset']['preset']
        several = not (len(changes) == 1 and same_preset(start['preset'], who[next(iter(changes))]))
        record = {'saved': several, 'presets': [], 'history': {}}
        history = nam_level.load_history(self.history_file)
        applied = 0
        try:
            for number in sorted(changes, key=lambda n: (n != home, n)):
                if self.cancelled.is_set():
                    break                    # before another preset: the ones done stay done (Undo has them)
                ident = who[number]
                state = self._goto(number, setlist=setlist)
                if not same_preset(state['preset'], ident):
                    raise LevelError(f'Preset {number:03d} is not the one that was measured '
                                     f'({describe(identity(state["preset"]))} now); nothing more was changed. '
                                     'Scan it again.')
                trims, back = changes[number], state.get('snapshot')
                self._update(progress=f'Applying to {number:03d} {state["preset"].get("name", "")}…')
                reply = self.command('levelApplyPlan', trims=trims, home=back, preset=ident)
                entry = {'preset': state['preset'], 'record': None, 'saved': False,
                         'trims': {str(n): dB for n, dB in trims.items()}}
                record['presets'].append(entry)
                try:
                    known = levels.get(number, {})
                    for snapshot in reply.get('visit') or []:
                        # The Level this snapshot had in the scan: written from, never read back.
                        extra = {'start': known[snapshot]} if isinstance(known.get(snapshot), (int, float)) else {}
                        self._visit(snapshot, 'levelApplyHere', trim=trims[snapshot], **extra)
                finally:
                    if back:
                        self.command('levelRecall', snapshot=back)
                        self.sleep(self.SETTLE)
                    entry['record'] = self.command('levelApplyEnd').get('record')
                    nam_level.save_records(record, self.records_file)
                if several:     # loading the next preset would drop an unsaved change
                    self._save(ident)
                    entry['saved'] = True
                    nam_level.save_records(record, self.records_file)
                self._shift(number, trims, 1)
                applied += 1
                # "Last leveled": when, with which guitar, to what (Undo puts the one before back).
                key = nam_level.history_key(state['preset'])
                record['history'][key] = history.get(key)
                history[key] = {'when': datetime.now().isoformat(timespec='seconds'), 'with': self.scanned_with,
                                'target': (target or {}).get('value'), 'metric': (target or {}).get('metric')}
                nam_level._write_json(history, self.history_file)
                nam_level.save_records(record, self.records_file)
        finally:
            if several:
                self._home(start)
        if applied < len(changes):           # cancelled
            if not applied:
                return 'Cancelled; nothing was changed.'
            return (f'Cancelled after {applied} of {len(changes)} preset(s): those were applied and saved, the '
                    'rest left as they were. Undo puts the changed ones back.')
        if several:
            return f'Applied and saved {len(changes)} preset(s). Undo puts the old levels back.'
        return 'Applied to this preset. Not saved: save it in HX Edit to keep it, or Undo.'

    def _undo(self):
        """Each preset of the last Apply back as it was, last first, each checked to be that preset (setlist,
        number, name). Cancel stops before the next preset; the record keeps the ones not undone yet."""
        records = nam_level.load_records(self.records_file)
        start = self._here()
        undone = 0
        pending = list(records['presets'])        # what the record still holds
        before = dict(records.get('history') or {})

        def done(entry, undid):
            pending.remove(entry)
            key = nam_level.history_key(entry.get('preset') or {})
            if undid and key in before:            # its "last leveled" note as it was before that Apply
                history = nam_level.load_history(self.history_file)
                if before[key]:
                    history[key] = before[key]
                else:
                    history.pop(key, None)
                nam_level._write_json(history, self.history_file)
            if pending:
                nam_level.save_records(dict(records, presets=pending), self.records_file)
            else:
                nam_level.forget_records(self.records_file)
        try:
            for entry in reversed(records['presets']):
                if self.cancelled.is_set():
                    break
                ident = identity(entry.get('preset'))
                number = ident['preset']
                if not entry.get('record') or number is None:
                    done(entry, False)
                    continue
                if not records.get('saved'):
                    if not same_preset(start['preset'], ident):
                        done(entry, False)
                        continue              # never saved, and gone with the preset change: nothing to undo
                elif not entry.get('saved'):
                    done(entry, False)
                    continue                  # its Apply stopped before the save: the Floor never kept it
                state = self._goto(number, setlist=ident['setlist'])
                if not same_preset(state['preset'], ident):
                    raise LevelError(f'Preset {number:03d} is not the one Level changed '
                                     f'({describe(identity(state["preset"]))} now); it was left alone.')
                self._update(progress=f'Undoing {number:03d} {state["preset"].get("name", "")}…')
                self.command('levelUndoLoad', record=entry['record'])
                reply = self.command('levelUndoPlan')
                for snapshot in reply.get('visit') or []:
                    self._visit(snapshot, 'levelUndoHere')
                if reply.get('snapshot'):
                    self.command('levelRecall', snapshot=reply['snapshot'])
                    self.sleep(self.SETTLE)
                self.command('levelApplyEnd', forget=True)
                if records.get('saved'):
                    self._save(ident)
                self._shift(number, {int(n): dB for n, dB in (entry.get('trims') or {}).items()}, -1)
                undone += 1
                done(entry, True)
        finally:
            if records.get('saved'):
                self._home(start)
        if pending:                          # cancelled
            return (f'Undo cancelled: {undone} preset(s) back as they were; Undo again for the other '
                    f'{len(pending)}.')
        if not undone:
            return 'Nothing to undo: those changes were never saved and are gone already.'
        return f'Undone: {undone} preset(s) are back as they were' + (' (saved).' if records.get('saved') else '.')
