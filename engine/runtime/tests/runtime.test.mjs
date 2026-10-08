// node --test engine/runtime/tests   -- pure modules only (no DOM, no WebGL)
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { check, extent, eyeHeight, defaultViews } from '../src/world.js';
import { step, look, pose } from '../src/controls/walk.js';
import { vector } from '../src/controls/joystick.js';

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`);
const garden = JSON.parse(readFileSync(new URL('../../worlds/contradiction_garden.world.json', import.meta.url)));

test('demo world is valid', () => assert.deepEqual(check(garden), []));

test('check reports every problem and does not modify the world', () => {
  const fx = JSON.parse(readFileSync(new URL('./fixtures_check.json', import.meta.url)));
  const w = fx[1].world, before = JSON.stringify(w), bad = check(w);
  assert.equal(JSON.stringify(w), before);
  for (const frag of ['format', 'name', 'bounds', 'pos', 'type must be', 'duplicated', 'rot', 'scale', '"nope"', 'children', 'views.bad', 'spawn', 'giant', 'fly'])
    assert.ok(bad.some(b => b.includes(frag)), `missing: ${frag}\n${bad.join('\n')}`);
});

test('eye heights: child 1.1 m, adult 1.7 m, world may add more', () => {
  close(eyeHeight(garden, 'child'), 1.1); close(eyeHeight(garden, 'adult'), 1.7);
  close(eyeHeight({ player: { eye_heights: { dog: 0.5 } } }, 'dog'), 0.5);
});

test('extent and default views frame the world', () => {
  const w = { format: 'world/1', name: 'w', entities: [{ type: 'box', pos: [10, 20, 0], size: [2, 2, 2] }] };
  const e = extent(w); assert.ok(e.min[0] <= 9 && e.max[0] >= 11 && e.min[1] <= 19 && e.max[1] >= 21);
  const v = defaultViews(w); close(v.eye.pos[2], 1.7);
});

test('walk: forward at yaw 90 deg moves north at speed', () => {
  const s = step({ x: 0, y: 0, yaw: Math.PI / 2, pitch: 0, eye: 1.7 }, { fwd: 1 }, 1, { speed: 1.4 });
  close(s.x, 0, 1e-12); close(s.y, 1.4, 1e-12);
});

test('walk: strafe right at yaw 90 deg moves east; diagonal is not faster', () => {
  const s = step({ x: 0, y: 0, yaw: Math.PI / 2, pitch: 0 }, { strafe: 1 }, 1, { speed: 1 });
  close(s.x, 1, 1e-12); close(s.y, 0, 1e-12);
  const d = step({ x: 0, y: 0, yaw: 0, pitch: 0 }, { fwd: 1, strafe: 1 }, 1, { speed: 1 });
  close(Math.hypot(d.x, d.y), 1, 1e-12);
});

test('walk: stops at a collider (keeps radius), slides along it, ignores ankle-high ones', () => {
  const o = { speed: 1, radius: 0.25, colliders: [[2, -5, 3, 5, 2.0], [0.5, -1, 0.7, 1, 0.1]] };
  let s = { x: 0, y: 0, yaw: 0, pitch: 0 };
  for (let i = 0; i < 400; i++) s = step(s, { fwd: 1 }, 0.01, o);
  assert.ok(s.x <= 2 - 0.25 + 1e-9 && s.x > 2 - 0.25 - 0.011, `x=${s.x}`);
  const sl = step({ ...s, yaw: Math.PI / 4 }, { fwd: 1 }, 0.1, o);      // pushing diagonally into the wall still moves along it
  assert.ok(sl.y > s.y);
});

test('walk: bounds clamp', () => {
  const s = step({ x: 0.3, y: 0.3, yaw: Math.PI, pitch: 0 }, { fwd: 1 }, 1, { speed: 5, radius: 0.25, bounds: { min: [0, 0], max: [10, 10] } });
  close(s.x, 0.25);
});

test('look: pitch is limited, pose points where it looks', () => {
  const s = look({ x: 0, y: 0, yaw: 0, pitch: 0, eye: 1.1 }, 0, 10);
  assert.ok(s.pitch < Math.PI / 2);
  const p = pose({ x: 1, y: 2, yaw: Math.PI / 2, pitch: 0, eye: 1.1 });
  assert.deepEqual(p.pos, [1, 2, 1.1]); close(p.target[0], 1, 1e-12); close(p.target[1], 3, 1e-12);
});

test('joystick: dead zone, up is forward, saturates at 1', () => {
  assert.deepEqual(vector(3, 3, 56), { x: 0, y: 0 });
  const v = vector(0, -56, 56); close(v.x, 0); close(v.y, 1);
  const f = vector(0, -500, 56); close(Math.hypot(f.x, f.y), 1);
  const h = vector(28, 0, 56); close(h.x, (0.5 - 0.12) / 0.88); close(h.y, 0);
});
