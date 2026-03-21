import { useEffect, useRef } from "react";
import { nlpComms } from "@/data/mockData";

export default function NLPCommsPanel({ feed }) {
  const comms = feed || nlpComms;
  const scrollRef = useRef(null);

  // Auto-scroll to bottom on new comms
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [comms]);

  return (
    <div className="panel flex flex-col h-full overflow-hidden bg-[#0a0a0e]" style={{ border: '1px solid var(--border-default)' }}>
      {/* Transcript Header */}
      <div className="py-2.5 px-4 flex items-center justify-between border-b border-[var(--border-default)] bg-[#050508]">
        <h3 className="font-display text-[11px] tracking-[0.2em] text-[var(--text-muted)] uppercase">
          VHF / DATALINK TRANSCRIPT
        </h3>
        <span className="font-display text-[9px] text-[var(--teal)] animate-pulse flex items-center gap-1.5 tracking-widest">
          <span className="w-1.5 h-1.5 bg-[var(--teal)] rounded-full shadow-[0_0_8px_var(--teal)]" />
          REC THREAD
        </span>
      </div>

      {/* Transcript Feed */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 no-scrollbar font-display text-[11px] tracking-wide scroll-smooth">
        {comms.map((comm, idx) => {
          const isATC = comm.type === 'ATC';
          const isPilot = comm.type === 'PILOT';
          const isSystem = comm.type === 'SYSTEM';
          
          const dotColor = isATC ? 'var(--amber)' : isPilot ? 'var(--text-secondary)' : 'var(--teal)';
          const textColor = isSystem ? 'var(--green)' : 'var(--text-primary)';

          return (
            <div key={comm.id || idx} className="flex flex-col gap-1 group hover:bg-white/[0.02] p-1.5 -mx-1.5 rounded transition-colors border-l-2 border-transparent hover:border-[var(--border-bright)]">
              <div className="flex items-center gap-2.5 opacity-60 group-hover:opacity-100 transition-opacity">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: dotColor }} />
                <span className="text-[10px] text-[var(--text-muted)]">121.500</span>
                <span className="text-[10px] text-[var(--text-muted)]">{comm.time}</span>
                <span className="text-[10px] uppercase tracking-widest" style={{ color: dotColor }}>{comm.type}</span>
              </div>
              <div className="pl-4 leading-relaxed" style={{ color: textColor }}>
                {comm.flight && <span className="text-white font-bold mr-2">{comm.flight}</span>}
                <span className={isSystem ? "text-[12px] text-[var(--green)] bg-[rgba(0,255,136,0.05)] px-1 py-0.5 rounded shadow-[inset_0_0_10px_rgba(0,255,136,0.1)]" : "opacity-90"}>
                  {comm.text}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
