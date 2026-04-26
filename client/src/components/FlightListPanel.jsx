import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { statusColors, statusColorsLight, statusIcons, weather, sortByUrgency, getAltBandCounts } from "@/data/mockData";
import { X, Cloud } from "lucide-react";

// Full-width Detail Drawer that sits at the bottom of the viewport
export function FlightDetailDrawer({ flight, onClose, palette = statusColors }) {
  if (!flight) return null;
  const fields = [
    ["Route", flight.route], ["Altitude", flight.altitude], ["Speed", flight.speed],
    ["Heading", `${flight.heading}°`], ["Aircraft", flight.aircraft],
    ["ETA", flight.eta], ["Squawk", flight.squawk], ["Fuel", flight.fuel],
  ];

  return (
    <motion.div
      initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
      transition={{ type: "spring", damping: 25 }}
      className="fixed bottom-0 left-0 right-0 z-50 p-6 shadow-2xl"
      style={{ background: 'var(--bg-panel-alt)', borderTop: `2px solid ${palette[flight.status] || 'var(--amber)'}` }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 flex items-center justify-center font-display text-[24px]" style={{ background: 'var(--bg-base)', color: palette[flight.status] || 'var(--text-primary)', border: '1px solid var(--border-default)' }}>
            {statusIcons[flight.status] || "✈"}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <span className="font-display text-[24px] tracking-wider" style={{ color: palette[flight.status] || 'var(--amber)' }}>{flight.callsign}</span>
              <span className="status-badge" style={{ borderColor: palette[flight.status], color: palette[flight.status], background: 'transparent' }}>{flight.status}</span>
            </div>
            <span className="font-display text-[14px]" style={{ color: 'var(--text-muted)' }}>Waypoint: {flight.waypoint}</span>
          </div>
        </div>
        <button onClick={onClose} className="p-2 transition-colors hover:bg-white/5 rounded"><X className="w-6 h-6" style={{ color: 'var(--text-muted)' }} /></button>
      </div>

      <div className="grid grid-cols-4 md:grid-cols-8 gap-4 mb-6">
        {fields.map(([label, val]) => (
          <div key={label} className="p-3" style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)' }}>
            <p className="font-body text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
            <p className="font-display text-[16px]" style={{ color: 'var(--text-primary)' }}>{val}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-4">
        {[{ label: "ISSUE CLEARANCE", color: "var(--amber)" }, { label: "ADD TO SEQUENCE", color: "var(--teal)" }, { label: "ASSIGN HOLDING", color: "var(--yellow)" }].map((a) => (
          <button 
            key={a.label} 
            onClick={() => {
              const ce = new CustomEvent("show-toast", { detail: `${a.label} action logged for ${flight.callsign}` });
              window.dispatchEvent(ce);
            }}
            className="px-8 py-3 font-display text-[12px] tracking-widest transition-colors hover:bg-white/5 active:scale-95" 
            style={{ border: `1px solid ${a.color}`, color: a.color, background: 'transparent' }}
          >
            {a.label}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

// ── CPA Badge ──────────────────────────────────────────────────────────────
function CpaBadge({ cpaSeconds }) {
  if (!cpaSeconds) return null;
  const min = Math.floor(cpaSeconds / 60);
  const sec = cpaSeconds % 60;
  const label = `CPA ${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  const color = cpaSeconds < 300 ? "var(--red)" : cpaSeconds < 600 ? "var(--amber)" : "var(--teal)";
  return (
    <span
      className="font-display text-[9px] tracking-wide px-1.5 py-0.5 rounded-sm"
      style={{ border: `1px solid ${color}`, color, background: `${color}15` }}
    >
      {label}
    </span>
  );
}

export default function FlightListPanel({ flightsData, selectedFlight, onSelectFlight, activeTab, onTabChange, theme = "dark" }) {
  const [showWeather, setShowWeather] = useState(false);
  const bands = getAltBandCounts(flightsData);
  const palette = theme === "light" ? statusColorsLight : statusColors;

  // Tabs: ALL, <FL100, FL100-250, >FL250, ALERTS
  const TABS = [
    { key: "ALL",      label: "ALL",        count: flightsData.length },
    { key: "LOW",      label: "<FL100",     count: bands.under100 },
    { key: "MID",      label: "FL100-250",  count: bands.band100250 },
    { key: "HIGH",     label: ">FL250",     count: bands.over250 },
    { key: "ALERTS",   label: "ALERTS",     count: flightsData.filter(f => f.status === "CONFLICT" || f.status === "HOLDING").length },
  ];

  function parseFL(alt) {
    if (!alt || alt === "GND") return 0;
    if (alt.startsWith("FL")) return parseInt(alt.slice(2), 10);
    const ft = parseInt(alt.replace(/[^0-9]/g, ""), 10);
    return Math.round(ft / 100);
  }

  const filterMap = {
    ALL:    () => true,
    LOW:    (f) => parseFL(f.altitude) < 100,
    MID:    (f) => { const fl = parseFL(f.altitude); return fl >= 100 && fl <= 250; },
    HIGH:   (f) => parseFL(f.altitude) > 250,
    ALERTS: (f) => f.status === "CONFLICT" || f.status === "HOLDING",
  };

  const filtered = sortByUrgency(flightsData.filter(filterMap[activeTab] || filterMap.ALL));

  return (
    <div className="panel flex flex-col h-full relative overflow-hidden">
      {/* Header */}
      <div className="panel-header flex items-center justify-between py-3 px-4">
        <h3 className="font-display text-[14px] tracking-widest" style={{ color: 'var(--text-primary)' }}>
          FLIGHTS
        </h3>
        <span className="px-2 py-0.5 font-display text-[11px]" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
          {filtered.length}/{flightsData.length}
        </span>
      </div>

      {/* Weather Header (Collapsible) */}
      <div
        className="px-4 py-2 flex items-center justify-between cursor-pointer transition-colors hover:bg-white/5"
        style={{ borderBottom: '1px solid var(--border-default)' }}
        onClick={() => setShowWeather(!showWeather)}
      >
        <span className="font-display text-[11px] uppercase" style={{ color: 'var(--text-muted)' }}>Weather & ATIS</span>
        <Cloud className="w-4 h-4" style={{ color: showWeather ? 'var(--teal)' : 'var(--text-muted)' }} />
      </div>
      <AnimatePresence>
        {showWeather && (
          <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden" style={{ background: 'var(--bg-panel-alt)', borderBottom: '1px solid var(--border-default)' }}>
            <div className="p-4 font-display text-[11px] space-y-1.5" style={{ color: 'var(--text-secondary)' }}>
              <p style={{ color: 'var(--teal)' }}>METAR: {weather.metar}</p>
              <p>{weather.atis} | W: {weather.wind} | VIS: {weather.visibility} | QNH: {weather.qnh}</p>
              <p>{weather.activeRwys}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tabs — with live counts */}
      <div className="flex overflow-x-auto no-scrollbar" style={{ borderBottom: '1px solid var(--border-default)' }}>
        {TABS.map(({ key, label, count }) => (
          <button
            key={key}
            onClick={() => onTabChange(key)}
            className="flex-shrink-0 px-2 py-2.5 font-display text-[10px] tracking-wide transition-colors flex flex-col items-center gap-0.5"
            style={{
              color: activeTab === key ? 'var(--amber)' : 'var(--text-secondary)',
              borderBottom: activeTab === key ? '2px solid var(--amber)' : '2px solid transparent',
              minWidth: 56,
            }}
          >
            <span>{label}</span>
            <span style={{ fontSize: 11, color: activeTab === key ? 'var(--amber)' : 'var(--text-muted)', fontWeight: 600 }}>
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* Flight list - Slim Strip, sorted by urgency */}
      <div className="flex-1 overflow-y-auto w-full no-scrollbar pb-10">
        {filtered.map((flight) => {
          const color = palette[flight.status] || "var(--text-muted)";
          const isSelected = selectedFlight === flight.callsign;
          const isConflict = flight.status === "CONFLICT";
          const isHolding = flight.status === "HOLDING";

          return (
            <button
              key={flight.callsign}
              onClick={() => onSelectFlight(isSelected ? null : flight.callsign)}
              className="w-full flex items-center justify-between px-4 py-2.5 transition-colors group"
              style={{
                borderBottom: '1px solid var(--border-default)',
                borderLeft: isConflict ? `3px solid var(--red)` : isHolding ? `3px solid var(--yellow)` : isSelected ? `3px solid ${color}` : '3px solid transparent',
                background: isSelected ? 'var(--bg-raised)' : isConflict ? 'rgba(255,45,45,0.08)' : 'transparent',
                boxShadow: isConflict ? 'inset 0 0 12px rgba(255,45,45,0.1)' : 'none',
              }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${isConflict ? 'animate-blink' : ''}`}
                  style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                />
                <div className="flex flex-col items-start min-w-0">
                  <span className="font-display text-[13px] tracking-wider truncate" style={{ color: isSelected || isConflict ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {flight.callsign}
                  </span>
                  {(isConflict || isHolding) && flight.cpaPair && (
                    <span className="font-display text-[9px]" style={{ color: 'var(--text-muted)' }}>
                      vs {flight.cpaPair}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-0.5 shrink-0 ml-2">
                <span className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {flight.altitude}
                </span>
                {flight.cpaSeconds && <CpaBadge cpaSeconds={flight.cpaSeconds} />}
              </div>
            </button>
          );
        })}
      </div>

      {/* Detail Drawer (Fixed at bottom) */}
      <AnimatePresence>
        {selectedFlight && (
          <FlightDetailDrawer
            flight={flightsData.find((f) => f.callsign === selectedFlight)}
            onClose={() => onSelectFlight(null)}
            palette={palette}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
