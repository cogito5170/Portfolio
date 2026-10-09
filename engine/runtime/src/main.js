// Boot: ?world=<url> [&view=aerial] [&mode=orbit|walk|fly] [&eye=adult|child] [&headless=1&w=&h=&t=] [&selftest=touch]
//       [&assets=<url template with {name}>] (where this page may read imported files, E-02)
//       [&player=1&works=<works.json>] (exhibition player, T-02)
import { Engine } from './engine.js';
import { core } from './plugins/core.js';
import { retail } from './plugins/retail.js';
import { robot } from './plugins/robot.js';
import { hud, guide, perf } from './ui/hud.js';
import { character } from './plugins/character.js';
import { TalkClient } from './talk.js';
import { Presence } from './presence.js';
import { enableXR } from './xr.js';
import { selftests } from './selftest.js';
import { report } from './report.js';

const P = new URLSearchParams(location.search), HEADLESS = P.has('headless');
const say = s => console.log('WE_STATUS:' + s);
try {
  const eng = new Engine(document.getElementById('app'), { headless: HEADLESS, width: +P.get('w') || undefined, height: +P.get('h') || undefined });
  eng.selftest = P.get('selftest');
  eng.registry.use(core, eng.mats).use(retail, eng.mats).use(robot, eng.mats).use(character, eng.mats);
  if (P.get('talk')) eng.talk = new TalkClient(P.get('talk'), eng);
  if (P.get('assets')) eng.assets.template = P.get('assets');
  const url = P.get('world') || '../worlds/contradiction_garden.world.json';
  const res = await fetch(url);
  if (!res.ok) throw new Error(`world ${url}: HTTP ${res.status}`);
  await eng.load(await res.json(), { view: P.get('view') || undefined, mode: P.get('mode') || undefined, eye: P.get('eye') || undefined });
  window.__engine = eng;
  if (P.get('presence')) eng.presence = new Presence(eng, P.get('presence'));
  if (P.has('lowspec')) eng.setLowSpec(P.get('lowspec') !== '0');
  if (eng.selftest) {
    if (!selftests[eng.selftest]) throw new Error('unknown selftest ' + eng.selftest);
    report(await selftests[eng.selftest](eng));
  }
  if (HEADLESS) eng.step(+(P.get('t') || 0));
  else { if (P.has('player')) (await import('./player.js')).player(eng, { works: P.get('works') }); hud(eng); guide(eng); enableXR(eng).then(x => { eng.xr = x; }); if (P.has('perf')) perf(eng, performance.now()); eng.start({ autoLowSpec: !P.has('lowspec') }); }
  window.__done = true; console.log(`WE_VIEWPORT:${innerWidth},${innerHeight}`); say('done');
} catch (e) {
  window.__err = String((e && e.message) || e); say('err:' + window.__err);
  const d = document.createElement('pre'); d.style.cssText = 'position:fixed;inset:auto 10px 10px 10px;background:#fff;color:#b00;padding:8px;white-space:pre-wrap';
  d.textContent = '세계를 열지 못했다: ' + window.__err; document.body.appendChild(d);
}
