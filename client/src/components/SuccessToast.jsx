import { motion, AnimatePresence } from "framer-motion";

export default function SuccessToast({ toast }) {
  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          initial={{ x: "100%", opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: "100%", opacity: 0 }}
          transition={{ type: "spring", damping: 20 }}
          className="fixed top-20 right-4 z-50 px-5 py-3 max-w-sm"
          style={{
            background: 'var(--bg-panel)',
            borderLeft: '4px solid var(--green)',
            border: '1px solid rgba(0,255,136,0.3)',
          }}
        >
          <p className="font-display text-[13px]" style={{ color: 'var(--green)' }}>
            ✓ {toast.message}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
