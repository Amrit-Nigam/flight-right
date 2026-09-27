import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { statusColors, statusColorsLight, statusIcons } from "@/lib/flightDisplay";
import { logAudit } from "@/lib/siteLogger";
import { submitClearance } from "@/lib/api";

// One aircraft, every field from a real source (27 Sep 2026). It used to show route "BOM TMA",
// type "UNK", fuel "--", squawk "----" and a "waypoint" guessed from position, with three buttons
// (ISSUE CLEARANCE / ADD TO SEQUENCE / ASSIGN HOLDING) that only showed a toast. Now:
//   registration and type -> adsb.lol; route -> adsbdb lookup; ETA -> only when the looked-up
//   destination is VABB, from distance and ground speed; distance and bearing -> computed;
//   flight phase -> derived from altitude and climb rate (and labelled so).
// ISSUE CLEARANCE records a typed instruction through POST /api/clearances, the same door the
// speech chain uses: it reshapes this aircraft's predicted paths and is audited. Nothing is
// transmitted. Sequencing and holding have no backend and were removed rather than faked.

const ACTIONS = [
  { key: "CLIMB", unit: "ft", placeholder: "e.g. 37000" },
  { key: "DESCEND", unit: "ft", placeholder: "e.g. 13000" },
  { key: "TURN", unit: "° heading", placeholder: "e.g. 270" },
  { key: "SPEED", unit: "kt", placeholder: "e.g. 250" },
];

export default function FlightDetailDrawer({ flight, onClose, theme = "light" }) {
  const palette = theme === "light" ? statusColorsLight : statusColors;
  const accentColor = (flight && palette[flight.status]) || "var(--amber)";
  const [formOpen, setFormOpen] = useState(false);
  const [action, setAction] = useState("DESCEND");
  const [value, setValue] = useState("");
  const [result, setResult] = useState(null);

  const submit = async () => {
    if (!flight || !value) return;
    try {
      const r = await submitClearance({ callsign: flight.callsign, action, value: Number(value) });
      setResult({ ok: true, text: r.applied ? `Applied: ${r.effect}` : `Recorded, not applied: ${(r.problems || []).join("; ")}` });
      logAudit("flights:drawer", "Typed clearance submitted", { callsign: flight.callsign, action, value });
    } catch (error) {
      setResult({ ok: false, text: error.message });
    }
  };

  const vs = Math.round(Number(flight?.verticalRateFpm) || 0);
  const fields = flight ? [
    ["ROUTE", flight.route ?? "not found", flight.routeSource ?? "adsbdb has no route for this callsign"],
    ["ALT", flight.altitude, "Reported altitude"],
    ["SPEED", flight.speed, "Ground speed"],
    ["V/S", `${vs > 0 ? "+" : ""}${vs} fpm`, "Reported vertical rate"],
    ["HDG", `${Math.round(flight.heading)}°`, "Track over ground"],
    ["ACFT", flight.aircraft ? `${flight.aircraft}${flight.registration ? ` · ${flight.registration}` : ""}` : "unknown",
      flight.aircraftDescription ? `${flight.aircraftDescription} (${flight.aircraftSource})` : "Not in the adsb.lol data"],
    ["FROM VABB", flight.distanceToVabbNm != null ? `${flight.distanceToVabbNm} NM · ${flight.bearingFromVabbDeg}°` : "—", "Distance and bearing from Mumbai"],
    ["ETA VABB", flight.eta ?? "—", flight.eta ? "Estimate: distance ÷ ground speed, for flights whose looked-up destination is VABB" : "Only shown for flights bound for VABB"],
    ["SQUAWK", flight.squawk ?? "not received", flight.squawk ? "Transponder code (adsb.lol)" : "OpenSky does not carry it; adsb.lol supplies it in live mode"],
  ] : [];

  return (
    <AnimatePresence>
      {flight && (
        <>
          <motion.div key="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
                      className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.35)" }}
                      onClick={() => { logAudit("flights:drawer", "Drawer backdrop dismissed", { callsign: flight.callsign }); setFormOpen(false); setResult(null); onClose(); }} />
          <motion.div key="drawer" initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
                      transition={{ type: "spring", damping: 30, stiffness: 320 }}
                      className="fixed bottom-0 left-0 right-0 z-50"
                      style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", background: "var(--bg-panel-alt)", borderTop: `3px solid ${accentColor}`, boxShadow: "0 -8px 40px rgba(0,0,0,0.25)" }}>
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: "1px solid var(--border-default)" }}>
              <div className="flex items-center gap-4 min-w-0">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded text-xl"
                     style={{ background: "var(--bg-base)", color: accentColor, border: `1px solid ${accentColor}40` }}>
                  {statusIcons[flight.status] || "✈"}
                </div>
                <div className="flex items-center gap-3 min-w-0">
                  <span className="font-display text-[26px] tracking-wider leading-none" style={{ color: accentColor }}>{flight.callsign}</span>
                  <span className="font-display text-[10px] tracking-widest px-2 py-0.5 rounded-sm border shrink-0"
                        style={{ borderColor: accentColor, color: accentColor, background: `${accentColor}14` }}
                        title="Flight phase derived from altitude and climb rate; no flight plan is available">
                    {flight.status} · DERIVED
                  </span>
                  <span className="font-display text-[11px] hidden sm:inline" style={{ color: "var(--text-muted)" }}>
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

            <div className="px-5 py-4 overflow-x-auto">
              <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(9, minmax(92px, 1fr))" }}>
                {fields.map(([label, val, source]) => (
                  <div key={label} className="flex flex-col gap-1 rounded px-3 py-2.5" title={source}
                       style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", minWidth: 0 }}>
                    <span className="font-display text-[9px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span className="font-display text-[15px] leading-tight" style={{ color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
              <button type="button" onClick={() => { setFormOpen((o) => !o); setResult(null); }}
                      className="font-display text-[11px] tracking-widest px-5 py-2.5 transition-all active:scale-95 hover:brightness-110"
                      style={{ border: "1.5px solid var(--amber)", color: "var(--amber)", background: "rgba(245,166,35,0.06)" }}>
                ISSUE CLEARANCE
              </button>
              {formOpen && (
                <>
                  <select value={action} onChange={(e) => setAction(e.target.value)} className="font-display text-[11px] px-2 py-2"
                          style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}>
                    {ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.key}</option>)}
                  </select>
                  <input type="number" value={value} onChange={(e) => setValue(e.target.value)}
                         placeholder={ACTIONS.find((a) => a.key === action)?.placeholder}
                         className="font-display text-[11px] px-2 py-2 w-[120px]"
                         style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }} />
                  <span className="font-body text-[10px]" style={{ color: "var(--text-muted)" }}>{ACTIONS.find((a) => a.key === action)?.unit}</span>
                  <button type="button" onClick={submit} disabled={!value}
                          className="font-display text-[11px] tracking-widest px-4 py-2 disabled:opacity-40"
                          style={{ background: "var(--amber)", color: "#0a0b0e" }}>
                    RECORD
                  </button>
                  <span className="font-body text-[10px]" style={{ color: "var(--text-muted)" }}>
                    Recorded and used to reshape this aircraft's predicted paths. Nothing is transmitted.
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
