// worldengine runtime: world JSON -> three.js scene you can orbit or walk through, on desktop and phone.
//
//   const eng = new Engine(container, {headless});  eng.registry.use(core, eng.mats) ...
//   await eng.load(world, {view: 'aerial', mode: 'orbit'});  eng.start();      // or eng.step(dt) yourself
//
// World axes are z up (x east, y north). One group (root) turns them into three's y-up; nothing else converts.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as W from './world.js';
import { Registry } from './registry.js';
import { Library } from './materials.js';
import { WalkControls, pose } from './controls/walk.js';
import { Joystick } from './controls/joystick.js';
import { AudioManager } from './audio.js';
import { physics, tourAt } from './physics.js';
import { Interaction } from './interact.js';
import { Captions } from './ui/captions.js';

export const T3 = (x, y, z) => new THREE.Vector3(x, z, -y);            // world (z up) -> three (y up)
export const FROM3 = v => [v.x, -v.z, v.y];
// Authored fov is vertical on landscape screens; on portrait phones it is kept as the horizontal fov instead,
// so a view framed on a PC still shows the whole subject on a phone (capped at 90 deg).
export const fitFov = (fov, aspect) => aspect >= 1 ? fov : Math.min(90, 2 * Math.atan(Math.tan(fov * Math.PI / 360) / aspect) * 180 / Math.PI);

export class Engine {
  constructor(container, { headless = false, width, height } = {}) {
    this.container = container; this.headless = headless;
    this.registry = new Registry(); this.mats = new Library();
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(headless ? 1 : Math.min(2, devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.size = [width || innerWidth || 1280, height || innerHeight || 800];
    this.renderer.setSize(...this.size);
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.style.touchAction = 'none';               // we handle touch gestures ourselves
    this.camera = new THREE.PerspectiveCamera(50, this.size[0] / this.size[1], 0.05, 5000);
    this.t = 0; this.realTime = 0; this.listeners = {}; this.mode = 'none';
    this.captionLog = []; this.captions = new Captions(container); this.tour = null; this.lowspec = false;
    if (!headless) addEventListener('resize', () => this.resize(innerWidth, innerHeight));
  }

  on(ev, fn) { (this.listeners[ev] ||= []).push(fn); return this; }
  emit(ev, x) { for (const f of this.listeners[ev] || []) f(x); }

  resize(w, h) {
    this.size = [w, h]; this.renderer.setSize(w, h); this.camera.aspect = w / h;
    this.camera.fov = fitFov(this.mode === 'walk' ? 70 : (this.views?.[this.viewName]?.fov ?? 50), w / h); this.camera.updateProjectionMatrix();
  }

  async load(world, { view, mode, eye } = {}) {
    const bad = W.check(world, this.registry.known());
    if (bad.length) throw new Error('invalid world: ' + bad.slice(0, 5).join('; '));
    this.world = world; this.mats.world = world.materials || {}; this.mats.cache.clear();
    this.extent = W.extent(world);
    this.views = { ...W.defaultViews(world), ...(world.views || {}) };
    this.scene = new THREE.Scene();
    this.root = new THREE.Group(); this.root.rotation.x = -Math.PI / 2; this.scene.add(this.root);
    this.animated = []; this.colliders = [];
    this.phys = physics(world);
    if (!this.audio) this.audio = new AudioManager(this);
    this.audio.sources = [];
    this._environment(world.environment || {});
    let seed = 12345;
    const ctx = { THREE, mats: this.mats, world, view: view || 'aerial', extent: this.extent, engine: this, audio: this.audio,
                  rnd: () => ((seed = (seed * 16807) % 2147483647) / 2147483647) };
    for (const e of world.entities) this.root.add(this._build(e, ctx, [0, 0, 0]));
    this._solidColliders();
    this.eyeName = eye || (world.player && world.player.eye) || 'adult';
    this.setView(view && this.views[view] ? view : Object.keys(this.views)[0]);
    this.setMode(mode || (world.controls && world.controls.default) || 'orbit');
    if (!this.interaction) this.interaction = new Interaction(this);
    if (this.mats.missing.size) console.warn('materials not defined, default used:', [...this.mats.missing]);
    this.emit('load', world);
    return this;
  }

  _environment(env) {
    const s = this.scene, { min, max } = this.extent, big = Math.max(max[0] - min[0], max[1] - min[1], 4), H = max[2];
    s.background = new THREE.Color(env.background || '#f4f1ea');
    this.renderer.toneMappingExposure = env.exposure ?? 0.88;
    if (env.env_map !== null) {
      const pm = new THREE.PMREMGenerator(this.renderer);
      s.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; s.environmentIntensity = env.env_intensity ?? 0.55;
    }
    if (env.fog) s.fog = new THREE.FogExp2(new THREE.Color(env.fog.color || env.background || '#f4f1ea'), env.fog.density ?? 0.02);
    s.add(new THREE.HemisphereLight(0xfffaf0, 0xcdbd9c, env.ambient ?? 0.75));
    const sun = env.sun || {}, dir = new THREE.Vector3(...(sun.dir || [-0.25, -0.33, 0.75])).normalize();
    const c = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, 0];
    const L = new THREE.DirectionalLight(new THREE.Color(sun.color || '#fff3e0'), sun.intensity ?? 2.2);
    L.position.copy(T3(c[0] + dir.x * big, c[1] + dir.y * big, dir.z * big + H)); L.target.position.copy(T3(...c));
    L.castShadow = sun.shadows !== false; L.shadow.mapSize.set(this.headless ? 4096 : 2048, this.headless ? 4096 : 2048);
    Object.assign(L.shadow.camera, { left: -0.75 * big, right: 0.75 * big, top: 0.75 * big, bottom: -0.75 * big, near: 0.1, far: 3 * big + 3 * H });
    L.shadow.bias = -0.0004; L.shadow.radius = 4; s.add(L, L.target); this.sun = L;
  }

  _build(e, ctx, off) {
    const def = this.registry.types.get(e.type);
    const pos = e.pos || [0, 0, 0], abs = pos.map((v, k) => v + off[k]);
    ctx.collide = (x0, y0, x1, y1, ztop) => this.colliders.push([x0 + abs[0], y0 + abs[1], x1 + abs[0], y1 + abs[1], ztop]);
    const o = def.build(e, ctx);
    o.position.set(...pos);
    if (e.rot) o.rotation.set(...e.rot.map(d => d * Math.PI / 180));
    if (e.scale !== undefined) o.scale.set(...(typeof e.scale === 'number' ? [e.scale, e.scale, e.scale] : e.scale));
    o.userData = { ...o.userData, id: e.id, type: e.type, entity: e, solid: !!e.solid,
      base: { pos: o.position.clone(), rot: o.rotation.clone() } };
    if ((e.behaviors && e.behaviors.length) || o.userData.tick) this.animated.push(o);   // tick: a type that animates itself (robot)
    for (const ch of e.children || []) o.add(this._build(ch, ctx, abs));
    return o;
  }

  _solidColliders() {
    this.scene.updateMatrixWorld(true);
    const b = new THREE.Box3();
    this.root.traverse(o => {
      if (!o.userData.solid) return;
      b.setFromObject(o); const lo = FROM3(b.min), hi = FROM3(b.max);
      this.colliders.push([Math.min(lo[0], hi[0]), Math.min(lo[1], hi[1]), Math.max(lo[0], hi[0]), Math.max(lo[1], hi[1]), Math.max(lo[2], hi[2])]);
    });
  }

  find(id) { let f = null; this.root.traverse(o => { if (o.userData.id === id) f = o; }); return f; }

  setView(name) {
    const v = this.views[name]; if (!v) return;
    this.viewName = name; const c = this.camera;
    c.fov = fitFov(v.fov, this.size[0] / this.size[1]); c.near = v.near || Math.max(0.05, Math.max(...this.extent.max) / 2000); c.updateProjectionMatrix();
    c.position.copy(T3(...v.pos)); c.lookAt(T3(...v.target));
    if (this.orbit) { this.orbit.target.copy(T3(...v.target)); this.orbit.update(); }
    if (this.walk && this.mode === 'walk') this._placeWalker(v);
    this.emit('view', name);
  }

  eyeHeight() { return W.eyeHeight(this.world, this.eyeName); }

  setEye(name) {
    this.eyeName = name;
    if (this.walk && this.walk.state) this.walk.state = { ...this.walk.state, eye: this.eyeHeight() };
    this.emit('eye', name);
  }

  _placeWalker(v) {
    const pl = this.world.player || {};
    let x, y, yaw;
    if (pl.spawn && !v) { [x, y] = pl.spawn; yaw = (pl.yaw_deg ?? 90) * Math.PI / 180; }
    else { const p = FROM3(this.camera.position); x = p[0]; y = p[1];
      const d = new THREE.Vector3(); this.camera.getWorldDirection(d); const dw = FROM3(d); yaw = Math.atan2(dw[1], dw[0]); }
    const { min, max } = this.extent;
    x = Math.min(max[0] - 0.3, Math.max(min[0] + 0.3, x)); y = Math.min(max[1] - 0.3, Math.max(min[1] + 0.3, y));
    this.walk.state = { x, y, yaw, pitch: -0.08, eye: this.eyeHeight() };
  }

  setMode(mode) {
    if (this.headless && !this.selftest) { this.mode = mode; if (mode === 'walk') this._walkHeadless(); return; }
    const dom = this.renderer.domElement;
    if (!this.orbit) {
      this.orbit = new OrbitControls(this.camera, dom); this.orbit.enableDamping = !this.headless;
      this.orbit.target.copy(T3(...this.views[this.viewName].target)); this.orbit.update();
    }
    if (!this.walk) {
      this.joystick = new Joystick(this.container);
      const { min, max } = this.extent;
      this.walk = new WalkControls(dom, this.joystick, { speed: (this.world.player || {}).speed ?? 1.4, colliders: this.colliders,
        bounds: { min: [min[0], min[1]], max: [max[0], max[1]] } });
    }
    this.mode = mode;
    this.orbit.enabled = mode === 'orbit'; this.walk.enabled = this.joystick.enabled = mode === 'walk';
    if (mode === 'walk') { this._placeWalker(this.world.player && this.world.player.spawn ? null : this.views[this.viewName]); this.camera.fov = fitFov(70, this.size[0] / this.size[1]); this.camera.updateProjectionMatrix(); }
    else this.setView(this.viewName);
    this.emit('mode', mode);
  }

  _walkHeadless() {   // a still frame from the walker's eye (spawn or the current view), no input devices
    this.walk = { state: null, update() { return this.state; } };
    this._placeWalker(this.world.player && this.world.player.spawn ? null : this.views[this.viewName]);
    this.camera.fov = fitFov(70, this.size[0] / this.size[1]); this.camera.updateProjectionMatrix(); this._applyWalk();
  }

  _applyWalk() {
    const p = pose(this.walk.state); this.camera.position.copy(T3(...p.pos)); this.camera.lookAt(T3(...p.target));
  }

  // World time runs at rules.physics.time_scale (XR-03): behaviours and robots read it. The visitor's own
  // movement, captions, gaze and tours run on real time.
  step(dt, render = true) {          // render=false: advance the simulation only (tests, catch-up)
    this.realTime += dt;
    this.t += dt * (this.phys ? this.phys.timeScale : 1);
    for (const o of this.animated) {
      if (o.userData.paused) continue;
      if (o.userData.tick) o.userData.tick(this.t, dt);
      for (const b of o.userData.entity.behaviors || []) { const f = this.registry.behaviors.get(b.type); if (f) f(o, b, this.t, dt, this); }
    }
    if (this.tour) this._tourStep();
    else if (this.interaction && (!this.headless || this.selftest)) this.interaction.step();
    if (this.audio) this.audio.update(this.camera);
    if (this.mode === 'walk' && this.walk) { this.walk.update(dt); if (this.walk.state) this._applyWalk(); }
    else if (this.orbit && this.orbit.enabled) this.orbit.update();
    this.emit('step', dt);
    if (render) this.renderer.render(this.scene, this.camera);
  }

  caption(text, obj, seconds) {
    this.captionLog.push({ t: +this.realTime.toFixed(3), text, id: obj && obj.userData ? obj.userData.id : null });
    this.captions.show(text, seconds);
    this.emit('caption', text);
  }

  // Artist-defined camera tour (XR-02/XR-11). Every stop has a caption (world check).
  startTour(id) {
    const tr = (this.world.tours || []).find(t => t.id === id);
    if (!tr) return false;
    if (this.orbit) this.orbit.enabled = false;
    if (this.walk && this.walk.enabled !== undefined) this.walk.enabled = false;
    const d = new THREE.Vector3(); this.camera.getWorldDirection(d);
    const p = FROM3(this.camera.position), dir = FROM3(d);
    this.tour = { tr, t0: this.realTime, shown: -1, start: { pos: p, target: p.map((x, i) => x + dir[i] * 5), fov: this.camera.fov } };
    this.emit('tour', id); return true;
  }
  _tourStep() {
    const T = this.tour, s = tourAt(T.tr.stops, this.realTime - T.t0, T.start);
    this.camera.position.copy(T3(...s.pos)); this.camera.lookAt(T3(...s.target));
    if (s.fov) { this.camera.fov = fitFov(s.fov, this.size[0] / this.size[1]); this.camera.updateProjectionMatrix(); }
    if (s.arrived && s.stop > T.shown) { T.shown = s.stop; this.caption(T.tr.stops[s.stop].caption, null, T.tr.stops[s.stop].dwell_s); }
    if (s.done) { this.tour = null; this.emit('tourEnd', T.tr.id); if (this.orbit) { this.orbit.enabled = this.mode === 'orbit'; this.orbit.target.copy(T3(...s.target)); } }
  }

  // Low-spec mode (XR-07): one pixel per pixel, no shadows, no environment reflections, at most 4 point lights.
  setLowSpec(on = true) {
    this.lowspec = on;
    this.renderer.setPixelRatio(on ? 1 : (this.headless ? 1 : Math.min(2, devicePixelRatio || 1)));
    this.renderer.shadowMap.enabled = !on;
    if (this.scene) {
      if (on) { this._env = this.scene.environment; this.scene.environment = null; } else if (this._env) this.scene.environment = this._env;
      let n = 0;
      this.scene.traverse(o => { if (o.isPointLight || o.isSpotLight) o.visible = !on || n++ < 4; if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.needsUpdate = true; }); });
    }
    this.emit('lowspec', on);
  }

  start({ autoLowSpec = true } = {}) {
    const clock = new THREE.Clock();
    let frames = 0, t0 = performance.now();
    this.renderer.setAnimationLoop(() => {
      this.step(Math.min(0.1, clock.getDelta()));
      if (autoLowSpec && !this.lowspec && t0 !== null && ++frames === 60) {      // FPS probe over the first 60 frames
        const fps = 60000 / (performance.now() - t0); t0 = null;
        if (fps < 30) { this.setLowSpec(true); this.caption(`저사양 모드로 바꿨어요 (처음 측정 ${fps.toFixed(0)} fps)`); }
      }
    });
  }
}
