// Slow-changing backend facts, polled every 15 s: /api/health (safety constants, controller
// identity, model versions, store) and /api/airport (VABB runways, the METAR for the time on
// screen, runway in use and movements derived from the tracks). Nothing here is invented: a
// value the backend cannot supply stays null and the panels say so.
import { useEffect, useState } from "react";
import { getAirport, getHealth } from "@/lib/api";

export function useBackendInfo(intervalMs = 15000) {
  const [health, setHealth] = useState(null);
  const [airport, setAirport] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      const [h, a] = await Promise.allSettled([getHealth(), getAirport()]);
      if (!alive) return;
      if (h.status === "fulfilled") setHealth(h.value);
      if (a.status === "fulfilled") setAirport(a.value);
      setError(h.status === "rejected" ? h.reason?.message : a.status === "rejected" ? a.reason?.message : null);
    };
    poll();
    const id = setInterval(poll, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [intervalMs]);
  return { health, airport, error };
}
