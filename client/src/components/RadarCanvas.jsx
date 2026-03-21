import { useRef, useEffect } from "react";
import { radarFlights } from "@/data/mockData";

const STATUS_COLORS = {
  landing: "#00e676",
  takeoff: "#00c8ff",
  cruise: "#a855f7",
  holding: "#ffaa00",
  conflict: "#ff3b5c",
};

const RANGE_LABELS = ["10 NM", "20 NM", "30 NM", "40 NM", "50 NM"];

export default function RadarCanvas() {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const angleRef = useRef(0);
  const flightsRef = useRef(
    radarFlights.map((f) => ({
      ...f,
      x: (f.xPct / 100),
      y: (f.yPct / 100),
    }))
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const dpr = window.devicePixelRatio || 1;
    const updateSize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      const size = Math.min(rect.width, rect.height);
      canvas.width = size * dpr;
      canvas.height = size * dpr;
      canvas.style.width = `${size}px`;
      canvas.style.height = `${size}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    updateSize();

    const draw = () => {
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.min(cx, cy) - 20;

      ctx.clearRect(0, 0, w, h);

      // Background
      const bgGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      bgGrad.addColorStop(0, "rgba(0, 200, 255, 0.03)");
      bgGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = bgGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      // Range rings
      for (let i = 1; i <= 5; i++) {
        const r = (radius / 5) * i;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(0, 200, 255, 0.1)";
        ctx.lineWidth = 1;
        ctx.stroke();
        // Ring label
        ctx.fillStyle = "rgba(0, 200, 255, 0.4)";
        ctx.font = "9px 'Space Mono', monospace";
        ctx.fillText(RANGE_LABELS[i - 1], cx + r - 30, cy - 4);
      }

      // Crosshairs
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy);
      ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius);
      ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = "rgba(0, 200, 255, 0.08)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Sweep beam with trail
      const angle = angleRef.current;
      const trailSteps = [0.5, 0.3, 0.15, 0.05];
      for (let t = trailSteps.length - 1; t >= 0; t--) {
        const a = angle - (t + 1) * 8 * (Math.PI / 180);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(a) * radius, cy + Math.sin(a) * radius);
        ctx.strokeStyle = `rgba(0, 200, 100, ${trailSteps[t]})`;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      // Main beam
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
      ctx.strokeStyle = "rgba(0, 200, 100, 0.85)";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Sweep glow wedge
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, angle - 0.15, angle, false);
      ctx.closePath();
      const sweepGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      sweepGrad.addColorStop(0, "rgba(0, 200, 100, 0.15)");
      sweepGrad.addColorStop(1, "rgba(0, 200, 100, 0)");
      ctx.fillStyle = sweepGrad;
      ctx.fill();

      // Flight blips
      const fl = flightsRef.current;
      for (const f of fl) {
        const fx = cx + (f.x - 0.5) * radius * 2;
        const fy = cy + (f.y - 0.5) * radius * 2;
        const color = STATUS_COLORS[f.status] || "#00c8ff";

        // Velocity vector
        const headRad = (f.heading - 90) * (Math.PI / 180);
        const vLen = 20;
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(fx + Math.cos(headRad) * vLen, fy + Math.sin(headRad) * vLen);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.6;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Conflict pulse
        if (f.status === "conflict") {
          const pulseR = 8 + Math.sin(Date.now() / 200) * 4;
          ctx.beginPath();
          ctx.arc(fx, fy, pulseR, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(255, 59, 92, 0.4)";
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Dot
        ctx.beginPath();
        ctx.arc(fx, fy, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Glow
        ctx.beginPath();
        ctx.arc(fx, fy, 8, 0, Math.PI * 2);
        const glowGrad = ctx.createRadialGradient(fx, fy, 2, fx, fy, 8);
        glowGrad.addColorStop(0, color + "40");
        glowGrad.addColorStop(1, color + "00");
        ctx.fillStyle = glowGrad;
        ctx.fill();

        // Label
        ctx.fillStyle = color;
        ctx.font = "bold 8px 'Space Mono', monospace";
        ctx.fillText(f.callsign, fx + 8, fy - 6);
        ctx.fillStyle = "rgba(200, 220, 240, 0.5)";
        ctx.font = "7px 'Space Mono', monospace";
        ctx.fillText(f.altitude, fx + 8, fy + 4);

        // Move blip
        const spd = f.speed > 0 ? 0.00015 : 0;
        f.x += Math.cos(headRad) * spd;
        f.y += Math.sin(headRad) * spd;
        // Wrap
        if (f.x < 0) f.x = 1;
        if (f.x > 1) f.x = 0;
        if (f.y < 0) f.y = 1;
        if (f.y > 1) f.y = 0;
      }

      // Update sweep angle
      angleRef.current += 1.2 * (Math.PI / 180);
      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  return (
    <div className="relative rounded-lg border border-atc-cyan/10 bg-atc-bg overflow-hidden box-glow-cyan">
      {/* Top-left overlay */}
      <div className="absolute top-3 left-3 z-10 space-y-0.5">
        {["MODE: APP/DEP", "RANGE: 50 NM", "SECTOR: 7B-ALPHA", "FILTER: ALL TRAFFIC"].map((t) => (
          <p key={t} className="text-[9px] font-mono text-atc-cyan/50 tracking-wider">{t}</p>
        ))}
      </div>

      {/* Canvas */}
      <div className="flex items-center justify-center p-2 aspect-square">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>

      {/* Bottom stats */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-atc-cyan/10 bg-atc-bg-secondary/50">
        {["28 TRACKS", "6 RWYS", "2 ALERTS", "87% OPT"].map((s) => (
          <span key={s} className="text-[9px] font-mono text-atc-text-muted tracking-wider">{s}</span>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-t border-atc-cyan/5 bg-atc-bg/80">
        {Object.entries(STATUS_COLORS).map(([st, col]) => (
          <div key={st} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: col }} />
            <span className="text-[8px] font-mono text-atc-text-muted uppercase tracking-wider">{st}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
