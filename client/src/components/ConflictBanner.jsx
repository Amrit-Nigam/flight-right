import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function ConflictBanner({ conflict, onResolve, onResolveClick }) {
  const resolveHandler = onResolve || onResolveClick;
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
          initial={{ y: -80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -80, opacity: 0 }}
          transition={{ type: "spring", damping: 20, stiffness: 200 }}
          className="w-full relative z-40 flex items-center justify-between px-8 py-4 shadow-2xl"
          style={{
            background: 'linear-gradient(90deg, #3a0000 0%, #1a0000 100%)',
            borderBottom: '2px solid var(--red)',
            boxShadow: '0 10px 40px rgba(255,45,45,0.3)',
          }}
        >
          {/* Subtle animated background warning stripes */}
          <div className="absolute inset-0 z-0 opacity-10" style={{ background: 'repeating-linear-gradient(45deg, transparent, transparent 20px, #ff0000 20px, #ff0000 40px)' }} />

          <div className="flex items-center gap-6 relative z-10">
            <div className="w-12 h-12 flex items-center justify-center rounded-full bg-[var(--red)] animate-pulse shadow-[0_0_20px_var(--red)]">
              <span className="text-white text-xl font-bold">!</span>
            </div>
            
            <div className="flex flex-col">
              <div className="flex items-center gap-3 mb-1">
                <span className="font-display text-[16px] tracking-[0.2em] font-bold" style={{ color: 'var(--red)', textShadow: '0 0 10px var(--red)' }}>
                  LOSS OF SEPARATION ALERT
                </span>
                <span className="px-2 py-0.5 border border-[var(--red)] bg-[rgba(255,45,45,0.2)] font-display text-[10px] text-[var(--red)] tracking-widest uppercase">
                  AI PREDICTED
                </span>
              </div>
              <p className="font-body text-[14px]" style={{ color: '#ffb3b3' }}>
                {conflict.detail}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-8 relative z-10">
            <div className="flex flex-col items-end">
              <p className="font-display text-[10px] text-[var(--red)] tracking-widest uppercase mb-1">Time to CPA</p>
              <p className="font-display tabular-nums text-[36px] leading-none glow-red font-bold animate-pulse" style={{ color: 'var(--red)' }}>
                {seconds > 0 ? `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}` : 'CRITICAL'}
              </p>
            </div>

            <button
              onClick={resolveHandler}
              className="font-display text-[14px] tracking-widest px-8 py-4 font-bold transition-all shadow-lg active:scale-95 hover:scale-105"
              style={{ 
                background: '#ffffff', 
                color: '#cc0000',
                boxShadow: '0 0 30px rgba(255,255,255,0.6)'
              }}
            >
              RESOLVE NOW
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
