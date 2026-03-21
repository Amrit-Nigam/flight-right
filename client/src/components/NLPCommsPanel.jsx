import { nlpComms } from "@/data/mockData";

const TYPE_BADGE = {
  ATC: { bg: "rgba(245,166,35,0.12)", border: "var(--amber)", color: "var(--amber)" },
  PILOT: { bg: "rgba(0,229,204,0.1)", border: "var(--teal)", color: "var(--teal)" },
  AI: { bg: "rgba(0,255,136,0.1)", border: "var(--green)", color: "var(--green)" },
};

export default function NLPCommsPanel({ feed }) {
  const data = feed || nlpComms;

  return (
    <div className="panel flex flex-col">
      <div className="panel-header">
        <h3 className="font-display text-[11px] tracking-wider" style={{ color: 'var(--amber)' }}>◎ NLP COMMS FEED</h3>
        <p className="font-body text-[8px] mt-0.5" style={{ color: 'var(--text-muted)' }}>AI-assisted transcript</p>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[240px]">
        {data.map((msg, i) => {
          const badge = TYPE_BADGE[msg.type] || TYPE_BADGE.ATC;
          return (
            <div key={i} className="flex gap-2 p-2" style={{ borderBottom: '1px solid var(--border-default)' }}>
              <span className="font-display text-[9px] shrink-0 pt-0.5" style={{ color: 'var(--text-muted)' }}>{msg.time}</span>
              <div className="min-w-0">
                <span className="inline-block font-display text-[9px] px-1.5 py-0.5 mb-1" style={{ background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color }}>
                  {msg.type} — {msg.flight}
                </span>
                <p className="font-body text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{msg.text}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
