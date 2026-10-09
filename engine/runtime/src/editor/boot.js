// Editor boot: ?world=<url> | ?studio=1&t=<token> (load from and save to the studio)  [&headless=1&w=&h=&selftest=editor]
import { Engine } from '../engine.js';
import { core } from '../plugins/core.js';
import { retail } from '../plugins/retail.js';
import { robot } from '../plugins/robot.js';
import { character } from '../plugins/character.js';
import { Editor } from './ui.js';
import { report } from '../report.js';

const P = new URLSearchParams(location.search), HEADLESS = P.has('headless');
const say = s => console.log('WE_STATUS:' + s);
try {
  const view = document.getElementById('view');
  const size = () => [Math.max(1, view.clientWidth), Math.max(1, view.clientHeight)];
  const eng = new Engine(view, { headless: HEADLESS, width: size()[0], height: size()[1] });
  eng.selftest = P.get('selftest') || 'editor';            // controls on, also when headless
  eng.registry.use(core, eng.mats).use(retail, eng.mats).use(robot, eng.mats).use(character, eng.mats);
  const studio = P.get('studio') ? { base: '', token: P.get('t') || '' } : null;
  const url = studio ? '/api/world.json?t=' + encodeURIComponent(studio.token) : (P.get('world') || '../worlds/contradiction_garden.world.json');
  const res = await fetch(url);
  if (!res.ok) throw new Error(`world ${url}: HTTP ${res.status}`);
  const ed = new Editor(eng, await res.json(), { studio });
  await ed.start();
  window.__editor = ed; window.__engine = eng;
  const fit = () => { const [w, h] = size(); eng.resize(w, h); };
  addEventListener('resize', fit); fit();
  const d = ed.draft();
  if (d && !HEADLESS) {
    const b = document.createElement('button'); b.type = 'button';
    b.textContent = '저장 안 한 고침 불러오기 (' + new Date(d.t).toLocaleString() + ')';
    b.onclick = async () => { ed.doc.replace(d.world, '임시 저장본'); await ed.reload(); ed.render(); b.remove(); };
    document.getElementById('bar').append(b);
  }
  if (P.get('selftest') === 'editor' || P.get('selftest') === 'editor_save') {
    const T = await import('./selftest.js');
    report(P.get('selftest') === 'editor' ? await T.editorSelftest(ed, eng) : await T.editorSaveTest(ed));
  }
  if (HEADLESS) eng.step(0);
  else eng.start({ autoLowSpec: false });
  window.__done = true; console.log(`WE_VIEWPORT:${innerWidth},${innerHeight}`); say('done');
} catch (e) {
  window.__err = String((e && e.message) || e); say('err:' + window.__err);
  const d = document.createElement('pre'); d.style.cssText = 'position:fixed;inset:auto 10px 10px 10px;background:#fff;color:#b00;padding:8px;white-space:pre-wrap';
  d.textContent = '편집기를 열지 못했다: ' + window.__err; document.body.appendChild(d);
}
