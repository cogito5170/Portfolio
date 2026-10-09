// node --test: the editor's document model (undo history, paths, ids, field kinds). No browser needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Doc, at, flatten, duplicate, remove, uniqueId, newEntity, fieldKind, TEMPLATES } from '../src/editor/model.js';
import { check } from '../src/world.js';

const W = () => ({ format: 'world/1', name: 'w', rules: { axes: { density: 0.5 } },
  entities: [{ id: 'a', type: 'box', pos: [0, 0, 0] }, { id: 'g', type: 'group', children: [{ id: 'b', type: 'sphere', radius: 0.5 }] }] });

test('a slider drag (many live changes) is one undo step; undo and redo restore exactly', () => {
  const d = new Doc(W());
  for (const v of [0.4, 0.3, 0.2]) d.live(w => { w.rules.axes.density = v; });
  assert.equal(d.settle('drag'), true);
  assert.equal(d.past.length, 1);
  d.edit(w => { w.entities[0].pos = [1, 0, 0]; }, 'move');
  assert.equal(d.past.length, 2);
  d.undo(); assert.deepEqual(d.world.entities[0].pos, [0, 0, 0]); assert.equal(d.world.rules.axes.density, 0.2);
  d.undo(); assert.equal(d.world.rules.axes.density, 0.5);
  assert.equal(d.undo(), false);
  d.redo(); d.redo(); assert.deepEqual(d.world.entities[0].pos, [1, 0, 0]);
  d.edit(w => { w.name = 'x'; }); assert.equal(d.redo(), false);          // a new edit clears the redo branch
});

test('an edit that changes nothing adds no undo step', () => {
  const d = new Doc(W()); d.edit(w => { w.rules.axes.density = 0.5; }); assert.equal(d.past.length, 0);
});

test('the editor never edits the world it was given', () => {
  const w = W(), d = new Doc(w); d.edit(x => { x.entities = []; }); assert.equal(w.entities.length, 2);
});

test('paths address nested bodies; duplicate renumbers ids, remove deletes', () => {
  const w = W();
  assert.equal(at(w, [1, 0]).id, 'b');
  assert.deepEqual(flatten(w).map(f => f.path), [[0], [1], [1, 0]]);
  const p = duplicate(w, [1]);
  assert.deepEqual(p, [2]);
  assert.deepEqual(flatten(w).map(f => f.e.id), ['a', 'g', 'b', 'g_2', 'b_2']);
  remove(w, [1, 0]); assert.deepEqual(flatten(w).map(f => f.e.id), ['a', 'g', 'g_2', 'b_2']);
  assert.equal(uniqueId(w, 'a'), 'a_2');
  assert.deepEqual(check(w), []);
});

test('every addable template is a valid body on its own', () => {
  const w = { format: 'world/1', name: 'w', entities: [] };
  for (const t of Object.keys(TEMPLATES)) w.entities.push(newEntity(w, t, [1, 2, 3]));
  assert.deepEqual(check(w), []);
  assert.equal(new Set(w.entities.map(e => e.id)).size, w.entities.length);
  assert.deepEqual(w.entities[0].pos, [1, 2, 0]);
});

test('field kinds come from the plugin field docs', () => {
  assert.deepEqual(fieldKind('[sx,sy,sz] m', [1, 2, 3]), { kind: 'vec', n: 3 });
  assert.deepEqual(fieldKind('[w,h] m'), { kind: 'vec', n: 2 });
  assert.equal(fieldKind('[Hz]').kind, 'numlist');
  assert.equal(fieldKind('[str]').kind, 'lines');
  assert.equal(fieldKind('str (required)').kind, 'text');
  assert.equal(fieldKind('bool').kind, 'bool');
  assert.equal(fieldKind('css colour').kind, 'colour');
  assert.deepEqual(fieldKind('point|spot'), { kind: 'enum', options: ['point', 'spot'] });
  assert.equal(fieldKind('m (default 1.68)').kind, 'number');
  assert.equal(fieldKind('[[x,y,z],...]').kind, 'json');
  assert.equal(fieldKind('{joints:[...]}').kind, 'json');
  assert.equal(fieldKind('[[...]]', Array(500).fill([1, 2, 3, 4, 5])).kind, 'big');
});
