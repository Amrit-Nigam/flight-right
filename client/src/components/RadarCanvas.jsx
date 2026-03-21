import { useRef, useEffect } from "react";
import { radarFlights } from "@/data/mockData";

const STATUS_COLORS = {
  conflict: "#ff2d2d", holding: "#ffdd00", landing: "#00e5cc",
  takeoff: "#f5a623", cruise: "#8a7d65", approach: "#00e5cc",
};

export default function RadarCanvas({ flights, selectedFlight }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const angleRef = useRef(0);
  const flightsRef = useRef(radarFlights.map((f) => ({ ...f, x: f.xPct / 100, y: f.yPct / 100 })));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    const updateSize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = 420 * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `420px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    updateSize();

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

    const drawHexGrid = (ctx, w, h) => {
      const s = 18;
      const hexW = s * 2;
      const hexH = Math.sqrt(3) * s;
      ctx.strokeStyle = "rgba(245,166,35,0.06)";
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
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.min(cx, cy) - 20;

      // Clear + background
      ctx.fillStyle = "#060608";
      ctx.fillRect(0, 0, w, h);

      // Hex grid
      drawHexGrid(ctx, w, h);

      // Range rings
      for (let i = 1; i <= 5; i++) {
        const r = (radius / 5) * i;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(245,166,35,0.12)";
        ctx.lineWidth = 0.8;
        ctx.stroke();
        ctx.fillStyle = "rgba(245,166,35,0.35)";
        ctx.font = "9px 'Share Tech Mono', monospace";
        const labels = ["10", "20", "30", "40", "50 NM"];
        ctx.fillText(labels[i - 1], cx + r - 25, cy - 4);
      }

      // Crosshairs
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = "rgba(245,166,35,0.08)";
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Sweep beam with trail
      const angle = angleRef.current;
      const trailOpacities = [0.5, 0.4, 0.3, 0.2, 0.15, 0.1, 0.06, 0.03];
      for (let t = trailOpacities.length - 1; t >= 0; t--) {
        const a1 = angle - (t + 1) * 1.5 * (Math.PI / 180);
        const a2 = angle - t * 1.5 * (Math.PI / 180);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, a1, a2, false);
        ctx.closePath();
        ctx.fillStyle = `rgba(245,166,35,${trailOpacities[t]})`;
        ctx.fill();
      }
      // Main sweep line
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
      ctx.strokeStyle = "rgba(245,166,35,0.7)";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Center dot
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#f5a623";
      ctx.fill();

      // Flight blips
      const fl = flightsRef.current;
      for (const f of fl) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const color = STATUS_COLORS[f.status] || "#f5a623";
        const headRad = (f.heading - 90) * (Math.PI / 180);

        // Velocity vector
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(fx + Math.cos(headRad) * 16, fy + Math.sin(headRad) * 16);
        ctx.strokeStyle = "rgba(245,166,35,0.5)";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Conflict pulsing hexagon
        if (f.status === "conflict") {
          const pulseR = 10 + Math.sin(Date.now() / 200) * 4;
          ctx.beginPath();
          for (let i = 0; i < 6; i++) {
            const a = (Math.PI / 3) * i - Math.PI / 6;
            const px = fx + pulseR * Math.cos(a);
            const py = fy + pulseR * Math.sin(a);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.strokeStyle = "rgba(255,45,45,0.5)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        // Selected ring
        if (selectedFlight === f.callsign) {
          ctx.beginPath();
          ctx.arc(fx, fy, 14, 0, Math.PI * 2);
          ctx.strokeStyle = "#f5a623";
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Diamond blip
        drawDiamond(ctx, fx, fy, 5, color);

        // Glow
        ctx.beginPath();
        ctx.arc(fx, fy, 10, 0, Math.PI * 2);
        const glow = ctx.createRadialGradient(fx, fy, 2, fx, fy, 10);
        glow.addColorStop(0, color + "30");
        glow.addColorStop(1, color + "00");
        ctx.fillStyle = glow;
        ctx.fill();

        // Labels
        ctx.fillStyle = color;
        ctx.font = "bold 9px 'Share Tech Mono', monospace";
        ctx.fillText(f.callsign, fx + 10, fy - 4);
        ctx.fillStyle = "rgba(138,125,101,0.6)";
        ctx.font = "8px 'Share Tech Mono', monospace";
        ctx.fillText(f.altitude, fx + 10, fy + 7);

        // Movement
        const spd = f.speed > 0 ? 0.0002 : 0;
        f.x += Math.cos(headRad) * spd;
        f.y += Math.sin(headRad) * spd;
        // Bounce at edges
        if (f.x < 0.05 || f.x > 0.95) f.x = Math.max(0.05, Math.min(0.95, f.x));
        if (f.y < 0.05 || f.y > 0.95) f.y = Math.max(0.05, Math.min(0.95, f.y));
      }

      // Overlay text
      ctx.fillStyle = "rgba(245,166,35,0.4)";
      ctx.font = "10px 'Share Tech Mono', monospace";
      ["MODE: APP/DEP", "RANGE: 50 NM", "SECTOR: 7B-ALPHA", "FILTER: ALL TRAFFIC"].forEach((t, i) => {
        ctx.fillText(t, 12, 20 + i * 16);
      });

      angleRef.current += 1.0 * (Math.PI / 180);
      animRef.current = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [selectedFlight]);

  return (
    <div className="panel overflow-hidden">
      <canvas ref={canvasRef} className="w-full" style={{ height: '420px' }} />
      <div className="flex items-center justify-between px-4 py-2" style={{ borderTop: '1px solid var(--border-default)' }}>
        {["28 TRACKS", "6 RWYS", "2 ALERTS", "87% OPT"].map((s) => (
          <span key={s} className="font-display text-[10px]" style={{ color: 'rgba(245,166,35,0.6)' }}>{s}</span>
        ))}
      </div>
    </div>
  );
}
