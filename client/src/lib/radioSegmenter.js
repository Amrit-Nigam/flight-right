// Energy gating only locates candidate transmissions; the backend performs speech VAD.
export class RadioSegmenter {
  constructor(rate, { threshold = 0.012, silenceSeconds = 0.8, maxSeconds = 25, onSegment }) {
    this.rate = rate;
    this.threshold = threshold;
    this.silenceLimit = silenceSeconds * rate;
    this.maxSamples = maxSeconds * rate;
    this.preLimit = Math.round(0.25 * rate);
    this.onSegment = onSegment;
    this.pre = []; this.preSamples = 0;
    this.continuation = false;
    this.reset();
  }
  reset() { this.parts = []; this.total = 0; this.voiced = 0; this.quiet = 0; this.startedAt = null; }
  push(samples, now = Date.now() / 1000) {
    let power = 0;
    for (const x of samples) power += x * x;
    const rms = Math.sqrt(power / Math.max(1, samples.length));
    const voiced = rms >= this.threshold;
    if (!this.parts.length && !voiced) {
      this.pre.push(samples); this.preSamples += samples.length;
      while (this.preSamples > this.preLimit && this.pre.length > 1) this.preSamples -= this.pre.shift().length;
      return { rms, active: false };
    }
    if (!this.parts.length) {
      this.parts = this.pre; this.total = this.preSamples;
      this.startedAt = now - (this.preSamples + samples.length) / this.rate;
      this.pre = []; this.preSamples = 0;
    }
    this.parts.push(samples); this.total += samples.length;
    this.voiced += voiced ? samples.length : 0;
    this.quiet = voiced ? 0 : this.quiet + samples.length;
    if (this.quiet >= this.silenceLimit || this.total >= this.maxSamples) this.flush(this.total < this.maxSamples);
    return { rms, active: this.parts.length > 0 };
  }
  flush(complete = true) {
    if (this.voiced >= this.rate * 0.2) this.onSegment({ chunks: this.parts, heardAt: this.startedAt, complete: complete && !this.continuation });
    this.continuation = !complete;
    this.reset();
  }
}
