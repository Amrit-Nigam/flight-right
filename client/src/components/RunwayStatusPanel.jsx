import { useState } from "react";
import { runways } from "@/data/mockData";
import { Sparkles } from "lucide-react";

export default function RunwayStatusPanel() {
  const [isBalanced, setIsBalanced] = useState(false);
  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-6">
        <h3 className="font-display text-[13px] tracking-widest text-[var(--text-primary)]">
          RUNWAY UTILIZATION
        </h3>
        <div className="flex items-center gap-3">
          {!isBalanced && (
            <button 
              onClick={() => {
                setIsBalanced(true);
                window.dispatchEvent(new CustomEvent("show-toast", { detail: "Runway loads auto-balanced. Saved 14 minutes total delay." }));
              }}
              className="group flex items-center gap-1.5 px-3 py-1 bg-[rgba(0,229,204,0.05)] text-[var(--teal)] font-display text-[10px] tracking-widest border border-[var(--teal)] transition-all hover:bg-[var(--teal)] hover:text-[#050508]"
            >
              <Sparkles className="w-3 h-3 group-hover:animate-pulse" />
              AI AUTO-BALANCE
            </button>
          )}
          {isBalanced && (
            <span className="font-display text-[10px] text-[var(--green)] border border-[var(--green)] px-2 py-0.5">OPTIMIZED</span>
          )}
        </div>
      </div>

      <div className="relative pt-4 pb-2">
        {/* Red NOW line cutting through all runways */}
        <div className="absolute top-0 bottom-0 z-10 w-[1px] bg-[var(--red)] opacity-80" style={{ left: '25%' }} />
        <div className="absolute -top-1.5 z-10 font-display text-[9px] px-1 bg-[var(--red)] text-white" style={{ left: '25%', transform: 'translateX(-50%)' }}>
          NOW
        </div>

        <div className="space-y-6">
          {runways.map((rwy) => (
            <div key={rwy.id} className="relative">
              {/* Runway marking label */}
              <div className="absolute -left-2 -translate-x-full top-1/2 -translate-y-1/2">
                <span className="font-display text-[13px] font-bold text-[var(--text-secondary)]">{rwy.id}</span>
              </div>

              {/* The "Runway" Base */}
              <div className="h-10 relative overflow-hidden rounded-sm" style={{ background: 'var(--bg-base)', border: '2px solid var(--border-default)' }}>
                {/* Centerline dashes */}
                <div className="absolute top-1/2 w-full h-[1px] -translate-y-1/2" style={{ background: 'repeating-linear-gradient(90deg, transparent, transparent 10px, var(--border-bright) 10px, var(--border-bright) 24px)' }} />
                
                {/* Slots */}
                {(isBalanced ? (rwy.balancedSlots || rwy.slots) : rwy.slots).map((slot, i) => {
                  if (slot.type === "clear") return null;

                  let bgColor, color, borderColor;
                  if (slot.type === "land") {
                    bgColor = "rgba(0,229,204,0.15)"; color = "var(--teal)"; borderColor = "var(--teal)";
                  } else if (slot.type === "take") {
                    bgColor = "rgba(245,166,35,0.15)"; color = "var(--amber)"; borderColor = "var(--amber)";
                  } else if (slot.type === "hold") {
                    bgColor = "rgba(255,221,0,0.1)"; color = "var(--yellow)"; borderColor = "var(--yellow)";
                  } else if (slot.type === "maint") {
                    bgColor = "repeating-linear-gradient(45deg, rgba(255,45,45,0.2) 0px, rgba(255,45,45,0.2) 4px, transparent 4px, transparent 8px)";
                    color = "var(--red)"; borderColor = "var(--red)";
                  }

                  return (
                    <div
                      key={i}
                      className="absolute top-0 h-full flex items-center justify-center group transition-colors hover:bg-white/10 shadow-sm"
                      style={{
                        left: `${slot.pctStart}%`,
                        width: `${slot.pctW}%`,
                        background: bgColor,
                        borderLeft: `2px solid ${borderColor}`,
                        borderRight: `2px solid ${borderColor}`
                      }}
                      title={slot.flight || slot.label || ""}
                    >
                      <span className="font-display text-[10px] font-bold tracking-wider px-1 truncate" style={{ color, textShadow: `0 0 10px ${color}` }}>
                        {slot.flight || slot.label || ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-6 mt-8 pt-4" style={{ borderTop: '1px solid var(--border-default)' }}>
          {[
            { l: "Landing", c: "var(--teal)" },
            { l: "Takeoff", c: "var(--amber)" },
            { l: "Maintenance", c: "var(--red)" }
          ].map((x) => (
            <div key={x.l} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-sm" style={{ background: x.c }} />
              <span className="font-display text-[10px] uppercase tracking-widest text-[var(--text-muted)]">{x.l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
