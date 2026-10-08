// Serial-chain forward kinematics, the JS twin of <repo>/kinematics/kinematics.py (same order of products:
// T = prod_i Trans(xyz_i) * RPY(rpy_i) * AxisAngle(axis_i, q_i)). Pure module: node tests it against the
// reference's test_vectors.json. Matrices are row-major 4x4 arrays, like the reference.
//
// chain = {joints: [{name, type: 'revolute'|'continuous'|'fixed', xyz, rpy, axis, lower, upper}]}

const ACTIVE = new Set(['revolute', 'continuous']);

export const mul = (A, B) => A.map((r, i) => [0, 1, 2, 3].map(j => r[0] * B[0][j] + r[1] * B[1][j] + r[2] * B[2][j] + r[3] * B[3][j]));
export const I4 = () => [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
const trans = ([x, y, z]) => [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]];

export function rpy([r, p, y]) {          // R = Rz(y) Ry(p) Rx(r)
  const cr = Math.cos(r), sr = Math.sin(r), cp = Math.cos(p), sp = Math.sin(p), cy = Math.cos(y), sy = Math.sin(y);
  return [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, 0], [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, 0], [-sp, cp * sr, cp * cr, 0], [0, 0, 0, 1]];
}

export function axisAngle(axis, a) {
  const L = Math.hypot(...axis), [x, y, z] = axis.map(v => v / L), c = Math.cos(a), s = Math.sin(a), C = 1 - c;
  return [[x * x * C + c, x * y * C - z * s, x * z * C + y * s, 0], [y * x * C + z * s, y * y * C + c, y * z * C - x * s, 0], [z * x * C - y * s, z * y * C + x * s, z * z * C + c, 0], [0, 0, 0, 1]];
}

export const active = chain => chain.joints.filter(j => ACTIVE.has(j.type));

// Local transform of joint i at angle q (q ignored for fixed joints).
export function local(j, q) {
  const T = mul(trans(j.xyz || [0, 0, 0]), rpy(j.rpy || [0, 0, 0]));
  return ACTIVE.has(j.type) ? mul(T, axisAngle(j.axis || [0, 0, 1], q)) : T;
}

// -> {frames: [T after each joint], points: [origin of each joint ..., tip]} (points match forward_kinematics_full)
export function fk(chain, q) {
  const n = active(chain).length;
  if (q.length !== n) throw new Error(`need ${n} joint angles, got ${q.length}`);
  let T = I4(), k = 0;
  const frames = [], points = [];
  for (const j of chain.joints) {
    points.push([T[0][3], T[1][3], T[2][3]]);
    T = mul(T, local(j, ACTIVE.has(j.type) ? q[k++] : 0));
    frames.push(T);
  }
  points.push([T[0][3], T[1][3], T[2][3]]);
  return { frames, points };
}

export const tip = (chain, q) => fk(chain, q).points.at(-1);

export function limitViolations(chain, Q) {
  const act = active(chain), out = [];
  Q.forEach((q, s) => q.forEach((a, i) => { if (a < act[i].lower || a > act[i].upper) out.push([s, act[i].name, a, act[i].lower, act[i].upper]); }));
  return out;
}

// Joint angles at time t by linear interpolation of a sampled trajectory {t:[...], q:[[...]], pen:[...]}.
export function sample(traj, t) {
  const T = traj.t, n = T.length;
  if (t <= T[0]) return { q: traj.q[0], i: 0, pen: traj.pen[0] };
  if (t >= T[n - 1]) return { q: traj.q[n - 1], i: n - 1, pen: traj.pen[n - 1] };
  let a = 0, b = n - 1;
  while (b - a > 1) { const m = (a + b) >> 1; if (T[m] <= t) a = m; else b = m; }
  const u = (t - T[a]) / (T[b] - T[a]);
  return { q: traj.q[a].map((v, k) => v + (traj.q[b][k] - v) * u), i: a, pen: traj.pen[a] && traj.pen[b] ? 1 : 0, u };
}
