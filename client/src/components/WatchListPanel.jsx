// Tier 2: pairs three to ten minutes out.
//
// This is a watch list and nothing more. It never carries a manoeuvre, because a
// ten-minute prediction is not accurate enough to justify turning a real aircraft, and
// turning one that was never going to conflict costs real fuel and real delay
// (CLAUDE.md Section 3). It is also where 97% of the false alarms live, which is why it
// is quiet and the alarm banner is not.

export default function WatchListPanel({ items = [], lowConfidence = {} }) {
  const collapsed = lowConfidence.count || 0;

  return (
    <div className="flex flex-col" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between px-4 py-2.5"
           style={{ borderBottom: "1px solid var(--border)" }}>
        <span className="font-display text-[11px] tracking-widest" style={{ color: "var(--teal)" }}>
          TIER 2 WATCH LIST
        </span>
        <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
          {items.length} pair{items.length === 1 ? "" : "s"} · 3–10 min · advisory only
        </span>
      </div>

      {items.length === 0 ? (
        <div className="px-4 py-4 text-[11px]" style={{ color: "var(--text-muted)" }}>
          No pairs on the watch list.
        </div>
      ) : (
        <div className="flex flex-col">
          {items.map((item) => (
            <div key={item.id} className="flex flex-col gap-1 px-4 py-2.5"
                 style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="flex items-center justify-between">
                <span className="font-display text-[12px]" style={{ color: "var(--text-primary)" }}>
                  {item.pair[0]} <span style={{ color: "var(--text-muted)" }}>↔</span> {item.pair[1]}
                </span>
                <span className="text-[10px] tracking-wider"
                      style={{ color: item.severity === "high" ? "var(--amber)" : "var(--text-muted)" }}>
                  {String(item.severity || "").toUpperCase()}
                </span>
              </div>
              <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                closest approach {item.cpaLateralNm?.toFixed(2)} NM /{" "}
                {Math.round(item.cpaVerticalFt)} ft in {Math.round(item.timeToCpaSeconds)} s
                {item.probability != null && ` · model ${(item.probability * 100).toFixed(0)}%`}
                {item.display === "low_confidence" && " · low confidence"}
              </div>
            </div>
          ))}
        </div>
      )}

      {collapsed > 0 && (
        <div className="px-4 py-2 text-[10px]" style={{ color: "var(--text-muted)" }}
             title="Collapsed rows are still on the active list and are released into a full alarm the moment they become tier 1.">
          + {collapsed} lower-confidence pair{collapsed === 1 ? "" : "s"} collapsed to keep the
          urgent ones readable. Still tracked.
        </div>
      )}
    </div>
  );
}
