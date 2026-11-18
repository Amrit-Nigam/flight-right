import { useState } from 'react';
import { previewSequence } from '@/lib/planningPreview';
import ReviewDialog from '@/components/ReviewDialog';

function slotUtc(plan, seconds) {
  return new Date((plan.baseTime + seconds) * 1000).toISOString().slice(11,19);
}

export function PlanningControls({ planning, selectedFlight }) {
  const {plan, busy, error, act, refresh} = planning;
  const scheduled = plan?.rows.find(r => r.id === selectedFlight);
  return <section aria-label="Controller planning authority" className="planning-controls shrink-0 border-b px-4 py-2" style={{background:'var(--bg-panel)',borderColor:'var(--border-default)'}}>
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <strong style={{color:plan?.mode === 'emergency' ? 'var(--red)' : 'var(--teal)'}}>{!plan ? 'PLANNING CONNECTING' : plan.mode === 'emergency' ? `EMERGENCY PLAN · ${plan.emergency}` : plan.mode === 'takeover' ? 'ATCO HAS CONTROL' : 'ASSIST · ATCO AUTHORIZES'}</strong>
      <span style={{color:'var(--text-muted)'}}>Planning demonstration · no pilot link</span>
      <button disabled={!plan || busy} onClick={() => act('optimize')} className="rounded border px-3 py-1" title="Stable earliest-ready scheduling under planning constraints">Recalculate sequence</button>
      <button disabled={!plan || busy || !scheduled || !!plan.emergency} onClick={() => act('emergency',{flight:selectedFlight})} className="rounded border px-3 py-1">Emergency for selected</button>
      <button disabled={!plan} onClick={() => { window.speechSynthesis?.cancel(); act('takeover'); }} className="rounded border px-3 py-1 font-bold" style={{borderColor:'var(--red)',color:'var(--red)'}}>Take control</button>
      {plan && plan.mode !== 'normal' && <button disabled={busy} onClick={() => act('normal')} className="underline">End case / normal</button>}
      <span className="ml-auto" style={{color:'var(--text-muted)'}}>Plan r{plan?.version ?? '—'}</span>
    </div>
    {error && <p role="alert" className="mt-2 text-xs" style={{color:'var(--red)'}}>{error} <button className="underline" onClick={refresh}>Refresh</button></p>}
  </section>;
}

export default function SequencePanel({planning, selectedFlight, onSelectFlight, flights=[], query='', nowSeconds=Date.now()/1000}) {
  const {plan, busy, act} = planning;
  const [drag, setDrag] = useState(null);
  const [proposal, setProposal] = useState(null);
  const [target, setTarget] = useState(null);
  const [departure, setDeparture] = useState('');
  const [dropIndex, setDropIndex] = useState(null);
  const [picker, setPicker] = useState(false);
  const [closing,setClosing]=useState(null);
  if (!plan) return <p className="p-3 text-xs">Connecting to sequence service…</p>;
  const preview = proposal ? previewSequence(plan, proposal.order) : null;
  const move = (id, index) => {
    const order = plan.rows.map(r => r.id).filter(k => k!==id);
    order.splice(index,0,id);
    setProposal({order, version:plan.version});
  };
  const save = async () => {
    if (proposal.version !== plan.version) { setProposal(null); return; }
    if (await act('reorder',{order:proposal.order})) setProposal(null);
  };
  const setTime = async () => {
    if (target.version !== plan.version) return;
    const seconds = Math.round(Date.parse(`${target.value}Z`)/1000-plan.baseTime);
    if (Number.isFinite(seconds) && await act('time',{flight:target.id,target:seconds})) setTarget(null);
  };
  return <section aria-label="Arrival and departure sequence" className="space-y-2 border-b pb-3" style={{borderColor:'var(--border-default)'}}>
    <div className="flex justify-between items-center text-xs"><h3 className="font-semibold tracking-wide">RUNWAY SEQUENCE</h3><button disabled={busy || !plan.undo || plan.mode==='emergency'} className="underline disabled:opacity-30" onClick={() => act('undo')}>Undo draft</button></div>
    <p className="text-[11px]" style={{color:'var(--text-muted)'}}>UTC targets · ARR / DEP · drag or use arrows</p>
    <button className="action-primary w-full" disabled={busy} onClick={()=>setPicker(!picker)} aria-expanded={picker}>+ Add observed flight</button>
    {picker && <div className="sequence-picker"><p>Choose a reported flight. ARR adds an arrival; DEP requires a surface report.</p>{flights.filter(f=>!plan.rows.some(r=>r.id===f.callsign)&&f.callsign.toLowerCase().includes(query.toLowerCase())).map(f=><div key={f.icao24 || f.callsign}><button className="font-semibold underline" onClick={()=>onSelectFlight(f.callsign,{surface:'sequence-picker'})}>{f.callsign}</button><button disabled={busy} aria-label={`Add ${f.callsign} arrival`} onClick={()=>act('add',{callsign:f.callsign,kind:'arrival'})}>+ ARR</button><button disabled={busy||f.onGround===false} title={f.onGround===false?'Already airborne':'Add departure'} aria-label={`Add ${f.callsign} departure`} onClick={()=>act('add',{callsign:f.callsign,kind:'departure'})}>+ DEP</button></div>)}{!flights.length&&<p>No reports available. Use a manual movement below.</p>}</div>}
    <details className="text-xs"><summary>Manual movement / unreported flight</summary><form className="flex flex-wrap gap-1 mt-2" onSubmit={async e => {e.preventDefault();const kind=e.nativeEvent.submitter?.value || 'departure';if(await act('add',{callsign:departure,kind})) setDeparture('');}}>
      <input aria-label="Movement callsign" placeholder="Movement callsign" maxLength={16} value={departure} onChange={e=>setDeparture(e.target.value)} className="min-w-0 flex-1 rounded border p-2 text-xs" style={{background:'var(--bg-base)',borderColor:'var(--border-default)'}} />
      <span className="w-full">Choose movement type:</span><button value="arrival" disabled={busy||!departure.trim()} className="rounded border px-2 py-2 text-xs">+ Arrival</button><button value="departure" disabled={busy||!departure.trim()} className="rounded border px-2 py-2 text-xs">+ Departure</button>
    </form></details>
    {!plan.rows.length && <p className="rounded border border-dashed p-3 text-xs" style={{color:'var(--text-muted)'}}>Select a flight below and add it to the arrival or departure sequence.</p>}
    {plan.rows.filter(r => r.callsign.toLowerCase().includes(query.toLowerCase())).map(r => {
      const i=plan.rows.indexOf(r);
      const late=Math.max(0,Math.floor(nowSeconds-plan.baseTime-r.target));
      const observed=flights.find(f=>f.callsign===r.callsign);
      return <article key={r.id} data-sequence-flight={r.id} onDragOver={e => { e.preventDefault(); setDropIndex(i); }} onDragLeave={()=>setDropIndex(null)} onDrop={e => { e.preventDefault(); if(drag && !busy) move(drag,i); setDrag(null);setDropIndex(null); }} className="rounded border p-2 text-xs" style={{borderColor:dropIndex===i?'var(--teal)':selectedFlight===r.id?'var(--amber)':'var(--border-default)',borderTopWidth:dropIndex===i?3:1,background:'var(--bg-base)'}}>
        <div className="flex items-center gap-2">
          <button draggable={!busy} disabled={busy} onDragStart={e => {setDrag(r.id);e.dataTransfer.setData('text/plain',r.id);}} onDragEnd={() => setDrag(null)} aria-label={`Drag ${r.callsign}`} title="Drag to reorder" className="cursor-grab px-1">⠿</button>
          <button onClick={() => onSelectFlight(r.callsign,{surface:'sequence'})} className="font-bold">{r.callsign}</button>
          <span title="Sequence position" className="text-[10px]">#{i+1}</span>
          <span className="rounded px-1" style={{background:'var(--bg-panel-alt)',color:r.kind==='arrival'?'var(--teal)':'var(--amber)'}}>{r.kind==='arrival'?'ARR':'DEP'}</span>
          <button disabled={busy} className="ml-auto font-mono underline" title={new Date((plan.baseTime+r.target)*1000).toISOString()} onClick={() => setTarget({id:r.id,value:new Date((plan.baseTime+r.target)*1000).toISOString().slice(0,19),version:plan.version})}>{slotUtc(plan,r.target)}Z</button>
        </div>
        <p className="mt-1 text-[10px]" style={{color:'var(--text-muted)'}}>{r.provenance}</p>
        {late>0&&<p className="sequence-overdue" role="status">Overdue {Math.floor(late/60)}m {late%60}s · reconcile target</p>}
        <p className="sequence-observed">{observed?`${observed.staleTrack?'Old':'Current feed'} report: ${observed.phaseLabel || (observed.onGround?'On ground':'Airborne')} · ${observed.distanceToVabbNm ?? '?'} NM from VABB`:'No linked aircraft in current feed.'} A report does not confirm movement completion.</p>
        <div className="mt-2 flex items-center gap-3" style={{color:'var(--text-muted)'}}>
          <button disabled={busy||i===0} aria-label={`Move ${r.callsign} earlier`} onClick={() => move(r.id,i-1)}>↑ Earlier</button>
          <button disabled={busy||i===plan.rows.length-1} aria-label={`Move ${r.callsign} later`} onClick={() => move(r.id,i+1)}>↓ Later</button>
          <button disabled={busy} onClick={() => act('pin',{flight:r.id})}>{r.pinned?'● Pinned':'Pin'}</button>
          <button disabled={busy||plan.emergency===r.id} className="ml-auto underline" aria-label={`Remove ${r.callsign} from plan`} onClick={() => act('remove',{flight:r.id})}>Remove</button>
          <button disabled={busy||plan.emergency===r.id} className="underline" aria-label={`Close out ${r.callsign}`} onClick={()=>setClosing({id:r.id,outcome:'completed',version:plan.version})}>Close out</button>
        </div>
      </article>;
    })}
    {proposal && <ReviewDialog label="Review sequence changes" onCancel={()=>setProposal(null)}><div className="sequence-review-content" tabIndex={0}>
      <strong>Proposed sequence</strong><p className="my-2">{proposal.order.join(' → ')}</p>
      <table className="my-2 w-full text-left text-[10px]"><caption className="text-left mb-1">Estimated runway slots · UTC</caption><thead><tr><th>Flight</th><th>Current</th><th>Proposed</th></tr></thead><tbody>{preview.rows.map(row=><tr key={row.id}><td className="py-1">{row.callsign}</td><td>{slotUtc(plan,row.previousTarget)}</td><td style={{color:row.target!==row.previousTarget?'var(--amber)':undefined}}>{slotUtc(plan,row.target)}</td></tr>)}</tbody></table>
      {preview.error && <p role="alert" className="my-2" style={{color:'var(--red)'}}>{preview.error}</p>}
      <p className="mb-2">Server checks slots and pins before saving. No pilot instruction is sent.</p>
      {proposal.version!==plan.version && <p>Plan changed. Cancel and move again.</p>}
      </div><footer><button disabled={busy||!!preview.error||proposal.version!==plan.version} className="action-primary disabled:opacity-40" onClick={save}>Check & save</button><button className="underline" onClick={() => setProposal(null)}>Cancel</button></footer></ReviewDialog>}
    {closing&&<ReviewDialog label="Close movement" onCancel={()=>setClosing(null)}><div className="sequence-review-content"><h3>Close out {closing.id}</h3><p>Controller-confirmed outcome. Surveillance does not automatically establish completion. The movement and its target stay in history.</p><label>Outcome <select aria-label="Movement outcome" value={closing.outcome} onChange={e=>setClosing({...closing,outcome:e.target.value})}><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label><p>Closing is final for draft undo; use Add movement for another operation.</p></div><footer><button className="action-primary" disabled={busy||closing.version!==plan.version} onClick={async()=>{if(await act('close',{flight:closing.id,outcome:closing.outcome}))setClosing(null);}}>Record close-out</button><button onClick={()=>setClosing(null)}>Cancel</button></footer>{closing.version!==plan.version&&<p>Plan changed. Cancel and review again.</p>}</ReviewDialog>}
    {!!plan.closedMovements?.length&&<details className="sequence-history"><summary>Closed movement history ({plan.closedMovements.length})</summary>{[...plan.closedMovements].reverse().map(r=><p key={`${r.revision}:${r.id}`}>{r.callsign} · {r.kind} · {r.outcome} · target {slotUtc(plan,r.target)}Z · closed {new Date(r.closedAt*1000).toISOString().replace('T',' ')} · {r.reason}</p>)}</details>}
    {target && <div className="rounded border p-2 text-xs"><label>Target date and time (UTC)<input type="datetime-local" step="1" value={target.value} onChange={e=>setTarget({...target,value:e.target.value})} className="mt-1 w-full border bg-transparent p-1" /></label><button disabled={busy||!target.value||target.version!==plan.version} className="mx-2 underline" onClick={setTime}>Save</button><button onClick={()=>setTarget(null)}>Cancel</button>{target.version!==plan.version && <p role="status">Plan changed. Cancel and reopen this target.</p>}</div>}
    <details className="text-[11px]" style={{color:'var(--text-muted)'}}><summary className="cursor-pointer">Planning limits</summary><p className="mt-1">Planning gap: 120 s. Manual departure readiness is unverified; operational wake, fuel, surface and local-rule clearance are not established.</p></details>
  </section>;
}

export function PlanningFlightActions({planning, flight}) {
  const {plan,busy,act} = planning;
  if (!plan || !flight || flight.staleSelection) return null;
  const row=plan.rows.find(r=>r.id===flight.callsign);
  return <div className="flex flex-wrap items-center gap-2 rounded border p-3 text-xs" style={{borderColor:'var(--border-default)'}}>
    {row ? <><strong>{row.kind==='arrival'?'Arrival':'Departure'} planned {slotUtc(plan,row.target)}Z</strong><button disabled={busy||!!plan.emergency} className="underline" onClick={()=>act('emergency',{flight:row.id})}>Emergency priority</button></> : <><span>Add {flight.callsign} to plan</span>{['arrival','departure'].map(kind=><button key={kind} disabled={busy || (kind==='departure' && flight.onGround===false)} title={kind==='departure' && flight.onGround===false ? 'Already airborne' : 'Add planning movement'} className="rounded border px-3 py-2" onClick={()=>act('add',{callsign:flight.callsign,kind})}>{kind==='arrival'?'Arrival':'Departure'}</button>)}</>}
  </div>;
}

export function InstructionJournal({planning}) {
  const {plan,busy,act} = planning;
  if (!plan) return null;
  const pending=plan.messages.filter(m=>m.status==='draft');
  const preview = text => {window.speechSynthesis?.cancel(); if('speechSynthesis' in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance(`${text}`));};
  return <section className="rounded border p-3 text-xs" style={{borderColor:'var(--border-default)'}}>
    <div className="flex items-center justify-between"><h3 className="font-semibold">Plan communications</h3><span>{pending.length} pending</span></div>
    <p className="my-2" style={{color:'var(--text-muted)'}}>Local plan advisories only. Authorization records simulated delivery, not a radio transmission.</p>
    <button disabled={busy||!pending.length||plan.mode!=='normal'} onClick={()=>act('issue',{authorized:true})} className="rounded border px-3 py-2 disabled:opacity-30">Authorize current plan advisories</button>
    <details className="mt-3"><summary className="cursor-pointer">Messages & history</summary>{plan.messages.slice(-20).reverse().map(m=><div key={m.id} className="border-b py-2"><p>{m.text}</p><p style={{color:'var(--teal)'}}>{m.status}</p>{m.status!=='cancelled'&&<button className="underline" onClick={()=>preview(m.text)}>Local voice preview</button>}</div>)}</details>
  </section>;
}
