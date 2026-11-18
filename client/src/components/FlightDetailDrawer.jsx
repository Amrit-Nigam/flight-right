import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { statusColors, statusColorsLight, statusIcons } from "@/lib/flightDisplay";
import { logAudit } from "@/lib/siteLogger";
import { submitClearance } from "@/lib/api";
import {ageLabel,INSTRUCTION_BOUNDS,instructionError} from '@/lib/trafficPresentation';

// One aircraft, every field from a real source (27 Sep 2026). It used to show route "BOM TMA",
// type "UNK", fuel "--", squawk "----" and a "waypoint" guessed from position, with three buttons
// (RECORD AIRBORNE INSTRUCTION / ADD TO SEQUENCE / ASSIGN HOLDING) that only showed a toast. Now:
//   registration and type -> adsb.lol; route -> adsbdb lookup; ETA -> only when the looked-up
//   destination is VABB, from distance and ground speed; distance and bearing -> computed;
//   flight phase -> derived from altitude and climb rate (and labelled so).
// RECORD AIRBORNE INSTRUCTION records a typed instruction through POST /api/clearances, the same door the
// speech chain uses: it reshapes this aircraft's predicted paths and is audited. Nothing is
// transmitted. Sequencing and holding have no backend and were removed rather than faked.

const ACTIONS = [
  { key: "CLIMB", unit: "ft", placeholder: "e.g. 37000" },
  { key: "DESCEND", unit: "ft", placeholder: "e.g. 13000" },
  { key: "TURN", unit: "° heading", placeholder: "e.g. 270" },
  { key: "SPEED", unit: "kt", placeholder: "e.g. 250" },
];

export default function FlightDetailDrawer({ flight, onClose, theme = "light", embedded = false }) {
  const palette = theme === "light" ? statusColorsLight : statusColors;
  const accentColor = (flight && palette[flight.status]) || "var(--amber)";
  const [formOpen, setFormOpen] = useState(false);
  const [action, setAction] = useState("DESCEND");
  const [value, setValue] = useState("");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const invalid=instructionError(action,value);
  const bounds=INSTRUCTION_BOUNDS[action];

  const submit = async () => {
    if (!flight || flight.staleSelection || !value || submitting || !Number.isFinite(Number(value))) return;
    if(invalid){setResult({ok:false,text:invalid});return;}
    setSubmitting(true);
    try {
      const r = await submitClearance({ callsign: flight.callsign, action, value: Number(value) });
      window.dispatchEvent(new Event("speech-heard"));
      setResult({ ok: true, text: r.applied ? `Applied: ${r.effect}` : `Recorded, not applied: ${(r.problems || []).join("; ")}` });
      logAudit("flights:drawer", "Typed clearance submitted", { callsign: flight.callsign, action, value });
    } catch (error) {
      setResult({ ok: false, text: error.message });
    } finally {
      setSubmitting(false);
    }
  };

  const vs = Math.round(Number(flight?.verticalRateFpm) || 0);
  const fields = flight ? [
    ["ROUTE", flight.route ?? "not found", flight.routeSource ?? "adsbdb has no route for this callsign"],
    ["ALT", flight.altitude, "Reported altitude"],
    ["SPEED", flight.speed, "Ground speed"],
    ["V/S", `${vs > 0 ? "+" : ""}${vs} fpm`, "Reported vertical rate"],
    ["TRACK", `${Math.round(flight.heading)}°`, "Track over ground"],
    ["ACFT", flight.aircraft ? `${flight.aircraft}${flight.registration ? ` · ${flight.registration}` : ""}` : "unknown",
      flight.aircraftDescription ? `${flight.aircraftDescription} (${flight.aircraftSource || 'source unavailable'})` : flight.aircraft ? `${flight.aircraftSource || 'Type lookup; source unavailable'} · description unavailable` : "Type unavailable from aircraft lookup"],
    ["FROM VABB", flight.distanceToVabbNm != null ? `${flight.distanceToVabbNm} NM · ${flight.bearingFromVabbDeg}°` : "—", "Distance and bearing from Mumbai"],
    ["ETA VABB", flight.displayEta ?? "—", "Distance ÷ ground speed for lookup destination VABB; not a landing slot"],
    ["SQUAWK", flight.squawk ?? "not received", flight.squawk ? "Transponder code (adsb.lol)" : "OpenSky does not carry it; adsb.lol supplies it in live mode"],
    ["POSITION REPORT UTC", Number.isFinite(flight.timePosition) ? new Date(flight.timePosition*1000).toISOString().replace('T',' ').replace('.000Z','Z') : 'Time unavailable', 'Timestamp of the reported position, distinct from the forecast and wall clock'],
  ] : [];

  return (
    <AnimatePresence>
      {flight && (
        <>
          {!embedded && <motion.div key="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
                      className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.35)" }}
                      onClick={() => { logAudit("flights:drawer", "Drawer backdrop dismissed", { callsign: flight.callsign }); setFormOpen(false); setResult(null); onClose(); }} />}
          <motion.div key="drawer" initial={embedded ? false : { y: "100%" }} animate={{ y: 0 }} exit={embedded ? undefined : { y: "100%" }}
                      transition={embedded ? {duration:0} : { type: "spring", damping: 30, stiffness: 320 }}
                      className={embedded ? "relative shrink-0 rounded overflow-hidden" : "fixed bottom-0 left-0 right-0 z-50"}
                      aria-label="Selected aircraft details"
                      style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", background: "var(--bg-panel-alt)", borderTop: `3px solid ${accentColor}`, boxShadow: "0 -8px 40px rgba(0,0,0,0.25)" }}>
            <div className="flight-details-header flex items-center justify-between px-5 py-3" style={{ borderBottom: "1px solid var(--border-default)" }}>
              <div className="flex flex-1 items-start gap-3 min-w-0">
                <div className="flight-identity-icon flex h-11 w-11 shrink-0 items-center justify-center rounded text-xl"
                     style={{ background: "var(--bg-base)", color: accentColor, border: `1px solid ${accentColor}40` }}>
                  {statusIcons[flight.status] || "✈"}
                </div>
                <div className={`flex min-w-0 gap-2 ${embedded ? 'flex-col items-start' : 'items-center'}`}>
                  <span className="font-display text-[24px] tracking-wider leading-none break-all" style={{ color: accentColor }}>{flight.callsign}</span>
                  <span className="font-display text-[10px] tracking-widest px-2 py-0.5 rounded-sm border shrink-0"
                        style={{ borderColor: accentColor, color: accentColor, background: `${accentColor}14` }}
                        title="Flight phase derived from altitude and climb rate; no flight plan is available">
                    {flight.phaseLabel || flight.status}
                  </span>
                  <span className="font-display text-[11px] break-words" style={{ color: "var(--text-muted)" }}>
                    ICAO24 {flight.icao24} · {flight.originCountry}
                  </span>
                </div>
              </div>
              <button type="button" aria-label="Close"
                      onClick={() => { logAudit("flights:drawer", "Flight detail drawer closed", { callsign: flight.callsign }); setFormOpen(false); setResult(null); onClose(); }}
                      className="shrink-0 ml-4 p-1.5 rounded hover:bg-[var(--bg-raised)] transition-colors">
                <X className="w-5 h-5" style={{ color: "var(--text-muted)" }} />
              </button>
            </div>

            {flight.staleSelection && <p role="status" className="px-5 py-3 text-xs" style={{color:'var(--amber)'}}>Last observed snapshot. Aircraft is absent from the current feed; instruction entry is disabled.</p>}
            {flight.qualityWarning&&<p className="px-5 pt-3 text-xs text-[var(--amber)]">{flight.qualityWarning}</p>}
            <div className="flight-provenance px-5 pt-3" role="status"><strong style={{color:flight.staleTrack?'var(--amber)':'var(--teal)'}}>{flight.staleTrack?'OLD / UNDATED POSITION · ':''}{ageLabel(flight.reportAgeSeconds)}</strong></div>
            <div className="flight-detail-fields px-5 py-4 overflow-x-auto">
              <div className="grid gap-3" style={{ gridTemplateColumns: embedded ? "repeat(2, minmax(0, 1fr))" : "repeat(9, minmax(92px, 1fr))" }}>
                {fields.map(([label, val, source]) => (
                  <div key={label} className="flex flex-col gap-1 rounded px-3 py-2.5" title={source}
                       style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", minWidth: 0 }}>
                    <span className="font-display text-[12px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span className="font-display text-[14px] leading-snug break-words" style={{ color: "var(--text-primary)" }}>{val}</span>
                    {['ETA VABB','ROUTE','ACFT'].includes(label)&&<small className="field-source">{source}</small>}
                  </div>
                ))}
              </div>
              <div className="flight-provenance"><p>Phase inferred from surveillance; a surface report does not establish arrival or departure intent. Metadata observation dates are not supplied.</p>{/^[a-f0-9]{6}$/i.test(flight.icao24 || '')&&String(flight.callsign).toUpperCase()===flight.icao24?.toUpperCase()&&<p>Identity is an ICAO24 address, not a received callsign.</p>}</div>
            </div>

            <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
              <button disabled={flight.onGround || flight.staleSelection} type="button" onClick={() => { setFormOpen((o) => !o); setResult(null); }}
                      className="font-display text-[11px] tracking-widest px-5 py-2.5 transition-all active:scale-95 hover:brightness-110"
                      style={{ border: "1.5px solid var(--amber)", color: "var(--amber)", background: "rgba(245,166,35,0.06)" }}>
                RECORD AIRBORNE INSTRUCTION
              </button>
              {formOpen && (
                <>
                  <select aria-label="Instruction action" value={action} onChange={(e) => setAction(e.target.value)} className="font-display text-[11px] px-2 py-2"
                          style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}>
                    {ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.key}</option>)}
                  </select>
                  <input aria-label="Instruction value" aria-invalid={!!value&&!!invalid} aria-describedby="instruction-limits" type="number" min={bounds?.[0]} max={bounds?.[1]} value={value} onChange={(e) => setValue(e.target.value)}
                         placeholder={ACTIONS.find((a) => a.key === action)?.placeholder}
                         className="font-display text-[11px] px-2 py-2 w-[120px]"
                         style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }} />
                  <span className="font-body text-[10px]" style={{ color: "var(--text-muted)" }}>{ACTIONS.find((a) => a.key === action)?.unit}</span>
                  <p id="instruction-limits" className="w-full text-xs" style={{color:value&&invalid?'var(--red)':'var(--text-muted)'}}>{value&&invalid?invalid:`Allowed range: ${bounds?.[0]}–${bounds?.[1]} ${ACTIONS.find(a=>a.key===action)?.unit}`}</p>
                  <button type="button" onClick={submit} disabled={!value || !!invalid || submitting || flight.staleSelection}
                          className="font-display text-[11px] tracking-widest px-4 py-2 disabled:opacity-40"
                          style={{ background: "var(--amber)", color: "var(--on-amber)" }}>
                    {submitting ? 'RECORDING…' : 'RECORD'}
                  </button>
                  <span className="font-body text-[10px]" style={{ color: "var(--text-muted)" }}>
                    Recorded and used to reshape this aircraft&apos;s predicted paths. Nothing is transmitted.
                  </span>
                </>
              )}
              {result && (
                <span className="font-body text-[11px] w-full" style={{ color: result.ok ? "var(--green)" : "var(--amber)" }}>{result.text}</span>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
