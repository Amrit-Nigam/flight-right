import { motion, AnimatePresence } from "framer-motion";

export default function SuccessToast({ toast }) {
  const failed = toast?.type === 'error';
  const color = failed ? 'var(--red)' : 'var(--green)';
  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          role={failed ? 'alert' : 'status'}
          initial={{ y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 12, opacity: 0 }}
          transition={{ type: "spring", damping: 20 }}
          className="fixed bottom-16 right-4 z-[9999] px-5 py-3 w-max max-w-[min(420px,calc(100vw-32px))] shadow-2xl rounded-sm"
          style={{
            background: 'var(--bg-panel)',
            border: `1px solid ${color}`,
            borderLeft: `4px solid ${color}`,
          }}
        >
          <p className="font-display text-[13px]" style={{ color }}>
            {failed ? '⚠' : '✓'} {toast.message}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
