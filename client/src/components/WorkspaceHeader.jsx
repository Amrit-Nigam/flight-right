import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Moon,Sun} from 'lucide-react';
import {ageLabel} from '@/lib/trafficPresentation';

export default function WorkspaceHeader({feed,connection,airport,health,theme,onToggleTheme,notifications,alertCount,aiEnabled,onToggleAI}){
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id);},[]);
  const age=Math.max(0,now-Date.parse(feed.updatedAt));
  const stale=!Number.isFinite(age)||age>45000;
  const receiptAge=feed.receivedAt?Math.max(0,Math.floor((now-Date.parse(feed.receivedAt))/1000)):null;
  const status=connection==='offline'?'Disconnected':!feed.source?'Connecting':feed.error?'Feed error':stale?'Stale data':alertCount?`${alertCount} active alert${alertCount===1?'':'s'}`:null;
  const at=Date.parse(feed.dataTimeUtc);
  const advancing=connection!=='offline'&&!feed.error&&!stale;
  const clock=Number.isFinite(at)?new Date(at+(advancing?age*(feed.replay?.speed ?? 1):0)):null;
  return <header className="workspace-header">
    <div className="workspace-brand"><strong>FlightRight</strong><span title={airport?.inUse?.basis}>VABB{airport?.inUse?` · RWY ${airport.inUse.end} estimated`:''}</span>{airport?.inUse&&<small className="runway-provenance">{airport.inUse.derived==='surface wind'?'Wind estimate':'Track-derived usage'} · not ATIS</small>}</div>
    <div className="workspace-clock"><strong className="data-clock">{clock?clock.toISOString().slice(11,19):'--:--:--'}</strong><span>UTC{clock?` · ${clock.toISOString().slice(0,10)}`:''}</span></div>
    <div className={`workspace-feed ${status?'needs-attention':''}`} role="status"><strong>{status || (feed.source==='replay'?'Replay':'Live')}</strong><span>{feed.count || 0} reports · {connection==='offline'?'cached':connection}</span><small>Last traffic update: {ageLabel(receiptAge)}</small>{feed.source&&<small>{feed.source==='replay'?'Recorded':'Live'} source · {stale?'feed timestamp stale':'per-track ages vary'}</small>}</div>
    <div className="workspace-header-actions">
      <button aria-label="Toggle Theme" title="Toggle Theme" onClick={onToggleTheme}>{theme==='dark'?<Sun size={18}/>:<Moon size={18}/>}</button>
      <details className="workspace-session"><summary>Session{notifications.length?` · ${notifications.length}`:''}</summary><div>
        <strong>{health?.controller || 'Controller unavailable'}</strong><p className="text-xs text-[var(--text-muted)]">Shared demonstration session</p>
        <Link to="/logs" title="Audit log">Open session logs</Link>
        <button aria-pressed={aiEnabled} onClick={onToggleAI}>Suggestions {aiEnabled?'shown':'hidden'}</button>
        <p className="font-semibold mt-3">Recent alert notifications</p>{!notifications.length&&<p>No notifications since this page opened.</p>}
        {notifications.map(n=><article key={n.key}><strong>{n.pair.join(' × ')} · tier {n.tier}</strong><small>{n.at}</small><p>{n.reason}</p></article>)}
      </div></details>
    </div>
  </header>;
}
