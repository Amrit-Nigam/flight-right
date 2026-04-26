import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function ConflictBanner({ conflict, onResolve, onResolveClick, theme = "dark" }) {
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
  const isLight = theme === "light";

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
            background: isLight
              ? "linear-gradient(90deg, #7f1d1d 0%, #991b1b 45%, #7f1d1d 100%)"
              : "linear-gradient(90deg, #3a0000 0%, #1a0000 100%)",
            borderBottom: "2px solid var(--red)",
            boxShadow: isLight ? "0 6px 24px rgba(127,29,29,0.2)" : "0 10px 40px rgba(255,45,45,0.3)",
          }}
        >
          {/* Subtle animated background warning stripes */}
          <div className="absolute inset-0 z-0" style={{ background: "repeating-linear-gradient(45deg, transparent, transparent 20px, #ff0000 20px, #ff0000 40px)", opacity: isLight ? 0.05 : 0.1 }} />

          <div className="flex items-center gap-6 relative z-10" style={{ fontFamily: "'Geist Variable', system-ui, sans-serif" }}>
            <div className="w-12 h-12 flex items-center justify-center rounded-full border-2 border-white/30 bg-white/10 backdrop-blur-[2px] animate-pulse shadow-[0_0_16px_rgba(0,0,0,0.35)]">
              <span className="text-white text-xl font-bold">!</span>
            </div>
            
            <div className="flex flex-col">
              <div className="flex flex-wrap items-center gap-3 mb-1">
                <span
                  className="font-display text-[16px] md:text-[17px] tracking-[0.12em] font-bold text-white"
                  style={{ textShadow: "0 1px 3px rgba(0,0,0,0.45)" }}
                >
                  LOSS OF SEPARATION ALERT
                </span>
                <span
                  className="px-2 py-0.5 font-display text-[10px] tracking-widest uppercase rounded-sm text-white"
                  style={{
                    border: "1px solid rgba(255,255,255,0.55)",
                    background: "rgba(0,0,0,0.22)",
                    textShadow: "0 1px 2px rgba(0,0,0,0.4)",
                  }}
                >
                  AI PREDICTED
                </span>
              </div>
              <p
                className="font-body text-[15px] md:text-[16px] leading-relaxed max-w-[52rem] text-white/95"
                style={{ textShadow: "0 1px 2px rgba(0,0,0,0.35)" }}
              >
                {conflict.detail}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-8 relative z-10" style={{ fontFamily: "'Geist Variable', system-ui, sans-serif" }}>
            <div className="flex flex-col items-end">
              <p className="font-display text-[10px] text-white/85 tracking-widest uppercase mb-1">Time to CPA</p>
              <p
                className="font-display tabular-nums text-[36px] leading-none font-bold text-white"
                style={{ textShadow: "0 2px 8px rgba(0,0,0,0.35)" }}
              >
                {seconds > 0 ? `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}` : "CRITICAL"}
              </p>
            </div>

            <button
              onClick={resolveHandler}
              className="font-display text-[14px] tracking-widest px-8 py-4 font-bold transition-all shadow-lg active:scale-95 hover:scale-105 rounded-sm"
              style={{ 
                background: "#ffffff",
                color: "#7f1d1d",
                boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
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
