import test from 'node:test';
import assert from 'node:assert/strict';
import { physics, fallHeight, tourAt, tourDuration, DEFAULT_G } from '../src/physics.js';

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`);

test('physics defaults and world values', () => {
  assert.deepEqual(physics({}), { g: DEFAULT_G, timeScale: 1 });
  assert.deepEqual(physics({ rules: { physics: { gravity_mps2: 1.62, time_scale: 0.6 } } }), { g: 1.62, timeScale: 0.6 });
});

test('fall: free fall, first contact, bounce apex, rest; no gravity floats', () => {
  const g = 9.81, h0 = 2, e = 0.5, t1 = Math.sqrt(2 * h0 / g);
  close(fallHeight(0, h0, g, e), 2); close(fallHeight(t1 / 2, h0, g, e), h0 - 0.5 * g * (t1 / 2) ** 2);
  close(fallHeight(t1, h0, g, e), 0, 1e-9);
  const v = g * t1 * e;                                  // apex of the first bounce = v^2/2g = e^2 h0
  close(fallHeight(t1 + v / g, h0, g, e), e * e * h0, 1e-9);
  assert.equal(fallHeight(100, h0, g, e), 0);
  assert.equal(fallHeight(5, h0, 0, e), h0);
  assert.ok(fallHeight(1, h0, 1.62, e) > fallHeight(1, h0, 9.81, e));   // moon gravity falls slower
});

test('tour: moves, dwells, ends at the last stop', () => {
  const start = { pos: [0, 0, 1], target: [1, 0, 1], fov: 50 };
  const stops = [{ pos: [10, 0, 1], target: [10, 5, 1], dwell_s: 3 }, { pos: [10, 10, 2], target: [0, 10, 0], dwell_s: 2, move_s: 1, fov: 40 }];
  assert.equal(tourDuration(stops), 2 + 3 + 1 + 2);
  close(tourAt(stops, 1, start).pos[0], 5);              // halfway through a smoothstep move
  assert.deepEqual(tourAt(stops, 3, start).pos, [10, 0, 1]); assert.equal(tourAt(stops, 3, start).arrived, true);
  assert.equal(tourAt(stops, 6.5, start).stop, 1); assert.equal(tourAt(stops, 6.5, start).fov, 40);
  assert.equal(tourAt(stops, 99, start).done, true);
});
