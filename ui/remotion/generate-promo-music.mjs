import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const sampleRate = 48_000;
const durationSeconds = 15;
const channels = 2;
const totalSamples = sampleRate * durationSeconds;
const bpm = 112;
const beatSeconds = 60 / bpm;
const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const outputPath = join(rootDir, "public", "audio", "homerun-promo-bed.wav");

const midiToHz = (note) => 440 * 2 ** ((note - 69) / 12);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const envelope = (t, attack, release) => {
  if (t < 0) return 0;
  const a = clamp(t / attack, 0, 1);
  return a * Math.exp(-release * Math.max(0, t - attack));
};

let noiseSeed = 123456789;
const noise = () => {
  noiseSeed = (1664525 * noiseSeed + 1013904223) >>> 0;
  return noiseSeed / 2147483648 - 1;
};

const softSaw = (frequency, time) => {
  const phase = (time * frequency) % 1;
  return (phase * 2 - 1) * 0.55 + Math.sin(time * Math.PI * 2 * frequency) * 0.45;
};

const chordProgression = [
  [midiToHz(41), midiToHz(44), midiToHz(48), midiToHz(53)],
  [midiToHz(37), midiToHz(41), midiToHz(44), midiToHz(49)],
  [midiToHz(44), midiToHz(48), midiToHz(51), midiToHz(56)],
  [midiToHz(39), midiToHz(43), midiToHz(46), midiToHz(51)],
];

const bassNotes = [midiToHz(29), midiToHz(29), midiToHz(25), midiToHz(27)];
const impactTimes = [0.2, 3.6, 9.3, 13.1];

function chordAt(time) {
  const index = Math.floor(time / (beatSeconds * 4)) % chordProgression.length;
  return chordProgression[index];
}

function addKick(time, beatPosition) {
  if (beatPosition > 0.42) return 0;
  const pitch = 44 + 62 * Math.exp(-beatPosition * 18);
  const body = Math.sin(Math.PI * 2 * pitch * beatPosition) * Math.exp(-beatPosition * 8.5);
  const click = noise() * Math.exp(-beatPosition * 80) * 0.18;
  return (body + click) * 0.74;
}

function addSnare(beatIndex, beatPosition) {
  if (!(beatIndex % 4 === 1 || beatIndex % 4 === 3) || beatPosition > 0.22) {
    return 0;
  }
  const crack = noise() * Math.exp(-beatPosition * 24) * 0.38;
  const tone = Math.sin(Math.PI * 2 * 185 * beatPosition) * Math.exp(-beatPosition * 18) * 0.12;
  return crack + tone;
}

function addHat(time) {
  const hatStep = beatSeconds / 2;
  const hatPosition = time % hatStep;
  if (hatPosition > 0.055) return 0;
  return noise() * Math.exp(-hatPosition * 70) * 0.13;
}

function addBass(time, beatIndex, beatPosition) {
  const note = bassNotes[Math.floor(beatIndex / 4) % bassNotes.length];
  const gate = beatPosition < beatSeconds * 0.72 ? 1 : 0;
  const env = gate * envelope(beatPosition, 0.018, 3.1);
  const sub = Math.sin(Math.PI * 2 * note * time);
  const growl = softSaw(note * 2, time) * 0.22;
  return (sub + growl) * env * 0.22;
}

function addPad(time) {
  const chord = chordAt(time);
  const fade = clamp(time / 1.7, 0, 1) * clamp((durationSeconds - time) / 1.2, 0, 1);
  return chord.reduce((sum, frequency, index) => {
    const detune = 1 + (index - 1.5) * 0.004;
    return sum + softSaw(frequency * detune, time + index * 0.013) * 0.019;
  }, 0) * fade;
}

function addArp(time) {
  const step = beatSeconds / 2;
  const stepIndex = Math.floor(time / step);
  const pos = time - stepIndex * step;
  if (pos > 0.22) return 0;
  const chord = chordAt(time);
  const note = chord[stepIndex % chord.length] * 2;
  const env = envelope(pos, 0.01, 13);
  return Math.sin(Math.PI * 2 * note * time) * env * 0.105;
}

function addRiser(time) {
  const start = 11.9;
  if (time < start) return 0;
  const p = clamp((time - start) / (durationSeconds - start), 0, 1);
  const tone = Math.sin(Math.PI * 2 * (480 + p * 880) * time) * p * 0.055;
  const air = noise() * p * p * 0.07;
  return tone + air;
}

function addImpact(time) {
  return impactTimes.reduce((sum, impactTime) => {
    const pos = time - impactTime;
    if (pos < 0 || pos > 0.85) return sum;
    const boom = Math.sin(Math.PI * 2 * (58 - pos * 19) * pos) * Math.exp(-pos * 4.3) * 0.36;
    const bite = noise() * Math.exp(-pos * 18) * 0.11;
    return sum + boom + bite;
  }, 0);
}

const left = new Float32Array(totalSamples);
const right = new Float32Array(totalSamples);
let max = 0;

for (let i = 0; i < totalSamples; i += 1) {
  const time = i / sampleRate;
  const beatIndex = Math.floor(time / beatSeconds);
  const beatPosition = time - beatIndex * beatSeconds;
  const fade = clamp(time / 0.45, 0, 1) * clamp((durationSeconds - time) / 0.75, 0, 1);

  const kick = addKick(time, beatPosition);
  const snare = addSnare(beatIndex, beatPosition);
  const hats = addHat(time);
  const bass = addBass(time, beatIndex, beatPosition);
  const pad = addPad(time);
  const arp = addArp(time);
  const riser = addRiser(time);
  const impact = addImpact(time);
  const center = (kick + snare + bass + impact) * fade;
  const stereo = (pad + arp + hats + riser) * fade;
  const pan = Math.sin(time * 0.7) * 0.08;

  left[i] = center + stereo * (1 - pan);
  right[i] = center + stereo * (1 + pan);
  max = Math.max(max, Math.abs(left[i]), Math.abs(right[i]));
}

const gain = 0.92 / Math.max(max, 0.001);
const dataBytes = totalSamples * channels * 2;
const buffer = Buffer.alloc(44 + dataBytes);

buffer.write("RIFF", 0);
buffer.writeUInt32LE(36 + dataBytes, 4);
buffer.write("WAVE", 8);
buffer.write("fmt ", 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(channels, 22);
buffer.writeUInt32LE(sampleRate, 24);
buffer.writeUInt32LE(sampleRate * channels * 2, 28);
buffer.writeUInt16LE(channels * 2, 32);
buffer.writeUInt16LE(16, 34);
buffer.write("data", 36);
buffer.writeUInt32LE(dataBytes, 40);

for (let i = 0; i < totalSamples; i += 1) {
  const offset = 44 + i * channels * 2;
  buffer.writeInt16LE(Math.round(clamp(left[i] * gain, -1, 1) * 32767), offset);
  buffer.writeInt16LE(Math.round(clamp(right[i] * gain, -1, 1) * 32767), offset + 2);
}

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, buffer);
console.log(`Generated ${outputPath}`);
