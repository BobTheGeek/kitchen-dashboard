// Talk to the house: microphone capture as 16 kHz WAV, silence detection, and the talk API.
// Speech never goes to the browser's own speech service: the WAV goes to the home server (whisper.cpp).
import { request } from "./api.js";

export const micAvailable = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

export class Recorder {
  constructor({ onLevel, onSilence, silenceMs = 1500, maxMs = 15000 } = {}) {
    Object.assign(this, { onLevel, onSilence, silenceMs, maxMs });
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.heard = false;
    this.started = this.quietSince = performance.now();
    this.node.onaudioprocess = (e) => {
      const data = new Float32Array(e.inputBuffer.getChannelData(0));
      this.chunks.push(data);
      let sum = 0;
      for (const v of data) sum += v * v;
      const rms = Math.sqrt(sum / data.length);
      this.onLevel?.(Math.min(1, rms * 8));
      const now = performance.now();
      if (rms > 0.02) { this.heard = true; this.quietSince = now; }
      if ((this.heard && now - this.quietSince > this.silenceMs) || now - this.started > this.maxMs) this.onSilence?.();
    };
    src.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  async stop() {
    this.node.disconnect();
    this.stream.getTracks().forEach((t) => t.stop());
    const rate = this.ctx.sampleRate;
    await this.ctx.close();
    const n = this.chunks.reduce((a, c) => a + c.length, 0);
    const all = new Float32Array(n);
    let o = 0;
    for (const c of this.chunks) { all.set(c, o); o += c.length; }
    return { wav: await toWav16k(all, rate), heard: this.heard };
  }

  cancel() {
    try { this.node?.disconnect(); this.stream?.getTracks().forEach((t) => t.stop()); this.ctx?.close(); } catch { /* already closed */ }
  }
}

async function toWav16k(samples, rate) {
  const len = Math.max(1, Math.round((samples.length * 16000) / rate));
  const off = new OfflineAudioContext(1, len, 16000);
  const buf = off.createBuffer(1, Math.max(1, samples.length), rate);
  buf.copyToChannel(samples, 0);
  const s = off.createBufferSource();
  s.buffer = buf;
  s.connect(off.destination);
  s.start();
  const out = (await off.startRendering()).getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + out.length * 2));
  const str = (p, t) => [...t].forEach((c, i) => view.setUint8(p + i, c.charCodeAt(0)));
  str(0, "RIFF"); view.setUint32(4, 36 + out.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); str(36, "data"); view.setUint32(40, out.length * 2, true);
  out.forEach((v, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([view], { type: "audio/wav" });
}

export const talkApi = {
  start: (context) => request("POST", "/api/talk/sessions", context ? { context } : {}),
  status: (id) => request("GET", `/api/talk/sessions/${id}`),
  end: (id) => request("DELETE", `/api/talk/sessions/${id}`).catch(() => {}),
  message: (id, text) => request("POST", "/api/talk/message", { session_id: id, text }),
  undo: (actionId) => request("POST", `/api/talk/actions/${actionId}/undo`),
  async listen(wav) {
    const r = await fetch("/api/talk/listen", { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const e = new Error(`HTTP ${r.status}`);
      e.status = r.status;
      e.data = data;
      throw e;
    }
    return data.text;
  },
};
