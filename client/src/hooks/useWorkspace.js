import { useCallback, useEffect, useState } from "react";
import { getWorkspace, updateWorkspace, getClearances } from "@/lib/api";

export function useWorkspace() {
  const [data, setData] = useState({ strips: {}, stages: {} });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { const [state, clearances] = await Promise.all([getWorkspace(), getClearances()]); const next = { ...state, clearances }; setData(next); setError(null); }
    catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { let alive = true;
    const poll = async () => { try { const [state, clearances] = await Promise.all([getWorkspace(), getClearances()]); const next = { ...state, clearances }; if (alive) { setData(next); setError(null); } } catch (e) { if (alive) setError(e.message); } };
    poll(); const timer = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  const change = async (aircraft, position, action, extra = {}) => {
    setBusy(true);
    try {
      await updateWorkspace({ scope: data.scope, aircraft, position, action, version: data.strips[aircraft]?.version || 0, ...extra });
      await refresh();
      return true;
    } catch (e) { setError(e.message); return false; }
    finally { setBusy(false); }
  };
  return { data, error, busy, change, refresh };
}
