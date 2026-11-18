import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';

async function requestPreview(path, params, signal) {
  const response = await fetch(`${API_BASE_URL}/api/examiner/resolution-preview${path}?${new URLSearchParams(params)}`, { signal, cache: 'no-store' });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(problem.detail || 'Pilot command preview is unavailable.');
  }
  return response;
}

export default function PilotCommandPreview({ pair, manoeuvre }) {
  const { aircraft, kind, magnitude, unit } = manoeuvre;
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [loadingAudio, setLoadingAudio] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState('');
  const player = useRef(null);
  const request = useRef(null);
  const audioUrl = useRef('');

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    async function load() {
      try {
        const response = await requestPreview('', { pair }, controller.signal);
        const { session, options } = await response.json();
        const option = options.find(({ manoeuvre: offered }) => offered.aircraft === aircraft &&
          offered.kind.toUpperCase() === kind && offered.magnitude === magnitude && offered.unit === unit);
        if (controller.signal.aborted) return;
        if (option) setPreview({ session, command: option.text });
        else setError('The resolution changed. Select a current option to preview its command.');
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure.message);
      }
    }
    load();
    return () => {
      controller.abort();
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
    };
  }, [pair, aircraft, kind, magnitude, unit]);

  async function listen() {
    setError('');
    setLoadingAudio(true);
    const signal = request.current.signal;
    try {
      if (!audioUrl.current) {
        const response = await requestPreview('/audio', { ...preview, pair }, signal);
        const blob = await response.blob();
        if (signal.aborted) return;
        audioUrl.current = URL.createObjectURL(blob);
        player.current.src = audioUrl.current;
        setDownloadUrl(audioUrl.current);
      }
      player.current.currentTime = 0;
      await player.current.play();
    } catch (failure) {
      if (!signal.aborted) setError(failure.name === 'NotAllowedError'
        ? 'Press play on the audio player to hear the command.' : failure.message);
    } finally {
      if (!signal.aborted) setLoadingAudio(false);
    }
  }

  return <section aria-label="Pilot command preview" className="mx-5 my-3 rounded border p-3 space-y-2"
    style={{ borderColor: 'var(--border-default)', background: 'var(--bg-panel-alt)' }}>
    <h3 className="font-medium">Pilot command preview</h3>
    {preview ? <p>{preview.command}</p> : !error && <p role="status">Preparing command…</p>}
    {preview && <button type="button" className="action-primary" disabled={loadingAudio} onClick={listen}>
      {loadingAudio ? 'Preparing audio…' : 'Listen to command'}
    </button>}
    <audio ref={player} controls hidden={!downloadUrl} className="max-w-full" aria-label="Pilot command audio" />
    {downloadUrl && <a className="block underline" href={downloadUrl} download="pilot-command-preview.wav">Download preview WAV</a>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
