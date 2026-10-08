// On-screen joystick for phones (XR-12). Appears where the thumb lands in the left 40% of the screen.

// Pure mapping, tested in node: thumb offset (px, screen y down) -> {x: right, y: forward} in [-1,1], with a dead zone.
export function vector(dx, dy, radius, dead = 0.12) {
  let x = dx / radius, y = -dy / radius;
  const m = Math.hypot(x, y);
  if (m > 1) { x /= m; y /= m; }
  const mm = Math.min(1, m);
  if (mm < dead) return { x: 0, y: 0 };
  const k = (mm - dead) / (1 - dead) / mm;                  // rescale so output starts at 0 just outside the dead zone
  return { x: x * k, y: y * k };
}

export class Joystick {
  constructor(parent, { radius = 56, zone = 0.4 } = {}) {
    this.radius = radius; this.zone = zone; this.id = null; this.v = { x: 0, y: 0 }; this.enabled = false;
    const el = this.el = document.createElement('div'); el.className = 'we-joy';
    el.innerHTML = '<div class="we-joy-base"></div><div class="we-joy-knob"></div>';
    parent.appendChild(el);
    this.base = el.children[0]; this.knob = el.children[1];
    this._down = e => {
      if (!this.enabled || this.id !== null || e.clientX > innerWidth * this.zone) return;
      if (e.pointerType === 'mouse') return;                 // desktop uses the keyboard
      this.id = e.pointerId; this.ox = e.clientX; this.oy = e.clientY; this._place(0, 0, true); e.stopPropagation();
    };
    this._move = e => {
      if (e.pointerId !== this.id) return;
      const dx = e.clientX - this.ox, dy = e.clientY - this.oy, m = Math.hypot(dx, dy), k = m > this.radius ? this.radius / m : 1;
      this.v = vector(dx, dy, this.radius); this._place(dx * k, dy * k, true);
    };
    this._up = e => { if (e.pointerId !== this.id) return; this.id = null; this.v = { x: 0, y: 0 }; this._place(0, 0, false); };
    addEventListener('pointerdown', this._down, true); addEventListener('pointermove', this._move, true);
    addEventListener('pointerup', this._up, true); addEventListener('pointercancel', this._up, true);
  }
  _place(dx, dy, on) {
    this.el.style.display = on ? 'block' : 'none';
    this.el.style.left = this.ox + 'px'; this.el.style.top = this.oy + 'px';
    this.knob.style.transform = `translate(${dx}px, ${dy}px)`;
  }
  owns(pointerId) { return pointerId === this.id; }
  value() { return this.v; }
  magnitude() { return Math.hypot(this.v.x, this.v.y); }
  dispose() {
    removeEventListener('pointerdown', this._down, true); removeEventListener('pointermove', this._move, true);
    removeEventListener('pointerup', this._up, true); removeEventListener('pointercancel', this._up, true); this.el.remove();
  }
}
