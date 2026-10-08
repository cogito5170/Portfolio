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
  // V-18 experience scenario: enter -> move -> proximity trigger -> tap trigger (sound) -> talk to character -> tour.
  // Driven through the real listeners (synthetic PointerEvents on the canvas, the same code path as a visitor).
  async scenario(eng) {
    const cv = eng.renderer.domElement, [w, h] = eng.size, steps = [];
    cv.setPointerCapture = cv.releasePointerCapture = () => {};
    const mouse = (type, x, y) => cv.dispatchEvent(new PointerEvent(type, { pointerId: 50, pointerType: 'mouse', isPrimary: true, clientX: x, clientY: y, button: 0, bubbles: true, cancelable: true }));
    const screen = id => { const v = new THREE.Box3().setFromObject(eng.find(id)).getCenter(new THREE.Vector3()); v.project(eng.camera); return [(v.x + 1) / 2 * w, (1 - v.y) / 2 * h]; };   // aim at the middle of the body
    const tapEntity = id => { const [x, y] = screen(id); mouse('pointerdown', x, y); mouse('pointerup', x, y); return eng.interaction.fired.some(f => f.id === id && f.on === 'tap'); };
    steps.push({ step: 'enter', ok: !!eng.world && eng.root.children.length > 0, audio_before_gesture: eng.audio.ctx === null });
    // move: walk forward with the on-screen joystick until the gate's proximity trigger fires
    eng.setMode('walk');
    ptr(cv, 'pointerdown', 1, 60, h - 140); ptr(cv, 'pointermove', 1, 60, h - 180);
    let k = 0; for (; k < 600 && !eng.interaction.fired.some(f => f.id === 'gate'); k++) eng.step(1 / 60, false);
    ptr(cv, 'pointerup', 1, 60, h - 180);
    steps.push({ step: 'move+near', ok: eng.interaction.fired.some(f => f.id === 'gate' && f.on === 'near'), walked_s: +(k / 60).toFixed(2),
                 caption: eng.captionLog.at(-1)?.text, audio_after_gesture: eng.audio.ctx !== null, sounds_started: eng.audio.started });
    // tap the moon from the aerial view: plays its hum, shows its caption
    eng.setMode('orbit'); eng.setView('aerial'); eng.step(1 / 60, false);
    const before = eng.captionLog.length, tapped = tapEntity('moon');
    steps.push({ step: 'tap', ok: tapped && eng.captionLog.slice(before).some(c => c.text.includes('달')), captions: eng.captionLog.slice(before).map(c => c.text) });
    // talk to the character (scripted line; live replies need the exhibit server)
    const b2 = eng.captionLog.length, talked = tapEntity('walker');
    const said = eng.captionLog.slice(b2).map(c => c.text);
    steps.push({ step: 'talk', ok: talked && said.some(t => t.startsWith('산책자: ')), captions: said });
    // tour: every stop's caption appears, then it ends
    const b3 = eng.captionLog.length; let ended = false; eng.on('tourEnd', () => { ended = true; });
    eng.startTour('walk');
    for (let i = 0; i < 60 * 20 && !ended; i++) eng.step(1 / 60, false);
    const tc = eng.captionLog.slice(b3).map(c => c.text);
    steps.push({ step: 'tour', ok: ended && eng.world.tours[0].stops.every(s => tc.includes(s.caption)), captions: tc });
    return { steps, ok: steps.every(s => s.ok), captionLog: eng.captionLog };
  },
  // XR-04: no AudioContext before a gesture; one is made on the first gesture and sources start with captions.
  async audio(eng) {
    eng.renderer.domElement.setPointerCapture = eng.renderer.domElement.releasePointerCapture = () => {};
    const before = eng.audio.ctx === null;
    eng.renderer.domElement.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 9, pointerType: 'mouse', bubbles: true }));
    const after = eng.audio.ctx !== null;
    const captioned = eng.audio.sources.filter(s => s.node).every(s => eng.captionLog.some(c => c.text.includes(s.spec.caption)));
    return { before_gesture_null: before, after_gesture_created: after, state: eng.audio.ctx && eng.audio.ctx.state, sources: eng.audio.sources.length,
             started: eng.audio.started, captioned };
  },
  // XR-03: world time runs at rules.physics.time_scale; fall uses rules.physics.gravity_mps2.
  async physics(eng) {
    const spin = eng.find('moon'), drop = eng.find('drop1');
    const a0 = spin.rotation.z;
    eng.step(2.0, false);
    return { time_scale: eng.phys.timeScale, g: eng.phys.g, world_t: eng.t, real_t: eng.realTime,
             spin_rad: spin.rotation.z - a0, drop_z: drop.position.z - drop.userData.base.pos.z };
  },
  async lowspec(eng) {
    return { lowspec: eng.lowspec, pixel_ratio: eng.renderer.getPixelRatio(), shadows: eng.renderer.shadowMap.enabled, env: eng.scene.environment !== null };
  },
};
