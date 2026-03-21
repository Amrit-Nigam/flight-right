import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function ConflictBanner({ conflict, onResolveClick }) {
  const [seconds, setSeconds] = useState(conflict?.countdown || 260);

  useEffect(() => {
    if (!conflict) return;
    setSeconds(conflict.countdown);
    const id = setInterval(() => {
      setSeconds((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [conflict]);

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;

  return (
    <AnimatePresence>
      {conflict && (
        <motion.div
          initial={{ y: -60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -60, opacity: 0 }}
          transition={{ type: "spring", damping: 20 }}
          className="flex items-center gap-4 px-4 py-3"
          style={{
            background: 'rgba(255,45,45,0.08)',
            border: '1px solid var(--red)',
            borderLeft: '4px solid var(--red)',
          }}
        >
          <span className="text-2xl animate-blink" style={{ color: 'var(--amber)' }}>⚡</span>

          <div className="flex-1 min-w-0">
            <p className="font-display text-[12px] tracking-wider glow-red" style={{ color: 'var(--red)' }}>
              POTENTIAL CONFLICT — AI PREDICTED
            </p>
            <p className="font-body text-[11px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {conflict.detail}
            </p>
          </div>

          <div className="text-right shrink-0">
            <p className="font-body text-[8px] uppercase tracking-wider" style={{ color: 'var(--red)' }}>TIME TO CPA</p>
            <p className="font-display text-[24px] glow-red tabular-nums" style={{ color: 'var(--red)' }}>
              {seconds > 0 ? `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}` : 'SEPARATION LOST'}
            </p>
          </div>

          <button
            onClick={onResolveClick}
            className="font-display text-[11px] tracking-wider px-6 py-2 shrink-0 transition-colors"
            style={{ background: 'var(--red)', color: 'white' }}
            onMouseEnter={(e) => e.target.style.background = 'var(--red-dim)'}
            onMouseLeave={(e) => e.target.style.background = 'var(--red)'}
          >
            RESOLVE NOW
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
