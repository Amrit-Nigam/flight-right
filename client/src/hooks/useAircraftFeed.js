import { useCallback, useEffect, useRef, useState } from "react";
import { initialFlights } from "@/data/mockData";
import { getLatestAircraft } from "@/lib/api";

const POLL_MS = 5000;

function mergeWithFallback(apiFlights) {
  const fallbackByCallsign = new Map(initialFlights.map((flight) => [flight.callsign, flight]));

  return apiFlights.map((flight) => {
    const fallback = fallbackByCallsign.get(flight.callsign) || {};
    return {
      ...fallback,
      ...flight,
      status: String(flight.status || fallback.status || "CRUISE").toUpperCase(),
      heading: Number(flight.heading ?? fallback.heading ?? 0),
      lat: Number(flight.lat),
      lng: Number(flight.lng),
      speedKt: Number((flight.speedKt ?? parseInt(flight.speed || fallback.speed || "0", 10)) || 0),
      altitudeFt: Number(flight.altitudeFt ?? 0),
      speed: flight.speed || fallback.speed || "0 kt",
      altitude: flight.altitude || fallback.altitude || "GND",
    };
  });
}

export function useAircraftFeed() {
  const [flights, setFlights] = useState(initialFlights);
  const [source, setSource] = useState({ provider: "mock", source: "mock", updatedAt: null });
  const [status, setStatus] = useState("mock");
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const payload = await getLatestAircraft();
      if (!mountedRef.current) return;
      const nextFlights = Array.isArray(payload.flights) && payload.flights.length > 0 ? mergeWithFallback(payload.flights) : initialFlights;
      setFlights(nextFlights);
      setSource({
        provider: payload.provider || payload.source || "api",
        source: payload.source || "api",
        updatedAt: payload.updatedAt || null,
        count: payload.count ?? nextFlights.length,
      });
      setStatus("connected");
      setError(payload.error || null);
    } catch (err) {
      if (!mountedRef.current) return;
      setFlights((prev) => (prev.length ? prev : initialFlights));
      setSource((prev) => ({ ...prev, provider: prev.provider || "mock", source: prev.source || "mock" }));
      setStatus("fallback");
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [load]);

  return { flights, source, status, error, refresh: load };
}
