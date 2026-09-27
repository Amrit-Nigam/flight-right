import { useCallback, useEffect, useState } from "react";
import { getSpeechClips, getSpeechStatus, getTranscriptions, hearClip, speechClipAudioUrl } from "@/lib/api";
import { logAudit } from "@/lib/siteLogger";

// A model is named by a Hugging Face id ("org/name") or a local directory, which on Windows uses
// backslashes; show only the last part either way.
const shortModel = (id) => String(id || "").split(/[\\/]/).filter(Boolean).pop() || "";

// The radio panel: speech -> transcript -> clearance -> the aircraft it is for.
//
// Every step is shown, because each one can fail on its own: the recogniser can mishear,
// the extractor can miss the instruction, the callsign can snap to the wrong aircraft, and
// the clearance door can refuse it. A single "applied" line would hide which one went wrong.
//
// The clips are labelled with where their audio came from. Real Mumbai ATC radio cannot be
// recorded legally (plan Phase 5), so the Mumbai demo clips are synthetic speech of real
// callsigns from the recordings -- demo only, never a reported number.

const fmtValue = (x) => {
  if (!x || !x.action) return "—";
  if (x.action === "DIRECT") return `DIRECT ${String(x.fix || "").toUpperCase()}`;
  if (x.action === "TURN") return `TURN HDG ${String(Math.round(x.value)).padStart(3, "0")}`;
  if (x.action === "SPEED") return `SPEED ${Math.round(x.value)} KT`;
  const ft = Math.round(x.value);
  return `${x.action} ${ft >= 10000 ? `FL${String(Math.round(ft / 100)).padStart(3, "0")}` : `${ft.toLocaleString()} FT`}`;
};

function Step({ label, children, tone }) {
  return (
    <div className="flex gap-2 items-baseline">
      <span className="font-display text-[9px] tracking-widest w-20 shrink-0" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="font-body text-[11px] leading-snug" style={{ color: tone || "var(--text-primary)" }}>{children}</span>
    </div>
  );
}

function Result({ r }) {
  if (!r) return null;
  if (r.error) return <p className="font-body text-[11px]" style={{ color: "var(--amber)" }}>{r.error}</p>;
  const c = r.clearance;
  const m = r.callsignMatch || {};
  return (
    <div className="mt-2 p-2 space-y-1" style={{ border: "1px solid var(--border-default)", background: "var(--bg-panel-alt)" }}>
      <Step label="HEARD">“{r.transcript}”</Step>
      <Step label="MODEL">{shortModel(r.modelId)} · {r.quantisation}{r.asrConfidence != null ? ` · recogniser confidence ${(r.asrConfidence * 100).toFixed(0)}%` : " · cached transcript"}</Step>
      <Step label="EXTRACTED">{fmtValue(r.extracted)} · callsign heard “{r.extracted?.callsign_spoken || "—"}”</Step>
      <Step label="AIRCRAFT" tone={m.code ? "var(--text-primary)" : "var(--amber)"}>
        {m.code ? `${m.code} (match ${m.score}, ${m.margin} ahead of the next of ${m.listSize} visible)` : `no visible aircraft matched (of ${m.listSize})`}
      </Step>
      <Step label="CLEARANCE" tone={c?.ok ? "var(--green)" : "var(--amber)"}>
        {c ? (c.ok ? `applied — ${c.effect}` : `recorded, not applied: ${(c.problems || []).join("; ")}`) : (r.reason || "—")}
      </Step>
    </div>
  );
}

export default function NLPCommsPanel() {
  const [status, setStatus] = useState(null);
  const [clips, setClips] = useState([]);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);

  const refresh = useCallback(() => {
    getSpeechStatus().then(setStatus).catch((e) => setError(e.message));
    getSpeechClips().then((d) => setClips(d.clips || [])).catch(() => {});
    getTranscriptions(8).then((d) => setHistory(d.transcriptions || [])).catch(() => {});
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    window.addEventListener("speech-heard", refresh);
    return () => window.removeEventListener("speech-heard", refresh);
  }, [refresh]);

  const hear = async (clip, cached) => {
    setBusy(clip.id);
    logAudit("radio:hear", "Controller ran the speech chain on a clip", { clip: clip.id, cached });
    try {
      const r = await hearClip(clip.id, cached);
      setResults((prev) => ({ ...prev, [clip.id]: r }));
    } catch (e) {
      setResults((prev) => ({ ...prev, [clip.id]: { error: e.message } }));
    } finally {
      setBusy(null);
      refresh();
    }
  };

  return (
    // shrink-0, not h-full: in the scrolling right-hand column h-full let this panel be squashed to
    // 2 px, hiding every clip and button (27 Sep demo run). Capped so the clip list scrolls inside.
    <div className="panel flex flex-col shrink-0 max-h-[640px] overflow-hidden" style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)" }}>
      <div className="py-2.5 px-4 flex items-center justify-between border-b border-[var(--border-default)]" style={{ background: "var(--bg-panel-alt)" }}>
        <h3 className="font-display text-[11px] tracking-[0.2em] text-[var(--text-secondary)] uppercase">
          Radio — speech to clearance
        </h3>
        <span className="font-display text-[9px] tracking-widest" style={{ color: status?.installed ? "var(--green)" : "var(--amber)" }}>
          {status?.installed ? shortModel(status.modelId) : "NO SPEECH MODEL"}
        </span>
      </div>

      <div className="px-4 py-1.5 font-body text-[10px]" style={{ color: "var(--text-muted)", background: "rgba(0,0,0,0.03)", borderBottom: "1px solid var(--border-default)" }}>
        Nothing is transmitted. A heard clearance only adjusts that aircraft's predicted paths, through the same checks as a typed one. Each clip says where its audio came from.
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3 no-scrollbar">
        {error && <p className="font-body text-[11px]" style={{ color: "var(--amber)" }}>Speech service unreachable: {error}</p>}
        {!error && clips.length === 0 && (
          <p className="font-body text-[11px]" style={{ color: "var(--text-muted)" }}>
            No demo clips installed. Generate them with <code>ml_pipeline/voice/demo_clips.py</code>.
          </p>
        )}
        {clips.map((clip) => (
          <div key={clip.id} className="p-2" style={{ border: "1px solid var(--border-default)" }}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-display text-[11px] tracking-wider" style={{ color: "var(--text-primary)" }}>{clip.label}</span>
              <span className="font-display text-[9px] px-1.5 py-0.5 shrink-0" style={{ border: "1px solid var(--amber)", color: "var(--amber)" }}>
                {clip.synthetic ? "SYNTHETIC VOICE" : "RECORDED"}
              </span>
            </div>
            <p className="font-body text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>{clip.source}</p>
            <audio controls preload="none" src={speechClipAudioUrl(clip.id)} className="w-full mt-1.5 h-8" />
            <div className="flex gap-2 mt-1.5">
              <button type="button" disabled={busy === clip.id} onClick={() => hear(clip, true)}
                className="flex-1 py-1.5 font-display text-[10px] tracking-widest disabled:opacity-40"
                style={{ background: "var(--teal)", color: "#050508" }}>
                {busy === clip.id ? "LISTENING…" : "HEAR"}
              </button>
              {status?.installed && (
                <button type="button" disabled={busy === clip.id} onClick={() => hear(clip, false)}
                  className="py-1.5 px-2 font-display text-[10px] tracking-widest disabled:opacity-40"
                  style={{ border: "1px solid var(--teal)", color: "var(--teal)" }}
                  title="Run the recogniser now instead of using the pre-computed transcript">
                  TRANSCRIBE NOW
                </button>
              )}
            </div>
            <Result r={results[clip.id]} />
          </div>
        ))}

        {history.length > 0 && (
          <div>
            <p className="font-display text-[9px] tracking-widest mt-2 mb-1" style={{ color: "var(--text-muted)" }}>RECENT TRANSCRIPTIONS (APPEND-ONLY)</p>
            {history.map((h) => (
              <p key={h.id} className="font-body text-[10px] leading-snug" style={{ color: "var(--text-secondary)" }}>
                #{h.id} · {shortModel(h.model_id)} · “{h.transcript}”
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
