// The server-side audit trail.
//
// CLAUDE.md Section 12 requires every AI suggestion, controller action and system
// decision to be recorded server-side and append-only, and says the browser-only log is
// demo-grade rather than the real thing. This reads the real one.

import { useCallback, useEffect, useRef, useState } from "react";
import { getAuditLog } from "@/lib/api";

const REFRESH_MS = 8000;

export function useAuditLog({ limit = 60, level, search, poll = true } = {}) {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const payload = await getAuditLog({ limit, level, search });
      if (!mountedRef.current) return;
      setEntries(payload.entries || []);
      setTotal(payload.total ?? 0);
      setError(null);
    } catch (failure) {
      if (mountedRef.current) setError(failure.message);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [limit, level, search]);

  useEffect(() => {
    mountedRef.current = true;
    load();
    if (!poll) return () => { mountedRef.current = false; };
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [load, poll]);

  return { entries, total, error, loading, refresh: load };
}
