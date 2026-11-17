import { useState } from "react";

export default function StripOperations({ flight, position, workspace }) {
  const { data, error, busy, change, refresh } = workspace;
  const key = flight.icao24 || flight.callsign;
  const strip = data.strips[key] || {};
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const owned = strip.owner === position;
  const act = (action, extra) => change(key, position, action, extra);
  const button = "rounded border px-2 py-2 text-xs disabled:opacity-40 hover:brightness-125";
  return <section className="rounded border p-3 space-y-3" style={{ borderColor: "var(--border-default)", background: "var(--bg-panel-alt)" }}>
    <div className="flex justify-between"><h2 className="font-semibold">{flight.callsign} · coordination</h2><span className="text-xs">v{strip.version || 0}</span></div>
    <p className="text-xs">Owner: <strong>{strip.owner || "Unassigned"}</strong>{strip.pending && ` → awaiting ${strip.pending}`}</p>
    <p className="text-xs">Recorded stage: <strong>{strip.stage || "Unassigned"}</strong></p>
    <p className="text-xs" style={{ color: "var(--text-muted)" }}>Manual demonstration records. No radio transmission or runway authorization.</p>
    {error && <div role="alert" className="text-xs" style={{ color: "var(--amber)" }}>{error} <button onClick={refresh} className={button}>Refresh</button></div>}
    <div className="flex flex-wrap gap-2">
      {!strip.owner && <button className={button} disabled={busy || !data.scope} onClick={() => act("claim")}>Assume at {position}</button>}
      {strip.pending === position && <button className={button} disabled={busy} onClick={() => act("acknowledge")}>Acknowledge handoff</button>}
      {owned && !strip.pending && ["clearance", "ground", "tower"].filter(x => x !== position).map(target => <button key={target} className={button} disabled={busy} onClick={() => act("handoff", { target })}>Offer to {target}</button>)}
      {owned && strip.pending && <button className={button} disabled={busy} onClick={() => act("cancel handoff")}>Cancel handoff</button>}
    </div>
    {owned && <><label className="block text-xs">Record operational stage
      <select aria-label="Record operational stage" value="" disabled={busy} onChange={e => e.target.value && act("stage", { value: e.target.value })} className="w-full mt-1 p-2 rounded" style={{ background: "var(--bg-base)" }}><option value="">Choose event…</option>{(data.stages[position] || []).map(x => <option key={x}>{x}</option>)}</select>
    </label><button className={button} disabled={busy} onClick={() => { setDraft({ note: strip.note || "", runway: strip.runway || "", taxiRoute: strip.taxiRoute || "", plannedRoute: strip.plannedRoute || "" }); setEditing(true); }}>Edit coordination notes</button></>}
    <dl className="text-xs space-y-2">{[["plannedRoute", "Manually entered route"], ["runway", "Recorded runway"], ["taxiRoute", "Recorded taxi instructions"], ["note", "Coordination note"]].map(([field, label]) => <div key={field}><dt style={{ color: "var(--text-muted)" }}>{label}</dt><dd className="break-words">{strip[field] || "Not recorded"}</dd></div>)}</dl>
    {editing && owned && <form className="space-y-2" onSubmit={async e => { e.preventDefault(); if (await act("annotate", draft)) setEditing(false); }}>{[["plannedRoute",500],["runway",30],["taxiRoute",200],["note",1000]].map(([field,max]) => <label key={field} className="block text-xs">{field}<input maxLength={max} value={draft[field]} onChange={e => setDraft({ ...draft, [field]: e.target.value })} className="block w-full p-2 mt-1 rounded" style={{ background: "var(--bg-base)" }} /></label>)}<button className={button} disabled={busy}>Save record</button><button type="button" className={button} onClick={() => setEditing(false)}>Cancel</button></form>}
    <div className="border-t pt-3 text-xs space-y-2" style={{borderColor:"var(--border-default)"}}>
      <h3 className="font-semibold">Instructions currently influencing predictions</h3>
      {(data.clearances?.inForce?.[key] || []).map((c,i) => <p key={i}>{c.action} {c.value ?? c.fix} ? {c.source}</p>)}
      {!(data.clearances?.inForce?.[key] || []).length && <p>None in force</p>}
      <details><summary>Recent recorded instructions</summary>{(data.clearances?.history || []).filter(c => c.matched_icao24 === key).map(c => <p key={c.id} className="py-1">{c.recorded_at} ? {c.action} {c.value ?? c.fix} ? {c.applied ? "Applied at recording" : "Not applied"}</p>)}</details>
    </div>
    <details><summary className="text-xs cursor-pointer">Event history ({strip.history?.length || 0})</summary><ol className="max-h-48 overflow-auto text-xs space-y-2 mt-2">{[...(strip.history || [])].reverse().map((event,i) => <li key={i}><time>{event.at.slice(11,19)}Z</time> · {event.position} · {event.action} {event.value || event.target}<div style={{color:"var(--text-muted)"}}>{event.user}</div></li>)}</ol></details>
  </section>;
}
