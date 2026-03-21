import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { statusColors, statusIcons, weather } from "@/data/mockData";
import { X, Cloud } from "lucide-react";

const TABS = ["ALL", "LANDING", "TAKEOFF", "ALERTS"];

const filterMap = {
  ALL: () => true,
  LANDING: (f) => f.status === "LANDING" || f.status === "APPROACH",
  TAKEOFF: (f) => f.status === "TAKEOFF" || f.status === "DEPARTING",
  ALERTS: (f) => f.status === "CONFLICT" || f.status === "HOLDING",
};

// Full-width Detail Drawer that sits at the bottom of the viewport
export function FlightDetailDrawer({ flight, onClose }) {
  if (!flight) return null;
  const fields = [
    ["Route", flight.route], ["Altitude", flight.altitude], ["Speed", flight.speed],
    ["Heading", `${flight.heading}°`], ["Aircraft", flight.aircraft],
    ["ETA", flight.eta], ["Squawk", flight.squawk],
    ["Fuel", flight.fuel]
  ];

  return (
    <motion.div
      initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
      transition={{ type: "spring", damping: 25 }}
      className="fixed bottom-0 left-0 right-0 z-50 p-6 shadow-2xl"
      style={{ background: 'var(--bg-panel-alt)', borderTop: `2px solid ${statusColors[flight.status] || 'var(--amber)'}` }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 flex items-center justify-center font-display text-[24px]" style={{ background: 'var(--bg-base)', color: statusColors[flight.status] || 'var(--text-primary)', border: '1px solid var(--border-default)' }}>
            {statusIcons[flight.status] || "✈"}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <span className="font-display text-[24px] tracking-wider" style={{ color: statusColors[flight.status] || 'var(--amber)' }}>{flight.callsign}</span>
              <span className="status-badge" style={{ borderColor: statusColors[flight.status], color: statusColors[flight.status], background: 'transparent' }}>{flight.status}</span>
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
          <button key={a.label} className="px-8 py-3 font-display text-[12px] tracking-widest transition-colors hover:bg-white/5" style={{ border: `1px solid ${a.color}`, color: a.color, background: 'transparent' }}>
            {a.label}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

export default function FlightListPanel({ flightsData, selectedFlight, onSelectFlight, activeTab, onTabChange }) {
  const [showWeather, setShowWeather] = useState(false);
  const filtered = flightsData.filter(filterMap[activeTab] || filterMap.ALL);

  return (
    <div className="panel flex flex-col h-full relative overflow-hidden">
      {/* Header */}
      <div className="panel-header flex items-center justify-between py-3 px-4">
        <h3 className="font-display text-[14px] tracking-widest" style={{ color: 'var(--text-primary)' }}>
          FLIGHTS
        </h3>
        <span className="px-2 py-0.5 font-display text-[11px]" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
          {filtered.length} TOTAL
        </span>
      </div>

      {/* Weather Header (Collapsible) */}
      <div className="px-4 py-2 flex items-center justify-between cursor-pointer transition-colors hover:bg-white/5" style={{ borderBottom: '1px solid var(--border-default)' }} onClick={() => setShowWeather(!showWeather)}>
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

      {/* Tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border-default)' }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => onTabChange(t)}
            className="flex-1 py-2 font-display text-[10px] tracking-wider transition-colors"
            style={{
              color: activeTab === t ? 'var(--amber)' : 'var(--text-muted)',
              borderBottom: activeTab === t ? '2px solid var(--amber)' : '2px solid transparent',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Flight list - Slim Strip */}
      <div className="flex-1 overflow-y-auto w-full no-scrollbar pb-10">
        {filtered.map((flight) => {
          const color = statusColors[flight.status] || "var(--text-muted)";
          const isSelected = selectedFlight === flight.callsign;
          const isConflict = flight.status === "CONFLICT";

          return (
            <button
              key={flight.callsign}
              onClick={() => onSelectFlight(isSelected ? null : flight.callsign)}
              className="w-full flex items-center justify-between px-4 py-2.5 transition-colors group"
              style={{
                borderBottom: '1px solid var(--border-default)',
                borderLeft: isConflict ? `3px solid var(--red)` : isSelected ? `3px solid ${color}` : '3px solid transparent',
                background: isSelected ? 'var(--bg-raised)' : isConflict ? 'rgba(255,45,45,0.08)' : 'transparent',
                boxShadow: isConflict ? 'inset 0 0 12px rgba(255,45,45,0.1)' : 'none'
              }}
            >
              <div className="flex items-center gap-3">
                <span 
                  className={`w-2 h-2 rounded-full ${isConflict ? 'animate-blink' : ''}`} 
                  style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                />
                <span className="font-display text-[13px] tracking-wider" style={{ color: isSelected || isConflict ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                  {flight.callsign}
                </span>
              </div>
              <span className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {flight.altitude}
              </span>
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
          />
        )}
      </AnimatePresence>
    </div>
  );
}
