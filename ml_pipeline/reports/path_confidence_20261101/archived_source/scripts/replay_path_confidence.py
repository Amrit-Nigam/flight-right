"""Run the isolated monitor over consecutive recorded airspace snapshots, offline."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('LOKY_MAX_CPU_COUNT','4')
import sys
import json
import time
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'ml_pipeline/utils'))
from offsets_ab_test import to_model_window
from server.app.ml.inference import MultiPathPredictor
from ml_pipeline.utils.path_confidence_monitor import PathConfidenceMonitor, PathConfidenceWorker


def main():
    raw_path = ROOT/'ml_pipeline/data/raw/session_b_20260905_023002_combined.parquet'
    data = pd.read_parquet(raw_path)
    columns = ['time_position','latitude','longitude','baro_altitude','velocity','true_track','vertical_rate']
    data = data.dropna(subset=columns).sort_values('time_position')
    tracks = {str(k):f.drop_duplicates('time_position',keep='last') for k,f in data.groupby('icao24')}
    start = int(data.time_position.min()+600)
    predictor = MultiPathPredictor(offsets='per_mode')
    monitor = PathConfidenceMonitor(.2,score='total_weight',consecutive=3)
    worker = PathConfidenceWorker(monitor)
    ticks = []
    out = ROOT/'ml_pipeline/data/processed/path_confidence_experiments/20261101/replay_events.jsonl'
    with out.open('w',encoding='utf-8') as log:
        for now in range(start,start+60,10):
            X, keys, calls, current = [], [], [], []
            excluded = 0
            for key,track in tracks.items():
                past = track[track.time_position<=now].tail(10)
                if len(past)<10 or now-past.time_position.iloc[-1]>15 or np.diff(past.time_position).max()>30:
                    excluded += 1
                    continue
                last = past.iloc[-1]
                if bool(last.on_ground) or last.baro_altitude<10000/3.28084 or last.velocity<=50:
                    excluded += 1
                    continue
                X.append(to_model_window(past[columns].to_numpy(dtype=float)))
                keys.append(key)
                calls.append(str(last.callsign).strip())
                current.append((float(last.latitude),float(last.longitude),float(last.baro_altitude)))
            started = time.perf_counter()
            matrix = np.stack(X)
            p, positions, patterns = predictor.predict(matrix,extra=predictor.route_inputs(matrix,calls,fetch=False))
            inputs = {key:dict(paths=predictor.paths_for_cpa(matrix,i,p,positions),patterns=patterns[i],current=current[i])
                      for i,key in enumerate(keys)}
            result = worker.submit(inputs,now).result(timeout=60)
            seconds = time.perf_counter()-started
            expected = len(keys)*(len(keys)-1)//2
            assert result['pairs_checked']==expected
            assert result['combinations_checked']==expected*25
            log.write(json.dumps(dict(time=now,result=result))+'\n')
            ticks.append(dict(time=now,aircraft=len(keys),excluded=excluded,pairs=expected,
                              combinations=result['combinations_checked'],pending=len(result['pending']),
                              visible=len(result['shadow_visible']),new_notifications=sum(x['new_notification'] for x in result['shadow_visible']),
                              inference_and_monitor_seconds=seconds))
            print(ticks[-1],flush=True)
    worker.close()
    report = dict(source=str(raw_path.relative_to(ROOT)),source_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                  threshold=.2,score='total_weight',consecutive=3,ticks=ticks,
                  label_caveat='Recorded traffic, no labelled pair outcomes here. Demonstrates state/all-pairs/latency, not detection accuracy or warning-time quality.',
                  scope='All current aircraft with ten valid states, airborne >=10000 ft and >50 m/s. No spatial prefilter or pair cap; no network route lookup.',
                  live_controller_changed=False)
    (ROOT/'ml_pipeline/reports/path_confidence_20261101/replay.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':
    with threadpool_limits(4):
        main()
