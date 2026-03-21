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

function FlightDetailDrawer({ flight, onClose }) {
  if (!flight) return null;
  const fields = [
    ["Altitude", flight.altitude], ["Speed", flight.speed],
    ["Heading", `${flight.heading}°`], ["Aircraft", flight.aircraft],
    ["ETA", flight.eta], ["Squawk", flight.squawk],
    ["Fuel", flight.fuel], ["Waypoint", flight.waypoint],
  ];

  return (
    <motion.div
      initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
      transition={{ type: "spring", damping: 25 }}
      className="absolute bottom-0 left-0 right-0 z-20 p-4"
      style={{ background: 'var(--bg-raised)', borderTop: '2px solid var(--amber)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="font-display text-[14px]" style={{ color: statusColors[flight.status] || 'var(--amber)' }}>{flight.callsign}</span>
          <span className="font-body text-[11px] ml-2" style={{ color: 'var(--text-muted)' }}>{flight.route}</span>
        </div>
        <button onClick={onClose}><X className="w-4 h-4" style={{ color: 'var(--text-muted)' }} /></button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {fields.map(([label, val]) => (
          <div key={label}>
            <p className="font-body text-[8px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>{label}</p>
            <p className="font-display text-[11px]" style={{ color: 'var(--text-primary)' }}>{val}</p>
          </div>
        ))}
      </div>
      <div className="flex gap-2 mt-3">
        {[{ label: "ISSUE CLEARANCE", color: "var(--amber)" }, { label: "ADD TO SEQUENCE", color: "var(--teal)" }, { label: "ASSIGN HOLDING", color: "var(--yellow)" }].map((a) => (
          <button key={a.label} className="flex-1 py-1.5 font-display text-[8px] tracking-wider" style={{ border: `1px solid ${a.color}`, color: a.color, background: 'transparent' }}>
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
      <div className="panel-header flex items-center justify-between">
        <h3 className="font-display text-[11px] tracking-wider" style={{ color: 'var(--amber)' }}>
          ✈ ACTIVE FLIGHTS <span className="ml-2 px-1.5 py-0.5 text-[9px]" style={{ background: 'var(--amber-glow)', border: '1px solid var(--amber)', color: 'var(--amber)' }}>{filtered.length}</span>
        </h3>
        <button onClick={() => setShowWeather(!showWeather)} className="font-display text-[9px]" style={{ color: showWeather ? 'var(--teal)' : 'var(--text-muted)' }}>
          <Cloud className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border-default)' }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => onTabChange(t)}
            className="flex-1 py-2 font-display text-[9px] tracking-wider transition-colors"
            style={{
              color: activeTab === t ? 'var(--amber)' : 'var(--text-muted)',
              borderBottom: activeTab === t ? '2px solid var(--amber)' : '2px solid transparent',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Weather collapsible */}
      <AnimatePresence>
        {showWeather && (
          <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden" style={{ background: 'var(--bg-panel-alt)', borderBottom: '1px solid var(--border-default)' }}>
            <div className="p-3 font-display text-[9px] space-y-1" style={{ color: 'var(--text-secondary)' }}>
              <p style={{ color: 'var(--teal)' }}>METAR: {weather.metar}</p>
              <p>{weather.atis} | W: {weather.wind} | VIS: {weather.visibility} | QNH: {weather.qnh}</p>
              <p>{weather.activeRwys}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Flight list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((flight) => {
          const color = statusColors[flight.status] || "#8a7d65";
          const icon = statusIcons[flight.status] || "→";
          const isSelected = selectedFlight === flight.callsign;
          const isConflict = flight.status === "CONFLICT";
          const isHolding = flight.status === "HOLDING";

          return (
            <button
              key={flight.callsign}
              onClick={() => onSelectFlight(isSelected ? null : flight.callsign)}
              className="w-full text-left grid grid-cols-[auto_1fr_auto] items-start gap-2 p-3 transition-all"
              style={{
                borderBottom: '1px solid var(--border-default)',
                borderLeft: isSelected ? '3px solid var(--amber)' : isConflict ? '3px solid var(--red)' : isHolding ? '3px solid var(--yellow)' : '3px solid transparent',
                background: isSelected ? 'rgba(245,166,35,0.06)' : isConflict ? 'rgba(255,45,45,0.04)' : isHolding ? 'rgba(255,221,0,0.03)' : 'transparent',
              }}
            >
              {/* Icon */}
              <div className="w-8 h-8 flex items-center justify-center font-display text-[14px] shrink-0" style={{ border: '1px solid var(--border-default)', background: `${color}10`, color }}>
                {icon}
              </div>
              {/* Center */}
              <div className="min-w-0">
                <p className="font-display text-[13px] font-bold" style={{ color }}>{flight.callsign}</p>
                <p className="font-body text-[11px]" style={{ color: 'var(--text-muted)' }}>{flight.route}</p>
                <div className="flex gap-3 mt-1">
                  {[flight.altitude, flight.speed, flight.eta, flight.aircraft].map((v, i) => (
                    <span key={i} className="font-body text-[10px]" style={{ color: 'var(--text-secondary)' }}>{v}</span>
                  ))}
                </div>
              </div>
              {/* Badge */}
              <span className="status-badge shrink-0" style={{
                borderColor: color, color, background: `${color}18`,
                ...(isConflict ? { animation: 'blink 1s infinite' } : {}),
              }}>
                {flight.status}
              </span>
            </button>
          );
        })}
      </div>

      {/* Flight Detail Drawer */}
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
