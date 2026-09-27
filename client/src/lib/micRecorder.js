// Record the controller's microphone as 16 kHz mono WAV, the format the speech chain reads.
//
// The backend decodes audio with soundfile, which reads WAV but not the WebM/Opus that
// MediaRecorder produces in Chrome, so the samples are captured raw through the Web Audio API,
// resampled to 16 kHz and wrapped in a WAV header here. At most 30 s, the backend's limit.

const TARGET_RATE = 16000;
const MAX_SECONDS = 30;

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

function resample(chunks, fromRate) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const joined = new Float32Array(total);
  let at = 0;
  for (const c of chunks) { joined.set(c, at); at += c.length; }
  const ratio = fromRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(total / ratio));
  for (let i = 0; i < out.length; i++) {
    // average the source samples that fall in this output sample (a simple low-pass)
    const start = Math.floor(i * ratio), end = Math.min(total, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += joined[j];
    out[i] = end > start ? sum / (end - start) : joined[start] || 0;
  }
  return out;
}

/** Start recording; resolves to { stop(): Promise<Blob>, cancel() }. */
export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const node = context.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let seconds = 0;
  node.onaudioprocess = (event) => {
    if (seconds >= MAX_SECONDS) return;
    const data = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(data));
    seconds += data.length / context.sampleRate;
  };
  source.connect(node);
  node.connect(context.destination);
  const close = () => {
    node.disconnect(); source.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    context.close();
  };
  return {
    stop: async () => {
      const rate = context.sampleRate;
      close();
      return encodeWav(resample(chunks, rate), TARGET_RATE);
    },
    cancel: close,
  };
}
