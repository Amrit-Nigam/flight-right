import { useRef, useEffect } from "react";

// A radar-scope view of the real traffic, centred on Mumbai (VABB), at true scale.
//
// Rewritten 27 Sep 2026. The previous version never placed aircraft at their real positions
// (its list started empty and was never seeded), animated invented motion, drew a fixed
// "SEVERE WX" cell and a diversion route for a callsign that never appears, labelled a
// made-up sector ("7B-ALPHA"), quoted "CPA 2.1 NM / minimum 3 NM" whatever the alarm said,
// and printed "28 TRACKS · 6 RWYS · 87% OPT" as fixed text. Now every mark is data:
//   - aircraft at their reported positions, with a 60-second straight-line velocity vector;
//   - Mumbai's runways from OurAirports (via /api/airport);
//   - for a confirmed alarm, each aircraft's straight-line position at the predicted time of
//     closest approach -- the prediction the alarm itself was computed from -- the numbers the
//     alarm reports, and 5 NM rings drawn to scale.
// The rotating sweep is only the scope's visual convention; it carries no data.

const BASE_RANGE_NM = 50;
// With an alarm on screen the range widens (in 50 NM steps) so both aircraft are on the scope:
// alarms are en-route and are often far from the airport.
function scopeRange(flights, conflict) {
  if (!conflict) return BASE_RANGE_NM;
  const far = [conflict.flight1, conflict.flight2]
    .map((cs) => flights.find((f) => f.callsign === cs))
    .filter((f) => f && f.lat != null)
    .map((f) => { const p = toNm(f.lat, f.lng); return Math.hypot(p.x, p.y); });
  return far.length ? Math.max(BASE_RANGE_NM, Math.ceil((Math.max(...far) + 25) / 50) * 50) : BASE_RANGE_NM;
}
const VABB = { lat: 19.0887, lng: 72.8679 };
const STATUS_COLORS_DARK = { conflict: "#ff2d2d", landing: "#00e5cc", takeoff: "#f5a623", cruise: "#8a7d65", approach: "#00e5cc", departing: "#f5a623" };
const STATUS_COLORS_LIGHT = { conflict: "#dc2626", landing: "#0d9488", takeoff: "#d97706", cruise: "#64748b", approach: "#0d9488", departing: "#d97706" };

function toNm(lat, lng) {
  return { x: (lng - VABB.lng) * 60 * Math.cos((VABB.lat * Math.PI) / 180), y: (lat - VABB.lat) * 60 };
}
function ahead(f, seconds) {
  // Straight-line position `seconds` from now: the constant-velocity prediction.
  const d = ((Number(f.speedKt) || 0) * seconds) / 3600;
  const h = ((Number(f.heading) || 0) * Math.PI) / 180;
  return { lat: f.lat + (d * Math.cos(h)) / 60, lng: f.lng + (d * Math.sin(h)) / (60 * Math.cos((f.lat * Math.PI) / 180)) };
}

export default function RadarCanvas({ flights = [], selectedFlight, theme, conflict = null, airport = null, feed = {} }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const angleRef = useRef(0);
  const dataRef = useRef({ flights, conflict, airport, feed, selectedFlight });
  dataRef.current = { flights, conflict, airport, feed, selectedFlight };

  const isLight = theme === "light";
  const range = scopeRange(flights, conflict);
  const inRange = flights.filter((f) => f.lat != null && Math.hypot(toNm(f.lat, f.lng).x, toNm(f.lat, f.lng).y) <= range).length;
  const runwayPairs = new Set((airport?.runways || []).map((r) => r.runway)).size;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const statusColors = isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS_DARK;
    const baseColor = isLight ? "#0f172a" : "#f5a623";
    const bgSolid = isLight ? "#eceae6" : "#060608";
    const ringRGB = isLight ? "148,163,184" : "245,166,35";
    const textPrimary = isLight ? "#0f172a" : "#f5a623";
    const textMuted = isLight ? "#64748b" : "rgba(138,125,101,0.8)";
    const sweepRGB = isLight ? "217,119,6" : "245,166,35";
    let w = 0, h = 0;

    const updateSize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = w * dpr; canvas.height = h * dpr;
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    updateSize();
    const ro = new ResizeObserver(updateSize);
    ro.observe(canvas.parentElement);

    const labelBox = (x, y, lines, accent, width) => {
      const lh = 15, height = 16 + lines.length * lh;
      ctx.save();
      ctx.fillStyle = isLight ? "rgba(255,255,255,0.94)" : "rgba(6,6,8,0.88)";
      ctx.strokeStyle = accent; ctx.lineWidth = 1;
      ctx.fillRect(x, y, width, height); ctx.strokeRect(x, y, width, height);
      lines.forEach((line, i) => {
        ctx.fillStyle = i === 0 ? accent : textPrimary;
        ctx.font = `${i === 0 ? "bold 11" : "10"}px 'Geist Variable', system-ui, sans-serif`;
        ctx.fillText(line, x + 10, y + 18 + i * lh, width - 20);
      });
      ctx.restore();
    };

    const draw = () => {
      const { flights: fl, conflict: c, airport: ap, feed: fd, selectedFlight: sel } = dataRef.current;
      const cx = w / 2, cy = h / 2;
      const radius = Math.max(0, Math.min(cx, cy) - 20);
      const RANGE_NM = scopeRange(fl, c);
      const px = (lat, lng) => { const p = toNm(lat, lng); return [cx + (p.x / RANGE_NM) * radius, cy - (p.y / RANGE_NM) * radius]; };
      const nmPx = radius / RANGE_NM;

      ctx.fillStyle = bgSolid; ctx.fillRect(0, 0, w, h);

      for (let i = 1; i <= 5; i++) {
        const r = (radius / 5) * i;
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${ringRGB},${isLight ? "0.4" : "0.15"})`; ctx.lineWidth = 0.8; ctx.stroke();
        ctx.fillStyle = `rgba(${ringRGB},${isLight ? "1" : "0.5"})`;
        ctx.font = "11px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(`${(RANGE_NM / 5) * i}${i === 5 ? " NM" : ""}`, cx + r - 30, cy - 4);
      }
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy); ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = `rgba(${ringRGB},${isLight ? "0.3" : "0.1"})`; ctx.lineWidth = 0.5; ctx.stroke();

      // Sweep: the scope's visual convention only.
      const angle = angleRef.current;
      [0.3, 0.2, 0.15, 0.1, 0.08, 0.05].forEach((o, t) => {
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, angle - (t + 1) * 0.026, angle - t * 0.026, false); ctx.closePath();
        ctx.fillStyle = `rgba(${sweepRGB},${isLight ? o : o * 1.6})`; ctx.fill();
      });

      // Real runways (OurAirports), drawn to scale.
      for (const r of ap?.runways || []) {
        const [x1, y1] = px(r.threshold[0], r.threshold[1]); const [x2, y2] = px(r.far[0], r.far[1]);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
        ctx.strokeStyle = ap?.inUse && r.runway.split("/").includes(ap.inUse.end) ? "#f5a623" : textMuted;
        ctx.lineWidth = 3; ctx.stroke();
      }
      ctx.fillStyle = textPrimary; ctx.font = "bold 10px 'Geist Variable', system-ui, sans-serif";
      ctx.fillText("VABB", cx + 8, cy + 14);

      // Confirmed alarm: each aircraft's straight-line position at the predicted CPA time.
      const pair = c ? [c.flight1, c.flight2].map((cs) => fl.find((f) => f.callsign === cs)).filter((f) => f && f.lat != null) : [];
      if (c && pair.length === 2) {
        const t = Math.max(0, c.countdown || 0);
        const ends = pair.map((f) => ahead(f, t));
        pair.forEach((f, i) => {
          const [ax, ay] = px(f.lat, f.lng); const [bx, by] = px(ends[i].lat, ends[i].lng);
          ctx.beginPath(); ctx.setLineDash([8, 6]); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
          ctx.strokeStyle = i === 0 ? "#ff2d2d" : (isLight ? "#d97706" : "#ffdd00"); ctx.lineWidth = 2.5; ctx.stroke(); ctx.setLineDash([]);
          ctx.beginPath(); ctx.arc(bx, by, 3.5, 0, Math.PI * 2); ctx.fillStyle = ctx.strokeStyle; ctx.fill();
          ctx.beginPath(); ctx.arc(ax, ay, 5 * nmPx, 0, Math.PI * 2); ctx.setLineDash([6, 5]);
          ctx.strokeStyle = "rgba(255,45,45,0.6)"; ctx.lineWidth = 1.3; ctx.stroke(); ctx.setLineDash([]);
        });
        const [m1x, m1y] = px(ends[0].lat, ends[0].lng); const [m2x, m2y] = px(ends[1].lat, ends[1].lng);
        const mx = (m1x + m2x) / 2, my = (m1y + m2y) / 2;
        ctx.beginPath(); ctx.arc(mx, my, 9 + Math.sin(Date.now() / 180) * 2.5, 0, Math.PI * 2);
        ctx.strokeStyle = "#ff2d2d"; ctx.lineWidth = 2; ctx.stroke();
        ctx.fillStyle = "#ff2d2d"; ctx.font = "bold 11px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(`CPA ${Number(c.cpaNM).toFixed(2)} NM / ${Math.round(c.cpaVerticalFt)} ft`, mx + 14, my - 6);
        ctx.fillStyle = textMuted; ctx.font = "10px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(`in ${Math.round(t)} s (straight-line prediction)`, mx + 14, my + 8);
        const best = c.resolution?.options?.[0]?.explanation;
        labelBox(14, Math.max(96, h - (best ? 104 : 72)),
                 [`LOSS OF SEPARATION · ${c.flight1} × ${c.flight2}`, c.reason || "", ...(best ? [`Top option: ${best.split(". Reason")[0]}`] : [])],
                 isLight ? "#b91c1c" : "#ff2d2d", Math.min(430, w - 28));
      }

      // Aircraft at their reported positions, with a 60 s straight-line vector.
      for (const f of fl) {
        if (f.lat == null) continue;
        const [fx, fy] = px(f.lat, f.lng);
        if (Math.hypot(fx - cx, fy - cy) > radius + 4) continue;
        const color = statusColors[String(f.status || "").toLowerCase()] || baseColor;
        const [vx, vy] = (() => { const p = ahead(f, 60); return px(p.lat, p.lng); })();
        ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(vx, vy);
        ctx.strokeStyle = `rgba(${ringRGB},0.7)`; ctx.lineWidth = 1; ctx.stroke();
        if (sel === f.callsign) { ctx.beginPath(); ctx.arc(fx, fy, 14, 0, Math.PI * 2); ctx.strokeStyle = baseColor; ctx.lineWidth = 2.5; ctx.stroke(); }
        ctx.beginPath(); ctx.moveTo(fx, fy - 5); ctx.lineTo(fx + 5, fy); ctx.lineTo(fx, fy + 5); ctx.lineTo(fx - 5, fy); ctx.closePath();
        ctx.fillStyle = color; ctx.fill();
        // At a widened (alarm) range only the alarm pair and the selected aircraft are labelled,
        // or the labels near VABB pile on top of each other.
        const labelled = RANGE_NM <= BASE_RANGE_NM || sel === f.callsign || pair.includes(f);
        if (labelled) {
          ctx.fillStyle = color; ctx.font = "bold 11px 'Geist Variable', system-ui, sans-serif"; ctx.fillText(f.callsign, fx + 10, fy - 5);
          ctx.fillStyle = textMuted; ctx.font = "10px 'Geist Variable', system-ui, sans-serif"; ctx.fillText(f.altitude || "", fx + 10, fy + 8);
        }
      }

      ctx.fillStyle = `rgba(${ringRGB},${isLight ? "0.9" : "0.6"})`; ctx.font = "11px 'Geist Variable', system-ui, sans-serif";
      [`SOURCE: ${fd?.source === "live" ? "LIVE OpenSky" : fd?.source === "replay" ? "RECORDED SESSION" : "—"}`,
       `RANGE: ${RANGE_NM} NM · CENTRE VABB`, "VECTORS: 60 s straight line"].forEach((t, i) => ctx.fillText(t, 16, 24 + i * 18));

      angleRef.current += Math.PI / 180;
      animRef.current = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(animRef.current); ro.disconnect(); };
  }, [isLight]);

  return (
    <div className="panel overflow-hidden flex flex-col h-full w-full">
      <div className="flex-1 relative w-full h-full">
        <canvas ref={canvasRef} className="absolute inset-0 block" style={{ background: isLight ? "var(--bg-base)" : "#060608" }} />
      </div>
      <div className="flex items-center justify-between px-5 py-3 shrink-0" style={{ background: "var(--bg-panel)", borderTop: "1px solid var(--border-default)" }}>
        {[`${inRange} IN ${range} NM`, `${flights.length} TRACKED`, `${runwayPairs || "—"} RUNWAYS`, conflict ? "ALARM" : "NO ALARM"].map((s) => (
          <span key={s} className="font-display text-[12px] tracking-wider" style={{ color: "var(--amber)" }}>{s}</span>
        ))}
        <span className="font-display text-[10px] tracking-wider" style={{ color: "rgba(255,45,45,0.6)" }}>─── 5 NM RING (to scale)</span>
      </div>
    </div>
  );
}
