// World rules -> runtime physics (XR-03). Pure functions, tested in node.
//
// rules.physics = {gravity_mps2 (default 9.81), time_scale (default 1)}: time_scale scales the world clock that
// behaviours and robots read; gravity drives the `fall` behaviour.

export const DEFAULT_G = 9.81;

export function physics(world) {
  const p = (world.rules && world.rules.physics) || {};
  return { g: p.gravity_mps2 ?? DEFAULT_G, timeScale: p.time_scale ?? 1 };
}

// Height above the resting point of a ball dropped from h0 at t=0, bouncing with restitution e (0..1), gravity g.
// Analytic per bounce, so any t (headless renders jump straight to it) gives the same answer as stepping.
export function fallHeight(t, h0, g, e = 0.5) {
  if (t <= 0) return h0;
  if (g <= 0) return h0;                              // no gravity: it floats where it was put
  let tFirst = Math.sqrt(2 * h0 / g);
  if (t < tFirst) return h0 - 0.5 * g * t * t;
  t -= tFirst;
  let v = g * tFirst * e;                             // take-off speed after the first bounce
  while (v > 1e-3) {
    const flight = 2 * v / g;
    if (t < flight) return v * t - 0.5 * g * t * t;
    t -= flight; v *= e;
  }
  return 0;
}

// Tour: where is the camera at time t (seconds since the tour started)?
// Each stop: move for `move_s` (default 2) with smoothstep, then dwell. Returns {pos, target, fov, stop, arrived, done}.
export function tourAt(stops, t, start) {
  let from = start, clock = 0;
  for (let i = 0; i < stops.length; i++) {
    const s = stops[i], move = s.move_s ?? 2;
    if (t < clock + move) {
      const u = (t - clock) / move, k = u * u * (3 - 2 * u);
      const mix = (a, b) => a.map((x, j) => x + (b[j] - x) * k);
      return { pos: mix(from.pos, s.pos), target: mix(from.target, s.target), fov: from.fov + ((s.fov ?? from.fov) - from.fov) * k, stop: i, arrived: false, done: false };
    }
    clock += move;
    if (t < clock + s.dwell_s) return { pos: s.pos, target: s.target, fov: s.fov ?? from.fov, stop: i, arrived: true, done: false };
    clock += s.dwell_s;
    from = { pos: s.pos, target: s.target, fov: s.fov ?? from.fov };
  }
  return { ...from, stop: stops.length - 1, arrived: true, done: true };
}

export function tourDuration(stops) { return stops.reduce((a, s) => a + (s.move_s ?? 2) + s.dwell_s, 0); }
