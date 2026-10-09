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
  // K-04: in a viewpoint combination, a child's eye sees world B and an adult's eye sees world A.
  async viewpoint(eng) {
    const count = () => { let a = 0, b = 0; for (const o of eng.eyeOnly) if (o.visible) (o.userData.entity.eye_only === 'adult' ? a++ : b++); return { adult_world: a, child_world: b }; };
    eng.setMode('walk'); eng.setEye('adult'); eng.step(1 / 60, false); const adult = count();
    eng.setEye('child'); eng.step(1 / 60, false); const child = count();
    return { total: eng.eyeOnly.length, adult, child };
  },
  // XR-10: export the built scene to .glb; Python validates the bytes independently.
  async gltf(eng) {
    const { exportGLB } = await import('./export.js');
    const buf = new Uint8Array(await exportGLB(eng));
    let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    let meshes = 0; eng.scene.traverse(o => { if (o.isMesh && o.visible) meshes++; });
    return { bytes: buf.length, scene_meshes: meshes, glb_b64: btoa(bin) };
  },
  // XR-09: wait (real time) until another visitor's avatar appears, then report what this page sees.
  async presence(eng) {
    const p = eng.presence; if (!p) return { error: 'no ?presence' };
    const t0 = performance.now();
    while (performance.now() - t0 < 8000 && !(p.connected && p.avatars.size > 0)) await new Promise(r => setTimeout(r, 100));
    let inRoot = 0; eng.root.traverse(o => { if (o.userData.presence) inRoot++; });
    return { connected: p.connected, my_id: p.id, count: p.count, avatars: p.avatars.size, avatar_ids: [...p.avatars.keys()], in_scene: inRoot, received: p.received };
  },
  // XR-08 smoke: the VR module loads, support is reported honestly, and without VR nothing is added.
  async xr(eng) {
    const { xrSupport, enableXR } = await import('./xr.js');
    const s = await xrSupport(); const e = await enableXR(eng);
    return { api: s.api, vr: s.vr, button: !!eng.xrButton, renderer_xr: eng.renderer.xr.enabled, agree: s.vr === e.vr };
  },
  // XR-01 bloom: mean luminance in a ring just outside the glowing body ("glow"), post-processing off / on / low-spec.
  async bloom(eng) {
    const o = eng.find('glow'); if (!o) return { error: 'no entity "glow"' };
    const sph = new THREE.Box3().setFromObject(o).getBoundingSphere(new THREE.Sphere()), cam = eng.camera;
    const c = sph.center.clone().project(cam), right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
    const e = sph.center.clone().addScaledVector(right, sph.radius).project(cam);
    const [W, H] = eng.size, cx = (c.x + 1) / 2 * W, cy = (1 - c.y) / 2 * H, r = Math.hypot((e.x - c.x) / 2 * W, (e.y - c.y) / 2 * H);
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H; const g = cv.getContext('2d', { willReadFrequently: true });
    const ring = () => {
      eng.step(0); g.drawImage(eng.renderer.domElement, 0, 0); const px = g.getImageData(0, 0, W, H).data;
      let sum = 0, n = 0;
      for (let y = Math.max(0, Math.floor(cy - 1.7 * r)); y < Math.min(H, cy + 1.7 * r); y++) for (let x = Math.max(0, Math.floor(cx - 1.7 * r)); x < Math.min(W, cx + 1.7 * r); x++) {
        const d = Math.hypot(x - cx, y - cy); if (d < 1.25 * r || d > 1.6 * r) continue;
        const k = 4 * (y * W + x); sum += 0.2126 * px[k] + 0.7152 * px[k + 1] + 0.0722 * px[k + 2]; n++;
      }
      return n ? +(sum / n).toFixed(2) : null;
    };
    const out = { has_post: !!eng.post, px_radius: +r.toFixed(1) };
    if (eng.post) eng.post.enabled = false; out.ring_off = ring();
    if (eng.post) eng.post.enabled = true; out.ring_on = ring();
    eng.setLowSpec(true); out.ring_lowspec = ring(); eng.setLowSpec(false);
    return out;
  },
  // XR-01 LOD: triangles drawn with the camera near the middle of the world and far away.
  async lod(eng) {
    const { min, max } = eng.extent, c = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, 0];
    const at = d => { eng.camera.position.set(c[0], d * 0.6, -(c[1] - d)); eng.camera.lookAt(c[0], 0, -c[1]); eng.camera.updateMatrixWorld();
      eng.renderer.render(eng.scene, eng.camera); return eng.renderer.info.render.triangles; };
    let lods = 0; eng.root.traverse(o => { if (o.isLOD) lods++; });
    return { lod_on: eng.lodOn, distance: eng.lodDistance, lod_objects: lods, near: at(0.4 * eng.lodDistance), far: at(4 * eng.lodDistance) };
  },
  // XR-02 fly: keys W (forward, looking level) then E (up) for 1 s each, through whatever is in the way.
  async fly(eng) {
    eng.setMode('fly');
    const s0 = { ...eng.walk.state }; eng.walk.state = { ...s0, pitch: 0 };
    const key = (code, down) => dispatchEvent(new KeyboardEvent(down ? 'keydown' : 'keyup', { code }));
    const a = { ...eng.walk.state }; key('KeyW', true); run(eng, 60); key('KeyW', false);
    const b = { ...eng.walk.state }; key('KeyE', true); run(eng, 60); key('KeyE', false);
    const c = { ...eng.walk.state }; key('KeyQ', true); run(eng, 600); key('KeyQ', false);
    const d = { ...eng.walk.state };
    eng.setMode('walk'); const w = { ...eng.walk.state };
    return { forward_m: +Math.hypot(b.x - a.x, b.y - a.y).toFixed(4), forward_dz: +(b.eye - a.eye).toFixed(4), up_m: +(c.eye - b.eye).toFixed(4),
      floor_m: +d.eye.toFixed(4), walk_eye_after: +w.eye.toFixed(4), eye_height: eng.eyeHeight(), camera_z: +eng.camera.position.y.toFixed(4) };
  },
  // T-02 player: works shown, idle -> attract tour (looping), a touch hands control back, fullscreen asked.
  async player(eng) {
    const { player } = await import('./player.js');
    const P = new URLSearchParams(location.search), pl = player(eng, { works: P.get('works'), idle_s: 5 });
    await pl.ready;
    const out = { items: pl.items.map(i => ({ title: i.title, ok: i.ok, w: i.img ? i.img.naturalWidth : 0, seconds: i.audio ? +i.audio.duration.toFixed(2) : null, reason: i.reason || null })) };
    const t0 = eng.realTime; while (!pl.attract && eng.realTime - t0 < 30) eng.step(0.25, false);
    out.attract_after_s = +(eng.realTime - t0).toFixed(2); out.touring = !!eng.tour;
    const t1 = eng.realTime; while (pl.attracts < 2 && eng.realTime - t1 < 600) eng.step(0.25, false);
    out.attract_loops = pl.attracts; out.cursor_hidden = document.body.classList.contains('we-attract');
    dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    out.after_touch = { attract: pl.attract, touring: !!eng.tour, orbit: !!(eng.orbit && eng.orbit.enabled) };
    out.fullscreen = await pl.fullscreen(); out.wake = { supported: pl.wake.supported, held: pl.wake.held, error: pl.wake.error };
    const big = pl.items.find(i => i.img) ? pl.show(pl.items.find(i => i.img).img.src, 'x') : null;
    out.big_opens = !!(big && big.isConnected); if (big) big.remove();
    const r = pl.strip.getBoundingClientRect(); out.strip_inside = r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && r.left >= 0;
    return out;
  },
  // E-02 imported files: what this page could read (and did), what it could not, and every request it made for them.
  async assets(eng) {
    const m = eng.find('model'), out = { template: eng.assets.template, loaded: eng.assets.loaded, missing: [...eng.assets.missing].sort() };
    if (m) { m.updateMatrixWorld(true); const sz = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
      out.model = { loaded: !!m.userData.loaded, size: [+sz.x.toFixed(3), +sz.z.toFixed(3), +sz.y.toFixed(3)], placeholder: m.children.some(c => c.userData.placeholder) }; }
    let img = null; eng.root.traverse(o => { if (!img && o.material && o.material.userData.spec && o.material.userData.spec.image) img = o.material; });
    out.image = img ? { has_map: !!img.map, w: img.map && img.map.image ? img.map.image.width : 0 } : null;
    // Recordings: the real playback path -- the audio unlocks, every sound with a file is fetched, decoded and
    // started through its panner. (Run live: Chromium's --timeout mode stops timers once audio starts.)
    if (eng.audio) { eng.audio.unlock(); await Promise.allSettled(eng.audio.pending || []); }
    out.audio = eng.audio && eng.audio.files ? { ...eng.audio.files, context: eng.audio.ctx && eng.audio.ctx.state } : null;
    out.requests = performance.getEntriesByType('resource').map(e => decodeURIComponent(new URL(e.name).pathname)).filter(p => p.startsWith('/assets/') || p.startsWith('/api/asset'));
    out.captions = eng.captionLog.map(c => c.text);
    return out;
  },
  // M-03 live inputs: nothing asked before the visitor turns it on; then levels move, a react body follows, nothing
  // goes over the network, no media element is added to the page; off stops the devices.
  async inputs(eng) {
    const sleep = ms => new Promise(r => setTimeout(r, ms)), net = { fetch: 0, xhr: 0, ws: 0, beacon: 0 };
    const f0 = window.fetch; window.fetch = (...a) => { net.fetch++; return f0(...a); };
    const x0 = XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open = function (...a) { net.xhr++; return x0.apply(this, a); };
    const w0 = WebSocket.prototype.send; WebSocket.prototype.send = function (...a) { net.ws++; return w0.apply(this, a); };
    if (navigator.sendBeacon) { const b0 = navigator.sendBeacon.bind(navigator); navigator.sendBeacon = (...a) => { net.beacon++; return b0(...a); }; }
    const out = { wanted: [...eng.inputsWanted], requested_before_enable: eng.inputs ? eng.inputs.requests : null };
    out.enabled = { mic: await eng.inputs.enable('mic'), camera: await eng.inputs.enable('camera') };
    const o = eng.find('listener'), max = { mic: 0, camera: 0, scale: 1 }, t0 = performance.now();
    while (performance.now() - t0 < 4000) {
      eng.step(1 / 30, false); max.mic = Math.max(max.mic, eng.inputs.levels.mic); max.camera = Math.max(max.camera, eng.inputs.levels.camera);
      if (o && o.userData.baseScale) max.scale = Math.max(max.scale, o.scale.x / o.userData.baseScale.x);
      await sleep(33);
    }
    const tracks = Object.values(eng.inputs.on).flatMap(d => d.stream.getTracks());
    out.max = { mic: +max.mic.toFixed(3), camera: +max.camera.toFixed(3), scale: +max.scale.toFixed(3) };
    out.tracks_on = tracks.map(t => t.kind + ':' + t.readyState);
    out.network_during_capture = net; out.media_elements_in_page = document.querySelectorAll('video,audio').length;
    eng.inputs.disable('mic'); eng.inputs.disable('camera'); eng.step(1 / 30, false);
    out.tracks_after_off = tracks.map(t => t.kind + ':' + t.readyState); out.levels_after_off = { ...eng.inputs.levels };
    out.scale_after_off = o && o.userData.baseScale ? +(o.scale.x / o.userData.baseScale.x).toFixed(3) : null;
    return out;
  },
};
