import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { resolveOptions } from "@/data/mockData";
import { logActivity, logAudit } from "@/lib/siteLogger";
import { X, ChevronDown, ChevronUp } from "lucide-react";

// ── Mini trajectory diagram ────────────────────────────────────────────────
function MiniRadar({ conflict }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !conflict) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;

    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = "rgba(0,0,0,0.4)";
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(255,45,45,0.15)";
    ctx.lineWidth = 0.5;
    // Simple grid lines
    for (let i = 1; i < 4; i++) {
      ctx.beginPath(); ctx.moveTo(i * W / 4, 0); ctx.lineTo(i * W / 4, H); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * H / 4); ctx.lineTo(W, i * H / 4); ctx.stroke();
    }

    const f1 = conflict.f1 || { x: 0.72, y: 0.30, heading: 45,  label: conflict.flight1 || "F1" };
    const f2 = conflict.f2 || { x: 0.28, y: 0.68, heading: 320, label: conflict.flight2 || "F2" };

    const draw = (f, color) => {
      const fx = f.x * W, fy = f.y * H;
      const headRad = (f.heading - 90) * Math.PI / 180;
      const trajLen = Math.min(W, H) * 0.4;
      const ex = fx + Math.cos(headRad) * trajLen;
      const ey = fy + Math.sin(headRad) * trajLen;

      // Trajectory line
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.moveTo(fx, fy);
      ctx.lineTo(ex, ey);
      ctx.strokeStyle = color + "bb";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);

      // Arrowhead
      const arrLen = 7;
      const angle1 = Math.atan2(ey - fy, ex - fx);
      ctx.beginPath();
      ctx.moveTo(ex, ey);
      ctx.lineTo(ex - arrLen * Math.cos(angle1 - 0.4), ey - arrLen * Math.sin(angle1 - 0.4));
      ctx.lineTo(ex - arrLen * Math.cos(angle1 + 0.4), ey - arrLen * Math.sin(angle1 + 0.4));
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();

      // Diamond blip
      ctx.beginPath();
      ctx.moveTo(fx, fy - 5); ctx.lineTo(fx + 5, fy); ctx.lineTo(fx, fy + 5); ctx.lineTo(fx - 5, fy);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();

      // Label
      ctx.fillStyle = color;
      ctx.font = "bold 9px 'Geist Variable', system-ui, sans-serif";
      ctx.fillText(f.label || f.callsign, fx + 7, fy - 4);
      if (f.altitude) {
        ctx.fillStyle = "rgba(180,180,180,0.7)";
        ctx.font = "8px 'Geist Variable', system-ui, sans-serif";
        ctx.fillText(f.altitude, fx + 7, fy + 7);
      }
    };

    draw(f1, "#ff2d2d");
    draw(f2, "#f5a623");

    // CPA midpoint
    const mx = ((f1.x + f2.x) / 2) * W;
    const my = ((f1.y + f2.y) / 2) * H;
    ctx.beginPath(); ctx.arc(mx, my, 5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,45,45,0.9)"; ctx.fill();
    const crossSize = 7;
    ctx.beginPath();
    ctx.moveTo(mx - crossSize, my - crossSize); ctx.lineTo(mx + crossSize, my + crossSize);
    ctx.moveTo(mx + crossSize, my - crossSize); ctx.lineTo(mx - crossSize, my + crossSize);
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = "rgba(255,45,45,0.8)";
    ctx.font = "bold 8px 'Geist Variable', system-ui, sans-serif";
    ctx.fillText("CPA", mx + 7, my - 3);
  }, [conflict]);

  return (
    <canvas
      ref={canvasRef}
      width={160}
      height={100}
      style={{ borderRadius: 4, border: '1px solid rgba(255,45,45,0.3)', display: 'block' }}
    />
  );
}

// ── XAI Reason expandable ──────────────────────────────────────────────────
function XaiReason({ reason }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() =>
          setOpen((o) => {
            const next = !o;
            logAudit("resolve:xai", next ? "Expanded XAI rationale" : "Collapsed XAI rationale", { chars: reason?.length });
            return next;
          })
        }
        className="flex items-center gap-1 font-display text-[10px] tracking-widest"
        style={{ color: 'var(--green)' }}
      >
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        WHY THIS OPTION?
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <p className="mt-1.5 font-body text-[12px] leading-relaxed p-2 rounded" style={{ background: 'rgba(0,255,136,0.05)', border: '1px solid rgba(0,255,136,0.15)', color: 'var(--text-secondary)' }}>
              {reason}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Live countdown hook ────────────────────────────────────────────────────
function useLiveCountdown(initialSeconds) {
  const [secs, setSecs] = useState(initialSeconds);
  useEffect(() => {
    setSecs(initialSeconds);
    const id = setInterval(() => setSecs(s => (s <= 1 ? 0 : s - 1)), 1000);
    return () => clearInterval(id);
  }, [initialSeconds]);
  return secs;
}

// ─────────────────────────────────────────────────────────────────────────────
export default function ResolveModal({ open, conflict, countdown, selectedOption, onSelectOption, onApply, onCancel }) {
  const secs = useLiveCountdown(countdown);
  if (!open || !conflict) return null;

  const mins    = Math.floor(secs / 60);
  const remSecs = secs % 60;
  const timeStr = `${String(mins).padStart(2, "0")}:${String(remSecs).padStart(2, "0")}`;
  const urgencyColor = secs < 180 ? "var(--red)" : secs < 480 ? "#f5a623" : "var(--green)";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)' }}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
            className="w-full max-w-[720px] mx-4 panel-cut overflow-hidden"
            style={{ background: 'var(--bg-panel)', border: '2px solid var(--red)' }}
          >
            {/* ── HEADER ── */}
            <div className="flex items-start justify-between p-5" style={{ borderBottom: '2px solid var(--red)', background: 'rgba(255,45,45,0.04)' }}>
              {/* Left: callsigns + mini diagram */}
              <div className="flex items-start gap-4 flex-1">
                <MiniRadar conflict={conflict} />
                <div>
                  <h2 className="font-display text-[15px] tracking-wider glow-red" style={{ color: 'var(--red)' }}>
                    ⚡ CONFLICT RESOLUTION
                  </h2>
                  <p className="font-display text-[20px] tracking-widest mt-0.5" style={{ color: 'var(--text-primary)' }}>
                    {conflict.flight1} × {conflict.flight2}
                  </p>
                  <p className="font-body text-[12px] mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                    {conflict.flight1} FL280 hdg045 @ 420kt &nbsp;↔&nbsp; {conflict.flight2} FL270 hdg320 @ 210kt
                  </p>
                  <p className="font-display text-[11px] mt-1 tracking-wide" style={{ color: 'var(--text-muted)' }}>
                    CPA: <span style={{ color: urgencyColor }}>{conflict.cpaNM ?? 2.1} NM</span> — Below 3 NM minimum separation
                  </p>
                </div>
              </div>

              {/* Right: big countdown */}
              <div className="flex flex-col items-end gap-1">
                <p className="font-display text-[10px] uppercase tracking-widest" style={{ color: urgencyColor }}>
                  Time to CPA
                </p>
                <p
                  className="font-display tabular-nums leading-none"
                  style={{ fontSize: 52, color: urgencyColor, textShadow: `0 0 24px ${urgencyColor}80`, fontVariantNumeric: 'tabular-nums', letterSpacing: 2 }}
                >
                  {secs > 0 ? timeStr : "CRITICAL"}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    logAudit("resolve:modal", "Modal header close (X) clicked");
                    onCancel();
                  }}
                  className="p-1 mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* ── SELECTION NOTICE ── */}
            <div className="px-5 pt-4">
              <p className="font-body text-[13px]" style={{ color: 'var(--text-secondary)' }}>
                Select a resolution strategy — <span style={{ color: 'var(--green)' }}>AI recommends Option 1</span>
              </p>
            </div>

            {/* ── OPTIONS ── */}
            <div className="p-5 space-y-3">
              {resolveOptions.map((opt) => {
                const selected = selectedOption === opt.id;
                return (
                  <button
                    key={opt.id}
                    onClick={() => {
                      logAudit("resolve:option", "Resolution strategy row selected", { optionId: opt.id, recommended: !!opt.recommended });
                      logActivity("conflict:option", `Selected mock resolution ${opt.id}`, {
                        recommended: !!opt.recommended,
                        label: opt.label,
                      });
                      onSelectOption(opt.id);
                    }}
                    className="w-full text-left p-4 transition-all relative"
                    style={{
                      border: selected ? '2px solid var(--green)' : '1px solid var(--border-default)',
                      background: selected ? 'rgba(0,255,136,0.06)' : 'var(--bg-panel-alt)',
                    }}
                  >
                    {opt.recommended && (
                      <div className="absolute top-3 right-3 flex flex-col items-end gap-1">
                        <span className="font-display text-[10px] px-2 py-0.5" style={{ border: '1px solid var(--green)', color: 'var(--green)', background: 'rgba(0,255,136,0.08)' }}>
                          AI RECOMMENDED
                        </span>
                      </div>
                    )}
                    <p className="font-display text-[14px] tracking-wider pr-28" style={{ color: 'var(--amber)' }}>
                      {opt.label}
                    </p>
                    <p className="font-body text-[13px] mt-1" style={{ color: 'var(--text-secondary)' }}>{opt.action}</p>
                    <p className="font-body text-[12px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{opt.result}</p>

                    <div className="flex gap-5 mt-2 font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {/* ATCO match replaces confidence % */}
                      <span>
                        ATCO match: <span style={{ color: 'var(--teal)' }}>{opt.atcoMatch}</span>
                        <span style={{ fontSize: 10, marginLeft: 4 }}>({opt.atcoCases?.toLocaleString()} cases)</span>
                      </span>
                      <span>Fuel: {opt.fuelImpact}</span>
                      <span>Delay: {opt.delayImpact}</span>
                    </div>

                    {/* XAI expandable reason */}
                    {opt.xaiReason && <XaiReason reason={opt.xaiReason} />}
                  </button>
                );
              })}
            </div>

            {/* ── FOOTER ACTIONS (equal weight) ── */}
            <div className="p-5 flex gap-3" style={{ borderTop: '1px solid var(--border-default)' }}>
              <button
                type="button"
                onClick={() => {
                  logAudit("resolve:modal", "APPLY RESOLUTION button clicked", { selectedOption });
                  onApply();
                }}
                disabled={!selectedOption}
                className="flex-1 py-3 font-display text-[14px] tracking-wider transition-colors disabled:opacity-30"
                style={{ background: 'var(--amber)', color: 'black' }}
              >
                APPLY RESOLUTION
              </button>
              <button
                type="button"
                onClick={() => {
                  logAudit("resolve:modal", "CANCEL — HANDLE MANUALLY button clicked", { selectedOption });
                  onCancel();
                }}
                className="flex-1 py-3 font-display text-[14px] tracking-wider transition-all hover:bg-white/5"
                style={{ border: '2px solid var(--red)', color: 'var(--red)', background: 'transparent' }}
              >
                CANCEL — HANDLE MANUALLY
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
