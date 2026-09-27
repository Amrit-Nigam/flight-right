import { logAudit } from "@/lib/siteLogger";

// Mumbai's real runways (OurAirports: 09/27 and 14/32) with movements DERIVED from the tracks:
// landings and departures actually seen, and arrivals still to come with an estimated time
// from distance and ground speed (server/app/services/airport_service.py).
//
// Until 27 Sep 2026 this panel showed invented slots on runways Mumbai does not have (27L/27R,
// 09L/09R, 32L/32R), a fake maintenance closure, and an "AI AUTO-BALANCE" button whose toast
// claimed "Saved 14 minutes total delay" from a model that was never built. All gone.

const PAST_MIN = 45;
const FUTURE_MIN = 30;
const pct = (minutes) => ((minutes + PAST_MIN) / (PAST_MIN + FUTURE_MIN)) * 100;

export default function RunwayStatusPanel({ airport = null }) {
  if (!airport) {
    return (
      <div className="panel p-5 shrink-0">
        <h3 className="font-display text-[13px] tracking-widest text-[var(--text-primary)]">RUNWAYS · VABB</h3>
        <p className="font-body text-[11px] mt-3" style={{ color: "var(--text-muted)" }}>Waiting for the airport feed…</p>
      </div>
    );
  }
  const now = Date.parse(airport.dataTimeUtc);
  const pairs = [...new Set((airport.runways || []).map((r) => r.runway))];
  const inUse = airport.inUse;
  const marks = [
    ...(airport.recentMovements || []).map((m) => ({
      runway: m.runway, end: m.end, callsign: m.callsign, kind: m.kind,
      minutes: (m.time * 1000 - now) / 60000,
    })),
    ...(airport.upcomingArrivals || []).map((u) => ({
      runway: (airport.runways || []).find((r) => r.end === u.end)?.runway, end: u.end,
      callsign: u.callsign, kind: "arrival", minutes: u.etaMinutes, detail: `${u.distanceNm} NM · ${u.basis}`,
    })),
  ].filter((m) => m.runway && m.minutes >= -PAST_MIN && m.minutes <= FUTURE_MIN);

  const style = {
    landing: { bg: "rgba(0,229,204,0.18)", c: "var(--teal)", label: "Landed (observed)" },
    departure: { bg: "rgba(245,166,35,0.18)", c: "var(--amber)", label: "Departed (observed)" },
    arrival: { bg: "transparent", c: "var(--teal)", label: "Arriving (estimated)", dashed: true },
  };

  return (
    <div className="panel p-5 shrink-0">
      <div className="flex items-start justify-between mb-4 gap-3">
        <div>
          <h3 className="font-display text-[12px] sm:text-[13px] tracking-widest text-[var(--text-primary)] whitespace-nowrap">
            RUNWAYS · VABB
          </h3>
          <p className="font-body text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
            {inUse ? `In use: ${inUse.end} — ${inUse.basis}` : "No movement observed and no wind report yet"}
          </p>
        </div>
        <span className="font-display text-[9px] px-1.5 py-0.5 shrink-0" style={{ border: "1px solid var(--border-default)", color: "var(--text-muted)" }}
              title={airport.notes}>
          DERIVED FROM TRACKS
        </span>
      </div>

      <div className="relative">
        <div className="absolute top-0 bottom-0 z-10 w-[1px] bg-[var(--red)] opacity-80" style={{ left: `calc(3.5rem + (100% - 3.5rem) * ${pct(0) / 100})` }} />
        <div className="space-y-4 pt-3">
          {pairs.map((pair) => {
            const active = inUse && pair.split("/").includes(inUse.end);
            // Stack marks into lanes so neighbouring movements stay readable.
            const MARK_W = 19;                                 // % of the track one 3.2rem label needs
            const lanes = [];
            const placed = marks.filter((m) => m.runway === pair).sort((a, b) => a.minutes - b.minutes).map((m) => {
              const x = pct(m.minutes);
              let lane = lanes.findIndex((end) => end <= x - MARK_W);
              if (lane === -1) { lane = lanes.length; lanes.push(x); } else lanes[lane] = x;
              return { ...m, x, lane };
            });
            const laneCount = Math.max(1, lanes.length);
            return (
              <div key={pair} className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-center gap-2">
                <span className="font-display text-[12px] font-bold text-right pr-1" style={{ color: active ? "var(--amber)" : "var(--text-secondary)" }}>
                  {pair}
                </span>
                <div className="relative overflow-hidden rounded-sm" style={{ height: 10 + laneCount * 20, background: "var(--bg-base)", border: `2px solid ${active ? "var(--amber)" : "var(--border-default)"}` }}>
                  <div className="absolute top-1/2 w-full h-[1px] -translate-y-1/2" style={{ background: "repeating-linear-gradient(90deg, transparent, transparent 10px, var(--border-bright) 10px, var(--border-bright) 24px)" }} />
                  {placed.map((m, i) => {
                    const s = style[m.kind];
                    return (
                      <button
                        type="button"
                        key={`${m.callsign}-${m.kind}-${i}`}
                        onClick={() => logAudit("runway:movement", "Runway movement inspected", { ...m })}
                        className="absolute flex items-center justify-center px-1"
                        style={{ left: `calc(${m.x}% - 1.6rem)`, width: "3.2rem", top: 4 + m.lane * 20, height: 17, background: s.bg,
                                 border: `1px ${s.dashed ? "dashed" : "solid"} ${s.c}` }}
                        title={`${m.callsign} · ${s.label} on ${m.end} · ${m.minutes >= 0 ? `in ~${Math.round(m.minutes)} min` : `${Math.round(-m.minutes)} min ago`}${m.detail ? ` · ${m.detail}` : ""}`}
                      >
                        <span className="font-display text-[9px] font-bold truncate" style={{ color: s.c }}>{m.callsign}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-2 mt-1">
          <span />
          <div className="flex justify-between font-display text-[9px]" style={{ color: "var(--text-muted)" }}>
            <span>−{PAST_MIN} min</span><span>NOW</span><span>+{FUTURE_MIN} min</span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 mt-4 pt-3" style={{ borderTop: "1px solid var(--border-default)" }}>
        {Object.values(style).map((x) => (
          <div key={x.label} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-sm" style={{ background: x.bg, border: `1px ${x.dashed ? "dashed" : "solid"} ${x.c}` }} />
            <span className="font-display text-[9px] uppercase tracking-widest text-[var(--text-muted)]">{x.label}</span>
          </div>
        ))}
      </div>
      <p className="font-body text-[9px] mt-2" style={{ color: "var(--text-muted)" }}>
        Runways: {airport.runwaySource}. Movements are classified from altitude, climb rate and alignment with a runway;
        arrival times are distance ÷ ground speed. No schedule or ATIS feed is used.
      </p>
    </div>
  );
}
