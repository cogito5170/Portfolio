// Spatial sound with no audio files (XR-04). Nothing is created before a user gesture: browsers forbid starting
// audio without one, and a visitor should not be surprised by sound. Every sound has a caption (world check), shown
// when it starts, so a visitor without sound still gets it (XR-11).
//
// sound entity: {type: "sound", caption, recipe: "tone"|"chord"|"noise"|"pulse", freq, freqs, wave, rate,
//                volume (0..1, default from the world's sound axis), ref_distance, max_distance, autoplay (default true),
//                src: "asset:<name>" (the artist's own recording, E-02: played, looped, instead of the recipe), loop}
import * as THREE from 'three';

export class AudioManager {
  constructor(eng) {
    this.eng = eng; this.ctx = null; this.sources = []; this.started = 0;
    this._unlock = () => this.unlock();
    for (const ev of ['pointerdown', 'keydown', 'touchend']) addEventListener(ev, this._unlock, true);
  }
  register(obj, spec) { this.sources.push({ obj, spec, node: null }); }
  get axisVolume() { const a = this.eng.world?.rules?.axes?.sound; return a === undefined ? 0.5 : a; }

  unlock() {
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { this.eng.caption('이 브라우저는 소리를 낼 수 없어요 — 자막으로 대신합니다'); return; }
    this.ctx = new AC(); this.ctx.resume?.();
    this.master = this.ctx.createGain(); this.master.gain.value = 0.8; this.master.connect(this.ctx.destination);
    for (const s of this.sources) if (s.spec.autoplay !== false) this.start(s);
    for (const ev of ['pointerdown', 'keydown', 'touchend']) removeEventListener(ev, this._unlock, true);
  }

  _graph(spec) {
    const c = this.ctx, out = c.createGain();
    const osc = (f, type) => { const o = c.createOscillator(); o.type = type || 'sine'; o.frequency.value = f; o.connect(out); o.start(); return o; };
    const r = spec.recipe || 'tone';
    if (spec.src) this._file(spec, out);
    else if (r === 'tone') osc(spec.freq || 220, spec.wave);
    else if (r === 'chord') for (const f of spec.freqs || [220, 277, 330]) osc(f, spec.wave);
    else if (r === 'noise') {
      const b = c.createBuffer(1, c.sampleRate * 2, c.sampleRate), d = b.getChannelData(0);
      let last = 0; for (let i = 0; i < d.length; i++) { const w = Math.random() * 2 - 1; last = spec.colour === 'white' ? w : (last + 0.02 * w) / 1.02; d[i] = spec.colour === 'white' ? w : last * 3.5; }
      const n = c.createBufferSource(); n.buffer = b; n.loop = true;
      const f = c.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = spec.freq || 1200; n.connect(f); f.connect(out); n.start();
    } else if (r === 'pulse') {
      osc(spec.freq || 330, spec.wave);
      const lfo = c.createOscillator(), depth = c.createGain(); lfo.frequency.value = spec.rate || 1; depth.gain.value = 0.5;
      lfo.connect(depth); depth.connect(out.gain); lfo.start(); out.gain.value = 0.5;
    }
    const vol = c.createGain(); vol.gain.value = (spec.volume ?? this.axisVolume) * 0.3;
    const pan = c.createPanner(); pan.panningModel = 'HRTF'; pan.distanceModel = 'inverse';
    pan.refDistance = spec.ref_distance ?? 1.5; pan.maxDistance = spec.max_distance ?? 40; pan.rolloffFactor = 1.2;
    out.connect(vol); vol.connect(pan); pan.connect(this.master);
    return { pan, vol };
  }

  // The artist's recording: decoded in this browser, played through the same panner. Not readable here -> caption says so.
  _file(spec, out) {
    const url = this.eng.assets && this.eng.assets.url(spec.src);
    this.files = this.files || { decoded: 0, failed: 0, seconds: [] }; this.pending = this.pending || [];
    if (!url) { this.files.failed++; this.eng.caption('♪ ' + spec.caption + ' (이 페이지에서는 파일을 들을 수 없어요)'); return; }
    const p = this.decode(url).then(buf => {
      const n = this.ctx.createBufferSource(); n.buffer = buf; n.loop = spec.loop !== false; n.connect(out); n.start();
      this.files.decoded++; this.files.seconds.push(+buf.duration.toFixed(3));
    }).catch(() => { this.files.failed++; this.eng.caption('♪ ' + spec.caption + ' (파일을 열지 못했어요)'); });
    this.pending.push(p); return p;
  }
  // Decoded on an offline context: the buffer plays on the live one all the same, and decoding does not wait for the
  // live context to be allowed to run (headless browsers never resolve that wait).
  decode(url, rate = this.ctx ? this.ctx.sampleRate : 48000) {
    return fetch(url).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.arrayBuffer(); })
      .then(b => new OfflineAudioContext(1, 1, rate).decodeAudioData(b));
  }

  start(s) {
    if (!this.ctx || s.node) return;
    s.node = this._graph(s.spec); this.started++;
    this.eng.caption('♪ ' + s.spec.caption, s.obj);
  }
  play(id) {
    const s = this.sources.find(x => x.obj.userData.id === id);
    if (!s) return;
    if (!this.ctx) { this.eng.caption('♪ ' + s.spec.caption + ' (소리를 켜려면 화면을 한 번 눌러 주세요)'); return; }
    if (s.node) { s.node.vol.gain.setTargetAtTime(s.node.vol.gain.value > 0 ? 0 : (s.spec.volume ?? this.axisVolume) * 0.3, this.ctx.currentTime, 0.1); this.eng.caption('♪ ' + s.spec.caption, s.obj); }
    else this.start(s);
  }
  update(camera) {
    if (!this.ctx) return;
    const L = this.ctx.listener, p = camera.position, f = new THREE.Vector3(), up = camera.up;
    camera.getWorldDirection(f);
    if (L.positionX) { L.positionX.value = p.x; L.positionY.value = p.y; L.positionZ.value = p.z; L.forwardX.value = f.x; L.forwardY.value = f.y; L.forwardZ.value = f.z; L.upX.value = up.x; L.upY.value = up.y; L.upZ.value = up.z; }
    else { L.setPosition(p.x, p.y, p.z); L.setOrientation(f.x, f.y, f.z, up.x, up.y, up.z); }
    const w = new THREE.Vector3();
    for (const s of this.sources) if (s.node) { s.obj.getWorldPosition(w); const P = s.node.pan;
      if (P.positionX) { P.positionX.value = w.x; P.positionY.value = w.y; P.positionZ.value = w.z; } else P.setPosition(w.x, w.y, w.z); }
  }
}
