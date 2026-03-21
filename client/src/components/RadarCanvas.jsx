import { useRef, useEffect } from "react";
import { radarFlights } from "@/data/mockData";

const STATUS_COLORS_DARK = {
  conflict: "#ff2d2d", holding: "#ffdd00", landing: "#00e5cc",
  takeoff: "#f5a623", cruise: "#8a7d65", approach: "#00e5cc",
};

const STATUS_COLORS_LIGHT = {
  conflict: "#dc2626", holding: "#ca8a04", landing: "#0d9488",
  takeoff: "#d97706", cruise: "#64748b", approach: "#0d9488",
};

export default function RadarCanvas({ flights, selectedFlight, theme }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const angleRef = useRef(0);
  const flightsRef = useRef(radarFlights.map((f) => ({ ...f, x: f.xPct / 100, y: f.yPct / 100 })));

  const isLight = theme === "light";
  const statusColors = isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS_DARK;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    const baseColor = isLight ? "#0f172a" : "#f5a623";
    const bgSolid = isLight ? "#f8fafc" : "#060608";
    const gridOpac = isLight ? "0.3" : "0.06";

    // Track size to handle resizes properly, or simply rely on parent
    let w = 0, h = 0;

    const updateSize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    
    // Initial size
    updateSize();

    // Re-measure periodically to adapt to layout shifts (like drawer opening)
    const resizeObserver = new ResizeObserver(() => updateSize());
    resizeObserver.observe(canvas.parentElement);

    const drawDiamond = (ctx, x, y, size, color) => {
      ctx.beginPath();
      ctx.moveTo(x, y - size);
      ctx.lineTo(x + size, y);
      ctx.lineTo(x, y + size);
      ctx.lineTo(x - size, y);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    };

    const hexBaseRGB = isLight ? "148,163,184" : "245,166,35";
    const textPrimary = isLight ? "#0f172a" : "#f5a623";
    const textMuted = isLight ? "#64748b" : "rgba(138,125,101,0.8)";
    const sweepBaseRGB = isLight ? "217,119,6" : "245,166,35";

    const drawHexGrid = (ctx, w, h) => {
      const s = 18;
      const hexW = s * 2;
      const hexH = Math.sqrt(3) * s;
      ctx.strokeStyle = `rgba(${hexBaseRGB},${gridOpac})`;
      ctx.lineWidth = 0.5;
      for (let row = 0; row < h / hexH + 1; row++) {
        for (let col = 0; col < w / hexW + 1; col++) {
          const xOff = row % 2 === 0 ? 0 : s;
          const cx = col * hexW + xOff;
          const cy = row * hexH;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i - Math.PI / 6;
            const px = cx + s * Math.cos(angle);
            const py = cy + s * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.stroke();
        }
      }
    };

    const draw = () => {
      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.max(0, Math.min(cx, cy) - 20); // Clamp to prevent negative radius error

      // Clear + background
      ctx.fillStyle = bgSolid;
      ctx.fillRect(0, 0, w, h);

      // Hex grid
      drawHexGrid(ctx, w, h);

      // Range rings
      for (let i = 1; i <= 5; i++) {
        const r = (radius / 5) * i;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${hexBaseRGB},${isLight ? '0.4' : '0.15'})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();
        ctx.fillStyle = isLight ? `rgba(${hexBaseRGB},1)` : `rgba(${hexBaseRGB},0.5)`;
        ctx.font = "11px 'Share Tech Mono', monospace";
        const labels = ["10", "20", "30", "40", "50 NM"];
        ctx.fillText(labels[i - 1], cx + r - 30, cy - 4);
      }

      // Crosshairs
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = `rgba(${hexBaseRGB},${isLight ? '0.3' : '0.1'})`;
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Sweep beam with trail
      const angle = angleRef.current;
      const trailOpacities = isLight ? [0.3, 0.2, 0.15, 0.1, 0.08, 0.05, 0.03, 0.01] : [0.5, 0.4, 0.3, 0.2, 0.15, 0.1, 0.06, 0.03];
      for (let t = trailOpacities.length - 1; t >= 0; t--) {
        const a1 = angle - (t + 1) * 1.5 * (Math.PI / 180);
        const a2 = angle - t * 1.5 * (Math.PI / 180);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, a1, a2, false);
        ctx.closePath();
        ctx.fillStyle = `rgba(${sweepBaseRGB},${trailOpacities[t]})`;
        ctx.fill();
      }
      // Main sweep line
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
      ctx.strokeStyle = `rgba(${sweepBaseRGB},0.8)`;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Center dot
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = textPrimary;
      ctx.fill();

      // Flight blips
      const fl = flightsRef.current;
      
      // Look for conflicts to draw trajectory
      const conflicts = fl.filter(f => f.status === "conflict");
      if (conflicts.length >= 2) {
        const f1 = conflicts[0];
        const f2 = conflicts[1];
        const fx1 = cx + (f1.x - 0.5) * radius * 2;
        const fy1 = cy + (f1.y - 0.5) * radius * 2;
        const fx2 = cx + (f2.x - 0.5) * radius * 2;
        const fy2 = cy + (f2.y - 0.5) * radius * 2;
        
        // Midpoint predicted collision
        const mx = (fx1 + fx2) / 2;
        const my = (fy1 + fy2) / 2;

        ctx.beginPath();
        ctx.setLineDash([4, 4]);
        ctx.moveTo(fx1, fy1);
        ctx.lineTo(mx, my);
        ctx.lineTo(fx2, fy2);
        ctx.strokeStyle = "rgba(255,45,45,0.8)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.setLineDash([]);
        
        ctx.beginPath();
        ctx.arc(mx, my, 4 + Math.sin(Date.now() / 150) * 2, 0, Math.PI * 2);
        ctx.fillStyle = "#ff2d2d";
        ctx.fill();
      }

      for (const f of fl) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const color = statusColors[f.status] || baseColor;
        const headRad = (f.heading - 90) * (Math.PI / 180);

        // Velocity vector
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(fx + Math.cos(headRad) * 16, fy + Math.sin(headRad) * 16);
        ctx.strokeStyle = isLight ? `rgba(${hexBaseRGB},0.8)` : `rgba(${hexBaseRGB},0.6)`;
        ctx.lineWidth = 1;
        ctx.stroke();

        // Conflict pulsing hexagon
        if (f.status === "conflict") {
          const pulseR = 12 + Math.sin(Date.now() / 200) * 4;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const a = (Math.PI / 3) * i - Math.PI / 6;
            const px = fx + pulseR * Math.cos(a);
            const py = fy + pulseR * Math.sin(a);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.strokeStyle = isLight ? "rgba(220,38,38,0.6)" : "rgba(255,45,45,0.7)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        // Selected ring
        if (selectedFlight === f.callsign) {
          ctx.beginPath();
          ctx.arc(fx, fy, 16, 0, Math.PI * 2);
          ctx.strokeStyle = baseColor;
          ctx.lineWidth = 2.5;
          ctx.stroke();
        }

        // Diamond blip
        drawDiamond(ctx, fx, fy, 6, color);

        // Glow (only on dark mode)
        if (!isLight) {
          ctx.beginPath();
          ctx.arc(fx, fy, 10, 0, Math.PI * 2);
          const glow = ctx.createRadialGradient(fx, fy, 2, fx, fy, 10);
          glow.addColorStop(0, color + "40");
          glow.addColorStop(1, color + "00");
          ctx.fillStyle = glow;
          ctx.fill();
        }

        // Labels
        ctx.fillStyle = color;
        ctx.font = "bold 11px 'Share Tech Mono', monospace";
        ctx.fillText(f.callsign, fx + 12, fy - 6);
        ctx.fillStyle = textMuted;
        ctx.font = "10px 'Share Tech Mono', monospace";
        ctx.fillText(f.altitude, fx + 12, fy + 7);

        // Movement
        const spd = f.speed > 0 ? 0.0002 : 0;
        f.x += Math.cos(headRad) * spd;
        f.y += Math.sin(headRad) * spd;
        // Bounce at edges
        if (f.x < 0.05 || f.x > 0.95) f.x = Math.max(0.05, Math.min(0.95, f.x));
        if (f.y < 0.05 || f.y > 0.95) f.y = Math.max(0.05, Math.min(0.95, f.y));
      }

      // Overlay text
      ctx.fillStyle = isLight ? `rgba(${hexBaseRGB},0.8)` : `rgba(${hexBaseRGB},0.5)`;
      ctx.font = "11px 'Share Tech Mono', monospace";
      ["MODE: APP/DEP", "RANGE: 50 NM", "SECTOR: 7B-ALPHA", "FILTER: ALL TRAFFIC"].forEach((t, i) => {
        ctx.fillText(t, 16, 24 + i * 18);
      });

      angleRef.current += 1.0 * (Math.PI / 180);
      animRef.current = requestAnimationFrame(draw);
    };
    draw();
    
    return () => {
      cancelAnimationFrame(animRef.current);
      resizeObserver.disconnect();
    };
  }, [selectedFlight, isLight, statusColors, theme]);

  return (
    <div className="panel overflow-hidden flex flex-col h-full w-full">
      <div className="flex-1 relative w-full h-full">
        <canvas ref={canvasRef} className="absolute inset-0 block" style={{ background: isLight ? 'var(--bg-base)' : '#060608' }} />
      </div>
      <div className="flex items-center justify-between px-5 py-3 shrink-0" style={{ background: 'var(--bg-panel)', borderTop: '1px solid var(--border-default)' }}>
        {["28 TRACKS", "6 RWYS", "2 ALERTS", "87% OPT"].map((s) => (
          <span key={s} className="font-display text-[12px] tracking-wider" style={{ color: 'var(--amber)' }}>{s}</span>
        ))}
      </div>
    </div>
  );
}
