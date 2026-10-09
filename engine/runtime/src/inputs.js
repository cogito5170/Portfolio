// Live inputs (M-03): how loud the room is (microphone) and how much moves in front of the screen (camera), each
// one number in [0,1], for behaviours {"type": "react", "input": "mic"|"camera", "prop": "scale"|"lift"|"glow", "amount"}.
//
// Opt-in only: nothing asks for a device until the visitor presses the button, and the HUD says while it is on.
// Nothing leaves this device: sound and pictures are reduced to that one number inside this page; nothing is sent,
// stored, recorded or shown. Turning it off stops the device (its light goes out).
const SMOOTH = 0.25;

export function inputsUsed(world) {
  const used = new Set();
  const walk = es => (es || []).forEach(e => { for (const b of (e && e.behaviors) || []) if (b && b.type === 'react') used.add(b.input); walk(e && e.children); });
  walk(world.entities);
  return used;
}

export class Inputs {
  constructor(eng) { this.eng = eng; this.on = {}; this.levels = { mic: 0, camera: 0 }; this.requests = 0; this._t = 0; }

  async enable(kind) {
    if (this.on[kind]) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { this.eng.caption('이 브라우저에서는 ' + (kind === 'mic' ? '마이크' : '카메라') + '를 쓸 수 없어요'); return false; }
    this.requests++;
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(kind === 'mic'
        ? { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false }
        : { video: { width: 160, height: 120 }, audio: false });
    } catch (e) { this.eng.caption((kind === 'mic' ? '마이크' : '카메라') + '를 켜지 못했어요 (' + (e.name || e) + ')'); return false; }
    if (kind === 'mic') {
      const AC = window.AudioContext || window.webkitAudioContext, ctx = new AC(), an = ctx.createAnalyser();
      an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an);            // to the analyser only, never to the speakers
      this.on.mic = { stream, ctx, an, buf: new Float32Array(an.fftSize) };
    } else {
      const video = document.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = stream;   // never added to the page
      await video.play().catch(() => {});
      const cv = document.createElement('canvas'); cv.width = 64; cv.height = 48;
      this.on.camera = { stream, video, g: cv.getContext('2d', { willReadFrequently: true }), prev: null };
    }
    this.eng.emit('inputs', kind);
    return true;
  }

  disable(kind) {
    const d = this.on[kind]; if (!d) return;
    for (const t of d.stream.getTracks()) t.stop();
    if (d.ctx) d.ctx.close();
    if (d.video) d.video.srcObject = null;
    delete this.on[kind]; this.levels[kind] = 0;
    this.eng.emit('inputs', kind);
  }

  update(dt) {
    const m = this.on.mic;
    if (m) {
      m.an.getFloatTimeDomainData(m.buf);
      let s = 0; for (const v of m.buf) s += v * v;
      const lv = Math.min(1, Math.sqrt(s / m.buf.length) * 6);
      this.levels.mic += (lv - this.levels.mic) * SMOOTH;
    }
    const c = this.on.camera;
    this._t += dt;
    if (c && this._t >= 0.1 && c.video.readyState >= 2) {          // ten looks a second, 64 x 48 grey levels
      this._t = 0;
      c.g.drawImage(c.video, 0, 0, 64, 48);
      const px = c.g.getImageData(0, 0, 64, 48).data, cur = new Uint8Array(64 * 48);
      for (let i = 0; i < cur.length; i++) cur[i] = (px[4 * i] * 54 + px[4 * i + 1] * 183 + px[4 * i + 2] * 19) >> 8;
      if (c.prev) {
        let d = 0; for (let i = 0; i < cur.length; i++) d += Math.abs(cur[i] - c.prev[i]);
        const lv = Math.min(1, d / cur.length / 255 * 8);
        this.levels.camera += (lv - this.levels.camera) * SMOOTH * 3;
      }
      c.prev = cur;
    }
  }
}
