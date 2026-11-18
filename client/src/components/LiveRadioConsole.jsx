import { useCallback, useEffect, useRef, useState } from "react";
import { getRadioConversation, getSpeechStatus, hearAudio, reviewRadioTransmission } from "@/lib/api";
import { listRadioInputs, startRadioCapture } from "@/lib/radioCapture";

const control = "rounded px-3 py-2 text-xs border border-[var(--border-default)] disabled:opacity-40";
const field = { background: "var(--bg-panel-alt)", color: "var(--text-primary)" };
const instruction = (c) => `${c.action} ${c.fix || c.value}${["CLIMB", "DESCEND"].includes(c.action) ? " ft" : c.action === "SPEED" ? " kt" : c.action === "TURN" ? "°" : ""}`;

export default function LiveRadioConsole() {
  const [conversation, setConversation] = useState({ messages: [], inForce: {}, readbacks: {} });
  const [status, setStatus] = useState(null);
  const [devices, setDevices] = useState([]);
  const [device, setDevice] = useState("");
  const [source, setSource] = useState("device");
  const [channelRole, setChannelRole] = useState("auto");
  const [threshold, setThreshold] = useState(-38);
  const [listening, setListening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [level, setLevel] = useState({ rms: 0, active: false });
  const [sourceLabel, setSourceLabel] = useState("");
  const [queued, setQueued] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [dropped, setDropped] = useState(0);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [review, setReview] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const [audioUrls, setAudioUrls] = useState({});
  const capture = useRef(null);
  const queue = useRef([]);
  const running = useRef(false);
  const generation = useRef(0);
  const request = useRef(null);
  const mounted = useRef(false);
  const recordings = useRef(new Map());

  const refresh = useCallback(async () => {
    try {
      const [data, speech] = await Promise.all([getRadioConversation(), getSpeechStatus()]);
      if (mounted.current) { setConversation(data); setStatus(speech); setConnectionError(""); }
    } catch (e) { if (mounted.current) setConnectionError(e.message); }
  }, []);
  const inputs = async () => {
    try { const found = await listRadioInputs(); if (mounted.current) setDevices(found); }
    catch (e) { if (mounted.current) setError(e.message); }
  };
  useEffect(() => {
    mounted.current = true; refresh(); inputs();
    const poll = setInterval(refresh, 3000);
    window.addEventListener("speech-heard", refresh);
    return () => {
      mounted.current = false; generation.current++; queue.current = [];
      capture.current?.cancel(); request.current?.abort();
      for (const url of recordings.current.values()) URL.revokeObjectURL(url);
      recordings.current.clear();
      clearInterval(poll); window.removeEventListener("speech-heard", refresh);
    };
  }, [refresh]);

  const pump = async (session, role) => {
    if (running.current) return;
    running.current = true;
    if (mounted.current) setProcessing(true);
    try {
      while (queue.current.length && session === generation.current) {
        const segment = queue.current.shift();
        if (mounted.current) setQueued(queue.current.length);
        if (Date.now() / 1000 - segment.heardAt > 45) {
          if (mounted.current) { setDropped((n) => n + 1); setError("A radio segment became stale and was skipped. Check transcription latency."); }
          continue;
        }
        request.current = new AbortController();
        const timeout = setTimeout(() => request.current?.abort(), 45000);
        try {
          const result = await hearAudio(segment.blob, segment.complete ? role : "unknown", {
            live: true, heardAt: segment.heardAt, signal: request.current.signal,
          });
          if (session === generation.current && mounted.current) {
            if (result.transcriptionId) {
              recordings.current.set(result.transcriptionId, URL.createObjectURL(segment.blob));
              while (recordings.current.size > 20) {
                const [oldest, url] = recordings.current.entries().next().value;
                URL.revokeObjectURL(url); recordings.current.delete(oldest);
              }
              setAudioUrls(Object.fromEntries(recordings.current));
            }
            window.dispatchEvent(new Event("speech-heard")); await refresh();
          }
        } catch (e) {
          if (session === generation.current && mounted.current) {
            setDropped((n) => n + 1); setError(`Radio segment failed: ${e.message}`);
          }
        } finally { clearTimeout(timeout); }
      }
    } finally {
      running.current = false;
      if (mounted.current && session === generation.current) setProcessing(false);
    }
  };
  const stop = () => {
    generation.current++; capture.current?.cancel(); capture.current = null;
    request.current?.abort(); queue.current = [];
    setQueued(0); setListening(false); setProcessing(false); setLevel({ rms: 0, active: false });
  };
  const start = async () => {
    if (starting || listening || running.current) return;
    setStarting(true); setError(""); setDropped(0);
    const session = ++generation.current;
    try {
      const feed = await startRadioCapture({ source, deviceId: device, threshold: 10 ** (threshold / 20),
        onLevel: (state) => { if (mounted.current && session === generation.current) setLevel(state); },
        onEnded: () => { if (mounted.current && session === generation.current) { stop(); setError("The radio audio source disconnected. Reconnect it to resume listening."); } },
        onSegment: (segment) => {
          if (session !== generation.current || !mounted.current) return;
          if (queue.current.length >= 6) { setDropped((n) => n + 1); setError("Transcription is behind the radio. A segment was skipped; check channel load."); return; }
          queue.current.push(segment); setQueued(queue.current.length); pump(session, channelRole);
        },
      });
      if (!mounted.current || session !== generation.current) { feed.cancel(); return; }
      capture.current = feed; setSourceLabel(feed.label); setListening(true); await inputs();
    } catch (e) { if (mounted.current) setError(`Radio input unavailable: ${e.message}`); }
    finally { if (mounted.current) setStarting(false); }
  };
  const submitReview = async () => {
    setReviewing(true); setError("");
    try {
      await reviewRadioTransmission(review.id, review.text, review.role);
      setReview(null); window.dispatchEvent(new Event("speech-heard")); await refresh();
    } catch (e) { setError(e.message); }
    finally { setReviewing(false); }
  };
  const active = Object.entries(conversation.inForce || {});
  return <section id="live-radio-monitor" className="panel shrink-0 overflow-hidden scroll-mt-24" aria-label="Live radio monitoring" style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)" }}>
    <header className="p-3 flex items-center justify-between gap-3 border-b border-[var(--border-default)]" style={field}>
      <h3 className="font-display text-xs tracking-widest">LIVE RADIO MONITOR</h3>
      <span className="text-[10px]" style={{ color: listening ? "var(--green)" : "var(--amber)" }}>{listening ? "LISTENING" : "STOPPED"}</span>
    </header>
    <div className="p-3 space-y-3 text-xs">
      <p style={{ color: "var(--text-secondary)" }}>Listen to pilot and ATCO radio. Each transmission is transcribed and matched to visible aircraft; usable clearance details feed trajectory and conflict assessment.</p>
      <label className="block">Radio audio source
        <select aria-label="Radio audio source" value={source} disabled={listening || starting} onChange={(e) => setSource(e.target.value)} className={`${control} w-full mt-1`} style={field}>
          <option value="device">Receiver / line-in / virtual audio cable</option><option value="shared">Audio from a browser tab or shared screen</option>
        </select>
      </label>
      {source === "device" ? <label className="block">Audio input
        <select aria-label="Radio input device" value={device} disabled={listening || starting} onChange={(e) => setDevice(e.target.value)} className={`${control} w-full mt-1`} style={field}>
          <option value="">Default audio input</option>{devices.filter((d) => d.deviceId).map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Audio input ${i + 1}`}</option>)}
        </select>
      </label> : <p className="text-[10px]">Select the tab or screen carrying the radio and enable Share audio. Only audio is processed.</p>}
      <label className="block">Channel type
        <select aria-label="Radio channel type" value={channelRole} disabled={listening || starting} onChange={(e) => setChannelRole(e.target.value)} className={`${control} w-full mt-1`} style={field}>
          <option value="auto">Mixed pilot + ATCO radio</option><option value="atco">Known ATCO-only channel</option><option value="pilot">Known pilot-only channel</option>
        </select>
      </label>
      <label className="block">Transmission threshold: {threshold} dB
        <input aria-label="Transmission threshold" type="range" min="-60" max="-15" value={threshold} className="w-full" onChange={(e) => { const n = Number(e.target.value); setThreshold(n); capture.current?.setThreshold(10 ** (n / 20)); }} />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button className={control} disabled={starting || (!listening && (!status?.installed || !!connectionError))} onClick={listening ? stop : start}
          style={{ background: listening ? "var(--amber)" : "var(--teal)", color: "var(--bg-base)" }}>{starting ? "Connecting audio…" : listening ? "Stop listening" : "Start listening"}</button>
        <span>{processing ? "Transcribing" : level.active ? "Receiving transmission" : listening ? "Waiting for speech" : status?.loaded ? "Whisper ready" : status?.installed ? "Whisper warming up" : "Speech model unavailable"} · {queued} queued</span>
      </div>
      <meter aria-label="Radio input level" min="0" max="1" value={Math.min(1, level.rms * 5)} className="w-full" />
      {sourceLabel && <p className="text-[10px]">Input: {sourceLabel}</p>}
      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Mixed-channel speaker hints can be uncertain. Such intent waits for review. Requests and readbacks never create new clearances.</p>
      {conversation.surveillanceSource !== "live" && <p style={{ color: "var(--amber)" }}>Surveillance: {conversation.surveillanceSource || "unavailable"}. Live radio will be transcribed, but cannot change replay aircraft predictions.</p>}
      <div role="status" aria-live="polite">{dropped > 0 && `${dropped} segments skipped or failed. Radio coverage is incomplete.`}</div>
      {error && <p role="alert" style={{ color: "var(--amber)" }}>{error}</p>}
      {connectionError && <p role="alert" style={{ color: "var(--amber)" }}>Radio service unavailable: {connectionError}</p>}
      {review && <div className="p-2 space-y-2 border border-[var(--amber)]" aria-label="Review captured transmission">
        <p>Review captured transmission #{review.id}</p>
        <textarea aria-label="Correct radio transcript" maxLength={2000} rows={3} value={review.text} disabled={reviewing} className={`${control} w-full`} style={field} onChange={(e) => setReview({ ...review, text: e.target.value })} />
        <select aria-label="Reviewed speaker role" value={review.role} disabled={reviewing} onChange={(e) => setReview({ ...review, role: e.target.value })} className={control} style={field}>
          <option value="">Identify speaker…</option><option value="atco">ATCO instruction</option><option value="pilot">Pilot request / readback / report</option>
        </select>
        <div className="flex gap-2"><button className={control} disabled={reviewing || !review.role || !review.text.trim()} onClick={submitReview}>Use reviewed information</button><button className={control} disabled={reviewing} onClick={() => setReview(null)}>Cancel</button></div>
      </div>}
      <div className="space-y-2 border-t border-[var(--border-default)] pt-3">
        <h4 className="font-display tracking-widest text-[10px]">TRAJECTORY INTENT</h4>
        {!active.length && <p style={{ color: "var(--text-muted)" }}>No active clearances extracted.</p>}
        {active.map(([icao, cs]) => <div key={icao} className="p-2 rounded border border-[var(--border-default)]" style={field}>
          <b>{cs[0].callsign}</b>
          {cs.map((c) => {
            const effect = conversation.prediction?.effects?.[icao]?.find((r) => r.clearance?.issued_at === c.issued_at && r.clearance?.action === c.action);
            return <p key={c.action}>{instruction(c)}<span className="block text-[10px]" style={{ color: "var(--text-muted)" }}>{effect ? `${effect.applied ? "Prediction updated" : "Prediction unchanged"}: ${effect.reason}` : ["SPEED", "DIRECT"].includes(c.action) ? "Recorded; trajectory adjustment not implemented for this action" : "Awaiting an eligible trajectory assessment"}</span></p>;
          })}
          <p className="mt-1" style={{ color: conversation.readbacks?.[cs[0].callsign]?.status === "confirmed" ? "var(--green)" : "var(--amber)" }}>{conversation.readbacks?.[cs[0].callsign]?.reason || "Awaiting pilot readback"}</p>
        </div>)}
      </div>
      <div className="space-y-2 max-h-96 overflow-y-auto" aria-label="Live radio transcript">
        <h4 className="font-display tracking-widest text-[10px]">RADIO TRANSCRIPT</h4>
        {!conversation.messages.length && <p style={{ color: "var(--text-muted)" }}>Captured transmissions will appear here.</p>}
        {conversation.messages.map((m, i) => <article key={m.transcriptionId || `${m.recordedAt}-${i}`} className="p-2 rounded border border-[var(--border-default)]" style={field}>
          <div className="flex justify-between gap-2"><b>{m.role.toUpperCase()} {m.callsignMatch?.code || "· unmatched"}</b><time>{new Date((m.heardAt || m.recordedAt) * 1000).toLocaleTimeString()}</time></div>
          <p className="my-1">“{m.transcript}”</p>
          {audioUrls[m.transcriptionId] && (!listening ? <audio controls preload="none" src={audioUrls[m.transcriptionId]} className="w-full h-8" aria-label="Captured radio transmission" /> : <p className="text-[10px]">Stop listening to replay this captured transmission.</p>)}
          <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{m.roleSource === "phrase-hint" ? `Role hint: ${m.roleReason}` : m.roleSource === "reviewed" ? "Reviewed transcript" : m.roleSource === "unresolved" ? "Incomplete transmission; role unresolved" : "Role from channel label"}{m.asrConfidence != null ? ` · ASR ${Math.round(m.asrConfidence * 100)}%` : ""}</p>
          {m.extracted?.all_actions?.map((a, n) => <p key={n}>Extracted: {instruction(a)}</p>)}
          {m.clearances?.map((c, n) => <p key={n} style={{ color: c.applied ? "var(--green)" : "var(--amber)" }}>{c.applied ? c.effect : c.problems.join("; ")}</p>)}
          {m.reason && <p style={{ color: m.readback?.status === "confirmed" ? "var(--green)" : "var(--amber)" }}>{m.reason}</p>}
          {m.readback?.items?.filter((item) => !item.matches).map((item, n) => <p key={n}>Heard {instruction(item.heard)} · expected {item.expected ? instruction(item.expected) : "no matching ATCO instruction"}</p>)}
          <button className="underline mt-1" disabled={reviewing} onClick={() => setReview({ id: m.transcriptionId, text: m.transcript, role: m.role === "unknown" ? "" : m.role })}>Review captured information</button>
        </article>)}
      </div>
    </div>
  </section>;
}
