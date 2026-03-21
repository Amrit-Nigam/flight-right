import { motion, AnimatePresence } from "framer-motion";
import { resolveOptions } from "@/data/mockData";
import { X } from "lucide-react";

export default function ResolveModal({ open, conflict, countdown, selectedOption, onSelectOption, onApply, onCancel }) {
  if (!open || !conflict) return null;
  const mins = Math.floor(countdown / 60);
  const secs = countdown % 60;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
            className="w-full max-w-[640px] mx-4 panel-cut"
            style={{ background: 'var(--bg-panel)', border: '2px solid var(--red)' }}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4" style={{ borderBottom: '2px solid var(--red)' }}>
              <div>
                <h2 className="font-display text-[14px] glow-red" style={{ color: 'var(--red)' }}>⚡ CONFLICT RESOLUTION — {conflict.flight1} × {conflict.flight2}</h2>
                <p className="font-body text-[11px] mt-1" style={{ color: 'var(--text-secondary)' }}>Select a resolution strategy. AI recommends Option 1.</p>
              </div>
              <button onClick={onCancel} className="p-1" style={{ color: 'var(--text-muted)' }}><X className="w-5 h-5" /></button>
            </div>

            {/* Conflict summary */}
            <div className="mx-4 mt-4 p-3 font-display text-[11px]" style={{ background: 'rgba(255,45,45,0.08)', border: '1px solid var(--red)', color: 'var(--text-secondary)' }}>
              {conflict.flight1} FL280 hdg045 @ 420kt ←→ {conflict.flight2} FL270 hdg320 @ 210kt | CPA: 2.1NM in {String(mins).padStart(2,"0")}:{String(secs).padStart(2,"0")}
            </div>

            {/* Options */}
            <div className="p-4 space-y-3">
              {resolveOptions.map((opt) => {
                const selected = selectedOption === opt.id;
                return (
                  <button
                    key={opt.id}
                    onClick={() => onSelectOption(opt.id)}
                    className="w-full text-left p-4 transition-all relative"
                    style={{
                      border: selected ? '2px solid var(--green)' : '1px solid var(--border-default)',
                      background: selected ? 'rgba(0,255,136,0.06)' : 'var(--bg-panel-alt)',
                    }}
                  >
                    {opt.recommended && (
                      <span className="absolute top-2 right-2 font-display text-[8px] px-2 py-0.5" style={{ border: '1px solid var(--green)', color: 'var(--green)', background: 'rgba(0,255,136,0.08)' }}>
                        AI RECOMMENDED
                      </span>
                    )}
                    <p className="font-display text-[12px] tracking-wider" style={{ color: 'var(--amber)' }}>{opt.label}</p>
                    <p className="font-body text-[11px] mt-1" style={{ color: 'var(--text-secondary)' }}>{opt.action}</p>
                    <p className="font-body text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>{opt.result}</p>
                    <div className="flex gap-4 mt-2 font-display text-[9px]" style={{ color: 'var(--text-muted)' }}>
                      <span>Confidence: <span style={{ color: 'var(--teal)' }}>{opt.confidence}</span></span>
                      <span>Fuel: {opt.fuelImpact}</span>
                      <span>Delay: {opt.delayImpact}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Footer */}
            <div className="p-4 space-y-2" style={{ borderTop: '1px solid var(--border-default)' }}>
              <button
                onClick={onApply}
                disabled={!selectedOption}
                className="w-full py-3 font-display text-[12px] tracking-wider transition-colors disabled:opacity-30"
                style={{ background: 'var(--amber)', color: 'black' }}
              >
                APPLY RESOLUTION
              </button>
              <button
                onClick={onCancel}
                className="w-full py-2 font-display text-[11px] tracking-wider"
                style={{ color: 'var(--red)', background: 'transparent' }}
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
