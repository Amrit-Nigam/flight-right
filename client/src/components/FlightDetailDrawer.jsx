import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { statusColors, statusColorsLight, statusIcons } from "@/data/mockData";
import { logActivity, logAudit } from "@/lib/siteLogger";

const ACTIONS = [
  { label: "ISSUE CLEARANCE", key: "clr", color: "var(--amber)" },
  { label: "ADD TO SEQUENCE", key: "seq", color: "var(--teal)" },
  { label: "ASSIGN HOLDING",  key: "hld", color: "var(--yellow)" },
];

export default function FlightDetailDrawer({ flight, onClose, theme = "light" }) {
  const palette = theme === "light" ? statusColorsLight : statusColors;
  const accentColor = (flight && palette[flight.status]) || "var(--amber)";

  function fireAction(label) {
    if (!flight) return;
    logAudit("flights:drawer", "Flight detail quick-action button pressed", { callsign: flight.callsign, action: label });
    logActivity("flights:drawer-action", `Mock quick action: ${label}`, { callsign: flight.callsign, action: label });
    window.dispatchEvent(new CustomEvent("show-toast", { detail: `${label} — ${flight.callsign}` }));
  }

  return (
    <AnimatePresence>
      {flight && (
        <>
          {/* Dim overlay */}
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.35)" }}
            onClick={() => {
              logAudit("flights:drawer", "Drawer backdrop dismissed", { callsign: flight.callsign });
              onClose();
            }}
          />

          {/* Panel */}
          <motion.div
            key="drawer"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 320 }}
            className="fixed bottom-0 left-0 right-0 z-50"
            style={{
              fontFamily: "'Geist Variable', system-ui, sans-serif",
              background: "var(--bg-panel-alt)",
              borderTop: `3px solid ${accentColor}`,
              boxShadow: "0 -8px 40px rgba(0,0,0,0.25)",
            }}
          >
            {/* ── IDENTITY BAR ─────────────────────────── */}
            <div
              className="flex items-center justify-between px-5 py-3"
              style={{ borderBottom: "1px solid var(--border-default)" }}
            >
              <div className="flex items-center gap-4 min-w-0">
                {/* Icon */}
                <div
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded text-xl"
                  style={{ background: "var(--bg-base)", color: accentColor, border: `1px solid ${accentColor}40` }}
                >
                  {statusIcons[flight.status] || "✈"}
                </div>

                {/* Callsign + status badge */}
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className="font-display text-[26px] tracking-wider leading-none"
                    style={{ color: accentColor }}
                  >
                    {flight.callsign}
                  </span>
                  <span
                    className="font-display text-[10px] tracking-widest px-2 py-0.5 rounded-sm border shrink-0"
                    style={{ borderColor: accentColor, color: accentColor, background: `${accentColor}14` }}
                  >
                    {flight.status}
                  </span>
                  <span className="font-display text-[12px] hidden sm:inline" style={{ color: "var(--text-muted)" }}>
                    WPT:&nbsp;
                    <span style={{ color: "var(--text-secondary)" }}>{flight.waypoint}</span>
                  </span>
                </div>
              </div>

              {/* Close */}
              <button
                type="button"
                aria-label="Close"
                onClick={() => {
                  logAudit("flights:drawer", "Flight detail drawer close control", { callsign: flight.callsign });
                  logActivity("flights:drawer", "Closed flight detail drawer", { callsign: flight.callsign });
                  onClose();
                }}
                className="shrink-0 ml-4 p-1.5 rounded hover:bg-[var(--bg-raised)] transition-colors"
              >
                <X className="w-5 h-5" style={{ color: "var(--text-muted)" }} />
              </button>
            </div>

            {/* ── DATA GRID ────────────────────────────── */}
            <div className="px-5 py-4 overflow-x-auto">
              <div
                className="grid gap-3"
                style={{ gridTemplateColumns: "repeat(8, minmax(88px, 1fr))" }}
              >
                {[
                  ["ROUTE",    flight.route],
                  ["ALT",      flight.altitude],
                  ["SPEED",    flight.speed],
                  ["HDG",      `${flight.heading}°`],
                  ["ACFT",     flight.aircraft],
                  ["ETA",      flight.eta],
                  ["SQUAWK",   flight.squawk],
                  ["FUEL",     flight.fuel],
                ].map(([label, val]) => (
                  <div
                    key={label}
                    className="flex flex-col gap-1 rounded px-3 py-2.5"
                    style={{
                      background: "var(--bg-base)",
                      border: "1px solid var(--border-default)",
                      minWidth: 0,
                    }}
                  >
                    <span
                      className="font-display text-[9px] uppercase tracking-widest"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {label}
                    </span>
                    <span
                      className="font-display text-[16px] leading-tight"
                      style={{
                        color: "var(--text-primary)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={String(val)}
                    >
                      {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* ── ACTION FOOTER ────────────────────────── */}
            <div
              className="flex flex-wrap gap-2 px-5 pb-4"
            >
              {ACTIONS.map((a) => (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => fireAction(a.label)}
                  className="font-display text-[11px] tracking-widest px-5 py-2.5 transition-all active:scale-95 hover:brightness-110"
                  style={{
                    border: `1.5px solid ${a.color}`,
                    color: a.color,
                    background: `${a.color}10`,
                  }}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
