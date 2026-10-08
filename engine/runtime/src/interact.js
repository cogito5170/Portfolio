// Interaction (XR-05): tap/click on an entity, or come near it, runs its trigger actions.
//   triggers: [{on: "tap"|"near", radius (near), once, do: [{action: "play"|"toggle"|"caption"|"tour"|"talk", target, text, tour}]}]
// A tap is a pointer press+release that moved < 10 px within 600 ms (so orbit drags and joystick pushes are not taps).
import * as THREE from 'three';
import { FROM3 } from './engine.js';

export class Interaction {
  constructor(eng) {
    this.eng = eng; this.ray = new THREE.Raycaster(); this.down = null; this.inside = new Set(); this.fired = [];
    const dom = eng.renderer.domElement;
    dom.addEventListener('pointerdown', e => { this.down = { x: e.clientX, y: e.clientY, t: performance.now(), id: e.pointerId }; });
    dom.addEventListener('pointerup', e => {
      const d = this.down; this.down = null;
      if (!d || d.id !== e.pointerId || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 10 || performance.now() - d.t > 600) return;
      if (eng.joystick && eng.joystick.owns(e.pointerId)) return;
      this.tapAt(e.clientX, e.clientY);
    });
  }
  owner(o) { while (o && !(o.userData.entity && o.userData.entity.triggers)) o = o.parent; return o; }
  tapAt(x, y) {
    const r = this.eng.renderer.domElement.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), this.eng.camera);
    for (const h of this.ray.intersectObject(this.eng.root, true)) {
      const o = this.owner(h.object);
      if (!o) continue;
      for (const tr of o.userData.entity.triggers) if (tr.on === 'tap') this.run(o, tr);
      return o.userData.id;
    }
    return null;
  }
  step() {                                            // proximity, from the visitor's eye (walk) or the camera
    const eye = FROM3(this.eng.camera.position), w = new THREE.Vector3();
    this.eng.root.traverse(o => {
      const trs = o.userData.entity && o.userData.entity.triggers; if (!trs) return;
      o.getWorldPosition(w); const p = FROM3(w);
      for (const tr of trs) {
        if (tr.on !== 'near') continue;
        const d = Math.hypot(p[0] - eye[0], p[1] - eye[1]), key = o.uuid + tr.radius;
        if (d < tr.radius && !this.inside.has(key)) { this.inside.add(key); if (!(tr.once && this.fired.some(f => f.key === key))) this.run(o, tr, key); }
        else if (d > tr.radius * 1.2) this.inside.delete(key);
      }
    });
  }
  run(o, tr, key) {
    this.fired.push({ id: o.userData.id, on: tr.on, key });
    for (const a of tr.do || []) {
      const target = a.target ? this.eng.find(a.target) : o;
      if (a.action === 'caption') this.eng.caption(a.text, o);
      else if (a.action === 'play') this.eng.audio && this.eng.audio.play(a.target || o.userData.id);
      else if (a.action === 'toggle' && target) target.userData.paused = !target.userData.paused;
      else if (a.action === 'tour') this.eng.startTour(a.tour);
      else if (a.action === 'talk' && target && target.userData.character) target.userData.character.talk();
    }
    this.eng.emit('trigger', { id: o.userData.id, on: tr.on });
  }
}
