// Multi-visitor presence (XR-09): other visitors as simple avatars. Only when the page is served by
// `worldengine exhibit` and opened with ?presence=/ws. Anonymous: the server assigns a random id and colour.
import * as THREE from 'three';
import { FROM3 } from './engine.js';

export class Presence {
  constructor(eng, path) {
    this.eng = eng; this.avatars = new Map(); this.id = null; this.count = 1; this.connected = false; this.received = 0;
    const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + path;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => { this.connected = true; };
    this.ws.onclose = () => { this.connected = false; };
    this.ws.onmessage = e => this._msg(JSON.parse(e.data));
    this.timer = setInterval(() => this.send(), 100);
    eng.on('step', () => this._fade());
  }
  state() {
    if (this.eng.mode === 'walk' && this.eng.walk && this.eng.walk.state) {
      const s = this.eng.walk.state; return { pos: [s.x, s.y, s.eye], yaw: s.yaw, eye: this.eng.eyeName };
    }
    const p = FROM3(this.eng.camera.position); return { pos: p, yaw: 0, eye: p[2] < 1.4 ? 'child' : 'adult' };
  }
  send() { if (this.ws.readyState === 1) this.ws.send(JSON.stringify(this.state())); }
  _avatar(o) {
    const g = new THREE.Group(), m = new THREE.MeshStandardMaterial({ color: o.colour, roughness: 0.5, transparent: true, opacity: 0.85 });
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.18, 0.9, 6, 12).rotateX(Math.PI / 2), m); body.position.z = 0.65;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12), m); head.position.z = 1.35;
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.14, 8).rotateZ(-Math.PI / 2), m); nose.position.set(0.17, 0, 1.35);
    g.add(body, head, nose); g.userData.presence = o.id; this.eng.root.add(g); return g;
  }
  _msg(m) {
    if (m.type === 'hello') { this.id = m.id; return; }
    if (m.type !== 'room') return;
    this.count = m.count; this.received++;
    const seen = new Set();
    for (const o of m.others) {
      seen.add(o.id);
      const g = this.avatars.get(o.id) || this.avatars.set(o.id, this._avatar(o)).get(o.id);
      const k = o.eye === 'child' ? 1.1 / 1.7 : 1;                      // a child-height visitor looks smaller
      g.scale.set(k, k, k); g.position.set(o.pos[0], o.pos[1], Math.max(0, o.pos[2] - (o.eye === 'child' ? 1.1 : 1.7)));
      g.rotation.z = o.yaw; g.userData.t = performance.now();
    }
    for (const [id, g] of this.avatars) if (!seen.has(id)) { this.eng.root.remove(g); this.avatars.delete(id); }
    this.eng.emit('presence', this.count);
  }
  _fade() {}
  close() { clearInterval(this.timer); this.ws.close(); }
}
