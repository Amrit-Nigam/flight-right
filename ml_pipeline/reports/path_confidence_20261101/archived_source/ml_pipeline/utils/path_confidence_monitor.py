"""Experimental all-pairs monitor. Not connected to controller notifications.

Scores describe normalized top-five path weights, not calibrated incident risk.
Pair scores use the existing independent-aircraft product approximation. Persistent
combination identities use route-pattern IDs, never ranks that change each update.
"""
from __future__ import annotations
from itertools import combinations
import math
from typing import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
import copy
from ml_pipeline.utils.cpa_conflict_detection import compute_cpa_from_paths


def summarize(a: Mapping, b: Mapping) -> dict:
    """Inputs: paths [(weight, horizon->position)], patterns, current (lat,lon,metres)."""
    for aircraft in (a, b):
        paths, patterns = aircraft['paths'], aircraft['patterns']
        if not 1 <= len(paths) <= 5 or len(patterns) != len(paths) or len(set(map(int, patterns))) != len(patterns):
            raise ValueError('Need 1..5 paths with distinct matching pattern IDs')
        weights = [float(p) for p, _ in paths]
        if any(not math.isfinite(p) or p < 0 for p in weights) or sum(weights) <= 0:
            raise ValueError('Path weights must be finite, nonnegative and have positive mass')
        if len(aircraft['current']) != 3 or not all(math.isfinite(float(x)) for x in aircraft['current']):
            raise ValueError('Current position must be finite latitude, longitude, altitude metres')
    result = compute_cpa_from_paths(a['paths'], b['paths'], tuple(a['current']), tuple(b['current']))
    pa = [float(x[0]) / sum(float(p) for p, _ in a['paths']) for x in a['paths']]
    pb = [float(x[0]) / sum(float(p) for p, _ in b['paths']) for x in b['paths']]
    hits = []
    for combo in result['combinations']:
        if not combo['breaches_alert_volume']:
            continue
        i, j = combo['path_a'], combo['path_b']
        hits.append(dict(pattern_a=int(a['patterns'][i]), pattern_b=int(b['patterns'][j]),
                         path_weight_a=pa[i], path_weight_b=pb[j], joint_weight=combo['joint_probability'],
                         time_to_cpa_seconds=combo['cpa']['time_to_cpa_seconds'],
                         lateral_nm=combo['cpa']['cpa_lateral_distance_nm'],
                         vertical_ft=combo['cpa']['cpa_vertical_separation_ft']))
    return dict(combinations_checked=result['combinations_checked'], combinations=hits,
                total_weight=sum(h['joint_weight'] for h in hits),
                max_joint_weight=max((h['joint_weight'] for h in hits), default=0.),
                both_path_weight=max((min(h['path_weight_a'], h['path_weight_b']) for h in hits), default=0.),
                time_to_cpa_seconds=result['time_to_cpa_seconds'])


class PathConfidenceMonitor:
    """One complete airspace snapshot per update; all unordered supplied pairs.

    This class computes experimental eligibility only. A scheduler can call it off
    the request thread; it does not spawn threads or change the live AlertFeed.
    """
    def __init__(self, threshold: float, score: str = 'total_weight', consecutive: int = 3,
                 max_gap_seconds: float = 30., forget_seconds: float = 120.):
        if score not in ('total_weight', 'max_joint_weight', 'both_path_weight'):
            raise ValueError('Unknown score')
        if not math.isfinite(threshold) or not 0 <= threshold <= 1 or consecutive < 1:
            raise ValueError('Invalid threshold or consecutive update count')
        if max_gap_seconds <= 0 or forget_seconds < max_gap_seconds:
            raise ValueError('Invalid gap/expiry durations')
        self.threshold, self.score, self.consecutive = threshold, score, consecutive
        self.max_gap, self.forget = max_gap_seconds, forget_seconds
        self.states: dict = {}
        self.last_update: float | None = None

    def update(self, aircraft: Mapping[str, Mapping], now: float,
               protected_pairs: set[tuple[str, str]] | None = None) -> dict:
        if not math.isfinite(now) or (self.last_update is not None and now <= self.last_update):
            raise ValueError('Snapshot times must be finite and strictly increasing')
        protected = {tuple(sorted(pair)) for pair in (protected_pairs or set())}
        # Compute before mutating state, so a malformed snapshot cannot partly update it.
        evidence = {pair: summarize(aircraft[pair[0]], aircraft[pair[1]])
                    for pair in combinations(sorted(aircraft), 2)}
        visible, pending, combinations_checked = [], [], 0
        for pair, item in evidence.items():
            combinations_checked += item['combinations_checked']
            in_horizon = 0 <= item['time_to_cpa_seconds'] <= 600
            qualifies = in_horizon and (pair in protected or (bool(item['combinations']) and item[self.score] >= self.threshold))
            previous = self.states.get(pair)
            streak = (previous['streak'] if previous and now-previous['last_seen'] <= self.max_gap else 0)
            streak = streak + 1 if qualifies else 0
            ready = qualifies and streak >= self.consecutive
            old_hits = previous['combinations'] if previous else {}
            tracked = {}
            for hit in item['combinations']:
                identity = (hit['pattern_a'], hit['pattern_b'])
                old = old_hits.get(identity)
                continuous = old and now-old['last_seen'] <= self.max_gap
                tracked[identity] = {**hit, 'first_seen': old['first_seen'] if continuous else now,
                                     'last_seen': now, 'updates': old['updates']+1 if continuous else 1}
            state = dict(last_seen=now, first_seen=previous['first_seen'] if previous else now,
                         streak=streak, ready=ready, score=item[self.score], combinations=tracked)
            self.states[pair] = state
            if tracked or pair in protected:
                row = dict(pair=pair, score=item[self.score], streak=streak, combinations=list(tracked.values()),
                           protected=pair in protected, new_notification=ready and not (
                               previous and previous['ready'] and now-previous['last_seen'] <= self.max_gap))
                (visible if ready else pending).append(row)
        for pair in list(self.states):
            if pair not in evidence:
                self.states[pair]['streak'] = 0
                self.states[pair]['ready'] = False
                if now-self.states[pair]['last_seen'] > self.forget:
                    del self.states[pair]
        self.last_update = now
        return dict(aircraft=len(aircraft), pairs_checked=len(evidence), combinations_checked=combinations_checked,
                    shadow_visible=visible, pending=pending, retained_pairs=len(self.states),
                    score_kind=self.score, threshold=self.threshold, live_notifications_changed=False)


class PathConfidenceWorker:
    """Isolated background worker; waits for each result before accepting another tick.

    No unbounded queue: a slow all-pairs scan reports busy instead of accumulating
    stale snapshots. The caller must handle backpressure and stale-result display.
    This experimental worker is not started by the live server.
    """
    def __init__(self, monitor: PathConfidenceMonitor):
        self.monitor = monitor
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='path-confidence-shadow')
        self.pending: Future | None = None

    def submit(self, aircraft: Mapping[str, Mapping], now: float,
               protected_pairs: set[tuple[str, str]] | None = None) -> Future:
        if self.pending is not None and not self.pending.done():
            raise RuntimeError('Previous scan is still running; do not queue stale airspace snapshots')
        self.pending = self.executor.submit(self.monitor.update, copy.deepcopy(aircraft), now,
                                            copy.deepcopy(protected_pairs))
        return self.pending

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
