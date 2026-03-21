import { motion, AnimatePresence } from "framer-motion";

export default function AISuggestionsPanel({ suggestions, onAccept, onDismiss, aiEnabled, acceptedCount }) {
  return (
    <div className="panel flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <h3 className="font-display text-[13px] tracking-wider" style={{ color: 'var(--amber)' }}>
          ✦ AI RECOMMENDATIONS
        </h3>
        {acceptedCount > 0 && (
          <span className="font-display text-[11px]" style={{ color: 'var(--green)' }}>{acceptedCount} applied</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2 relative">
        {!aiEnabled && (
          <div className="absolute inset-0 z-10 flex items-center justify-center" style={{ background: 'rgba(6,6,8,0.85)' }}>
            <p className="font-display text-[14px] tracking-wider" style={{ color: 'var(--text-muted)' }}>AI ASSIST DISABLED</p>
          </div>
        )}

        <AnimatePresence>
          {suggestions.map((s) => (
            <motion.div
              key={s.id}
              layout
              initial={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: "100%" }}
              transition={{ duration: 0.3 }}
              className="p-3"
              style={{
                background: 'var(--bg-panel)',
                borderLeft: `3px solid ${s.typeColor}`,
                border: '1px solid var(--border-default)',
                borderLeftWidth: '3px',
                borderLeftColor: s.typeColor,
              }}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-display text-[10px] uppercase tracking-wider px-2 py-0.5" style={{ borderWidth: '2px', borderStyle: 'solid', borderColor: s.typeColor, color: s.typeColor, background: `${s.typeColor}18` }}>
                    {s.type}
                  </span>
                  <span className="font-display text-[10px] px-2 py-0.5" style={{
                    borderWidth: '1px', borderStyle: 'solid',
                    borderColor: s.priority === 'CRITICAL' ? 'var(--red)' : s.priority === 'HIGH' ? 'var(--amber)' : 'var(--text-muted)',
                    color: s.priority === 'CRITICAL' ? 'var(--red)' : s.priority === 'HIGH' ? 'var(--amber)' : 'var(--text-muted)',
                  }}>
                    {s.priority}
                  </span>
                </div>
                <span className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>{s.confidence}</span>
              </div>

              {/* Flight chips */}
              <div className="flex gap-1 mb-2">
                {s.flights.map((f) => (
                  <span key={f} className="font-display text-[10px] px-2 py-0.5" style={{ background: 'var(--amber-glow)', border: '1px solid var(--border-default)', color: 'var(--amber)' }}>
                    {f}
                  </span>
                ))}
              </div>

              {/* Text */}
              <p className="font-body text-[13px] leading-relaxed mb-3" style={{ color: 'var(--text-secondary)' }}>{s.text}</p>

              {/* Actions */}
              <div className="flex gap-2">
                <button
                  onClick={() => onAccept(s)}
                  className="font-display text-[11px] px-3 py-1.5 transition-colors"
                  style={{ border: '1px solid var(--green)', color: 'var(--green)', background: 'rgba(0,255,136,0.08)' }}
                  onMouseEnter={(e) => e.target.style.background = 'rgba(0,255,136,0.15)'}
                  onMouseLeave={(e) => e.target.style.background = 'rgba(0,255,136,0.08)'}
                >
                  ✓ ACCEPT
                </button>
                <button
                  onClick={() => onDismiss(s.id)}
                  className="font-display text-[11px] px-3 py-1.5 transition-colors"
                  style={{ border: '1px solid var(--border-default)', color: 'var(--text-muted)' }}
                >
                  ✕ DISMISS
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {suggestions.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <p className="font-display text-[13px]" style={{ color: 'var(--text-muted)' }}>— ALL RECOMMENDATIONS REVIEWED —</p>
          </div>
        )}
      </div>
    </div>
  );
}
