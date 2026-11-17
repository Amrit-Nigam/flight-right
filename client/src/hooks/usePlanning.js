import { useCallback, useEffect, useRef, useState } from 'react';
import { getPlan, changePlan, syncPlanningRadio, submitPlanningCommunication } from '@/lib/api';

export function usePlanning(source) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(0);
  const refresh = useCallback(async () => {
    try { const next = await getPlan(); setPlan(previous => previous?.scope===next.scope && previous.version>next.version ? previous : next); setError(''); setConnectionError(''); }
    catch (e) { setConnectionError(e.message); }
  }, []);
  useEffect(() => {
    let alive = true;
    let polling = false;
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const next = await getPlan();
        if (alive) { setPlan(previous => previous?.scope===next.scope && previous.version>next.version ? previous : next); setConnectionError(''); }
        const synced=await syncPlanningRadio(next.scope);
        if(alive)setPlan(previous=>previous?.scope===synced.scope&&previous.version>synced.version?previous:synced);
      }
      catch (e) { if (alive) setConnectionError(e.message); }
      finally { polling = false; }
    };
    poll(); const timer = setInterval(poll, 3000);
    window.addEventListener('speech-heard',poll);
    return () => { alive = false; clearInterval(timer); window.removeEventListener('speech-heard',poll); };
  }, [source]);
  const act = async (action, extra = {}) => {
    if (!plan || (pending.current && action !== 'takeover')) return false;
    pending.current += 1;
    setBusy(true); setError('');
    try {
      const next = action==='communication'
        ? await submitPlanningCommunication({scope:plan.scope,...extra})
        : await changePlan({version:plan.version, scope:plan.scope, action, ...extra});
      setPlan(previous => previous?.scope===next.scope && previous.version>next.version ? previous : next); return true;
    } catch (e) { setError(e.message); await getPlan().then(setPlan).catch(() => {}); return false; }
    finally { pending.current -= 1; setBusy(pending.current > 0); }
  };
  return {plan, error: error || connectionError, busy, act, refresh};
}
