// Editor self-test: drives the editor's own DOM controls and canvas with real events (no internal shortcuts except
// one deliberate invalid edit), and reports what the world and the 3D scene became. Python checks the exported
// world with its own check() and violations() (tests/test_editor.py).
import * as THREE from 'three';
import { at, flatten } from './model.js';
import { violations } from '../rules.js';

const q = k => document.querySelector(`[data-k="${k}"]`);
const fire = (el, type) => el.dispatchEvent(new Event(type, { bubbles: true }));
function set(k, v) { const el = q(k); if (!el) throw new Error('no control ' + k); el.value = v; fire(el, 'input'); fire(el, 'change'); }
function click(k) { const el = q(k); if (!el) throw new Error('no control ' + k); el.click(); }
function tick(k, on) { const el = q(k); if (!el) throw new Error('no control ' + k); if (el.checked !== on) el.click(); }

export async function editorSelftest(ed, eng) {
  const r = { steps: {} }, S = r.steps, W = () => ed.doc.world;
  eng.step(0);
  S.start = { bodies: flatten(W()).length, errors: ed.errors.length, viol: ed.viol.length };

  // tap a body in the 3D view (pointer events on the canvas at its projected centre). The body chosen is one that
  // is in front at its own centre (otherwise the tap rightly selects whatever is in front of it).
  const cv = eng.renderer.domElement, rect = cv.getBoundingClientRect(), ray = new THREE.Raycaster();
  cv.setPointerCapture = cv.releasePointerCapture = () => {};   // synthetic pointers cannot be captured; the handlers still run
  const screen = ent => { const c = new THREE.Box3().setFromObject(ed.objectsOf(ent)[0]).getCenter(new THREE.Vector3()).project(eng.camera); return c; };
  const front = ent => { const c = screen(ent); if (Math.abs(c.x) > 1 || Math.abs(c.y) > 1) return false;
    ray.setFromCamera(new THREE.Vector2(c.x, c.y), eng.camera);
    for (const hit of ray.intersectObject(eng.root, true)) { let o = hit.object; while (o && !o.userData.entity) o = o.parent; if (o) return o.userData.entity === ent; }
    return false; };
  const target = flatten(W()).find(x => x.e.id && ed.objectsOf(x.e).length && front(x.e)) || flatten(W()).find(x => x.e.id && ed.objectsOf(x.e).length);
  const c = screen(target.e), px = rect.left + (c.x + 1) / 2 * rect.width, py = rect.top + (1 - c.y) / 2 * rect.height;
  for (const t of ['pointerdown', 'pointerup']) cv.dispatchEvent(new PointerEvent(t, { clientX: px, clientY: py, pointerId: 7, pointerType: 'touch', isPrimary: true, bubbles: true, cancelable: true }));
  const picked = ed.selected;
  S.tap = { wanted: target.e.id, picked: picked && picked.id, at: [Math.round(px), Math.round(py)] };
  if (!picked) ed.select(target.path);                       // keep going so the other steps still report; the test fails on S.tap
  const e = ed.selected, id = e.id, x0 = (e.pos || [0, 0, 0])[0], y0 = (e.pos || [0, 0, 0])[1];

  // move with the number field, then nudge with +
  set('f.pos.0', String(x0 + 1));
  click('f.pos.1.inc');
  const obj = ed.objectsOf(at(W(), ed.sel))[0];
  S.move = { pos: at(W(), ed.sel).pos, object: obj ? [+obj.position.x.toFixed(4), +obj.position.y.toFixed(4)] : null, want: [x0 + 1, +(y0 + 0.1).toFixed(4)] };

  // a slider drag is one undo step
  click('tab.rules');
  const before = ed.doc.past.length, sl = q('axis.density');
  for (const v of ['0.4', '0.3', '0.2']) { sl.value = v; fire(sl, 'input'); }
  fire(sl, 'change');
  S.slider = { density: W().rules.axes.density, undo_steps: ed.doc.past.length - before };

  // own colour off the palette -> review item; palette switched off -> gone; on again; "only this body" -> gone
  click('tab.bodies');
  const ms = q('f.material'); ms.value = '__own'; fire(ms, 'change');
  set('f.material.color', '#ff00ff');
  const pal = () => ed.viol.filter(v => v.kind === 'palette' && v.entity === id).length;
  S.palette = { after_colour: pal() };
  click('tab.rules');
  const pi = (W().rules.constraints || []).findIndex(c => c.kind === 'palette');
  tick(`rule.${pi}.enabled`, false); S.palette.rule_off = pal(); S.palette.enabled_field = W().rules.constraints[pi].enabled;
  tick(`rule.${pi}.enabled`, true); S.palette.rule_on = pal();
  click('tab.review');
  const ri = ed.viol.findIndex(v => v.kind === 'palette' && v.entity === id);
  click(`rev.${ri}.ignore`); S.palette.ignored = pal(); S.palette.ignore_rules = at(W(), ed.sel).ignore_rules;

  // forbidden list: forbid this body's type -> review item; switch the item off -> gone
  click('tab.words');
  set('fb.add.kind', 'type'); set('fb.add.value', e.type); click('fb.add');
  const fb = () => ed.viol.filter(v => v.kind === 'forbidden').length;
  const fi = W().forbidden.length - 1;
  S.forbidden = { item: W().forbidden[fi], hits: fb() };
  tick(`fb.${fi}.enabled`, false); S.forbidden.off = fb();
  set('fb.add.kind', 'colour'); set('fb.add.value', 'pink'); click('fb.add');
  S.forbidden.bad_colour_refused = W().forbidden.length === fi + 1;

  // glossary: add a word; the same word again is refused
  set('gl.add.term', '숨'); set('gl.add.meaning', '비어 있는 곳이 아니라 쉬는 곳'); click('gl.add');
  const n1 = W().glossary.length;
  set('gl.add.term', '숨'); set('gl.add.meaning', '다른 뜻'); click('gl.add');
  S.glossary = { entries: W().glossary, duplicate_refused: W().glossary.length === n1 };

  // add a body, duplicate it, delete the duplicate (two presses)
  click('tab.bodies');
  const nb = flatten(W()).length;
  set('add.type', 'box'); click('add.go');
  const added = ed.selected; await ed.flush();
  S.add = { bodies: flatten(W()).length - nb, id: added.id, in_scene: !!eng.find(added.id) };
  click('f.dup'); const dupId = ed.selected.id, n2 = flatten(W()).length;
  click('f.del'); const armed = flatten(W()).length; click('f.del');
  await ed.flush();
  S.duplicate = { id: dupId, after_dup: n2 - nb, first_press_kept: armed === n2, after_delete: flatten(W()).length - nb, in_scene: !!eng.find(dupId) };

  // an id that already exists is refused
  ed.select(flatten(W()).find(x => x.e.id === added.id).path);
  set('f.id', id); S.rename_refused = at(W(), ed.sel).id === added.id;

  // a format error (programmatic: the UI cannot produce one) blocks export and keeps the last good 3D
  ed.change(w => { w.rules.axes.density = 2; }, 'test');
  await ed.flush();
  const blocked = ed.exportFile();
  S.invalid = { errors: ed.errors.slice(0, 2), export_blocked: blocked === null };
  await ed.undo();
  S.invalid.after_undo = ed.errors.length;

  // undo / redo
  const p0 = ed.doc.past.length; await ed.undo(); const p1 = ed.doc.past.length; await ed.redo();
  S.undo = { undone: p0 - p1, redone: ed.doc.past.length - p1 };

  // reloading on every change must not pile up GPU objects (engine disposes the old scene)
  await ed.reload(); eng.step(0); const m0 = { ...eng.renderer.info.memory };
  for (let i = 0; i < 5; i++) { await ed.reload(); eng.step(0); }
  r.memory = { before: m0, after: { ...eng.renderer.info.memory }, reloads: 5 };

  // export through the button
  click('tab.review'); ed.lastExport = null; document.getElementById('export').click();
  r.exported = JSON.parse(ed.lastExport);
  r.js_violations = violations(r.exported);
  r.history = ed.doc.past.length;

  // layout on this screen: nothing wider than the screen, touch targets
  await new Promise(res => requestAnimationFrame(res));
  const vis = [...document.querySelectorAll('#side button, #side input:not([type=checkbox]), #side select')].filter(b => { const x = b.getBoundingClientRect(); return x.width > 0 && x.height > 0; });
  const view = document.getElementById('view').getBoundingClientRect(), side = document.getElementById('side').getBoundingClientRect();
  r.layout = { inner: [innerWidth, innerHeight], scroll_width: document.documentElement.scrollWidth, min_target_px: Math.min(...vis.map(b => b.getBoundingClientRect().height)),
    controls: vis.length, view: [Math.round(view.width), Math.round(view.height)], canvas: [eng.renderer.domElement.width, eng.renderer.domElement.height],
    side: [Math.round(side.width), Math.round(side.height)], stacked: side.top >= view.bottom - 1 };
  return r;
}

// Served by the studio: one slider change, then the save button. The studio must hold it as a new version.
export async function editorSaveTest(ed) {
  const st = document.getElementById('status');
  q('tab.rules').click();
  const sl = q('axis.texture'); sl.value = '0.77'; fire(sl, 'input'); fire(sl, 'change');
  st.textContent = '';
  document.getElementById('save').click();
  const t0 = performance.now();
  while (performance.now() - t0 < 8000 && !/판 \d+|못 했어요|않았어요/.test(st.textContent)) await new Promise(r => setTimeout(r, 50));
  return { status: st.textContent, save_visible: !document.getElementById('save').hidden, texture: ed.doc.world.rules.axes.texture };
}
