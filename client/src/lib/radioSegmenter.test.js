import test from "node:test";
import assert from "node:assert/strict";
import { RadioSegmenter } from "./radioSegmenter.js";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const frame = (amplitude) => new Float32Array(100).fill(amplitude);
const feed = (segmenter, n, amplitude) => { for (let i = 0; i < n; i++) segmenter.push(frame(amplitude), 100 + i / 10); };

test("silence keeps bounded pre-roll without producing transmissions", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { onSegment: (s) => out.push(s) });
  feed(segmenter, 1000, 0);
  assert.equal(out.length, 0);
  assert.ok(segmenter.preSamples <= 300);
});
test("separate transmissions preserve leading audio and timestamp", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { onSegment: (s) => out.push(s) });
  feed(segmenter, 10, 0); feed(segmenter, 10, .1); feed(segmenter, 10, 0);
  feed(segmenter, 5, .1); feed(segmenter, 10, 0);
  assert.equal(out.length, 2);
  assert.equal(out[0].complete, true);
  assert.ok(out[0].chunks[0].every((x) => x === 0));
  assert.ok(Number.isFinite(out[0].heardAt));
});
test("short squelch clicks are ignored", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { onSegment: (s) => out.push(s) });
  feed(segmenter, 1, .8); feed(segmenter, 10, 0);
  assert.equal(out.length, 0);
});
test("long transmissions are bounded and marked incomplete", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { maxSeconds: 2, onSegment: (s) => out.push(s) });
  feed(segmenter, 20, .1);
  assert.equal(out.length, 1);
  assert.equal(out[0].complete, false);
  assert.equal(out[0].chunks.reduce((n, c) => n + c.length, 0), 2000);
});
test("capture interruption does not mark a partial transmission complete", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { onSegment: (s) => out.push(s) });
  feed(segmenter, 10, .1); segmenter.flush(false);
  assert.equal(out[0].complete, false);
});

test("a continuation after a forced split stays incomplete until silence", () => {
  const out = [];
  const segmenter = new RadioSegmenter(1000, { maxSeconds: 2, onSegment: (s) => out.push(s) });
  feed(segmenter, 25, .1); feed(segmenter, 10, 0);
  feed(segmenter, 5, .1); feed(segmenter, 10, 0);
  assert.equal(out[0].complete, false);
  assert.equal(out[1].complete, false);
  assert.equal(out[2].complete, true);
});

test("audio worklet downmixes channels and preserves the audio clock", () => {
  const messages = [];
  let Processor;
  const context = vm.createContext({ currentFrame: 0, sampleRate: 48000, Float32Array,
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: (value) => messages.push(value) }; } },
    registerProcessor: (name, implementation) => { assert.equal(name, "radio-audio"); Processor = implementation; },
  });
  vm.runInContext(readFileSync(new URL("./radioAudioWorklet.js", import.meta.url), "utf8"), context);
  const processor = new Processor();
  for (let i = 0; i < 32; i++) {
    context.currentFrame = i * 128;
    processor.process([[new Float32Array(128).fill(.5), new Float32Array(128).fill(-.1)]]);
  }
  assert.equal(messages.length, 2);
  assert.equal(messages[0].samples.length, 2048);
  assert.ok(Math.abs(messages[0].samples[0] - .2) < 1e-6);
  assert.equal(messages[0].endTime, 2048 / 48000);
  assert.equal(messages[1].endTime, 4096 / 48000);
});
