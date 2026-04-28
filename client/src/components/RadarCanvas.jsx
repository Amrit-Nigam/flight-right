import { useRef, useEffect } from "react";
import { radarFlights, weatherCell, deviationRoutes } from "@/data/mockData";

const STATUS_COLORS_DARK = {
  conflict: "#ff2d2d", holding: "#ffdd00", landing: "#00e5cc",
  takeoff: "#f5a623", cruise: "#8a7d65", approach: "#00e5cc",
};
const STATUS_COLORS_LIGHT = {
  conflict: "#dc2626", holding: "#ca8a04", landing: "#0d9488",
  takeoff: "#d97706", cruise: "#64748b", approach: "#0d9488",
};

// How far ahead (in canvas-px) to draw the trajectory line
const TRAJ_PX = 55; // roughly 60s look-ahead at average scale
// 5 NM ring radius in canvas-px (approx at 50NM range with radius ~40% of canvas min dimension)
const SEP_RING_PX_RATIO = 0.10; // 5NM as fraction of the 50NM radius
const CONFLICT_CALLSIGNS = ["AI6302", "SG881"];
const CONFLICT_ACTIONS = [
  "CONTACT AI6302 FIRST: descend FL260 + left heading 020",
  "THEN SG881: maintain FL270 + right heading 350",
  "CPA projected 2.1 NM, below 3 NM minimum",
];

export default function RadarCanvas({ flights, selectedFlight, theme, weatherOn, weatherDevAccepted }) {
  const canvasRef = useRef(null);
  const animRef   = useRef(null);
  const angleRef  = useRef(0);
  const flightsRef = useRef(radarFlights.map((f) => ({ ...f, x: f.xPct / 100, y: f.yPct / 100 })));

  const isLight = theme === "light";
  const statusColors = isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS_DARK;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    const baseColor   = isLight ? "#0f172a" : "#f5a623";
    const bgSolid     = isLight ? "#eceae6" : "#060608";
    const gridOpac    = isLight ? "0.3" : "0.06";
    const hexBaseRGB  = isLight ? "148,163,184" : "245,166,35";
    const textPrimary = isLight ? "#0f172a"  : "#f5a623";
    const textMuted   = isLight ? "#64748b"  : "rgba(138,125,101,0.8)";
    const sweepBaseRGB = isLight ? "217,119,6" : "245,166,35";

    let w = 0, h = 0;

    const updateSize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width  = w * dpr; canvas.height = h * dpr;
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    updateSize();
    const ro = new ResizeObserver(() => updateSize());
    ro.observe(canvas.parentElement);

    const drawDiamond = (ctx, x, y, size, color) => {
      ctx.beginPath();
      ctx.moveTo(x, y - size); ctx.lineTo(x + size, y);
      ctx.lineTo(x, y + size); ctx.lineTo(x - size, y);
      ctx.closePath();
      ctx.fillStyle = color; ctx.fill();
    };

    const drawHexGrid = (ctx, w, h) => {
      const s = 18, hexW = s * 2, hexH = Math.sqrt(3) * s;
      ctx.strokeStyle = `rgba(${hexBaseRGB},${gridOpac})`;
      ctx.lineWidth = 0.5;
      for (let row = 0; row < h / hexH + 1; row++) {
        for (let col = 0; col < w / hexW + 1; col++) {
          const xOff = row % 2 === 0 ? 0 : s;
          const cx = col * hexW + xOff, cy = row * hexH;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i - Math.PI / 6;
            const px = cx + s * Math.cos(angle), py = cy + s * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.closePath(); ctx.stroke();
        }
      }
    };

    const drawLabelBox = (x, y, lines, accent, width = 260) => {
      const lineHeight = 15;
      const height = 16 + lines.length * lineHeight;
      ctx.save();
      ctx.fillStyle = isLight ? "rgba(255,255,255,0.94)" : "rgba(6,6,8,0.88)";
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1;
      ctx.shadowColor = accent;
      ctx.shadowBlur = isLight ? 0 : 14;
      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);
      ctx.shadowBlur = 0;
      lines.forEach((line, index) => {
        ctx.fillStyle = index === 0 ? accent : textPrimary;
        ctx.font = `${index === 0 ? "bold " : ""}${index === 0 ? 11 : 10}px 'Geist Variable', system-ui, sans-serif`;
        ctx.fillText(line, x + 10, y + 18 + index * lineHeight);
      });
      ctx.restore();
    };

    const draw = () => {
      const cx = w / 2, cy = h / 2;
      const radius = Math.max(0, Math.min(cx, cy) - 20);

      ctx.fillStyle = bgSolid;
      ctx.fillRect(0, 0, w, h);
      drawHexGrid(ctx, w, h);

      // Range rings
      for (let i = 1; i <= 5; i++) {
        const r = (radius / 5) * i;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${hexBaseRGB},${isLight ? '0.4' : '0.15'})`;
        ctx.lineWidth = 0.8; ctx.stroke();
        ctx.fillStyle = isLight ? `rgba(${hexBaseRGB},1)` : `rgba(${hexBaseRGB},0.5)`;
        ctx.font = "11px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(["10", "20", "30", "40", "50 NM"][i - 1], cx + r - 30, cy - 4);
      }

      // Crosshairs
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = `rgba(${hexBaseRGB},${isLight ? '0.3' : '0.1'})`;
      ctx.lineWidth = 0.5; ctx.stroke();

      // Sweep beam with trail
      const angle = angleRef.current;
      const trailOpacities = isLight
        ? [0.3,0.2,0.15,0.1,0.08,0.05,0.03,0.01]
        : [0.5,0.4,0.3,0.2,0.15,0.1,0.06,0.03];
      for (let t = trailOpacities.length - 1; t >= 0; t--) {
        const a1 = angle - (t + 1) * 1.5 * (Math.PI / 180);
        const a2 = angle - t * 1.5 * (Math.PI / 180);
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, a1, a2, false); ctx.closePath();
        ctx.fillStyle = `rgba(${sweepBaseRGB},${trailOpacities[t]})`; ctx.fill();
      }
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
      ctx.strokeStyle = `rgba(${sweepBaseRGB},0.8)`; ctx.lineWidth = 2; ctx.stroke();

      // Center dot
      ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = textPrimary; ctx.fill();

      const fl = flightsRef.current;
      const conflictPair = CONFLICT_CALLSIGNS
        .map(callsign => fl.find(f => f.callsign === callsign))
        .filter(Boolean);
      const conflicts = conflictPair.length >= 2 ? conflictPair : fl.filter(f => f.status === "conflict");
      const cpaX = cx;
      const cpaY = cy - radius * 0.08;

      // ── WEATHER CELL ─────────────────────────────────────────────────────
      if (weatherOn && weatherCell?.length > 0) {
        ctx.beginPath();
        for (let i = 0; i < weatherCell.length; i++) {
          const pt = weatherCell[i];
          const px = cx + (pt.xPct / 100 - 0.5) * radius * 2;
          const py = cy + (pt.yPct / 100 - 0.5) * radius * 2;
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.closePath();
        
        ctx.fillStyle = `rgba(255, 60, 0, ${0.1 + Math.sin(Date.now() / 400) * 0.05})`;
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 60, 0, 0.4)";
        ctx.lineWidth = 1; ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
        
        const pt0 = weatherCell[0];
        const lblX = cx + (pt0.xPct / 100 - 0.5) * radius * 2;
        const lblY = cy + (pt0.yPct / 100 - 0.5) * radius * 2;
        ctx.fillStyle = "rgba(255, 60, 0, 0.8)";
        ctx.font = "bold 10px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText("SEVERE WX", lblX, lblY);
      }

      // ── DEVIATION ROUTES ─────────────────────────────────────────────────
      if (weatherOn && deviationRoutes) {
        Object.entries(deviationRoutes).forEach(([callsign, pts]) => {
          const isAccepted = weatherDevAccepted;
          const color = isAccepted ? "rgba(0, 229, 204, 0.8)" : "rgba(245, 166, 35, 0.8)";
          
          const f = fl.find(x => x.callsign === callsign);
          if (f) {
            const fx = cx + (f.x - 0.5) * radius * 2;
            const fy = cy + (f.y - 0.5) * radius * 2;
            
            ctx.beginPath();
            ctx.moveTo(fx, fy);
            pts.forEach(pt => {
              const px = cx + (pt.xPct / 100 - 0.5) * radius * 2;
              const py = cy + (pt.yPct / 100 - 0.5) * radius * 2;
              ctx.lineTo(px, py);
            });
            
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([5, 5]);
            ctx.stroke();
            ctx.setLineDash([]);
            
            if (pts.length > 0) {
              const lastPt = pts[pts.length - 1];
              const lx = cx + (lastPt.xPct / 100 - 0.5) * radius * 2;
              const ly = cy + (lastPt.yPct / 100 - 0.5) * radius * 2;
              ctx.fillStyle = color;
              ctx.font = "9px 'Geist Variable', system-ui, sans-serif";
              ctx.fillText(isAccepted ? "DEV APPROVED" : "DEV PROP", lx + 4, ly);
            }
          }
        });
      }

      // ── ACTIVE CONFLICT STORY: projected convergence and controller intent ─
      if (conflicts.length >= 2) {
        const conflictPoints = conflicts.map((f) => ({
          f,
          x: cx + (f.x - 0.5) * radius * 2,
          y: cy + (f.y - 0.5) * radius * 2,
        }));

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(conflictPoints[0].x, conflictPoints[0].y);
        ctx.lineTo(cpaX, cpaY);
        ctx.lineTo(conflictPoints[1].x, conflictPoints[1].y);
        ctx.closePath();
        ctx.fillStyle = isLight ? "rgba(220,38,38,0.08)" : "rgba(255,45,45,0.12)";
        ctx.fill();
        ctx.strokeStyle = isLight ? "rgba(185,28,28,0.38)" : "rgba(255,45,45,0.4)";
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 6]);
        ctx.stroke();
        ctx.setLineDash([]);

        conflictPoints.forEach(({ f, x, y }, index) => {
          const color = index === 0 ? "#ff2d2d" : (isLight ? "#d97706" : "#ffdd00");
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.quadraticCurveTo((x + cpaX) / 2, y - 34, cpaX, cpaY);
          ctx.strokeStyle = color;
          ctx.lineWidth = 3;
          ctx.setLineDash([12, 8]);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = color;
          ctx.font = "bold 10px 'Geist Variable', system-ui, sans-serif";
          ctx.fillText(index === 0 ? "CALL FIRST" : "VECTOR SECOND", x - 34, y - 18);
          ctx.font = "10px 'Geist Variable', system-ui, sans-serif";
          ctx.fillText(`${f.heading}° / ${f.speed}kt`, x - 28, y - 4);
        });

        ctx.beginPath();
        ctx.arc(cpaX, cpaY, 10 + Math.sin(Date.now() / 180) * 3, 0, Math.PI * 2);
        ctx.fillStyle = isLight ? "rgba(185,28,28,0.2)" : "rgba(255,45,45,0.25)";
        ctx.fill();
        ctx.strokeStyle = "#ff2d2d";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = "#ff2d2d";
        ctx.font = "bold 11px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText("CPA 2.1 NM", cpaX + 14, cpaY - 8);
        ctx.fillStyle = textMuted;
        ctx.font = "10px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText("minimum 3 NM", cpaX + 14, cpaY + 7);
        ctx.restore();
      }

      // ── TRAJECTORY PREDICTION LINES (all aircraft) ───────────────────────
      for (const f of fl) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const headRad = (f.heading - 90) * (Math.PI / 180);
        const color   = statusColors[f.status] || baseColor;
        const isConflictFlight = CONFLICT_CALLSIGNS.includes(f.callsign);
        const endX    = isConflictFlight ? cpaX : fx + Math.cos(headRad) * TRAJ_PX;
        const endY    = isConflictFlight ? cpaY : fy + Math.sin(headRad) * TRAJ_PX;

        // Conflicts glow red/amber; others dim
        let trajColor;
        if (isConflictFlight) {
          trajColor = `rgba(255,${Math.round(45 + 80 * Math.abs(Math.sin(Date.now() / 300)))},45,0.85)`;
        } else if (f.status === "holding") {
          trajColor = "rgba(255,221,0,0.45)";
        } else {
          trajColor = `${color}40`;
        }

        ctx.beginPath();
        ctx.setLineDash([4, 6]);
        ctx.moveTo(fx, fy);
        ctx.lineTo(endX, endY);
        ctx.strokeStyle = trajColor;
        ctx.lineWidth = isConflictFlight ? 1.8 : 1;
        ctx.stroke();
        ctx.setLineDash([]);

        // Arrowhead at end of trajectory
        ctx.beginPath();
        ctx.arc(endX, endY, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = trajColor.replace(/,[^,]+\)$/, ",0.9)");
        ctx.fill();
      }

      // ── 5NM SEPARATION RINGS around conflicting aircraft ─────────────────
      const ringR = radius * SEP_RING_PX_RATIO;
      for (const f of conflicts) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const pulse = 1 + 0.08 * Math.sin(Date.now() / 250);

        ctx.beginPath();
        ctx.arc(fx, fy, ringR * pulse, 0, Math.PI * 2);
        ctx.setLineDash([6, 5]);
        ctx.strokeStyle = "rgba(255,45,45,0.6)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.setLineDash([]);

        // Label ring
        ctx.fillStyle = "rgba(255,45,45,0.55)";
        ctx.font = "9px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText("5NM", fx + ringR + 2, fy - 4);
      }

      // ── CONFLICT PAIR LINK + INSTRUCTION PANEL ───────────────────────────
      if (conflicts.length >= 2) {
        const f1 = conflicts[0], f2 = conflicts[1];
        const fx1 = cx + (f1.x - 0.5) * radius * 2;
        const fy1 = cy + (f1.y - 0.5) * radius * 2;
        const fx2 = cx + (f2.x - 0.5) * radius * 2;
        const fy2 = cy + (f2.y - 0.5) * radius * 2;

        ctx.beginPath(); ctx.setLineDash([3, 3]);
        ctx.moveTo(fx1, fy1); ctx.lineTo(cpaX, cpaY); ctx.lineTo(fx2, fy2);
        ctx.strokeStyle = "rgba(255,45,45,0.6)"; ctx.lineWidth = 1.2; ctx.stroke();
        ctx.setLineDash([]);

        drawLabelBox(
          Math.max(12, Math.min(18, w - 342)),
          Math.max(86, h - 104),
          ["LOSS OF SEPARATION", ...CONFLICT_ACTIONS],
          isLight ? "#b91c1c" : "#ff2d2d",
          330
        );
      }

      // ── FLIGHT BLIPS ─────────────────────────────────────────────────────
      for (const f of fl) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const color   = statusColors[f.status] || baseColor;
        const headRad = (f.heading - 90) * (Math.PI / 180);

        // Short velocity vector
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(fx + Math.cos(headRad) * 16, fy + Math.sin(headRad) * 16);
        ctx.strokeStyle = isLight ? `rgba(${hexBaseRGB},0.8)` : `rgba(${hexBaseRGB},0.6)`;
        ctx.lineWidth = 1; ctx.stroke();

        // Conflict pulsing hexagon
        if (f.status === "conflict") {
          const pulseR = 12 + Math.sin(Date.now() / 200) * 4;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const a = (Math.PI / 3) * i - Math.PI / 6;
            const px = fx + pulseR * Math.cos(a), py = fy + pulseR * Math.sin(a);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.strokeStyle = isLight ? "rgba(220,38,38,0.6)" : "rgba(255,45,45,0.7)";
          ctx.lineWidth = 1.5; ctx.stroke();
        }

        // Selected ring
        if (selectedFlight === f.callsign) {
          ctx.beginPath(); ctx.arc(fx, fy, 16, 0, Math.PI * 2);
          ctx.strokeStyle = baseColor; ctx.lineWidth = 2.5; ctx.stroke();
        }

        // Diamond blip + glow
        drawDiamond(ctx, fx, fy, 6, color);
        if (!isLight) {
          ctx.beginPath(); ctx.arc(fx, fy, 10, 0, Math.PI * 2);
          const glow = ctx.createRadialGradient(fx, fy, 2, fx, fy, 10);
          glow.addColorStop(0, color + "40"); glow.addColorStop(1, color + "00");
          ctx.fillStyle = glow; ctx.fill();
        }

        // Labels
        ctx.fillStyle = color;
        ctx.font = "bold 11px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(f.callsign, fx + 12, fy - 6);
        ctx.fillStyle = textMuted;
        ctx.font = "10px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(f.altitude, fx + 12, fy + 7);

        // Movement
        const spd = f.speed > 0 ? 0.0002 : 0;
        f.x += Math.cos(headRad) * spd;
        f.y += Math.sin(headRad) * spd;
        if (f.x < 0.05 || f.x > 0.95) f.x = Math.max(0.05, Math.min(0.95, f.x));
        if (f.y < 0.05 || f.y > 0.95) f.y = Math.max(0.05, Math.min(0.95, f.y));
      }

      // Overlay text
      ctx.fillStyle = isLight ? `rgba(${hexBaseRGB},0.8)` : `rgba(${hexBaseRGB},0.5)`;
      ctx.font = "11px 'Geist Variable', system-ui, sans-serif";
      ["MODE: APP/DEP", "RANGE: 50 NM", "SECTOR: 7B-ALPHA", "FILTER: ALL TRAFFIC"].forEach((t, i) => {
        ctx.fillText(t, 16, 24 + i * 18);
      });

      angleRef.current += 1.0 * (Math.PI / 180);
      animRef.current = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animRef.current);
      ro.disconnect();
    };
  }, [selectedFlight, isLight, statusColors, theme, weatherOn, weatherDevAccepted]);

  return (
    <div className="panel overflow-hidden flex flex-col h-full w-full">
      <div className="flex-1 relative w-full h-full">
        <canvas ref={canvasRef} className="absolute inset-0 block" style={{ background: isLight ? 'var(--bg-base)' : '#060608' }} />
      </div>
      <div className="flex items-center justify-between px-5 py-3 shrink-0" style={{ background: 'var(--bg-panel)', borderTop: '1px solid var(--border-default)' }}>
        {["28 TRACKS", "6 RWYS", "2 ALERTS", "87% OPT"].map((s) => (
          <span key={s} className="font-display text-[12px] tracking-wider" style={{ color: 'var(--amber)' }}>{s}</span>
        ))}
        <span className="font-display text-[10px] tracking-wider" style={{ color: 'rgba(255,45,45,0.6)' }}>
          ─── 5NM SEP RING
        </span>
        <span className="font-display text-[10px] tracking-wider" style={{ color: 'rgba(245,166,35,0.5)' }}>
          ╌╌ TRAJECTORY
        </span>
      </div>
    </div>
  );
}
