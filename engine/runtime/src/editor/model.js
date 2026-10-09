// World editor model (T-01): the document being edited, its undo history and helpers. Pure (no DOM, no three),
// so node tests it. The UI (editor/ui.js) only calls these.
//
//   const d = new Doc(world);  d.edit(w => { w.rules.axes.density = 0.3; }, '밀도');  d.undo();  d.redo();
//   d.live(fn) ... d.settle(label)  -- a slider drag: many live changes, ONE undo step
//
// Entities are addressed by path (indices through children): [2] = entities[2], [2, 0] = entities[2].children[0].

export const clone = v => JSON.parse(JSON.stringify(v));

export class Doc {
  constructor(world) { this.world = clone(world); this.past = []; this.future = []; this.pending = null; this.label = ''; }
  live(fn) { if (this.pending === null) this.pending = JSON.stringify(this.world); fn(this.world); }
  settle(label = '') {
    if (this.pending === null) return false;
    if (this.pending !== JSON.stringify(this.world)) { this.past.push(this.pending); if (this.past.length > 300) this.past.shift(); this.future = []; this.label = label; }
    this.pending = null; return true;
  }
  edit(fn, label = '') { this.live(fn); return this.settle(label); }
  replace(world, label = '') { return this.edit(w => { for (const k of Object.keys(w)) delete w[k]; Object.assign(w, clone(world)); }, label); }
  undo() { this.settle(); if (!this.past.length) return false; this.future.push(JSON.stringify(this.world)); this.world = JSON.parse(this.past.pop()); return true; }
  redo() { if (!this.future.length) return false; this.past.push(JSON.stringify(this.world)); this.world = JSON.parse(this.future.pop()); return true; }
  get dirty() { return this.past.length > 0; }
}

export function at(w, path) {
  let list = w.entities, e = null;
  for (const i of path || []) { e = (list || [])[i]; if (!e) return null; list = e.children; }
  return e;
}

export function parentList(w, path) {
  const p = at(w, path.slice(0, -1));
  return path.length === 1 ? w.entities : p && p.children;
}

export function flatten(w) {
  const out = [];
  const walk = (list, path, depth) => (list || []).forEach((e, i) => {
    if (!e || typeof e !== 'object') return;
    const p = [...path, i]; out.push({ path: p, depth, e });
    walk(e.children, p, depth + 1);
  });
  walk(w.entities, [], 0);
  return out;
}

export const label = e => e.id || `${e.type}`;

export function allIds(w) { return new Set(flatten(w).map(x => x.e.id).filter(Boolean)); }

export function uniqueId(w, base) {
  const ids = allIds(w), b = String(base || 'body').replace(/[^\w가-힣.-]+/g, '_').replace(/_\d+$/, '');
  if (!ids.has(b)) return b;
  for (let i = 2; ; i++) if (!ids.has(`${b}_${i}`)) return `${b}_${i}`;
}

export function pathOf(w, entity) { const f = flatten(w).find(x => x.e === entity); return f ? f.path : null; }

// New bodies the editor can add without extra data. Types that need data (terrain heights, robot chains, store
// scenes, paths) are added by their own tools, not here. Required fields satisfy world.check (captions, lines).
export const TEMPLATES = {
  box: { size: [1, 1, 1] }, sphere: { radius: 0.5 }, cylinder: { radius: 0.5, height: 1 }, cone: { radius: 0.5, height: 1 },
  capsule: { radius: 0.3, height: 1.5 }, torus: { radius: 0.5, tube: 0.1 }, plane: { size: [4, 4] }, arch: { width: 2, height: 2.4, depth: 0.6, thickness: 0.5 },
  text: { text: '글', size: [2, 0.5] }, light: { kind: 'point', intensity: 7 }, person: {}, group: { children: [] },
  sound: { caption: '소리', recipe: 'tone', freq: 440, volume: 0.3 }, character: { name: '이름', lines: ['안녕하세요'] },
};

export function newEntity(w, type, centre = [0, 0, 0]) {
  return { id: uniqueId(w, type.split('.').pop()), type, pos: [+centre[0].toFixed(2), +centre[1].toFixed(2), 0], ...clone(TEMPLATES[type] || {}) };
}

export function duplicate(w, path) {
  const src = at(w, path); if (!src) return null;
  const c = clone(src), taken = allIds(w);
  const fresh = id => { const b = String(id).replace(/_\d+$/, ''); for (let i = 2; ; i++) if (!taken.has(`${b}_${i}`)) { taken.add(`${b}_${i}`); return `${b}_${i}`; } };
  const renumber = e => { if (e.id) e.id = fresh(e.id); (e.children || []).forEach(renumber); };
  renumber(c);
  if (Array.isArray(c.pos)) c.pos = [+(c.pos[0] + 1).toFixed(3), c.pos[1], c.pos[2]];
  parentList(w, path).splice(path[path.length - 1] + 1, 0, c);
  return [...path.slice(0, -1), path[path.length - 1] + 1];
}

export function remove(w, path) { const list = parentList(w, path); if (list) list.splice(path[path.length - 1], 1); }

// How to edit a field, from the type's own field doc (registry catalogue) -- plugins describe their fields, the
// editor never names a type's fields itself.
export function fieldKind(doc, value) {
  const d = String(doc || '').trim();
  if (value !== undefined && JSON.stringify(value).length > 2000) return { kind: 'big' };
  if (d.startsWith('[str]')) return { kind: 'lines' };
  if (d.startsWith('str')) return { kind: 'text' };
  if (d === 'bool') return { kind: 'bool' };
  if (/css|colour/.test(d)) return { kind: 'colour' };
  const first = d.split(/\s/)[0];
  if (/^[a-z0-9_]+(\|[a-z0-9_]+)+$/i.test(first) && first !== 'name|spec') return { kind: 'enum', options: first.split('|') };
  if (d.startsWith('[[') || d.startsWith('{') || d.startsWith('render3d')) return { kind: 'json' };
  if (d.startsWith('[')) {
    const inner = d.slice(1, d.indexOf(']'));
    if (Array.isArray(value) ? value.every(v => typeof v === 'number') && value.length <= 4 && inner.includes(',') : inner.includes(','))
      return { kind: 'vec', n: Array.isArray(value) ? value.length : inner.split(',').length };
    return { kind: 'numlist' };
  }
  return { kind: 'number' };
}

export const parseNumList = s => String(s).split(/[,\s]+/).filter(Boolean).map(Number);
export const isHexColour = v => typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v);
