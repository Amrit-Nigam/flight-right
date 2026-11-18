import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { logAudit } from "@/lib/siteLogger";
import { X, ChevronDown, ChevronUp } from "lucide-react";
import AlertEvidence from '@/components/AlertEvidence';

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
  const [clock, setClock] = useState({initialSeconds,secs:initialSeconds});
  if(clock.initialSeconds!==initialSeconds)setClock({initialSeconds,secs:initialSeconds});
  useEffect(() => {
    const id = setInterval(() => setClock(s => ({...s,secs:s.secs<=1?0:s.secs-1})), 1000);
    return () => clearInterval(id);
  }, [initialSeconds]);
  return clock.secs;
}

// ─────────────────────────────────────────────────────────────────────────────
export default function ResolveModal({ open, conflict, options = [], countdown, selectedOption, onSelectOption, onApply, onCancel }) {
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
          initial={false} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)' }}
        >
          <motion.div
            initial={false} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
            role="dialog" aria-modal="true" aria-label="Conflict resolution"
            className="w-full max-w-[720px] max-h-[90dvh] mx-4 rounded overflow-y-auto"
            style={{ background: 'var(--bg-panel)', border: '2px solid var(--red)' }}
          >
            {/* ── HEADER ── */}
            <div className="flex flex-wrap items-start justify-between gap-3 p-5" style={{ borderBottom: '2px solid var(--red)', background: 'rgba(255,45,45,0.04)' }}>
              {/* Left: callsigns + mini diagram */}
              <div className="flex items-start gap-4 flex-1 min-w-0">
                <div className="hidden sm:block shrink-0"><MiniRadar conflict={conflict} /><small>Schematic · not to scale</small></div>
                <div className="min-w-0 flex-1">
                  <h2 className="font-display text-[15px] tracking-wider glow-red" style={{ color: 'var(--red)' }}>
                    ⚡ CONFLICT RESOLUTION
                  </h2>
                  <p className="font-display text-[20px] tracking-widest mt-0.5" style={{ color: 'var(--text-primary)' }}>
                    {conflict.flight1} × {conflict.flight2}
                  </p>
                  <p className="font-body text-[12px] mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                    {conflict.reason}
                  </p>
                  <p className="font-display text-[11px] mt-1 tracking-wide" style={{ color: 'var(--text-muted)' }}>
                    Alert-path closest approach:{" "}
                    <span style={{ color: urgencyColor }}>
                      {Number(conflict.cpaNM).toFixed(2)} NM / {Math.round(conflict.cpaVerticalFt ?? 0)} ft
                    </span>{" "}
                    — separation standard 5 NM laterally or 1000 ft vertically (en-route)
                    {conflict.probability != null && (
                      <> · classifier probability {(conflict.probability * 100).toFixed(0)}%</>
                    )}
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
                  style={{ fontSize: 'clamp(28px, 6vw, 52px)', color: urgencyColor, fontVariantNumeric: 'tabular-nums', letterSpacing: 2 }}
                >
                  {secs > 0 ? timeStr : "00:00"}
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
              <AlertEvidence alert={conflict}/>
              <p className="font-body text-[13px]" style={{ color: 'var(--text-secondary)' }}>
                {options.length
                  ? <>Select a resolution strategy — <span style={{ color: 'var(--green)' }}>ranked best first</span>. Nothing is transmitted; accepting records your decision.</>
                  : "No manoeuvre in the candidate set restores separation in the time available."}
              </p>
            </div>

            {/* ── OPTIONS ── */}
            <div className="p-5 space-y-3">
              {options.map((opt) => {
                const selected = selectedOption === opt.id;
                return (
                  <div
                    key={opt.id}
                    role="radio"
                    aria-checked={selected}
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectOption(opt.id);
                      }
                    }}
                    onClick={() => {
                      logAudit("resolve:option", "Resolution strategy row selected", { optionId: opt.id, recommended: !!opt.recommended });
                      onSelectOption(opt.id);
                    }}
                    className="w-full text-left p-4 transition-all relative cursor-pointer"
                    style={{
                      border: selected ? '2px solid var(--green)' : '1px solid var(--border-default)',
                      background: selected ? 'rgba(0,255,136,0.06)' : 'var(--bg-panel-alt)',
                    }}
                  >
                    {opt.recommended && (
                      <div className="absolute top-3 right-3 flex flex-col items-end gap-1">
                        <span className="font-display text-[10px] px-2 py-0.5" style={{ border: '1px solid var(--green)', color: 'var(--green)', background: 'rgba(0,255,136,0.08)' }}>
                          TOP RANKED SIMULATION
                        </span>
                      </div>
                    )}
                    <p className="font-display text-[14px] tracking-wider pr-28" style={{ color: 'var(--amber)' }}>
                      {opt.label}
                    </p>
                    <p className="font-body text-[13px] mt-1" style={{ color: 'var(--text-secondary)' }}>{opt.action}</p>
                    <p className="font-body text-[12px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{opt.result}</p>
                    <div className="resolution-timing" style={{color:opt.timingMargin<0?'var(--amber)':'var(--text-secondary)'}}>
                      <strong>Full-manoeuvre margin to {Number.isFinite(conflict.nominalCpa?.seconds)?'nominal':'displayed'} CPA: {opt.timingMargin==null?'not reported':`${Math.round(opt.timingMargin)} s`} (assessment time)</strong>
                      {opt.timingMargin<0&&<p>Fully established after nominal CPA. Separation may improve during the manoeuvre; the engine tests the simulated window, including response delay. Full establishment is not its acceptance gate. Review the rationale and residual path risk before recording a decision.</p>}
                      <p>Residual candidate-path breach weight: {opt.residualRisk==null?'not reported':`${Math.round(opt.residualRisk*100)}%`}. Simulation does not establish operational viability.</p>
                    </div>

                    <div className="flex flex-wrap gap-x-5 gap-y-2 mt-2 font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      <span>
                        Manoeuvre heuristic: <span style={{ color: 'var(--teal)' }}>{opt.confidence}</span>
                      </span>
                      <span>Weighted ranking score: {opt.score?.toFixed(3)} (higher ranks first)</span>
                      <span>Fuel: {opt.fuelImpact}</span>
                      <span>Delay: {opt.delayImpact}</span>
                      {opt.newConflictRisk > 0 && (
                        <span style={{ color: 'var(--amber)' }}>
                          New-conflict risk {(opt.newConflictRisk * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <details className="resolution-definitions"><summary>What these scores mean</summary><p>Manoeuvre heuristic combines simulated separation margin, establishment timing, vertical-motion steadiness and residual path risk. It is not a measured success probability. Ranking score combines safety, delay, fuel, workload and that heuristic using fixed project weights; it is not classifier confidence.</p></details>

                    {/* XAI expandable reason */}
                    {opt.xaiReason && <XaiReason reason={opt.xaiReason} />}
                  </div>
                );
              })}
            </div>

            {/* ── FOOTER ACTIONS (equal weight) ── */}
            <div className="p-5 flex flex-col sm:flex-row gap-3" style={{ borderTop: '1px solid var(--border-default)',position:'sticky',bottom:0,background:'var(--bg-panel)',zIndex:2 }}>
              <button
                type="button"
                onClick={() => {
                  logAudit("resolve:modal", "Accept clicked — recording controller decision", { selectedOption });
                  onApply();
                }}
                disabled={!selectedOption || !options.length}
                className="flex-1 py-3 font-display text-[14px] tracking-wider transition-colors disabled:opacity-30"
                style={{ background: 'var(--amber)', color: 'var(--on-amber)' }}
              >
                ACCEPT — RECORD DECISION
              </button>
              <button
                type="button"
                onClick={() => {
                  logAudit("resolve:modal", "Dismissed — controller handling manually", { selectedOption });
                  onCancel();
                }}
                className="flex-1 py-3 font-display text-[14px] tracking-wider transition-all hover:bg-white/5"
                style={{ border: '2px solid var(--red)', color: 'var(--red)', background: 'transparent' }}
              >
                DISMISS — HANDLE MANUALLY
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
