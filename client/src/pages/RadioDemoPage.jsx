import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mic, Play, Square, RotateCcw } from "lucide-react";
import { getSpeechClips, getSpeechStatus, hearAudio, hearClip, speechClipAudioUrl } from "@/lib/api";
import { startRecording } from "@/lib/micRecorder";
import { logAudit } from "@/lib/siteLogger";

// Full-screen radio demo: the audience HEARS a transmission first, then READS what the system took
// out of it, one step at a time. Same backend chain as the dashboard's radio panel
// (POST /api/speech/hear); nothing is transmitted and a heard instruction only reshapes that
// aircraft's predicted paths.

const shortModel = (id) => String(id || "").split(/[\\/]/).filter(Boolean).pop() || "";

const fmtInstruction = (x) => {
  if (!x || !x.action) return "—";
  if (x.action === "DIRECT") return `DIRECT ${String(x.fix || "").toUpperCase()}`;
  if (x.action === "TURN") return `TURN HEADING ${String(Math.round(x.value)).padStart(3, "0")}`;
  if (x.action === "SPEED") return `SPEED ${Math.round(x.value)} KT`;
  const ft = Math.round(x.value);
  return `${x.action} ${ft >= 10000 ? `FL${String(Math.round(ft / 100)).padStart(3, "0")}` : `${ft.toLocaleString()} FT`}`;
};

const sameInstruction = (a, b) =>
  a?.action && b?.action && a.action === b.action && Math.abs(Number(a.value || 0) - Number(b.value || 0)) < 1;

function Row({ label, shown, children, tone }) {
  return (
    <div className="flex gap-4 items-baseline transition-opacity duration-500" style={{ opacity: shown ? 1 : 0 }}>
      <span className="font-display text-[11px] tracking-[0.2em] w-36 shrink-0" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="text-[18px] leading-snug" style={{ color: tone || "var(--text-primary)" }}>{children}</span>
    </div>
  );
}

// Reveals the transcript word by word, then each later step.
function Reveal({ result, truth }) {
  const words = String(result?.transcript || "").split(/\s+/).filter(Boolean);
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    if (!result || result.error) return undefined;
    const timer = setInterval(() => setN((k) => k + 1), 160);
    return () => clearInterval(timer);
  }, [result]);
  if (!result) return null;
  if (result.error) return <p className="text-[16px]" style={{ color: "var(--amber)" }}>{result.error}</p>;

  const step = n - words.length;           // steps after the transcript, one every 160 ms x 4
  const m = result.callsignMatch || {};
  const c = result.clearance;
  const heardRight = truth && sameInstruction(result.extracted, truth);
  return (
    <div className="space-y-4">
      <div className="p-5" style={{ border: "1px solid var(--border-default)", background: "var(--bg-panel-alt)" }}>
        <p className="font-display text-[11px] tracking-[0.2em] mb-2" style={{ color: "var(--text-muted)" }}>WHAT THE MODEL HEARD</p>
        <p className="text-[28px] leading-snug" style={{ color: "var(--text-primary)" }}>
          “{words.slice(0, n).join(" ")}{n < words.length ? <span className="animate-pulse">▍</span> : "”"}
        </p>
        <p className="text-[12px] mt-2 transition-opacity duration-500" style={{ color: "var(--text-muted)", opacity: step >= 0 ? 1 : 0 }}>
          {shortModel(result.modelId)} · {result.asrConfidence != null
            ? `recognised live in ${result.seconds} s · recogniser confidence ${(result.asrConfidence * 100).toFixed(0)}%`
            : "pre-computed transcript"}
        </p>
      </div>
      <div className="p-5 space-y-3" style={{ border: "1px solid var(--border-default)" }}>
        <Row label="INSTRUCTION" shown={step >= 4}>
          {fmtInstruction(result.extracted)}
          <span className="text-[13px] ml-3" style={{ color: "var(--text-muted)" }}>callsign heard “{result.extracted?.callsign_spoken || "—"}”</span>
        </Row>
        <Row label="AIRCRAFT" shown={step >= 8} tone={m.code ? "var(--text-primary)" : "var(--amber)"}>
          {m.code ? `${m.code}` : "no aircraft on screen matched"}
          <span className="text-[13px] ml-3" style={{ color: "var(--text-muted)" }}>
            {m.code ? `match ${m.score}/100 against the ${m.listSize} aircraft on screen` : `checked ${m.listSize} aircraft on screen`}
          </span>
        </Row>
        <Row label="DECISION" shown={step >= 12} tone={c?.ok ? "var(--green)" : "var(--amber)"}>
          {c ? (c.ok ? `USED — ${c.effect}` : `RECORDED, NOT USED — ${(c.problems || []).join("; ")}`) : (result.reason || "—")}
        </Row>
      </div>
      {truth && (
        <div className="p-5 transition-opacity duration-500" style={{ border: "1px dashed var(--border-default)", opacity: step >= 16 ? 1 : 0 }}>
          <Row label="ACTUALLY SAID" shown>
            {truth.callsign} · {fmtInstruction(truth)}
            <span className="text-[14px] ml-3" style={{ color: heardRight ? "var(--green)" : "var(--amber)" }}>
              {heardRight ? "instruction heard correctly" : "instruction differs"}
              {m.code ? (m.code === truth.callsign ? " · right aircraft" : " · different aircraft matched") : ""}
            </span>
          </Row>
        </div>
      )}
    </div>
  );
}

export default function RadioDemoPage() {
  const [status, setStatus] = useState(null);
  const [clips, setClips] = useState([]);
  const [selected, setSelected] = useState(null);
  const [live, setLive] = useState(true);
  const [phase, setPhase] = useState("idle");          // idle | playing | recognising | done | recording
  const [result, setResult] = useState(null);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [error, setError] = useState(null);
  const audioRef = useRef(null);
  const recorderRef = useRef(null);

  const load = useCallback(() => {
    getSpeechStatus().then((s) => { setStatus(s); setError(null); if (!s.installed) setLive(false); })
      .catch((e) => setError(`Backend unreachable (${e.message}) — retrying…`));
    getSpeechClips().then((d) => {
      setClips(d.clips || []);
      setSelected((cur) => cur || (d.clips || [])[0] || null);
    }).catch(() => {});
  }, []);
  useEffect(() => { load(); logAudit("radio:demo", "Radio demo page opened", {}); }, [load]);
  useEffect(() => {
    if (status && !error) return undefined;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [status, error, load]);

  const recognise = async (clip) => {
    setPhase("recognising");
    try {
      let r;
      try {
        r = await hearClip(clip.id, !live);
      } catch (e) {
        if (!live) throw e;
        r = await hearClip(clip.id, true);           // live failed: fall back to the pre-computed text
      }
      setResult(r);
    } catch (e) {
      setResult({ error: e.message });
    }
    setPhase("done");
  };

  const pick = (clip) => {
    audioRef.current?.pause();
    setSelected(clip); setResult(null); setRecordingUrl(null); setPhase("idle");
  };

  const play = () => {
    if (!selected || !audioRef.current) return;
    setResult(null); setRecordingUrl(null); setPhase("playing");
    logAudit("radio:demo", "Played a radio clip to the audience", { clip: selected.id, live });
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => setPhase("idle"));
  };

  const toggleMic = async () => {
    if (phase === "recording") {
      const blob = await recorderRef.current.stop();
      recorderRef.current = null;
      setRecordingUrl(URL.createObjectURL(blob));
      setPhase("recognising");
      try { setResult(await hearAudio(blob)); } catch (e) { setResult({ error: e.message }); }
      setPhase("done");
      return;
    }
    try {
      audioRef.current?.pause();
      setSelected(null); setResult(null); setRecordingUrl(null);
      recorderRef.current = await startRecording();
      setPhase("recording");
    } catch (e) {
      setResult({ error: `Microphone unavailable: ${e.message}` }); setPhase("done");
    }
  };

  return (
    <div className="min-h-screen" style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", background: "var(--bg-base)", color: "var(--text-primary)" }}>
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b px-6 py-3"
        style={{ background: "var(--bg-panel-alt)", borderColor: "var(--border-default)" }}>
        <div className="flex items-center gap-4">
          <Link to="/" className="flex items-center gap-1 text-[12px]" style={{ color: "var(--text-secondary)" }}>
            <ArrowLeft size={14} /> Dashboard
          </Link>
          <h1 className="font-display text-[14px] tracking-[0.25em]">RADIO — HEAR IT, THEN READ IT</h1>
        </div>
        <div className="flex items-center gap-4 text-[12px]" style={{ color: "var(--text-secondary)" }}>
          <span>
            Speech model: <b>{status?.installed ? shortModel(status.modelId) : status ? "none installed" : "…"}</b>
            {status?.device ? ` · running on ${status.device === "cuda" ? "GPU" : "CPU"}` : ""}
          </span>
          <label className="flex items-center gap-1.5 cursor-pointer" title="Live runs the model on the clip now; pre-computed uses the transcript made earlier with the same model">
            <input type="checkbox" checked={live} disabled={!status?.installed} onChange={(e) => setLive(e.target.checked)} />
            recognise live
          </label>
        </div>
      </header>

      <main className="grid gap-6 p-6 lg:grid-cols-[340px_1fr]">
        <aside className="space-y-2">
          <p className="font-display text-[11px] tracking-[0.2em] mb-1" style={{ color: "var(--text-muted)" }}>TRANSMISSIONS</p>
          {error && <p className="text-[12px]" style={{ color: "var(--amber)" }}>{error}</p>}
          {clips.map((clip) => (
            <button key={clip.id} type="button" onClick={() => pick(clip)} className="w-full text-left p-3"
              style={{ border: `1px solid ${selected?.id === clip.id ? "var(--teal)" : "var(--border-default)"}`,
                       background: selected?.id === clip.id ? "var(--bg-panel-alt)" : "transparent" }}>
              <span className="font-display text-[9px] tracking-widest px-1.5 py-0.5" style={{ border: "1px solid var(--amber)", color: "var(--amber)" }}>
                {clip.synthetic ? "SYNTHETIC VOICE" : "REAL RECORDING"}
              </span>
              <p className="text-[13px] mt-1.5">{clip.truth?.callsign} · {fmtInstruction(clip.truth)}</p>
            </button>
          ))}
          <button type="button" onClick={toggleMic} className="w-full p-3 flex items-center justify-center gap-2 font-display text-[11px] tracking-widest mt-4"
            style={{ border: "1px solid var(--teal)", color: phase === "recording" ? "#050508" : "var(--teal)",
                     background: phase === "recording" ? "var(--red, #d33)" : "transparent" }}>
            {phase === "recording" ? <><Square size={14} /> STOP AND RECOGNISE</> : <><Mic size={14} /> SPEAK YOUR OWN</>}
          </button>
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Try: “IFLY zero eight six, descend flight level three three zero”. Up to 30 s.
          </p>
        </aside>

        <section className="space-y-5">
          {selected && (
            <div className="p-5" style={{ border: "1px solid var(--border-default)" }}>
              <p className="text-[13px]" style={{ color: "var(--text-muted)" }}>{selected.source}</p>
              <div className="flex items-center gap-4 mt-4">
                <button type="button" onClick={play} disabled={phase === "playing" || phase === "recognising"}
                  className="flex items-center gap-2 px-6 py-3 font-display text-[13px] tracking-widest disabled:opacity-50"
                  style={{ background: "var(--teal)", color: "#050508" }}>
                  {result ? <RotateCcw size={16} /> : <Play size={16} />}
                  {phase === "playing" ? "PLAYING…" : phase === "recognising" ? "RECOGNISING…" : result ? "PLAY AGAIN" : "PLAY TRANSMISSION"}
                </button>
                <button type="button" onClick={() => recognise(selected)} disabled={phase === "playing" || phase === "recognising"}
                  className="px-4 py-3 font-display text-[11px] tracking-widest disabled:opacity-50"
                  style={{ border: "1px solid var(--teal)", color: "var(--teal)" }}>
                  SHOW TEXT NOW
                </button>
                <audio ref={audioRef} src={speechClipAudioUrl(selected.id)} preload="auto" controls className="h-10 flex-1"
                  onEnded={() => { if (phase === "playing") recognise(selected); }} />
              </div>
              <p className="text-[11px] mt-2" style={{ color: "var(--text-muted)" }}>
                The text appears when the transmission finishes.
              </p>
            </div>
          )}
          {recordingUrl && (
            <div className="p-5" style={{ border: "1px solid var(--border-default)" }}>
              <p className="font-display text-[11px] tracking-[0.2em] mb-2" style={{ color: "var(--text-muted)" }}>YOUR RECORDING</p>
              <audio src={recordingUrl} controls className="w-full h-10" />
            </div>
          )}
          {phase === "recording" && <p className="text-[22px] animate-pulse" style={{ color: "var(--red, #d33)" }}>● Recording — speak now</p>}
          {phase === "playing" && <p className="text-[22px] animate-pulse" style={{ color: "var(--teal)" }}>Listen…</p>}
          {phase === "recognising" && <p className="text-[22px] animate-pulse" style={{ color: "var(--teal)" }}>Recognising…</p>}
          <Reveal result={result} truth={selected?.truth} />
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Nothing is transmitted. A heard instruction is used only when the system is at least 85% sure of it, and then it only
            reshapes that aircraft's predicted paths; it can never switch an alarm off. Every step is recorded in the audit log.
          </p>
        </section>
      </main>
    </div>
  );
}
