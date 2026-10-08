// Talking character (CH-01..04). Persona and lines come from the world (its concepts and narrative), not from code.
//   {"type": "character", "name", "lines": [...] (scripted; each line is its own caption), "color", "height",
//    "live": true -> replies come from the exhibit server's /api/talk when the page was opened with ?talk=...}
// It looks at the visitor (head turns toward the camera) and gestures while it speaks (CH-02).
import * as THREE from 'three';

const UP = g => g.rotateX(Math.PI / 2);

export const character = {
  name: 'character', version: '1',
  types: {
    character: {
      doc: 'a figure that speaks scripted or live lines, looks at the visitor and gestures', fields: { name: 'str', lines: '[str]', color: 'css', height: 'm', live: 'bool' },
      build(e, c) {
        const h = e.height ?? 1.6, g = new THREE.Group(), mat = new THREE.MeshStandardMaterial({ color: e.color ?? '#9fb7ff', roughness: 0.35, metalness: 0.5 });
        const dark = new THREE.MeshStandardMaterial({ color: 0x15171b, roughness: 0.4 });
        const body = new THREE.Mesh(UP(new THREE.CapsuleGeometry(0.22 * h / 1.6, h * 0.42, 8, 20)), mat); body.position.z = h * 0.42; body.castShadow = true; g.add(body);
        const head = new THREE.Group(); head.position.z = h * 0.86; g.add(head);
        const skull = new THREE.Mesh(new THREE.SphereGeometry(0.16 * h / 1.6, 32, 20), mat); skull.castShadow = true; head.add(skull);
        for (const s of [-1, 1]) { const eye = new THREE.Mesh(new THREE.SphereGeometry(0.025 * h / 1.6, 12, 8), dark); eye.position.set(0.14 * h / 1.6, s * 0.055 * h / 1.6, 0.02); head.add(eye); }
        const arms = [-1, 1].map(s => { const pivot = new THREE.Group(); pivot.position.set(0, s * 0.27 * h / 1.6, h * 0.66);
          const arm = new THREE.Mesh(UP(new THREE.CapsuleGeometry(0.05 * h / 1.6, h * 0.3, 6, 12)), mat); arm.position.z = -h * 0.18; arm.castShadow = true; pivot.add(arm); g.add(pivot); return pivot; });
        let line = -1, speakUntil = 0;
        const state = g.userData.character = {
          name: e.name || '캐릭터', spoken: [],
          say(text, seconds) { state.spoken.push(text); c.engine.caption(`${state.name}: ${text}`, g, seconds ?? Math.max(3, text.length / 8)); speakUntil = c.engine.realTime + Math.max(2, text.length / 8); },
          talk() {
            if (e.live && c.engine.talk) return c.engine.talk.open(state);
            line = (line + 1) % e.lines.length; state.say(e.lines[line]);
          },
          speaking: () => c.engine.realTime < speakUntil,
        };
        const v = new THREE.Vector3(), q = new THREE.Vector3();
        g.userData.tick = () => {
          // CH-02 gaze: turn the head (yaw, clamped) toward the camera, in this figure's own frame
          c.engine.camera.getWorldPosition(v); head.getWorldPosition(q);
          const local = g.worldToLocal(v.clone()), yaw = Math.atan2(local.y - head.position.y, local.x - head.position.x);
          head.rotation.z = Math.max(-1.2, Math.min(1.2, yaw));
          const talking = state.speaking(), t = c.engine.realTime;
          arms[0].rotation.y = talking ? -0.6 + 0.35 * Math.sin(t * 7) : 0;
          arms[1].rotation.y = talking ? -0.2 + 0.2 * Math.sin(t * 5 + 1) : 0;
          body.position.z = h * 0.42 + (talking ? 0.01 * Math.sin(t * 12) : 0);
        };
        return g;
      },
    },
  },
};
