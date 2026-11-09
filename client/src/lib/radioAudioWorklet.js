/* global AudioWorkletProcessor, registerProcessor, currentFrame, sampleRate */
class RadioAudioProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.buffer = new Float32Array(2048); this.at = 0; }
  process(inputs) {
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i] || 0;
      this.buffer[this.at++] = mono / channels.length;
      if (this.at === this.buffer.length) {
        this.port.postMessage({ samples: this.buffer, endTime: (currentFrame + i + 1) / sampleRate }, [this.buffer.buffer]);
        this.buffer = new Float32Array(2048); this.at = 0;
      }
    }
    return true;
  }
}
registerProcessor("radio-audio", RadioAudioProcessor);
