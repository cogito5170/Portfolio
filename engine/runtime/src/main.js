// Boot: ?world=<url> [&view=aerial] [&mode=orbit|walk] [&eye=adult|child] [&headless=1&w=&h=&t=] [&selftest=touch]
import { Engine } from './engine.js';
import { core } from './plugins/core.js';
import { retail } from './plugins/retail.js';
import { robot } from './plugins/robot.js';
import { hud } from './ui/hud.js';
import { selftests } from './selftest.js';

const P = new URLSearchParams(location.search), HEADLESS = P.has('headless');
const say = s => console.log('WE_STATUS:' + s);
try {
  const eng = new Engine(document.getElementById('app'), { headless: HEADLESS, width: +P.get('w') || undefined, height: +P.get('h') || undefined });
  eng.selftest = P.get('selftest');
  eng.registry.use(core, eng.mats).use(retail, eng.mats).use(robot, eng.mats);
  const url = P.get('world') || '../worlds/contradiction_garden.world.json';
  const res = await fetch(url);
  if (!res.ok) throw new Error(`world ${url}: HTTP ${res.status}`);
  await eng.load(await res.json(), { view: P.get('view') || undefined, mode: P.get('mode') || undefined, eye: P.get('eye') || undefined });
  window.__engine = eng;
  if (eng.selftest) {
    if (!selftests[eng.selftest]) throw new Error('unknown selftest ' + eng.selftest);
    console.log('WE_RESULT:' + btoa(JSON.stringify(await selftests[eng.selftest](eng))));
  }
  if (HEADLESS) eng.step(+(P.get('t') || 0));
  else { hud(eng); eng.start(); }
  window.__done = true; console.log(`WE_VIEWPORT:${innerWidth},${innerHeight}`); say('done');
} catch (e) {
  window.__err = String((e && e.message) || e); say('err:' + window.__err);
  const d = document.createElement('pre'); d.style.cssText = 'position:fixed;inset:auto 10px 10px 10px;background:#fff;color:#b00;padding:8px;white-space:pre-wrap';
  d.textContent = '세계를 열지 못했다: ' + window.__err; document.body.appendChild(d);
}
