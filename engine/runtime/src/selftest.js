// In-browser self-tests, run by ?selftest=<name>. They drive the real input path (synthetic PointerEvents into the
// canvas/joystick listeners) and step the engine with a fixed dt, then report measurements. Python asserts on them.
import * as THREE from 'three';
import { vector } from './controls/joystick.js';

const ptr = (el, type, id, x, y) => el.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', isPrimary: id === 1, clientX: x, clientY: y, bubbles: true, cancelable: true }));
const run = (eng, n, dt = 1 / 60) => { for (let i = 0; i < n; i++) eng.step(dt, false); };   // no rendering: SwiftShader is slow

export const selftests = {
  // Phone controls (XR-12): joystick walk, drag look, eye heights, two-finger pinch in orbit.
  async touch(eng) {
    const cv = eng.renderer.domElement, [w, h] = eng.size, out = {};
    cv.setPointerCapture = cv.releasePointerCapture = () => {};   // synthetic pointers cannot be captured; the handlers still run
    eng.setMode('walk');
    const s0 = { ...eng.walk.state };
    ptr(cv, 'pointerdown', 1, 60, h - 140); ptr(cv, 'pointermove', 1, 60, h - 180);     // thumb 40 px up
    run(eng, 60);
    const s1 = { ...eng.walk.state };
    const v = vector(0, -40, eng.joystick.radius), exp = 1.4 * v.y * 1.0;
    out.walk = { moved: Math.hypot(s1.x - s0.x, s1.y - s0.y), expected: exp,
      along_yaw: (s1.x - s0.x) * Math.cos(s0.yaw) + (s1.y - s0.y) * Math.sin(s0.yaw) };
    ptr(cv, 'pointerup', 1, 60, h - 180); run(eng, 30);
    out.after_release = Math.hypot(eng.walk.state.x - s1.x, eng.walk.state.y - s1.y);
    ptr(cv, 'pointerdown', 2, w * 0.75, h / 2); ptr(cv, 'pointermove', 2, w * 0.75 + 100, h / 2); ptr(cv, 'pointerup', 2, w * 0.75 + 100, h / 2);
    out.look = { dyaw: eng.walk.state.yaw - s1.yaw, expected: -100 * eng.walk.lookSens };
    eng.setEye('child'); run(eng, 1); out.eye_child = eng.camera.position.y;
    eng.setEye('adult'); run(eng, 1); out.eye_adult = eng.camera.position.y;
    eng.setMode('orbit'); run(eng, 1);
    const d0 = eng.camera.position.distanceTo(eng.orbit.target);
    ptr(cv, 'pointerdown', 3, w / 2 - 20, h / 2); ptr(cv, 'pointerdown', 4, w / 2 + 20, h / 2);
    for (let k = 1; k <= 10; k++) { ptr(cv, 'pointermove', 3, w / 2 - 20 - 8 * k, h / 2); ptr(cv, 'pointermove', 4, w / 2 + 20 + 8 * k, h / 2); }
    ptr(cv, 'pointerup', 3, 0, 0); ptr(cv, 'pointerup', 4, 0, 0); run(eng, 30);
    out.pinch = { d0, d1: eng.camera.position.distanceTo(eng.orbit.target) };
    return out;
  },
  // Collision: walk straight at the first solid collider and stop before it.
  async collide(eng) {
    eng.setMode('walk');
    const lo = eng.extent.min[0] + 2.5;                  // room to run up to it without hitting the world edge
    const c = eng.colliders.filter(k => k[0] > lo && k[4] > 0.3).sort((a, b) => a[0] - b[0])[0];
    if (!c) return { error: 'no colliders' };
    const cy = (c[1] + c[3]) / 2;
    eng.walk.state = { ...eng.walk.state, x: c[0] - 2, y: cy, yaw: 0, pitch: 0 };
    eng.walk.keys.add('KeyW'); run(eng, 240); eng.walk.keys.delete('KeyW');
    return { x: eng.walk.state.x, start_x: c[0] - 2, wall_x0: c[0], radius: 0.25 };
  },
  // Drawing robot: the ink this runtime draws (its own FK) vs the planner's intended targets, at every pen-down sample.
  async robot(eng) {
    let arm = null; eng.root.traverse(o => { if (o.userData.robot && !arm) arm = o; });
    if (!arm) return { error: 'no robot.arm' };
    const tr = arm.userData.entity.trajectory, st = arm.userData.robot;
    let worst = 0, n = 0, pairs = 0;
    tr.pen.forEach((p, i) => { if (!p) return; n++; const a = st.tips[i], b = tr.target[i]; worst = Math.max(worst, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])); });
    for (let i = 1; i < tr.pen.length; i++) if (tr.pen[i] && tr.pen[i - 1]) pairs++;
    eng.step(tr.t.at(-1) / 2, false);
    return { pen_samples: n, ink_err_max_m: worst, ink_segments: st.inkSegments, pen_pairs: pairs, mid_time: st.time, mid_index: st.i };
  },
};
