import { useState } from "react";
import {localTraffic,sortLocalTraffic,ageLabel} from '@/lib/trafficPresentation';

export const POSITIONS = {
  tower: { name: "Tower", detail: "Runway picture · arrivals and departures" },
  ground: { name: "Ground", detail: "Reported surface traffic · coverage dependent" },
  clearance: { name: "Clearance", detail: "Flight information · recorded instructions" },
};

export function PositionSwitcher({ position, onChange, flights }) {
  return <nav aria-label="Controller position" className="position-switcher flex shrink-0 flex-wrap items-center gap-2 px-4 py-2 border-b" style={{ borderColor: "var(--border-default)", background: "var(--bg-panel-alt)" }}>
    <span className="text-xs uppercase tracking-widest mr-3">Working position</span>
    {Object.entries(POSITIONS).map(([key, value]) => <button key={key} aria-pressed={position === key} onClick={() => onChange(key)} className="rounded px-5 py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2" style={{ background: position === key ? "var(--amber)" : "var(--bg-base)", color: position === key ? "#111" : "var(--text-primary)" }}>
      {value.name}{key === "ground" ? ` · ${flights.filter(f => f.onGround === true).length}` : ""}
    </button>)}
    <span className="ml-auto text-xs" style={{ color: "var(--text-muted)" }}>Shared demonstration session · recorded position handoffs</span>
  </nav>;
}

export default function ControllerWorkspace({ position, flights, selectedFlight, onSelectFlight, source, workspace, compact=false }) {
  const [query, setQuery] = useState("");
  const [radius,setRadius]=useState('50');
  const strips = workspace?.data.strips || {};
  const record = f => strips[f.icao24 || f.callsign] || {};
  const positionScope = position === "ground" ? flights.filter(f => f.onGround === true || record(f).owner === "ground" || record(f).pending === "ground") : flights;
  const scope=sortLocalTraffic(positionScope.filter(f=>radius==='all'||localTraffic(f,Number(radius))||f.status==='CONFLICT'||record(f).owner===position||record(f).pending===position));
  const bay = f => record(f).pending === position ? "INCOMING HANDOFF" : record(f).owner === position ? (record(f).stage || "ASSUMED").toUpperCase() : record(f).owner ? "OTHER POSITIONS" : "UNASSIGNED";
  const visible = scope.filter(f => `${f.callsign} ${f.icao24} ${f.route || ""}`.toLowerCase().includes(query.toLowerCase()));
  return <section aria-label={`${POSITIONS[position].name} flight strips`} className="flex flex-col h-full min-h-0 rounded border" style={{ borderColor: "var(--border-default)", background: "var(--bg-panel-alt)" }}>
    <div className="p-3 border-b" style={{ borderColor: "var(--border-default)" }}>
      {!compact&&<><div className="flex justify-between font-semibold"><h2>Flight strips</h2><span>{scope.length}</span></div><p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{POSITIONS[position].detail}</p></>}
      <input aria-label="Search flight strips" placeholder="Callsign, route or ICAO24" value={query} onChange={e => setQuery(e.target.value)} className={`${compact?'':'mt-3'} w-full rounded border p-2 text-sm`} style={{ background: "var(--bg-base)", borderColor: "var(--border-default)" }} />
      <label className="traffic-scope"><span>Strip scope</span><select aria-label="Strip surveillance scope" value={radius} onChange={e=>setRadius(e.target.value)}><option value="25">VABB · 25 NM</option><option value="50">VABB · 50 NM</option><option value="100">VABB · 100 NM</option><option value="all">All surveillance</option></select></label>
      <p className="text-xs mt-2 text-[var(--text-muted)]">{scope.length} of {positionScope.length} reports · surface, VABB arrivals, then callsign. Alerts / owned strips stay listed. Map shows wider surveillance.</p>
    </div>
    <div className="overflow-y-auto flex-1 p-2 space-y-2">
      {workspace?.error && <p role="alert" className="text-xs p-2">Workflow unavailable: {workspace.error}</p>}
      {[...new Set(visible.map(bay))].sort().map(group => <div key={group} className="space-y-2"><h3 className="text-xs tracking-widest py-2" style={{color:"var(--teal)"}}>{group}</h3>{visible.filter(f => bay(f) === group).map(f => <button key={f.icao24 || f.callsign} onClick={() => onSelectFlight(f.callsign, { surface: "flight-strip" })} aria-pressed={selectedFlight === f.callsign} className="w-full text-left border-l-4 rounded p-2 focus-visible:outline focus-visible:outline-2" style={{ borderColor: selectedFlight === f.callsign ? "var(--amber)" : f.onGround ? "var(--teal)" : "var(--border-default)", background: "var(--bg-base)" }}>
        <div className="flex justify-between gap-2"><strong>{f.callsign}</strong><span className="text-xs">{f.aircraft || "Type unknown"}</span></div>
        <p className="text-xs mt-1" title={f.routeSource}>{f.route || "Route unavailable"}</p>
        <div className="grid grid-cols-2 text-xs gap-2 mt-2"><span>ALT {f.altitude ?? "—"}</span><span>GS {f.speed ?? "—"}</span></div>
        <p className="strip-freshness text-xs mt-2" style={{ color: f.staleTrack?'var(--amber)':"var(--text-muted)" }}>{f.staleTrack?'OLD REPORT · ':''}{ageLabel(f.reportAgeSeconds)}</p>
        {f.qualityWarning&&<p className="text-xs mt-1 text-[var(--amber)]">Check ground flag / altitude / speed</p>}
        <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>{f.phaseLabel}{f.staleTrack?' · last reported':''}</p>
      </button>)}</div>)}
      {!visible.length && <p role="status" className="p-3 text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{position === "ground" && !scope.length ? `No ground reports in this ${source || "disconnected"} feed. This does not establish that the airport surface is clear. The bundled replay contains airborne traffic only.` : "No matching aircraft reports."}</p>}
    </div>
    {!compact&&<p className="p-3 text-xs border-t" style={{ color: "var(--text-muted)", borderColor: "var(--border-default)" }}>Route lookup is not a filed flight plan. Select a strip for source details.</p>}
  </section>;
}
