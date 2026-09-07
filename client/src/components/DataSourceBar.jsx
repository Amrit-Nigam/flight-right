// Says where the data on screen came from, always.
//
// CLAUDE.md Section 8 item 7 asks for a live-vs-simulation indicator, and Section 12
// requires the system never to imply more than it has. A dashboard that cannot say
// whether it is showing live traffic, a recording, or nothing at all is a dashboard
// that can quietly present yesterday's aircraft as if they were outside the window.

const TONE = {
  live: { label: "LIVE — OpenSky", colour: "var(--green, #008300)" },
  replay: { label: "REPLAY — recorded session", colour: "var(--teal, #1baf7a)" },
  none: { label: "NO DATA", colour: "var(--red, #e34948)" },
};

const CONNECTION = {
  streaming: "streaming",
  polling: "polling (websocket unavailable)",
  connecting: "connecting…",
  offline: "BACKEND UNREACHABLE",
};

export default function DataSourceBar({ feed = {}, connection, lastError, conflicts = {} }) {
  const tone = TONE[feed.source] || TONE.none;
  const offline = connection === "offline";
  const counts = conflicts.counts || {};

  return (
    <div
      className="flex w-full shrink-0 flex-wrap items-center gap-x-5 gap-y-1 px-4 py-1.5"
      style={{
        background: offline ? "rgba(227,73,72,0.10)" : "var(--bg-panel, rgba(0,0,0,0.03))",
        borderBottom: "1px solid var(--border, rgba(0,0,0,0.08))",
        fontSize: 10.5,
        letterSpacing: "0.06em",
        fontFamily: "'Geist Variable', system-ui, sans-serif",
      }}
    >
      <span className="flex items-center gap-1.5" style={{ color: offline ? TONE.none.colour : tone.colour, fontWeight: 600 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor",
                       display: "inline-block" }} />
        {offline ? TONE.none.label : tone.label}
      </span>

      <span style={{ color: "var(--text-muted)" }}>
        {CONNECTION[connection] || connection}
      </span>

      {feed.replay && (
        <span style={{ color: "var(--text-muted)" }}>
          {feed.replay.session} · frame {feed.replay.frame + 1}/{feed.replay.frames}
          {feed.replay.speed !== 1 ? ` · ${feed.replay.speed}×` : ""}
        </span>
      )}

      {feed.creditsRemaining != null && (
        <span style={{ color: "var(--text-muted)" }}>{feed.creditsRemaining} OpenSky credits left</span>
      )}

      <span style={{ color: "var(--text-muted)" }}>
        {feed.count ?? 0} tracked · {conflicts.eligibleAircraft ?? 0} en-route ·{" "}
        {conflicts.pairsAssessed ?? 0} pairs assessed
        {conflicts.durationMs != null ? ` in ${conflicts.durationMs} ms` : ""}
      </span>

      {(counts.repeats_suppressed > 0 || counts.collapsed_low_confidence > 0) && (
        <span style={{ color: "var(--text-muted)" }}
              title="Suppression only affects whether a pair raises a new interruption. Every confirmed pair stays on the active list.">
          {counts.repeats_suppressed || 0} repeats suppressed ·{" "}
          {counts.collapsed_low_confidence || 0} collapsed
        </span>
      )}

      {feed.updatedAt && (
        <span style={{ color: "var(--text-muted)" }}>
          updated {new Date(feed.updatedAt).toLocaleTimeString()}
        </span>
      )}

      {(feed.error || lastError) && (
        <span style={{ color: TONE.none.colour }} title={feed.error || lastError}>
          {String(feed.error || lastError).slice(0, 90)}
        </span>
      )}

      <span className="ml-auto" style={{ color: "var(--text-muted)", opacity: 0.75 }}>
        PROTOTYPE · DECISION SUPPORT · CONTROLLER DECIDES
      </span>
    </div>
  );
}
