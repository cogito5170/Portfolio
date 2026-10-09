// World editor UI (T-01): edit a world without code, on a PC or a phone, with the live 3D runtime beside it.
//   몸      pick a body (tap it in the 3D view or in the list), move/turn/scale it, change its material and its
//           type's own fields (from the plugin's field docs), add / duplicate / delete bodies, let one body break a
//           rule on purpose (E-03 ignore_rules)
//   규칙    style axes as sliders (A-02; artists may add axes, X-02), constraints with on/off switches (E-03),
//           material colours, world physics
//   금지·용어  forbidden list (W-01) and glossary (W-05)
//   개념    concept card titles and statements (new cards come through the studio: they need sources)
//   검토    format errors (cannot save/export) and rule indicators "검토 필요" (C-02: never a verdict)
// Every change is one undo step; a slider drag is one step. Export/import is the world JSON itself (W-06).
// Served by the studio (?studio=1&t=token) the editor saves each state as a new version of the work (E-01, A-05).
import * as THREE from 'three';
import { Doc, at, flatten, label, newEntity, duplicate, remove, fieldKind, parseNumList, isHexColour, pathOf, TEMPLATES } from './model.js';
import { check, AXES, CONSTRAINT_KINDS, RULE_KINDS, FORBIDDEN_KINDS } from '../world.js';
import { violations, KO } from '../rules.js';
import { FROM3 } from '../engine.js';

const AXKO = { density: '밀도', colour: '색', form: '형태', texture: '질감', motion: '움직임', sound: '소리', narrative: '서사' };
const RULEKO = { dimension_series: '치수 계열', palette: '팔레트', max_elements: '요소 수 상한', forbidden: '금지 목록' };
const FBKO = { type: '몸 종류', colour: '색', word: '말' };
const TABS = [['bodies', '몸'], ['rules', '규칙'], ['words', '금지·용어'], ['concepts', '개념'], ['review', '검토']];
const COMMON = new Set(['id', 'type', 'pos', 'rot', 'scale', 'material', 'children', 'behaviors', 'triggers', 'solid', 'eye_only', 'ignore_rules']);

function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'k') e.dataset.k = v;
    else if (k in e && k !== 'list') e[k] = v; else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : String(c));
  return e;
}
const btn = (text, onclick, attrs = {}) => h('button', { type: 'button', onclick, ...attrs }, text);
const num = v => (typeof v === 'number' && Number.isFinite(v) ? +v.toFixed(4) : '');

export class Editor {
  constructor(eng, world, { studio = null } = {}) {
    this.eng = eng; this.doc = new Doc(world); this.sel = null; this.tab = 'bodies'; this.studio = studio;
    this.known = eng.registry.known();
    this.catalogue = new Map(eng.registry.catalogue().map(c => [c.type, c]));
    this.errors = []; this.viol = []; this.timer = null; this.lastExport = null; this.armDelete = false;
    this.panel = document.getElementById('panel'); this.tabs = document.getElementById('tabs');
    const $ = id => document.getElementById(id);
    $('undo').onclick = () => this.undo(); $('redo').onclick = () => this.redo();
    $('export').onclick = () => this.exportFile();
    $('import').onclick = () => $('file').click();
    $('file').onchange = async e => { const f = e.target.files[0]; if (f) await this.importText(await f.text()); e.target.value = ''; };
    if (studio) { $('save').hidden = false; $('save').onclick = () => this.saveToStudio(); }
    this.$ = $;
    this._tapSelect();
    eng.on('step', () => { if (this.box) this.box.update(); });
  }

  // ------------------------------------------------------------------ state
  validate() { this.errors = check(this.doc.world, this.known); this.viol = this.errors.length ? [] : violations(this.doc.world); }
  get selected() { return this.sel ? at(this.doc.world, this.sel) : null; }

  status(text, cls = '') { const s = this.$('status'); s.textContent = text; s.className = cls; }

  async start() { this.validate(); if (this.errors.length) throw new Error('invalid world: ' + this.errors.slice(0, 3).join('; ')); await this.reload(true); this.render(); }

  async reload(first = false) {
    clearTimeout(this.timer); this.timer = null;
    this.validate();
    if (this.errors.length) { this.status(`형식 오류 ${this.errors.length}개 — 미리보기는 마지막 올바른 상태, 저장·내보내기 안 됨`, 'bad'); return false; }
    const keep = !first && this.eng.orbit ? { cam: this.eng.camera.position.clone(), tgt: this.eng.orbit.target.clone() } : null;
    await this.eng.load(this.doc.world, { view: first ? undefined : this.eng.viewName, mode: 'orbit' });
    if (keep) { this.eng.camera.position.copy(keep.cam); this.eng.orbit.target.copy(keep.tgt); this.eng.orbit.update(); }
    if (this.eng.interaction) this.eng.interaction.run = () => {};        // editing: a tap selects, it does not fire triggers
    this.highlight();
    return true;
  }
  schedule() { clearTimeout(this.timer); this.timer = setTimeout(() => this.reload(), 250); }
  async flush() { if (this.timer) await this.reload(); }

  // how: 'full' rebuild the 3D world (debounced) | 'transform' move the selected body's objects | 'none'
  change(fn, what, how = 'full') { this.doc.edit(fn, what); this.after(how, what); }
  after(how, what = '') {
    this.validate(); this._draft();
    if (how === 'full') this.schedule(); else if (how === 'transform') this.applyTransform();
    if (!this.errors.length) this.status(what ? `고침: ${what}` + (this.viol.length ? ` · 검토 필요 ${this.viol.length}` : '') : '');
    this.render();
  }
  async undo() { if (this.doc.undo()) { if (this.sel && !at(this.doc.world, this.sel)) this.sel = null; this._draft(); await this.reload(); this.status('되돌렸어요'); this.render(); } }
  async redo() { if (this.doc.redo()) { if (this.sel && !at(this.doc.world, this.sel)) this.sel = null; this._draft(); await this.reload(); this.status('다시 했어요'); this.render(); } }

  objectsOf(e) { const out = []; if (this.eng.root) this.eng.root.traverse(o => { if (o.userData.entity === e) out.push(o); }); return out; }
  applyTransform() {
    const e = this.selected; if (!e) return;
    for (const o of this.objectsOf(e)) {
      o.position.set(...(e.pos || [0, 0, 0]));
      o.rotation.set(...(e.rot || [0, 0, 0]).map(d => d * Math.PI / 180));
      const s = e.scale ?? 1; o.scale.set(...(typeof s === 'number' ? [s, s, s] : s));
      o.userData.base = { pos: o.position.clone(), rot: o.rotation.clone() };
    }
    this.highlight();
  }
  highlight() {
    if (this.box) { this.box.removeFromParent(); this.box.dispose(); this.box = null; }
    const e = this.selected, o = e && this.objectsOf(e)[0];
    if (o && this.eng.scene) { this.box = new THREE.BoxHelper(o, 0x1b6ef3); this.eng.scene.add(this.box); }
  }
  select(path) { this.sel = path; this.armDelete = false; this.tab = 'bodies'; this.highlight(); this.render(); }

  _tapSelect() {
    const dom = this.eng.renderer.domElement, ray = new THREE.Raycaster();
    let down = null;
    dom.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY, id: e.pointerId }; });
    dom.addEventListener('pointerup', e => {
      const d = down; down = null;
      if (!d || d.id !== e.pointerId || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 8) return;
      this.pickAt(e.clientX, e.clientY, ray);
    });
  }
  pickAt(x, y, ray = new THREE.Raycaster()) {
    const r = this.eng.renderer.domElement.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), this.eng.camera);
    for (const hit of ray.intersectObject(this.eng.root, true)) {
      let o = hit.object; while (o && !o.userData.entity) o = o.parent;
      if (!o || o.userData.type === 'ground') continue;
      const p = pathOf(this.doc.world, o.userData.entity);
      if (p) { this.select(p); return p; }
    }
    return null;
  }

  // ------------------------------------------------------------------ files and saving
  exportText() { return JSON.stringify(this.doc.world, null, 1); }
  exportFile() {
    this.validate();
    if (this.errors.length) { this.status('형식 오류가 있어 내보내지 않았어요 (검토 탭)', 'bad'); return null; }
    const text = this.lastExport = this.exportText();
    const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'application/json' })), download: String(this.doc.world.name || 'world').replace(/[^\w가-힣.-]+/g, '_') + '.world.json' });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    this.status('내보냈어요 (세계 파일 하나 — 사람이 읽을 수 있는 JSON)');
    return text;
  }
  async importText(text) {
    let w; try { w = JSON.parse(text); } catch (e) { this.status('JSON 이 아니에요: ' + e.message, 'bad'); return false; }
    const bad = check(w, this.known);
    if (bad.length) { this.status('가져오지 않았어요 — 형식 오류: ' + bad.slice(0, 3).join('; '), 'bad'); return false; }
    this.doc.replace(w, '가져오기'); this.sel = null; await this.reload(); this.status('가져왔어요 (되돌리기로 취소)'); this.render(); return true;
  }
  async saveToStudio() {
    this.validate();
    if (this.errors.length) { this.status('형식 오류가 있어 저장하지 않았어요', 'bad'); return null; }
    const r = await fetch(this.studio.base + '/api/edit?t=' + encodeURIComponent(this.studio.token), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ world: this.doc.world, why: '편집기에서 직접 고침' }) }).then(x => x.json());
    if (r.error) { this.status('저장 못 했어요: ' + r.error, 'bad'); return r; }
    this._draft(true);
    this.status(`판 ${r.version} 으로 저장했어요 — ` + (r.summary || []).slice(0, 3).join(' · '));
    return r;
  }
  _draftKey() { return 'we-editor:' + (this.doc.world.name || ''); }
  _draft(clear = false) {
    try { if (clear) localStorage.removeItem(this._draftKey()); else if (this.doc.dirty) localStorage.setItem(this._draftKey(), JSON.stringify({ t: Date.now(), world: this.doc.world })); } catch (_) { /* private mode: no drafts */ }
  }
  draft() { try { const d = JSON.parse(localStorage.getItem(this._draftKey()) || 'null'); return d && JSON.stringify(d.world) !== JSON.stringify(this.doc.world) ? d : null; } catch (_) { return null; } }

  // ------------------------------------------------------------------ rendering
  render() {
    this.$('undo').disabled = !this.doc.past.length; this.$('redo').disabled = !this.doc.future.length;
    const nRev = this.errors.length + this.viol.length;
    this.tabs.replaceChildren(...TABS.map(([k, t]) => btn(k === 'review' && nRev ? `${t} (${nRev})` : t, () => { this.tab = k; this.render(); },
      { role: 'tab', 'aria-selected': String(this.tab === k), k: 'tab.' + k, className: k === 'review' && this.errors.length ? 'bad' : '' })));
    const top = this.panel.scrollTop;
    this.panel.replaceChildren(...{ bodies: () => this.bodies(), rules: () => this.rules(), words: () => this.words(), concepts: () => this.concepts(), review: () => this.review() }[this.tab]());
    this.panel.scrollTop = top;
  }

  // ---- 몸
  bodies() {
    const w = this.doc.world, out = [];
    const types = Object.keys(TEMPLATES).filter(t => this.known.has(t));
    const sel = h('select', { k: 'add.type', 'aria-label': '추가할 몸 종류' }, types.map(t => h('option', { value: t }, t)));
    out.push(h('div', { className: 'row' }, sel, btn('몸 추가', () => {
      const c = this.eng.orbit ? FROM3(this.eng.orbit.target) : [0, 0, 0], e = newEntity(w, sel.value, c);
      this.change(x => x.entities.push(e), `${e.id} 추가`); this.select([w.entities.length - 1]);
    }, { k: 'add.go' })));
    const e = this.selected;
    if (e) out.push(this.entityCard(e));
    else out.push(h('p', { className: 'sub' }, '3D 화면이나 아래 목록에서 몸을 누르면 고칠 수 있어요.'));
    const list = h('div', { className: 'list' });
    for (const { path, depth, e: x } of flatten(w)) {
      const cur = this.sel && path.join('.') === this.sel.join('.');
      const bad = this.viol.some(v => v.entity && v.entity === x.id);
      list.append(btn(`${'　'.repeat(depth)}${label(x)} · ${x.type}${bad ? ' ⚠' : ''}`, () => this.select(path), { className: 'ent', 'aria-current': String(!!cur), k: 'ent.' + path.join('.') }));
    }
    out.push(h('h3', {}, `몸 ${flatten(w).length}개`), list);
    return out;
  }

  entityCard(e) {
    const card = h('div', { className: 'card' }), path = this.sel;
    const set = (key, v, how = 'full') => this.change(() => { const x = at(this.doc.world, path); if (v === undefined || v === '' || (Array.isArray(v) && !v.length)) delete x[key]; else x[key] = v; }, `${label(e)}.${key}`, how);
    card.append(h('h3', {}, `${label(e)} · ${e.type}`));
    const id = h('input', { value: e.id || '', k: 'f.id', className: 'grow', 'aria-label': '이름(id)', onchange: () => {
      const v = id.value.trim(); if (v && v !== e.id && flatten(this.doc.world).some(f => f.e.id === v)) { this.status(`"${v}" 는 이미 있어요`, 'bad'); id.value = e.id || ''; return; }
      set('id', v || undefined, 'none'); } });
    card.append(h('div', { className: 'row' }, h('label', {}, '이름'), id));
    card.append(this.vecRow('위치 m', e.pos || [0, 0, 0], 'pos', v => set('pos', v, 'transform'), 0.1));
    card.append(this.vecRow('회전 °', e.rot || [0, 0, 0], 'rot', v => set('rot', v.some(Boolean) ? v : undefined, 'transform'), 15));
    const sc = h('input', { type: 'number', step: 'any', min: 0, value: typeof e.scale === 'number' ? e.scale : (e.scale === undefined ? 1 : ''), className: 'num', k: 'f.scale', disabled: Array.isArray(e.scale),
      onchange: () => { const v = +sc.value; if (v > 0) set('scale', v === 1 ? undefined : v, 'transform'); } });
    card.append(h('div', { className: 'row' }, h('label', {}, '크기 배율'), sc, Array.isArray(e.scale) ? h('span', { className: 'sub' }, JSON.stringify(e.scale)) : null));
    // material: a world material by name, or this body's own colour
    const mats = Object.keys(this.doc.world.materials || {});
    const inline = e.material && typeof e.material === 'object';
    const ms = h('select', { k: 'f.material', className: 'grow', onchange: () => {
      if (ms.value === '__own') set('material', { color: '#888888' }); else set('material', ms.value || undefined);
    } }, h('option', { value: '' }, '(기본)'), mats.map(m => h('option', { value: m, selected: e.material === m }, m)),
      typeof e.material === 'string' && !mats.includes(e.material) ? h('option', { value: e.material, selected: true }, e.material) : null,
      h('option', { value: '__own', selected: inline }, '(이 몸만의 색)'));
    const row = h('div', { className: 'row' }, h('label', {}, '재질'), ms);
    if (inline) row.append(h('input', { type: 'color', value: isHexColour(e.material.color) ? e.material.color : '#888888', k: 'f.material.color',
      onchange: ev => set('material', { ...e.material, color: ev.target.value }) }));
    card.append(row);
    const solid = h('input', { type: 'checkbox', checked: !!e.solid, k: 'f.solid', onchange: () => set('solid', solid.checked || undefined) });
    const eye = h('select', { k: 'f.eye_only', onchange: () => set('eye_only', eye.value || undefined) },
      [['', '모두'], ['child', '아이 눈높이만'], ['adult', '어른 눈높이만']].map(([v, t]) => h('option', { value: v, selected: (e.eye_only || '') === v }, t)));
    card.append(h('div', { className: 'row' }, h('label', {}, '부딪힘'), solid, h('label', {}, '보이는 눈'), eye));
    // the type's own fields, from its plugin's field docs
    const cat = this.catalogue.get(e.type);
    for (const [key, doc] of Object.entries((cat && cat.fields) || {})) {
      if (COMMON.has(key)) continue;
      card.append(this.fieldRow(e, key, doc, v => set(key, v)));
    }
    for (const key of Object.keys(e)) if (!COMMON.has(key) && !(cat && cat.fields && key in cat.fields))
      card.append(h('div', { className: 'row sub' }, h('label', {}, key), '(이 몸 종류의 문서에 없는 칸 — 그대로 둔다)'));
    // E-03: this body breaks a rule on purpose
    const ign = h('div', { className: 'row' }, h('label', {}, '규칙 깨기'));
    for (const k of RULE_KINDS) {
      const c = h('input', { type: 'checkbox', checked: (e.ignore_rules || []).includes(k), k: 'f.ignore.' + k, onchange: () => {
        const s = new Set(e.ignore_rules || []); c.checked ? s.add(k) : s.delete(k); set('ignore_rules', RULE_KINDS.filter(x => s.has(x)), 'none'); } });
      ign.append(h('label', { className: 'chip' }, c, RULEKO[k]));
    }
    card.append(ign);
    if (e.triggers || e.behaviors) card.append(h('p', { className: 'sub' }, `반응 ${(e.triggers || []).length}개 · 움직임 ${(e.behaviors || []).length}개 (스튜디오 대화로 고친다, 여기서는 그대로 둔다)`));
    card.append(h('div', { className: 'row' },
      btn('복제', () => { let p; this.change(w => { p = duplicate(w, path); }, `${label(e)} 복제`); if (p) this.select(p); }, { k: 'f.dup' }),
      btn(this.armDelete ? '정말 지우기' : '지우기', () => {
        if (!this.armDelete) { this.armDelete = true; this.render(); return; }
        this.sel = null; this.armDelete = false; this.change(w => remove(w, path), `${label(e)} 지움`);
      }, { k: 'f.del', className: this.armDelete ? 'bad' : '' })));
    return card;
  }

  vecRow(title, v, key, onset, step) {
    const row = h('div', { className: 'row' }, h('label', {}, title));
    v.forEach((x, i) => {
      const inp = h('input', { type: 'number', step: 'any', value: num(x), className: 'num', k: `f.${key}.${i}`, 'aria-label': `${title} ${'xyz'[i]}`,
        onchange: () => { if (inp.value === '' || !Number.isFinite(+inp.value)) return; const n = v.slice(); n[i] = +inp.value; onset(n); } });
      const nudge = d => () => { const n = v.slice(); n[i] = +(n[i] + d).toFixed(4); onset(n); };
      row.append(h('span', { className: 'chip' }, btn('−', nudge(-step), { 'aria-label': `${'xyz'[i]} 줄이기`, k: `f.${key}.${i}.dec` }), inp, btn('+', nudge(step), { 'aria-label': `${'xyz'[i]} 늘리기`, k: `f.${key}.${i}.inc` })));
    });
    return row;
  }

  fieldRow(e, key, doc, onset) {
    const v = e[key], f = fieldKind(doc, v), k = 'f.' + key, row = h('div', { className: 'row' }, h('label', { title: doc }, key));
    let inp;
    switch (f.kind) {
      case 'big': row.append(h('span', { className: 'sub' }, `데이터 ${(JSON.stringify(v).length / 1024).toFixed(0)} KB — 편집기에서 바꾸지 않는다`)); return row;
      case 'text': inp = h('input', { value: v ?? '', className: 'grow', k, onchange: () => onset(inp.value) }); break;
      case 'lines': inp = h('textarea', { value: (v || []).join('\n'), k, onchange: () => onset(inp.value.split('\n').map(s => s.trim()).filter(Boolean)) }); row.append(h('span', { className: 'sub' }, '한 줄에 하나')); break;
      case 'bool': inp = h('input', { type: 'checkbox', checked: !!v, k, onchange: () => onset(inp.checked) }); break;
      case 'colour': inp = isHexColour(v) || v === undefined ? h('input', { type: 'color', value: v || '#888888', k, onchange: () => onset(inp.value) })
        : h('input', { value: v, k, onchange: () => onset(inp.value) }); break;
      case 'enum': inp = h('select', { k, onchange: () => onset(inp.value || undefined) }, h('option', { value: '' }, '(기본)'), f.options.map(o => h('option', { value: o, selected: v === o }, o))); break;
      case 'vec': { const cur = Array.isArray(v) ? v : Array(f.n).fill(0); row.append(...cur.map((x, i) => { const n = h('input', { type: 'number', step: 'any', value: num(x), className: 'num', k: `${k}.${i}`,
        onchange: () => { const c = cur.slice(); c[i] = +n.value; onset(c); } }); return n; })); row.append(h('span', { className: 'sub' }, doc)); return row; }
      case 'numlist': inp = h('input', { value: (v || []).join(', '), className: 'grow', k, onchange: () => { const l = parseNumList(inp.value); if (l.every(Number.isFinite)) onset(l); else this.status(`${key}: 숫자만 쉼표로`, 'bad'); } }); break;
      case 'json': inp = h('textarea', { value: v === undefined ? '' : JSON.stringify(v), k, onchange: () => { try { onset(inp.value.trim() ? JSON.parse(inp.value) : undefined); } catch (err) { this.status(`${key}: JSON 이 아니에요`, 'bad'); } } }); break;
      default: inp = h('input', { type: 'number', step: 'any', value: num(v), className: 'num', k, onchange: () => onset(inp.value === '' ? undefined : +inp.value) });
    }
    row.append(inp, f.kind === 'number' ? h('span', { className: 'sub' }, doc) : null);
    return row;
  }

  // ---- 규칙
  rules() {
    const w = this.doc.world, r = w.rules || {}, axes = r.axes || {}, out = [];
    const axCard = h('div', { className: 'card' }, h('h3', {}, '스타일 축 (0~1)'));
    for (const k of [...AXES, ...Object.keys(axes).filter(a => !AXES.includes(a))]) {
      const has = k in axes, val = h('span', { className: 'num' }, has ? (+axes[k]).toFixed(2) : '—');
      const sl = h('input', { type: 'range', min: 0, max: 1, step: 0.01, value: has ? axes[k] : 0.5, k: 'axis.' + k, 'aria-label': AXKO[k] || k, className: has ? '' : 'off',
        oninput: () => { this.doc.live(x => { x.rules = x.rules || {}; x.rules.axes = x.rules.axes || {}; x.rules.axes[k] = +sl.value; }); val.textContent = (+sl.value).toFixed(2); sl.className = ''; },
        onchange: () => { if (this.doc.settle(`축 ${AXKO[k] || k} ${(+sl.value).toFixed(2)}`)) this.after('none', `축 ${AXKO[k] || k} ${(+sl.value).toFixed(2)}`); } });
      axCard.append(h('div', { className: 'row' }, h('label', {}, AXKO[k] || k), sl, val,
        !AXES.includes(k) ? btn('×', () => this.change(x => { delete x.rules.axes[k]; }, `축 ${k} 뺌`, 'none'), { 'aria-label': `축 ${k} 빼기`, k: 'axis.del.' + k }) : null));
    }
    const nn = h('input', { placeholder: '새 축 이름 (예: 고요)', className: 'grow', k: 'axis.new' });
    axCard.append(h('div', { className: 'row' }, nn, btn('축 추가', () => {
      const n = nn.value.trim(); if (!n || n in axes) { this.status(n ? `"${n}" 축은 이미 있어요` : '축 이름을 써 주세요', 'bad'); return; }
      this.change(x => { x.rules = x.rules || {}; x.rules.axes = { ...(x.rules.axes || {}), [n]: 0.5 }; }, `축 ${n} 추가`, 'none');
    }, { k: 'axis.add' })));
    out.push(axCard);

    const cCard = h('div', { className: 'card' }, h('h3', {}, '제약 (끄면 생성기도 검사도 그 규칙을 보지 않는다)'));
    (r.constraints || []).forEach((c, i) => {
      const at_ = fn => x => fn(x.rules.constraints[i]);
      const on = h('input', { type: 'checkbox', checked: c.enabled !== false, k: `rule.${i}.enabled`, onchange: () =>
        this.change(at_(cc => { if (on.checked) delete cc.enabled; else cc.enabled = false; }), `${RULEKO[c.kind]} ${on.checked ? '켬' : '끔'}`, 'none') });
      const box = h('div', { className: 'card' + (c.enabled === false ? ' off' : '') }, h('div', { className: 'row' }, h('label', { className: 'chip' }, on, h('b', {}, RULEKO[c.kind] || c.kind)),
        btn('×', () => this.change(x => x.rules.constraints.splice(i, 1), `${RULEKO[c.kind]} 지움`, 'none'), { 'aria-label': '제약 지우기', k: `rule.${i}.del` })));
      if (c.kind === 'palette') {
        const row = h('div', { className: 'row' });
        c.colours.forEach((col, j) => row.append(h('span', { className: 'chip' },
          h('input', { type: 'color', value: isHexColour(col) ? col : '#000000', k: `rule.${i}.colour.${j}`, onchange: ev => this.change(at_(cc => { cc.colours[j] = ev.target.value; }), '팔레트 색', 'none') }),
          c.colours.length > 1 ? btn('×', () => this.change(at_(cc => cc.colours.splice(j, 1)), '팔레트 색 뺌', 'none'), { 'aria-label': '색 빼기' }) : null)));
        row.append(btn('+ 색', () => this.change(at_(cc => cc.colours.push('#888888')), '팔레트 색 추가', 'none'), { k: `rule.${i}.colour.add` }));
        box.append(row);
      } else if (c.kind === 'max_elements') {
        const n = h('input', { type: 'number', min: 1, step: 1, value: c.value, className: 'num', k: `rule.${i}.value`, onchange: () => { const v = Math.round(+n.value); if (v > 0) this.change(at_(cc => { cc.value = v; }), `요소 수 상한 ${v}`, 'none'); } });
        box.append(h('div', { className: 'row' }, h('label', {}, '최대'), n, h('span', { className: 'sub' }, `지금 ${flatten(w).length}개`)));
      } else if (c.kind === 'dimension_series') {
        const t = h('input', { value: (c.values_m || []).join(', '), className: 'grow', k: `rule.${i}.values`, onchange: () => {
          const l = parseNumList(t.value); if (l.length && l.every(x => x > 0)) this.change(at_(cc => { cc.values_m = l; }), '치수 계열', 'none'); else this.status('양수만 쉼표로', 'bad'); } });
        box.append(h('div', { className: 'row' }, h('label', {}, '값 m'), t));
      }
      cCard.append(box);
    });
    const ks = h('select', { k: 'rule.add.kind' }, CONSTRAINT_KINDS.map(k => h('option', { value: k }, RULEKO[k])));
    cCard.append(h('div', { className: 'row' }, ks, btn('제약 추가', () => {
      const d = { palette: { kind: 'palette', colours: ['#ffffff', '#222222'] }, max_elements: { kind: 'max_elements', value: Math.max(1, flatten(w).length) },
        dimension_series: { kind: 'dimension_series', values_m: [1] } }[ks.value];
      this.change(x => { x.rules = x.rules || {}; (x.rules.constraints = x.rules.constraints || []).push(d); }, `${RULEKO[ks.value]} 추가`, 'none');
    }, { k: 'rule.add' })));
    out.push(cCard);

    const mats = Object.entries(w.materials || {});
    if (mats.length) {
      const mCard = h('div', { className: 'card' }, h('h3', {}, '재질 색'));
      for (const [name, m] of mats) {
        const row = h('div', { className: 'row' }, h('label', {}, name));
        for (const f of ['color', 'emissive']) if (isHexColour(m[f])) row.append(h('input', { type: 'color', value: m[f], k: `mat.${name}.${f}`, 'aria-label': `${name} ${f}`,
          onchange: ev => this.change(x => { x.materials[name][f] = ev.target.value; }, `재질 ${name}`) }));
        mCard.append(row);
      }
      out.push(mCard);
    }
    const ph = r.physics || {};
    const g = h('input', { type: 'number', step: 'any', min: 0, max: 100, value: num(ph.gravity_mps2), placeholder: '9.81', className: 'num', k: 'phys.g' });
    const ts = h('input', { type: 'number', step: 'any', min: 0.01, max: 10, value: num(ph.time_scale), placeholder: '1', className: 'num', k: 'phys.ts' });
    const setPh = (key, inp) => () => this.change(x => { x.rules = x.rules || {}; x.rules.physics = { ...(x.rules.physics || {}) }; if (inp.value === '') delete x.rules.physics[key]; else x.rules.physics[key] = +inp.value; }, `물리 ${key}`);
    g.onchange = setPh('gravity_mps2', g); ts.onchange = setPh('time_scale', ts);
    out.push(h('div', { className: 'card' }, h('h3', {}, '세계의 물리'), h('div', { className: 'row' }, h('label', {}, '중력 m/s²'), g, h('label', {}, '시간 배속'), ts)));
    return out;
  }

  // ---- 금지·용어
  words() {
    const w = this.doc.world, out = [];
    const fCard = h('div', { className: 'card' }, h('h3', {}, '금지 목록 — 이 세계에 없는 것'), h('p', { className: 'sub' }, '몸 종류·색·말. 생성기 결과에서 나오면 만들지 않고, 몸에 있으면 검토 필요로 보여요.'));
    (w.forbidden || []).forEach((f, i) => {
      const upd = fn => this.change(x => fn(x.forbidden[i]), '금지 목록', 'none');
      const on = h('input', { type: 'checkbox', checked: f.enabled !== false, k: `fb.${i}.enabled`, onchange: () => upd(ff => { if (on.checked) delete ff.enabled; else ff.enabled = false; }) });
      const val = f.kind === 'colour' ? h('input', { type: 'color', value: isHexColour(f.value) ? f.value : '#000000', k: `fb.${i}.value`, onchange: ev => upd(ff => { ff.value = ev.target.value; }) })
        : h('input', { value: f.value || '', className: 'grow', k: `fb.${i}.value`, onchange: ev => { if (ev.target.value.trim()) upd(ff => { ff.value = ev.target.value.trim(); }); } });
      const why = h('input', { value: f.why || '', placeholder: '왜 (선택)', className: 'grow', k: `fb.${i}.why`, onchange: ev => upd(ff => { if (ev.target.value) ff.why = ev.target.value; else delete ff.why; }) });
      fCard.append(h('div', { className: 'row' + (f.enabled === false ? ' off' : '') }, h('label', { className: 'chip' }, on, FBKO[f.kind] || f.kind), val, why,
        btn('×', () => this.change(x => x.forbidden.splice(i, 1), '금지 항목 지움', 'none'), { 'aria-label': '금지 항목 지우기', k: `fb.${i}.del` })));
    });
    const kind = h('select', { k: 'fb.add.kind' }, FORBIDDEN_KINDS.map(k => h('option', { value: k }, FBKO[k])));
    const v = h('input', { placeholder: '예: 네온, robot, #ff00ff', className: 'grow', k: 'fb.add.value' });
    fCard.append(h('div', { className: 'row' }, kind, v, btn('금지 추가', () => {
      const val = v.value.trim();
      if (!val || (kind.value === 'colour' && !isHexColour(val))) { this.status(kind.value === 'colour' ? '색은 #rrggbb 로' : '무엇을 금지할지 써 주세요', 'bad'); return; }
      this.change(x => { (x.forbidden = x.forbidden || []).push({ kind: kind.value, value: val }); }, `금지: ${val}`, 'none');
    }, { k: 'fb.add' })));
    out.push(fCard);

    const gCard = h('div', { className: 'card' }, h('h3', {}, '용어집 — 이 세계의 말'), h('p', { className: 'sub' }, '어느 언어든. 스튜디오의 조수는 이 뜻으로 읽어요.'));
    (w.glossary || []).forEach((g, i) => {
      const term = h('input', { value: g.term, className: 'grow', k: `gl.${i}.term`, onchange: ev => {
        const t = ev.target.value.trim(); if (!t || (w.glossary || []).some((o, j) => j !== i && o.term === t)) { this.status(t ? `"${t}" 는 이미 있어요` : '말을 써 주세요', 'bad'); ev.target.value = g.term; return; }
        this.change(x => { x.glossary[i].term = t; }, '용어', 'none'); } });
      const mean = h('textarea', { value: g.meaning, k: `gl.${i}.meaning`, onchange: ev => { if (ev.target.value.trim()) this.change(x => { x.glossary[i].meaning = ev.target.value.trim(); }, '용어 뜻', 'none'); } });
      gCard.append(h('div', { className: 'card' }, h('div', { className: 'row' }, term, btn('×', () => this.change(x => x.glossary.splice(i, 1), '용어 지움', 'none'), { 'aria-label': '용어 지우기', k: `gl.${i}.del` })), mean,
        g.axes ? h('p', { className: 'sub' }, '축: ' + Object.entries(g.axes).map(([a, x]) => `${AXKO[a] || a} ${x}`).join(', ')) : null));
    });
    const nt = h('input', { placeholder: '말 (예: 여백)', className: 'grow', k: 'gl.add.term' }), nm = h('textarea', { placeholder: '이 세계에서의 뜻', k: 'gl.add.meaning' });
    gCard.append(h('div', { className: 'row' }, nt), nm, btn('용어 추가', () => {
      const t = nt.value.trim(), m = nm.value.trim();
      if (!t || !m) { this.status('말과 뜻을 모두 써 주세요', 'bad'); return; }
      if ((w.glossary || []).some(o => o.term === t)) { this.status(`"${t}" 는 이미 있어요`, 'bad'); return; }
      this.change(x => { (x.glossary = x.glossary || []).push({ term: t, meaning: m }); }, `용어 ${t}`, 'none');
    }, { k: 'gl.add' }));
    out.push(gCard);
    return out;
  }

  // ---- 개념
  concepts() {
    const cs = this.doc.world.concepts || [];
    const out = [h('p', { className: 'sub' }, '새 개념 카드는 스튜디오 대화로 만들어요 (출처가 필요해요). 여기서는 제목과 문장을 고쳐요.')];
    cs.forEach((c, i) => {
      const t = h('input', { value: c.title, className: 'grow', k: `cc.${i}.title`, onchange: ev => { if (ev.target.value.trim()) this.change(x => { x.concepts[i].title = ev.target.value.trim(); }, '개념 제목', 'none'); } });
      const s = h('textarea', { value: c.statement, k: `cc.${i}.statement`, onchange: ev => { if (ev.target.value.trim()) this.change(x => { x.concepts[i].statement = ev.target.value.trim(); }, '개념 문장', 'none'); } });
      out.push(h('div', { className: 'card' }, h('div', { className: 'row' }, t), s,
        h('p', { className: 'sub' }, '출처: ' + (c.sources || []).map(so => `${so.who} (${so.kind})`).join(', ') + ` · 규칙 ${(c.rules || []).length}개` + ((c.drives || []).length ? ` · 움직이는 몸 ${c.drives.join(', ')}` : ''))));
    });
    if (!cs.length) out.push(h('p', {}, '개념 카드가 없어요.'));
    return out;
  }

  // ---- 검토
  review() {
    const out = [];
    if (this.errors.length) out.push(h('div', { className: 'card' }, h('h3', { className: 'bad' }, `형식 오류 ${this.errors.length}개 — 고치기 전에는 저장·내보내기를 하지 않아요`),
      h('ul', {}, this.errors.map(e => h('li', {}, e)))));
    if (!this.viol.length && !this.errors.length) out.push(h('p', {}, '검토할 것이 없어요.'));
    if (this.viol.length) {
      const card = h('div', { className: 'card' }, h('h3', { className: 'warn' }, `검토 필요 ${this.viol.length}개`), h('p', { className: 'sub' }, '판정이 아니라 알림이에요. 그대로 두어도 되고, 규칙을 끄거나 그 몸만 예외로 둘 수 있어요.'));
      this.viol.forEach((v, i) => {
        const f = v.entity && flatten(this.doc.world).find(x => x.e.id === v.entity);
        card.append(h('div', { className: 'row' }, h('span', { className: 'grow' }, `${KO[v.kind] || v.kind} — ${v.entity ?? '세계'} ${v.field} = ${typeof v.value === 'number' ? +v.value.toFixed(4) : v.value}`),
          f ? btn('고르기', () => this.select(f.path), { k: `rev.${i}.pick` }) : null,
          f ? btn('이 몸만 예외', () => this.change(x => { const e = at(x, f.path); e.ignore_rules = RULE_KINDS.filter(k => k === v.kind || (e.ignore_rules || []).includes(k)); }, `${v.entity} 예외: ${KO[v.kind]}`, 'none'), { k: `rev.${i}.ignore` }) : null));
      });
      out.push(card);
    }
    return out;
  }
}
