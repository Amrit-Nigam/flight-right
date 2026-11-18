"""Single-runway planning sandbox. Never transmits or changes live model intent.

The 120-second gap is an educational resource constraint, NOT an ATC minimum.
There is no claim of operational feasibility, global optimality or pilot delivery.
"""
import copy
import json
import sqlite3
import uuid
import time
from contextlib import contextmanager
from pathlib import Path
from ..config import AUDIT_DATABASE


class PlanConflict(ValueError):
    pass


class PlanningService:
    def __init__(self, path=None):
        self.path = Path(path or AUDIT_DATABASE.with_name('planning.sqlite3'))
        self.instance = uuid.uuid4().hex

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS controller_plans (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL)')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def initial(scope="sandbox", base_time=0):
        return dict(version=0, mode='normal', rows=[], messages=[], events=[], undo=None,
                    gap=120, clock=0, emergency=None, scope=scope, baseTime=base_time, emergencyOwner=None,
                    radioAuto=True, radioEvents=[], closedMovements=[])

    def snapshot(self, scope="sandbox", base_time=0):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM controller_plans WHERE scope=? ORDER BY id DESC LIMIT 1', (scope,)).fetchone()
        state = json.loads(row[0]) if row else self.initial(scope, base_time)
        return self.recover(state)

    def recover(self, state):
        state.setdefault('radioAuto',True)
        state.setdefault('radioEvents',[])
        state.setdefault('closedMovements',[])
        if state['mode'] == 'emergency' and state.get('emergencyOwner') != self.instance:
            state['mode'] = 'takeover'
            state['recoveryRequired'] = True
        return state

    @staticmethod
    def validate(rows):
        ids = [r['id'] for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate flight identifier')
        previous = -120
        for r in rows:
            if r['target'] < r['earliest'] or r['target'] > r['latest']:
                raise ValueError(f"{r['callsign']}: target outside feasible sandbox window")
            if r['target'] < previous + 120:
                raise ValueError('Conflicting runway slots: sandbox gap is 120 seconds')
            previous = r['target']

    @staticmethod
    def sequence(rows):
        previous = -120
        for r in rows:
            target = max(r['earliest'], previous + 120)
            if r['pinned']:
                if r['target'] < target:
                    raise ValueError(f"Pinned slot for {r['callsign']} blocks this sequence")
                target = r['target']
            r['target'] = target
            previous = target

    def apply(self, version, action, scope="sandbox", base_time=0, **args):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM controller_plans WHERE scope=? ORDER BY id DESC LIMIT 1', (scope,)).fetchone()
            state = self.recover(json.loads(row[0]) if row else self.initial(scope, base_time))
            if state['version'] != version and action != 'takeover':
                raise PlanConflict('Plan changed. Refresh and retry.')
            before = copy.deepcopy(state['rows'])
            rows = state['rows']
            ident = args.get('flight')
            flight = next((r for r in rows if r['id'] == ident), None)
            if action=='radio_auto':
                state['radioAuto']=bool(args.get('enabled'))
            elif action in ('radio_event','radio_accept'):
                if action=='radio_event':
                    event=copy.deepcopy(args['radio_event'])
                    if any(e['id']==event['id'] for e in state['radioEvents']):return state
                    state['radioEvents'].append(event)
                    apply=args.get('radio_apply',False)
                else:
                    event=next((e for e in state['radioEvents'] if e['id']==args.get('event_id')),None)
                    if not event or event['status'] not in ('review','blocked') or not event.get('proposal'):
                        raise ValueError('No reviewable transcript proposal remains')
                    if state['mode']!='normal':raise ValueError('Return to normal planning before applying a transcript proposal')
                    apply=True
                if apply:
                    proposal=event['proposal'];callsign=proposal['callsign']
                    existing=next((r for r in rows if r['id']==callsign),None)
                    if existing and existing['kind']!=proposal['kind']:
                        raise ValueError('Movement type differs from the current plan; review it manually')
                    if existing is None:
                        if len(rows)>=100:raise ValueError('Sandbox limited to 100 movements')
                        ready=max(state['clock'],int(max(0,proposal.get('ready_at',base_time)-state['baseTime'])))
                        existing=dict(id=callsign,callsign=callsign,kind=proposal['kind'],earliest=ready,latest=ready+86400,target=ready,pinned=False,provenance='Recorded tower communication; operational readiness unverified')
                        rows.append(existing)
                    if 'position' in proposal or 'after' in proposal:
                        rows.remove(existing)
                        if 'after' in proposal:
                            index=next((i+1 for i,r in enumerate(rows) if r['id']==proposal['after']),None)
                            if index is None:raise ValueError('Preceding flight left the sequence')
                        else:index=proposal['position']-1
                        if index>len(rows):raise ValueError('Sequence position exceeds known movements; add the missing flights first')
                        rows.insert(index,existing)
                    self.sequence(rows)
                    event.update(status='applied',appliedRevision=version+1,reason='Recorded in planning only; no instruction transmitted')
            elif action == 'add':
                if len(rows) >= 100:
                    raise ValueError('Sandbox limited to 100 movements')
                callsign = args.get('callsign', '').strip().upper()
                if not callsign or len(callsign) > 16 or not callsign.isalnum():
                    raise ValueError('Use an alphanumeric callsign of 1–16 characters')
                if any(r['id'] == callsign for r in rows):
                    raise ValueError('Flight already scheduled')
                kind = args.get('kind')
                if kind not in ('arrival', 'departure'):
                    raise ValueError('Choose arrival or departure')
                ready = max(state['clock'], int(max(0, args.get('ready_at', base_time) - state.get('baseTime', base_time))))
                rows.append(dict(id=callsign, callsign=callsign, kind=kind, earliest=ready,
                                 latest=ready+86400, target=max(ready, rows[-1]['target']+120 if rows else 0), pinned=False, provenance=args.get('provenance','Manual planning input')))
            elif action == 'reorder':
                order = args.get('order', [])
                if len(order) != len(rows) or set(order) != {r['id'] for r in rows}:
                    raise ValueError('Sequence must contain every scheduled flight exactly once')
                by_id = {r['id']: r for r in rows}
                rows = [by_id[k] for k in order]
                self.sequence(rows)
            elif action in ('pin', 'time'):
                if not flight:
                    raise ValueError('Flight not scheduled')
                if action == 'pin':
                    flight['pinned'] = not flight['pinned']
                else:
                    target = args.get('target')
                    if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target <= 172800:
                        raise ValueError('Target must be integer sandbox seconds, 0–172800')
                    flight['target'] = target
            elif action == 'undo':
                if state['undo'] is None or state['mode'] == 'emergency':
                    raise ValueError('No editable draft undo available')
                rows = state['undo']
            elif action == 'emergency':
                if not flight:
                    raise ValueError('Choose a scheduled emergency flight')
                if state['emergency']:
                    raise ValueError('One sandbox case at a time; close the current case first')
                rows = [flight] + [r for r in rows if r['id'] != ident]
                self.sequence(rows)
                state.update(mode='emergency', emergency=ident, emergencyOwner=self.instance)
            elif action == 'takeover':
                state['mode'] = 'takeover'
            elif action == 'normal':
                state.update(mode='normal', emergency=None, emergencyOwner=None, recoveryRequired=False)
            elif action == 'issue':
                if state['mode'] != 'normal' or args.get('authorized') is not True:
                    raise ValueError('Normal issue requires explicit ATCO authorization')
            elif action in ('remove', 'close'):
                if not flight:
                    raise ValueError('Flight not scheduled')
                if state['emergency'] == ident:
                    raise ValueError('Close the emergency case before removing it')
                if action == 'close':
                    outcome = args.get('outcome')
                    if outcome not in ('completed', 'cancelled'):
                        raise ValueError('Choose completed or cancelled')
                    state['closedMovements'].append(dict(**copy.deepcopy(flight), outcome=outcome,
                        closedAt=time.time(), revision=version+1,
                        reason='Controller close-out; not automatically verified from surveillance'))
                rows = [r for r in rows if r['id'] != ident]
                if action == 'remove':
                    self.sequence(rows)
            elif action == 'optimize':
                # Stable earliest-ready baseline, with explicit pins honoured.
                rows = sorted(rows, key=lambda r: (r['id'] != state.get('emergency') if state['mode']=='emergency' else False, r['earliest'], r['target']))
                self.sequence(rows)
            elif action == 'tick':
                state['clock'] += 30
            else:
                raise ValueError('Unknown planning action')
            self.validate(rows)
            state['rows'] = rows
            changed = before != rows
            if action in ('emergency', 'takeover', 'normal') or changed:
                for m in state['messages']:
                    if m['status'] == 'draft':
                        m['status'] = 'cancelled'
            if changed or action == 'emergency':
                state['undo'] = before if action != 'undo' else None
                for r in rows:
                    state['messages'].append(dict(id=f"{version+1}:{r['id']}", flight=r['id'],
                        text=f"{r['callsign']}: planned {r['kind']} slot T+{r['target']} seconds (sandbox advisory)",
                        status='draft', revision=version+1))
            if state['mode'] == 'emergency' or action == 'issue':
                for m in state['messages']:
                    if m['status'] == 'draft':
                        m.update(status='simulated delivery', authority='emergency policy' if state['mode']=='emergency' else 'ATCO authorization')
            if state['mode'] == 'emergency' or action == 'issue':
                state['undo'] = None
            if action == 'close':
                # Final close-out cannot be resurrected by an unrelated draft undo.
                state['undo'] = None
            state['version'] += 1
            state['events'].append(dict(revision=state['version'], action=action, clock=state['clock'],
                                        **({'flight': ident, 'outcome': args['outcome']} if action == 'close' else {})))
            db.execute('INSERT INTO controller_plans(scope,payload) VALUES (?,?)', (scope, json.dumps(state)))
        return state


planning_service = PlanningService()
