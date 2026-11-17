import { useEffect, useMemo, useState } from "react";
import { getAircraftHistory, getAircraftTrajectory } from "@/lib/api";
import { flightTrackSegments } from "@/lib/flightTrack";
import {createRequestCache} from '@/lib/requestCache';

const historyCache=createRequestCache({ttl:8000});
const predictionCache=createRequestCache({ttl:15000});

export function useFlightTrack(flight, source, update, scope=source, intentRevision='') {
  const identity = flight?.icao24 || flight?.callsign;
  const [,refresh]=useState(0);
  const [now,setNow]=useState(Date.now);
  const observationKey=`${scope}|${identity}`;
  const [wait,setWait]=useState(()=>({key:observationKey,since:Date.now()}));
  if(wait.key!==observationKey)setWait({key:observationKey,since:now});
  useEffect(()=>{const id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id);},[]);
  const historyKey=`${scope}|${identity}`;
  const predictionKey=`${historyKey}|${flight?.timePosition}|${intentRevision}`;
  useEffect(() => {
    if (!identity || flight?.staleSelection) return;
    let cancelled = false;
    const settled=()=>{if(!cancelled)refresh(n=>n+1);};
    historyCache.load(historyKey,()=>getAircraftHistory(identity)).then(settled,settled);
    predictionCache.load(predictionKey,()=>getAircraftTrajectory(identity)).then(settled,settled);
    return () => { cancelled = true; };
  }, [identity, historyKey, predictionKey, update, flight?.staleSelection]);

  const history=historyCache.peek(historyKey);
  const predicted=predictionCache.peek(predictionKey);
  const prediction=predicted?.value;
  const states=history?.value?.states;
  const segments = useMemo(() => flightTrackSegments(states || [], flight),[states, flight]);
  const predictionMatches = prediction?.source === source
    && prediction?.timePosition === flight?.timePosition;
  return { segments, prediction: predictionMatches && !predicted?.error && !flight?.staleSelection ? prediction : null,
    elapsedSeconds:Math.max(0,Math.floor((now-wait.since)/1000)),
    predictionError:predicted?.error?.message || prediction?.reason || '',
    predictionStatus: predicted?.error ? 'unavailable' : predictionMatches ? prediction.status
      : predicted?.error ? 'unavailable' : 'loading',
    status: flight?.staleSelection ? "stale" : history?.error ? 'error' : !states ? 'loading' : segments.length ? 'ready' : 'empty' };
}
