// World format "world/1" -- the one JSON the runtime reads. Pure module (no DOM, no three) so node can test it.
//
// Coordinates: metres, z up, x east, y north. The renderer converts once (engine.js root group).
//
// {
//   "format": "world/1", "name": str,
//   "bounds": [W, D, H]?,                       // extent; derived from entities when absent
//   "environment": {"background", "ambient", "sun": {"dir", "intensity", "color", "shadows"}, "env_map": "room"|null,
//                   "exposure", "fog": {"density", "color"}|null},
//   "materials": {name: {kind, color, roughness, metalness, emissive, emissive_intensity, opacity, transmission, texture}},
//   "entities": [{"id", "type", "pos": [x,y,z], "rot": [rx,ry,rz] (deg), "scale": s|[sx,sy,sz],
//                 "material": name|{...}, "behaviors": [{"type", ...}], "solid": bool, "children": [...], <type fields>}],
//   "views": {name: {"pos": [x,y,z], "target": [x,y,z], "fov": deg}},
//   "player": {"spawn": [x,y], "yaw_deg", "eye": "adult"|"child", "eye_heights": {"child": 1.1, "adult": 1.7}, "speed"},
//   "controls": {"default": "orbit"|"walk"}
// }
//
// Unknown fields are kept and ignored (open data): a newer plugin may read them.
// check() says what is wrong; it never fixes the world.

export const FORMAT = 'world/1';
export const EYE_HEIGHTS = { child: 1.1, adult: 1.7 };

const isNum = v => typeof v === 'number' && Number.isFinite(v);
const isVec = (v, n) => Array.isArray(v) && v.length === n && v.every(isNum);

export function check(w, knownTypes = null) {
  const bad = [];
  if (!w || typeof w !== 'object' || Array.isArray(w)) return ['world must be an object'];
  if (w.format !== FORMAT) bad.push(`format must be "${FORMAT}": ${JSON.stringify(w.format ?? null)}`);
  if (typeof w.name !== 'string' || !w.name) bad.push('name must be a non-empty string');
  if (w.bounds !== undefined && !(isVec(w.bounds, 3) && w.bounds.every(v => v > 0))) bad.push(`bounds must be three positive numbers: ${JSON.stringify(w.bounds)}`);
  if (!Array.isArray(w.entities)) bad.push('entities must be a list');
  const ids = new Set();
  const walk = (list, path) => (list || []).forEach((e, i) => {
    const p = `${path}[${i}]`;
    if (!e || typeof e !== 'object') { bad.push(`${p} must be an object`); return; }
    if (typeof e.type !== 'string') bad.push(`${p}.type must be a string`);
    else if (knownTypes && !knownTypes.has(e.type)) bad.push(`${p}.type unknown: "${e.type}"`);
    if (e.id !== undefined) { if (ids.has(e.id)) bad.push(`${p}.id duplicated: "${e.id}"`); ids.add(e.id); }
    if (e.pos !== undefined && !isVec(e.pos, 3)) bad.push(`${p}.pos must be [x,y,z]`);
    if (e.rot !== undefined && !isVec(e.rot, 3)) bad.push(`${p}.rot must be [rx,ry,rz] degrees`);
    if (e.scale !== undefined && !(isNum(e.scale) || isVec(e.scale, 3))) bad.push(`${p}.scale must be a number or [sx,sy,sz]`);
    if (typeof e.material === 'string' && !(w.materials && e.material in w.materials) && !e.material.includes('.'))
      bad.push(`${p}.material "${e.material}" is not in materials`);
    if (e.children !== undefined) { if (!Array.isArray(e.children)) bad.push(`${p}.children must be a list`); else walk(e.children, p + '.children'); }
  });
  if (Array.isArray(w.entities)) walk(w.entities, 'entities');
  for (const [k, v] of Object.entries(w.views || {}))
    if (!(v && isVec(v.pos, 3) && isVec(v.target, 3) && isNum(v.fov) && v.fov > 0 && v.fov < 180)) bad.push(`views.${k} needs pos, target, fov (0..180)`);
  const pl = w.player;
  if (pl !== undefined) {
    if (pl.spawn !== undefined && !isVec(pl.spawn, 2)) bad.push('player.spawn must be [x,y]');
    if (pl.eye !== undefined && !(pl.eye in { ...EYE_HEIGHTS, ...(pl.eye_heights || {}) })) bad.push(`player.eye unknown: "${pl.eye}"`);
  }
  checkConcepts(w, ids, bad);
  checkRules(w, bad);
  checkExperience(w, bad);
  const mode = w.controls && w.controls.default;
  if (mode !== undefined && !['orbit', 'walk'].includes(mode)) bad.push(`controls.default must be orbit|walk: "${mode}"`);
  return bad;
}

export const SOURCE_KINDS = ['quote', 'paraphrase', 'own', 'interview'];

// Concept cards (the Concept ingredient): same rules and messages as world.py _check_concepts.
function checkConcepts(w, ids, bad) {
  const cs = w.concepts;
  if (cs === undefined || cs === null) return;
  if (!Array.isArray(cs)) { bad.push('concepts must be a list'); return; }
  const seen = new Set();
  cs.forEach((c, i) => {
    const p = `concepts[${i}]`;
    if (!c || typeof c !== 'object' || Array.isArray(c)) { bad.push(`${p} must be an object`); return; }
    if (typeof c.id !== 'string' || !c.id) bad.push(`${p}.id must be a non-empty string`);
    else if (seen.has(c.id)) bad.push(`${p}.id duplicated: "${c.id}"`);
    else seen.add(c.id);
    for (const k of ['title', 'statement']) if (typeof c[k] !== 'string' || !c[k]) bad.push(`${p}.${k} must be a non-empty string`);
    const src = c.sources;
    if (!Array.isArray(src) || !src.length) bad.push(`${p}.sources must be a non-empty list (say where the idea comes from, even if it is your own)`);
    else src.forEach((so, j) => {
      if (!so || typeof so !== 'object' || !so.who) bad.push(`${p}.sources[${j}].who is required`);
      else if (!SOURCE_KINDS.includes(so.kind)) bad.push(`${p}.sources[${j}].kind must be one of ${SOURCE_KINDS.join('|')}: ${JSON.stringify(so.kind ?? null)}`);
      else if (so.kind === 'quote' && !so.where) bad.push(`${p}.sources[${j}] is a quote: where (book/page/url) is required`);
    });
    (c.rules || []).forEach((r, j) => { if (!r || typeof r !== 'object' || typeof r.param !== 'string' || !('value' in r)) bad.push(`${p}.rules[${j}] needs param and value`); });
    for (const d of c.drives || []) if (!ids.has(d)) bad.push(`${p}.drives "${d}" is not an entity id`);
  });
}

export const AXES = ['density', 'colour', 'form', 'texture', 'motion', 'sound', 'narrative'];
export const CONSTRAINT_KINDS = ['dimension_series', 'palette', 'max_elements'];

// World ingredient (rules), Expression ingredient (expressions), version/fork: same as world.py _check_rules.
function checkRules(w, bad) {
  const r = w.rules;
  if (r !== undefined && r !== null) {
    if (typeof r !== 'object' || Array.isArray(r)) bad.push('rules must be an object');
    else {
      const ax = r.axes ?? {};
      if (typeof ax !== 'object' || Array.isArray(ax)) bad.push('rules.axes must be an object');
      else for (const [k, v] of Object.entries(ax)) if (!isNum(v) || v < 0 || v > 1) bad.push(`rules.axes.${k} must be a number in [0,1]: ${JSON.stringify(v ?? null)}`);
      (r.constraints || []).forEach((c, i) => {
        const p = `rules.constraints[${i}]`, kind = c && typeof c === 'object' ? c.kind : undefined;
        if (!CONSTRAINT_KINDS.includes(kind)) bad.push(`${p}.kind must be one of ${CONSTRAINT_KINDS.join('|')}: ${JSON.stringify(kind ?? null)}`);
        else if (kind === 'dimension_series' && !(Array.isArray(c.values_m) && c.values_m.length && c.values_m.every(x => isNum(x) && x > 0))) bad.push(`${p}.values_m must be a non-empty list of positive numbers`);
        else if (kind === 'palette' && !(Array.isArray(c.colours) && c.colours.length && c.colours.every(x => typeof x === 'string' && x.length === 7 && x[0] === '#'))) bad.push(`${p}.colours must be a non-empty list of "#rrggbb"`);
        else if (kind === 'max_elements' && !(Number.isInteger(c.value) && c.value > 0)) bad.push(`${p}.value must be a positive integer`);
      });
    }
  }
  const ex = w.expressions;
  if (ex !== undefined && ex !== null) {
    if (!Array.isArray(ex)) bad.push('expressions must be a list');
    else ex.forEach((e, i) => { if (!e || typeof e !== 'object' || typeof e.medium !== 'string' || !e.medium) bad.push(`expressions[${i}].medium must be a non-empty string`); });
  }
  if ('version' in w && !(typeof w.version === 'string' && w.version)) bad.push('version must be a non-empty string');
  const fk = w.forked_from;
  if (fk !== undefined && fk !== null && !(typeof fk === 'object' && typeof fk.world === 'string' && fk.world)) bad.push('forked_from.world must name the parent world');
}

export const TRIGGER_ON = ['tap', 'near'];
export const ACTIONS = ['play', 'toggle', 'caption', 'tour', 'talk'];

// Experience runtime: same rules and messages as world.py _check_experience.
function checkExperience(w, bad) {
  const ph = w.rules && typeof w.rules === 'object' && !Array.isArray(w.rules) ? w.rules.physics : undefined;
  if (ph !== undefined && ph !== null) {
    if (typeof ph !== 'object' || Array.isArray(ph)) bad.push('rules.physics must be an object');
    else {
      const g = ph.gravity_mps2, ts = ph.time_scale;
      if (g !== undefined && g !== null && !(isNum(g) && g >= 0 && g <= 100)) bad.push(`rules.physics.gravity_mps2 must be in [0,100]: ${JSON.stringify(g)}`);
      if (ts !== undefined && ts !== null && !(isNum(ts) && ts > 0 && ts <= 10)) bad.push(`rules.physics.time_scale must be in (0,10]: ${JSON.stringify(ts)}`);
    }
  }
  const tours = w.tours, tourIds = new Set();
  if (tours !== undefined && tours !== null) {
    if (!Array.isArray(tours)) bad.push('tours must be a list');
    else tours.forEach((t, i) => {
      const p = `tours[${i}]`;
      if (!t || typeof t !== 'object' || typeof t.id !== 'string' || !t.id) { bad.push(`${p}.id must be a non-empty string`); return; }
      tourIds.add(t.id);
      if (!Array.isArray(t.stops) || !t.stops.length) { bad.push(`${p}.stops must be a non-empty list`); return; }
      t.stops.forEach((st, j) => {
        const q = `${p}.stops[${j}]`;
        if (!st || typeof st !== 'object' || !(isVec(st.pos, 3) && isVec(st.target, 3))) bad.push(`${q} needs pos and target`);
        else if (!(isNum(st.dwell_s) && st.dwell_s > 0)) bad.push(`${q}.dwell_s must be > 0`);
        else if (typeof st.caption !== 'string' || !st.caption) bad.push(`${q}.caption is required (자막 없는 투어 정지점)`);
      });
    });
  }
  const walk = (es, path) => (es || []).forEach((e, i) => {
    if (!e || typeof e !== 'object') return;
    const q = `${path}[${i}]`;
    if ('eye_only' in e && !['child', 'adult'].includes(e.eye_only)) bad.push(`${q}.eye_only must be child|adult`);
    if (e.type === 'sound' && !(typeof e.caption === 'string' && e.caption)) bad.push(`${q} is a sound without caption (소리마다 자막이 필요하다)`);
    if (e.type === 'character' && !(Array.isArray(e.lines) && e.lines.length && e.lines.every(x => typeof x === 'string' && x))) bad.push(`${q}.lines must be a non-empty list of strings (대사가 곧 자막이다)`);
    (e.triggers || []).forEach((tr, k) => {
      const r = `${q}.triggers[${k}]`;
      if (!tr || typeof tr !== 'object' || !TRIGGER_ON.includes(tr.on)) { bad.push(`${r}.on must be tap|near`); return; }
      if (tr.on === 'near' && !(isNum(tr.radius) && tr.radius > 0)) bad.push(`${r}.radius must be > 0 for near`);
      (tr.do || []).forEach((a, m) => {
        const act = a && typeof a === 'object' ? a.action : undefined;
        if (!ACTIONS.includes(act)) bad.push(`${r}.do[${m}].action must be one of ${ACTIONS.join('|')}: ${JSON.stringify(act ?? null)}`);
        else if (act === 'caption' && !(typeof a.text === 'string' && a.text)) bad.push(`${r}.do[${m}] caption needs text`);
        else if (act === 'tour' && !tourIds.has(a.tour)) bad.push(`${r}.do[${m}] tour "${a.tour}" does not exist`);
      });
    });
    if (Array.isArray(e.children)) walk(e.children, q + '.children');
  });
  walk(w.entities, 'entities');
}

// Extent of everything with a position (used when bounds is absent). Rough on purpose: for camera framing only.
export function extent(w) {
  if (w.bounds) return { min: [0, 0, 0], max: w.bounds.slice() };
  const min = [Infinity, Infinity, 0], max = [-Infinity, -Infinity, 1];
  const visit = (list, off) => (list || []).forEach(e => {
    const p = (e.pos || [0, 0, 0]).map((v, k) => v + off[k]);
    const r = Math.max(e.size ? Math.max(...[].concat(e.size)) / 2 : 0, e.radius || 0, 0.5);
    for (let k = 0; k < 3; k++) { min[k] = Math.min(min[k], p[k] - r); max[k] = Math.max(max[k], p[k] + r); }
    visit(e.children, p);
  });
  visit(w.entities, [0, 0, 0]);
  if (!Number.isFinite(min[0])) return { min: [0, 0, 0], max: [10, 10, 3] };
  return { min, max };
}

export function eyeHeight(w, which) {
  const pl = w.player || {};
  const table = { ...EYE_HEIGHTS, ...(pl.eye_heights || {}) };
  return table[which || pl.eye || 'adult'];
}

// Default views when the world has none: aerial (three-quarter, from the south-west) and eye (adult, from the south edge).
export function defaultViews(w) {
  const { min, max } = extent(w);
  const c = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, 0], big = Math.max(max[0] - min[0], max[1] - min[1], 4);
  return {
    aerial: { pos: [c[0] - 0.55 * big, c[1] - 0.85 * big, 0.75 * big], target: c, fov: 45 },
    eye: { pos: [c[0], min[1] + 0.5, eyeHeight(w)], target: [c[0], max[1], eyeHeight(w) * 0.8], fov: 60 },
  };
}
