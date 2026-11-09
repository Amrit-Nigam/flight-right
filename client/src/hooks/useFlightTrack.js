import { useEffect, useMemo, useState } from "react";
import { getAircraftHistory, getAircraftTrajectory } from "@/lib/api";
import { flightTrackSegments } from "@/lib/flightTrack";

export function useFlightTrack(flight, source, update) {
  const identity = flight?.icao24 || flight?.callsign;
  const [result, setResult] = useState(null);
  const [prediction, setPrediction] = useState(null);
  useEffect(() => {
    if (!identity) return;
    let cancelled = false;
    getAircraftHistory(identity).then((data) => {
      if (!cancelled) setResult({ identity, source, update, states: data.states || [] });
    }).catch(() => {
      if (!cancelled) setResult({ identity, source, update, states: [], error: true });
    });
    getAircraftTrajectory(identity).then((data) => {
      if (!cancelled) setPrediction({ identity, update, ...data });
    }).catch(() => {
      if (!cancelled) setPrediction({ identity, source, update, status: "unavailable" });
    });
    return () => { cancelled = true; };
  }, [identity, source, update]);

  const matching = result?.identity === identity && result?.source === source;
  const segments = useMemo(() => flightTrackSegments(matching ? result.states : [], flight),
    [matching, result, flight]);
  const predictionMatches = prediction?.identity === identity && prediction?.source === source
    && prediction?.timePosition === flight?.timePosition;
  return { segments, prediction: predictionMatches ? prediction : null,
    predictionStatus: predictionMatches ? prediction.status
      : prediction?.identity === identity && prediction?.update === update && prediction?.status === "unavailable"
        ? "unavailable" : "loading",
    status: !matching || result.update !== update ? "loading"
    : result.error ? "error" : segments.length ? "ready" : "empty" };
}
