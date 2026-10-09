// World rules on the bodies (entities): JS twin of worldengine/constraints.py violations(). Pure module (node tests it).
// The editor shows these live as "검토 필요" (C-02: indicators, not verdicts). Same order and values as Python.
//   dimension_series · max_elements · palette · forbidden (type | colour | word)
// Switches (E-03): {"enabled": false} on a constraint or forbidden item; entity.ignore_rules = [kind, ...].

const SIZED = { box: ['size'], cylinder: ['height', 'radius*2'], cone: ['height', 'radius*2'], sphere: ['radius*2'],
  capsule: ['height', 'radius*2'], arch: ['width', 'height', 'depth', 'thickness'] };
const TEXT_FIELDS = ['caption', 'text', 'lines'];
const isObj = v => v && typeof v === 'object' && !Array.isArray(v);

function* walk(list) {
  for (const e of list || []) { if (!isObj(e)) continue; yield e; yield* walk(e.children); }
}
function* sizes(e) {
  for (const f of SIZED[e.type] || []) {
    const [key, k] = f.endsWith('*2') ? [f.slice(0, -2), 2] : [f, 1];
    if (!(key in e)) continue;
    for (const v of Array.isArray(e[key]) ? e[key] : [e[key]]) yield [f, v * k];
  }
}
const on = r => r.enabled !== false;
const ignores = (e, kind) => (e.ignore_rules || []).includes(kind);

function* colours(w, ents) {
  for (const [name, m] of Object.entries(w.materials || {}))
    for (const f of ['color', 'emissive']) if (isObj(m) && typeof m[f] === 'string') yield [null, 'materials.' + name, f, m[f]];
  for (const e of ents) {
    const m = e.material;
    if (isObj(m)) for (const f of ['color', 'emissive']) if (typeof m[f] === 'string') yield [e, e.id ?? null, 'material.' + f, m[f]];
  }
}
function* texts(w, ents) {
  for (const e of ents) {
    for (const f of TEXT_FIELDS) for (const s of Array.isArray(e[f]) ? e[f] : [e[f]]) if (typeof s === 'string') yield [e, e.id ?? null, f, s];
    for (const tr of e.triggers || []) for (const a of isObj(tr) ? tr.do || [] : [])
      if (isObj(a) && typeof a.text === 'string') yield [e, e.id ?? null, 'triggers.text', a.text];
  }
  for (const t of w.tours || []) for (const st of isObj(t) ? t.stops || [] : [])
    if (isObj(st) && typeof st.caption === 'string') yield [null, 'tours.' + String(t.id ?? 'None'), 'caption', st.caption];
}

export function violations(w) {
  const out = [], ents = [...walk(w.entities)];
  for (const c of (w.rules && w.rules.constraints) || []) {
    if (!on(c)) continue;
    if (c.kind === 'dimension_series') {
      for (const e of ents) {
        if (ignores(e, 'dimension_series')) continue;
        for (const [f, v] of sizes(e)) if (!c.values_m.some(s => Math.abs(v - s) <= 1e-6 * s)) out.push({ entity: e.id ?? null, field: f, value: v, kind: 'dimension_series' });
      }
    } else if (c.kind === 'max_elements') {
      const n = ents.filter(e => !ignores(e, 'max_elements')).length;
      if (n > c.value) out.push({ entity: null, field: 'entities', value: n, kind: 'max_elements' });
    } else if (c.kind === 'palette') {
      const allowed = new Set(c.colours.map(x => x.toLowerCase()));
      for (const [e, label, f, v] of colours(w, ents))
        if (!allowed.has(v.toLowerCase()) && !(e && ignores(e, 'palette'))) out.push({ entity: label, field: f, value: v, kind: 'palette' });
    }
  }
  for (const r of w.forbidden || []) {
    if (!on(r)) continue;
    const val = r.value;
    if (r.kind === 'type') {
      for (const e of ents) { const t = e.type || ''; if ((t === val || t.startsWith(val + '.')) && !ignores(e, 'forbidden')) out.push({ entity: e.id ?? null, field: 'type', value: t, kind: 'forbidden' }); }
    } else if (r.kind === 'colour') {
      for (const [e, label, f, v] of colours(w, ents)) if (v.toLowerCase() === val.toLowerCase() && !(e && ignores(e, 'forbidden'))) out.push({ entity: label, field: f, value: v, kind: 'forbidden' });
    } else if (r.kind === 'word') {
      for (const [e, label, f, s] of texts(w, ents)) if (s.toLowerCase().includes(val.toLowerCase()) && !(e && ignores(e, 'forbidden'))) out.push({ entity: label, field: f, value: val, kind: 'forbidden' });
    }
  }
  return out;
}

// Korean one-liners for the editor's review list.
export const KO = { dimension_series: '치수 계열 밖', max_elements: '요소 수 상한 넘음', palette: '팔레트 밖 색', forbidden: '금지 목록' };
