import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import LiveRadioConsole from "@/components/LiveRadioConsole";
import { getSpeechClips, hearClip, speechClipAudioUrl } from "@/lib/api";

export default function RadioDemoPage() {
  const [clips, setClips] = useState([]);
  const [role, setRole] = useState("auto");
  const [cached, setCached] = useState(false);
  const [busy, setBusy] = useState(null);
  const [results, setResults] = useState({});
  const [error, setError] = useState("");
  useEffect(() => {
    getSpeechClips().then((data) => setClips(data.clips || [])).catch((e) => setError(e.message));
  }, []);
  const hear = async (clip) => {
    setBusy(clip.id); setError("");
    try {
      const result = await hearClip(clip.id, cached, role);
      setResults((prev) => ({ ...prev, [clip.id]: result }));
      window.dispatchEvent(new Event("speech-heard"));
    } catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };
  return <div className="min-h-screen" style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}>
    <header className="flex flex-wrap items-center gap-5 px-6 py-4 border-b border-[var(--border-default)]" style={{ background: "var(--bg-panel-alt)" }}>
      <Link to="/" className="text-xs underline" style={{ color: "var(--teal)" }}>← Dashboard</Link>
      <h1 className="font-display text-sm tracking-widest">RADIO WORKSPACE</h1>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Live radio → Transcript → Extracted intent → Predictions</p>
    </header>
    <main className="grid items-start gap-6 p-6 max-w-7xl mx-auto lg:grid-cols-[1.2fr_1fr]">
      <LiveRadioConsole />
      <section className="panel p-4 space-y-4 border border-[var(--border-default)]">
        <h2 className="font-display text-xs tracking-widest">SAMPLE RECORDINGS</h2>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Choose who is speaking before processing a recording. Matching ATCO instructions affect visible aircraft; pilot speech is checked as a request or readback.</p>
        <div className="flex flex-wrap gap-3 text-xs">
          <label>Speaker <select aria-label="Recording speaker" value={role} disabled={!!busy} onChange={(e) => setRole(e.target.value)} className="border rounded p-2 ml-1" style={{ background: "var(--bg-panel-alt)" }}>
            <option value="auto">Mixed / unknown</option><option value="atco">Known ATCO recording</option><option value="pilot">Known pilot recording</option>
          </select></label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={cached} disabled={!!busy} onChange={(e) => setCached(e.target.checked)} />Use cached transcript</label>
        </div>
        {error && <p role="alert" className="text-xs" style={{ color: "var(--amber)" }}>{error}</p>}
        {!clips.length && <p className="text-xs">No sample recordings available.</p>}
        {clips.map((clip) => <article key={clip.id} className="p-3 space-y-2 border rounded border-[var(--border-default)] text-xs">
          <div className="flex justify-between gap-2"><b>{clip.label || clip.id}</b><span style={{ color: "var(--amber)" }}>{clip.synthetic ? "Synthetic" : "Recorded audio"}</span></div>
          <p style={{ color: "var(--text-muted)" }}>{clip.source}</p>
          <audio controls preload="none" src={speechClipAudioUrl(clip.id)} className="w-full h-9" />
          <button type="button" disabled={!!busy} onClick={() => hear(clip)} className="px-3 py-2 rounded disabled:opacity-40" style={{ background: "var(--teal)", color: "var(--bg-base)" }}>
            {busy === clip.id ? "Recognising…" : `Process as ${role.toUpperCase()}`}
          </button>
          {results[clip.id] && <div aria-live="polite" className="space-y-1">
            <p>“{results[clip.id].transcript}”</p>
            <p>Aircraft: {results[clip.id].callsignMatch?.code || "unmatched"}</p>
            {results[clip.id].clearances?.map((c, i) => <p key={i}>{c.clearance.action} {c.clearance.value || c.clearance.fix}: {c.applied ? c.effect : c.problems.join("; ")}</p>)}
            {results[clip.id].reason && <p style={{ color: "var(--amber)" }}>{results[clip.id].reason}</p>}
          </div>}
        </article>)}
      </section>
    </main>
  </div>;
}
