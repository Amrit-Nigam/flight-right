import {useEffect,useState} from 'react';
import {getClearances} from '@/lib/api';
import {flightInstructions,instructionText} from '@/lib/instructionContext';

export default function FlightInstructions({flight,shared}) {
  const [loaded,setLoaded]=useState(null);
  const [error,setError]=useState('');
  const identity=flight?.icao24;
  const scope=shared?.context?.scope;
  useEffect(()=>{
    if(!identity)return;
    let alive=true;
    const refresh=()=>getClearances(identity).then(data=>{if(alive){setLoaded({identity,data});setError('');}}).catch(e=>{if(alive)setError(e.message);});
    refresh();const timer=setInterval(refresh,10000);
    window.addEventListener('speech-heard',refresh);
    return ()=>{alive=false;clearInterval(timer);window.removeEventListener('speech-heard',refresh);};
  },[identity,scope]);
  if(!flight)return null;
  const matched=loaded?.identity===identity && loaded.data.context?.scope===scope && loaded.data.context?.runId===shared?.context?.runId;
  const history=[...new Map([...(matched?loaded.data.history:[]),...(shared?.history || [])].map(row=>[row.id,row])).values()].sort((a,b)=>b.id-a.id);
  const data={...shared,history};
  const info=flightInstructions(data,flight);
  return <section aria-label="Flight instruction history" className="instruction-card">
    <header><strong>Recorded instructions</strong><span>{flight.callsign}</span></header>
    <div className="instruction-values"><div><small>Last altitude instruction</small><strong>{info.level || 'Not recorded'}</strong>{info.levelRecord&&<small>{info.levelRecord.issued_at?.slice(11,19)}Z · {info.levelRecord.source}</small>}</div><div><small>Last direction instruction</small><strong>{info.direction || 'Not recorded'}</strong>{info.directionRecord&&<small>{info.directionRecord.issued_at?.slice(11,19)}Z · {info.directionRecord.source}</small>}</div></div>
    <p className="text-[11px] text-[var(--text-muted)]">Current traffic session · recorded instructions are separate from reported position and time-limited prediction intent.</p>
    {error && <p role="status" className="text-xs text-[var(--amber)]">History refresh unavailable: {error}</p>}
    <details><summary>Instruction timeline ({info.current.length})</summary><ol className="instruction-timeline">{info.current.map(r=><li key={r.id}><time>{r.issued_at?.slice(11,19)}Z</time><strong>{instructionText(r)}</strong><span>{r.applied?'Accepted at recording':'Rejected'} · {r.source}</span></li>)}</ol>{!info.current.length&&<p className="text-xs py-2">No instructions recorded for this flight in this session.</p>}</details>
    {!!info.earlier.length&&<details><summary>Earlier / unlinked records ({info.earlier.length})</summary><p className="text-xs py-2">These records are not established as instructions for the current flight/session.</p>{info.earlier.map(r=><p key={r.id} className="text-xs py-1">{r.issued_at} · {instructionText(r)} · {r.applied?'accepted at recording':'rejected'}</p>)}</details>}
  </section>;
}
