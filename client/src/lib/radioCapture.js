import { RadioSegmenter } from "./radioSegmenter";
import { encodeWav } from "./micRecorder";
import radioWorkletUrl from "./radioAudioWorklet.js?url&no-inline";

export async function listRadioInputs() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
}

// Listen to an existing radio channel. No audio is played back or transmitted to pilots.
export async function startRadioCapture({ source = "device", deviceId = "", threshold, onSegment, onLevel, onEnded }) {
  if (!navigator.mediaDevices) throw new Error("Audio capture requires localhost or HTTPS.");
  let stream, context, node, input, mute;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    if (node) { node.port.onmessage = null; node.disconnect(); }
    input?.disconnect(); mute?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    context?.close();
  };
  try {
    if (source === "shared") {
      if (!navigator.mediaDevices.getDisplayMedia) throw new Error("Shared tab audio is unavailable in this browser. Use a radio audio input or virtual cable.");
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true, systemAudio: "include" });
    } else {
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : {}), channelCount: 1,
        echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      }, video: false });
    }
    if (!stream.getAudioTracks().length) throw new Error("No audio was shared. Select a source with Share audio enabled, or use a radio audio input.");
    context = new AudioContext();
    if (!context.audioWorklet) throw new Error("This browser does not support live audio processing.");
    await context.resume();
    await context.audioWorklet.addModule(radioWorkletUrl);
    const epoch = Date.now() / 1000 - context.currentTime;
    const segmenter = new RadioSegmenter(context.sampleRate, { threshold, onSegment: ({ chunks, ...metadata }) => {
      // Preserve the input rate; the backend uses scipy's filtered polyphase resampler.
      const samples = new Float32Array(chunks.reduce((n, chunk) => n + chunk.length, 0));
      let at = 0;
      for (const chunk of chunks) { samples.set(chunk, at); at += chunk.length; }
      if (!closed) onSegment({ ...metadata, blob: encodeWav(samples, context.sampleRate) });
    } });
    input = context.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    node = new AudioWorkletNode(context, "radio-audio");
    mute = context.createGain(); mute.gain.value = 0;
    let lastLevel = 0;
    node.port.onmessage = ({ data }) => {
      if (closed) return;
      const state = segmenter.push(data.samples, epoch + data.endTime);
      if (Date.now() - lastLevel > 100) { onLevel?.(state); lastLevel = Date.now(); }
    };
    input.connect(node); node.connect(mute); mute.connect(context.destination);
    context.addEventListener("statechange", () => {
      if (!closed && context.state !== "running") { close(); onEnded?.(); }
    });
    for (const track of stream.getTracks()) track.addEventListener("ended", () => {
      if (!closed) { segmenter.flush(false); close(); onEnded?.(); }
    });
    return { stop: () => { segmenter.flush(false); close(); }, cancel: close,
      setThreshold: (value) => { segmenter.threshold = value; },
      label: stream.getAudioTracks()[0].label || "Radio audio" };
  } catch (error) { close(); throw error; }
}
