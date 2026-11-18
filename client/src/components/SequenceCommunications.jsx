import {useState} from 'react';

export default function SequenceCommunications({planning,selectedFlight}) {
  const {plan,busy,act}=planning;
  const [text,setText]=useState('');
  const [role,setRole]=useState('atco');
  if(!plan)return null;
  return <section className="instruction-card" aria-label="Communication-based sequencing">
    <header><strong>Communications → sequence</strong><label className="text-xs"><input type="checkbox" checked={plan.radioAuto!==false} disabled={busy} onChange={e=>act('radio_auto',{enabled:e.target.checked})}/> Auto-update plan</label></header>
    <p className="text-xs text-[var(--text-muted)]">Reviewed or identified tower instructions can update the movement plan. Pilot requests, uncertain speech and blocked changes stay for review. No outbound transmission.</p>
    <details><summary>Enter / correct a transcript</summary><form className="space-y-2 mt-2" onSubmit={async e=>{e.preventDefault();if(await act('communication',{text,role}))setText('');}}>
      <div className="flex items-center justify-between gap-2"><label className="text-xs">Speaker <select aria-label="Transcript speaker" value={role} onChange={e=>setRole(e.target.value)}><option value="atco">Tower / ATCO (reviewed)</option><option value="pilot">Pilot</option><option value="unknown">Uncertain</option></select></label>{selectedFlight&&<button type="button" className="text-xs underline" onClick={()=>setText(`${selectedFlight}, `)}>Use selected flight</button>}</div>
      <textarea aria-label="Sequence transcript" value={text} onChange={e=>setText(e.target.value)} maxLength={2000} placeholder="IGO123, number two for landing" rows={3} className="w-full rounded border p-2 text-xs bg-[var(--bg-base)]"/>
      <button disabled={busy||!text.trim()} className="action-primary">Process transcript</button>
      <p className="text-[11px] text-[var(--text-muted)]">Supported: cleared to land, taxi / line up / cleared for takeoff, number 1–100, follow/behind a queued callsign. Enter the matched flight identifier first. This text entry does not run speech recognition.</p>
    </form></details>
    <details open={!!plan.radioEvents?.some(e=>['review','blocked'].includes(e.status))}><summary>Sequence communication log ({plan.radioEvents?.length || 0})</summary><div className="max-h-64 overflow-auto">{[...(plan.radioEvents || [])].slice(-12).reverse().map(e=><article className="radio-sequence-event" key={e.id}><div className="flex justify-between gap-2"><strong>{e.role.toUpperCase()}</strong><span className={`radio-status radio-${e.status}`}>{e.status}</span></div><p>{e.text}</p><p className="text-[11px] text-[var(--text-muted)]">{e.reason}</p>{e.proposal&&['review','blocked'].includes(e.status)&&<button disabled={busy||plan.mode!=='normal'} className="mt-2 text-xs underline" onClick={()=>act('radio_accept',{event_id:e.id})}>Apply to plan after review</button>}</article>)}</div></details>
  </section>;
}
