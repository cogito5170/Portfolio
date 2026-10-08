// Robot plugin: an articulated arm (URDF chain as JSON) that plays a joint trajectory and leaves ink where the
// pen is down. The ink is placed by this runtime's own FK (robot/kinematics.js), not copied from the planner's
// targets, so the picture shows what the simulated arm actually drew.
//
//   {"type": "robot.arm", "chain": {joints: [...]}, "trajectory": {t, q, pen, target}, "speed": 1, "loop": true,
//    "link_radius": 0.05, "pen_down_z": 0, "ink": "#1b1f27", "material": name, "joint_material": name}
import * as THREE from 'three';
import { fk, local, active, sample } from '../robot/kinematics.js';

const M4 = T => new THREE.Matrix4().set(...T.flat());

export const robot = {
  name: 'robot',
  version: '1',
  materials: {
    link: { color: '#d7dbe0', roughness: 0.22, metalness: 0.95 },
    joint: { color: '#2b2f36', roughness: 0.35, metalness: 0.6 },
    accent: { color: '#ff5a36', roughness: 0.4 },
  },
  types: {
    'robot.arm': {
      doc: 'serial arm from a URDF chain; plays trajectory {t,q,pen}; ink where pen=1',
      fields: { chain: '{joints:[...]}', trajectory: '{t,q,pen,target?}', speed: 'playback x', loop: 'bool', link_radius: 'm', ink: 'css colour' },
      build(e, c) { return buildArm(e, c); },
    },
  },
};

function buildArm(e, c) {
  const chain = e.chain, tr = e.trajectory, r = e.link_radius ?? 0.05, lift = e.pen_lift ?? 0.03;
  const root = new THREE.Group();
  const linkM = c.mats.get(e.material ?? 'robot.link'), jointM = c.mats.get(e.joint_material ?? 'robot.joint'), accM = c.mats.get('robot.accent');
  const shadow = m => { m.castShadow = m.receiveShadow = true; return m; };
  // Visual stacking: planar arms have every link in one plane, so each link is drawn a little higher (zs[i]).
  const planar = chain.joints.every(j => Math.abs((j.xyz || [0, 0, 0])[2]) < 1e-9 && (!j.axis || Math.abs(j.axis[2]) > 0.999));
  const zs = chain.joints.map((_, i) => (planar ? (i + 1) * 2.4 * r : 0));
  const baseH = zs[0] || 2 * r;
  root.add(shadow(new THREE.Mesh(new THREE.CylinderGeometry(3 * r, 3.4 * r, baseH, 48).rotateX(Math.PI / 2).translate(0, 0, baseH / 2), jointM)));
  const nodes = [];
  let parent = root;
  chain.joints.forEach((j, i) => {
    const g = new THREE.Group(); g.matrixAutoUpdate = false; parent.add(g); nodes.push(g);
    const next = chain.joints[i + 1], off = next ? new THREE.Vector3(...(next.xyz || [0, 0, 0])) : null;
    if (j.type !== 'fixed') {
      const hub = shadow(new THREE.Mesh(new THREE.CylinderGeometry(1.5 * r, 1.5 * r, 1.6 * r, 40), jointM));
      const ax = new THREE.Vector3(...(j.axis || [0, 0, 1])).normalize();
      hub.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), ax); hub.position.z = zs[i]; g.add(hub);
    }
    if (off && off.length() > 1e-9) {
      const L = off.length(), m = shadow(new THREE.Mesh(new THREE.CapsuleGeometry(r, Math.max(1e-3, L - 2 * r), 8, 24), linkM));
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), off.clone().normalize());
      m.position.copy(off.clone().multiplyScalar(0.5)); m.position.z += planar ? zs[i] + 1.2 * r : 0; g.add(m);
    }
    parent = g;
  });
  // Pen at the tip: a vertical rod that drops to the paper (z = pen_down_z in the arm frame) when pen = 1.
  const pen = new THREE.Group(); parent.add(pen);
  const penTop = (planar ? zs.at(-1) : 0) + 2 * r;
  const rod = shadow(new THREE.Mesh(new THREE.CylinderGeometry(0.35 * r, 0.35 * r, 1, 16).rotateX(Math.PI / 2).translate(0, 0, 0.5), accM));
  const nib = shadow(new THREE.Mesh(new THREE.ConeGeometry(0.35 * r, 0.8 * r, 16).rotateX(-Math.PI / 2).translate(0, 0, 0.4 * r), jointM));
  pen.add(rod, nib);

  // Ink: positions from this runtime's FK of every sample; drawRange grows with time.
  const n = tr ? tr.q.length : 0, inkPos = new Float32Array(Math.max(1, n - 1) * 6);
  let segs = 0; const segEnd = new Int32Array(n);     // number of ink segments completed up to sample i
  const tips = tr ? tr.q.map(q => fk(chain, q).points.at(-1)) : [];
  for (let i = 1; i < n; i++) {
    if (tr.pen[i] && tr.pen[i - 1]) { inkPos.set([...tips[i - 1], ...tips[i]].map((v, k) => (k % 3 === 2 ? (e.pen_down_z ?? 0) + 0.002 : v)), 6 * segs); segs++; }
    segEnd[i] = segs;
  }
  const inkG = new THREE.BufferGeometry(); inkG.setAttribute('position', new THREE.BufferAttribute(inkPos, 3)); inkG.setDrawRange(0, 0);
  const ink = new THREE.LineSegments(inkG, new THREE.LineBasicMaterial({ color: new THREE.Color(e.ink ?? '#1b1f27') }));
  root.add(ink);

  const pose = q => {
    let k = 0;
    chain.joints.forEach((j, i) => { nodes[i].matrix.copy(M4(local(j, j.type === 'fixed' ? 0 : q[k++]))); nodes[i].matrixWorldNeedsUpdate = true; });
  };
  const duration = n ? tr.t[n - 1] : 0, speed = e.speed ?? 1;
  const state = { time: 0, i: 0, pen: 0, q: tr ? tr.q[0] : active(chain).map(() => 0), tips, inkSegments: segs };
  root.userData.robot = state;
  root.userData.tick = t => {
    if (!tr) { pose(state.q); return; }
    let tt = t * speed; if (e.loop !== false && duration > 0) tt %= duration + 2;   // 2 s pause at the end of a loop
    const s = sample(tr, tt);
    state.time = tt; state.i = s.i; state.pen = s.pen; state.q = s.q;
    pose(s.q);
    const tipZ = (fk(chain, s.q).points.at(-1))[2];
    const bottom = (e.pen_down_z ?? 0) + (s.pen ? 0 : lift) - tipZ;              // pen rod spans from the paper (or above it) to penTop
    nib.position.z = bottom; rod.position.z = bottom + 0.8 * r; rod.scale.z = Math.max(1e-3, penTop - bottom - 0.8 * r);
    inkG.setDrawRange(0, 2 * segEnd[s.i]);
  };
  root.userData.tick(0);
  return root;
}
