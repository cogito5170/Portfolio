// First-person walking (desktop: WASD/arrows + drag to look, Shift runs; phone: left joystick + right-side drag).
// The kinematics are a pure function (step) so node can test them without a browser.

// state = {x, y, yaw, pitch, eye}   yaw: radians from +x (east) counter-clockwise; pitch: radians, + looks up.
// input = {fwd, strafe, up} in [-1,1] (strafe + = right, up + = rise; up is used when flying), run: bool.
// opts  = {speed m/s, run_factor, radius m, bounds: {min:[x,y], max:[x,y]}|null, colliders: [[x0,y0,x1,y1,ztop],...],
//          fly: bool, fly_speed m/s, z_max m}
// Flying (XR-02): forward follows the gaze (pitch included), up/down moves straight up or down, nothing blocks;
// the eye stays between 0.3 m and z_max, and inside the bounds.
export function step(state, input, dt, opts = {}) {
  if (opts.fly) return flyStep(state, input, dt, opts);
  const speed = (opts.speed ?? 1.4) * (input.run ? (opts.run_factor ?? 2.2) : 1);
  let f = input.fwd || 0, s = input.strafe || 0;
  const n = Math.hypot(f, s); if (n > 1) { f /= n; s /= n; }
  const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
  const dx = (f * cy + s * sy) * speed * dt, dy = (f * sy - s * cy) * speed * dt;
  const r = opts.radius ?? 0.25, cols = (opts.colliders || []).filter(c => c[4] === undefined || c[4] > 0.3);  // ankle-high things don't block
  const hits = (x, y) => cols.some(c => x > c[0] - r && x < c[2] + r && y > c[1] - r && y < c[3] + r);
  let x = state.x, y = state.y;
  if (!hits(x + dx, y)) x += dx;                          // axis-separated: slide along walls instead of sticking
  if (!hits(x, y + dy)) y += dy;
  if (opts.bounds) {
    x = Math.min(opts.bounds.max[0] - r, Math.max(opts.bounds.min[0] + r, x));
    y = Math.min(opts.bounds.max[1] - r, Math.max(opts.bounds.min[1] + r, y));
  }
  return { ...state, x, y };
}

function flyStep(state, input, dt, opts) {
  const speed = (opts.fly_speed ?? 4) * (input.run ? (opts.run_factor ?? 2.2) : 1);
  let f = input.fwd || 0, s = input.strafe || 0;
  const n = Math.hypot(f, s); if (n > 1) { f /= n; s /= n; }
  const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw), cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
  let x = state.x + (f * cy * cp + s * sy) * speed * dt, y = state.y + (f * sy * cp - s * cy) * speed * dt;
  let z = state.eye + (f * sp + Math.max(-1, Math.min(1, input.up || 0))) * speed * dt;
  z = Math.min(opts.z_max ?? 200, Math.max(0.3, z));
  if (opts.bounds) { x = Math.min(opts.bounds.max[0], Math.max(opts.bounds.min[0], x)); y = Math.min(opts.bounds.max[1], Math.max(opts.bounds.min[1], y)); }
  return { ...state, x, y, eye: z };
}

export function look(state, dYaw, dPitch) {
  const lim = Math.PI / 2 - 0.05;
  return { ...state, yaw: state.yaw + dYaw, pitch: Math.min(lim, Math.max(-lim, state.pitch + dPitch)) };
}

// Camera pose in world axes (z up): eye position and a point 1 m ahead.
export function pose(state) {
  const cp = Math.cos(state.pitch);
  return { pos: [state.x, state.y, state.eye], target: [state.x + Math.cos(state.yaw) * cp, state.y + Math.sin(state.yaw) * cp, state.eye + Math.sin(state.pitch)] };
}

// Browser side: wires keys, pointer drag and the joystick to step()/look(). `dom` is the canvas.
export class WalkControls {
  constructor(dom, joystick, opts) {
    this.dom = dom; this.joy = joystick; this.opts = opts; this.keys = new Set(); this.enabled = false; this.state = null;
    this.lookSens = opts.look_sensitivity ?? 0.005; this._drag = null;
    this._kd = e => { if (this.enabled) this.keys.add(e.code); };
    this._ku = e => this.keys.delete(e.code);
    this._pd = e => {
      if (!this.enabled || (this.joy && this.joy.owns(e.pointerId))) return;
      this._drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
      try { dom.setPointerCapture(e.pointerId); } catch (_) { /* synthetic pointers cannot be captured */ }
    };
    this._pm = e => {
      if (!this._drag || e.pointerId !== this._drag.id) return;
      const dx = e.clientX - this._drag.x, dy = e.clientY - this._drag.y; this._drag.x = e.clientX; this._drag.y = e.clientY;
      this.state = look(this.state, -dx * this.lookSens, -dy * this.lookSens);
    };
    this._pu = e => { if (this._drag && e.pointerId === this._drag.id) this._drag = null; };
    addEventListener('keydown', this._kd); addEventListener('keyup', this._ku);
    dom.addEventListener('pointerdown', this._pd); dom.addEventListener('pointermove', this._pm);
    dom.addEventListener('pointerup', this._pu); dom.addEventListener('pointercancel', this._pu);
  }
  input() {
    const k = c => this.keys.has(c) ? 1 : 0;
    let fwd = k('KeyW') + k('ArrowUp') - k('KeyS') - k('ArrowDown'), strafe = k('KeyD') + k('ArrowRight') - k('KeyA') - k('ArrowLeft');
    if (this.joy) { const v = this.joy.value(); fwd += v.y; strafe += v.x; }
    const up = k('KeyE') + k('Space') + (this.vert || 0) - k('KeyQ') - k('ControlLeft');
    return { fwd, strafe, up, run: this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') || (this.joy && this.joy.magnitude() > 0.95) };
  }
  update(dt) { if (this.enabled && this.state) this.state = step(this.state, this.input(), dt, this.opts); return this.state; }
  dispose() {
    removeEventListener('keydown', this._kd); removeEventListener('keyup', this._ku);
    for (const [k, f] of [['pointerdown', this._pd], ['pointermove', this._pm], ['pointerup', this._pu], ['pointercancel', this._pu]]) this.dom.removeEventListener(k, f);
  }
}
