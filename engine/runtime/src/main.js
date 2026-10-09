// Boot: ?world=<url> [&view=aerial] [&mode=orbit|walk] [&eye=adult|child] [&headless=1&w=&h=&t=] [&selftest=touch]
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

const P = new URLSearchParams(location.search), HEADLESS = P.has('headless');
const say = s => console.log('WE_STATUS:' + s);
try {
  const eng = new Engine(document.getElementById('app'), { headless: HEADLESS, width: +P.get('w') || undefined, height: +P.get('h') || undefined });
  eng.selftest = P.get('selftest');
  eng.registry.use(core, eng.mats).use(retail, eng.mats).use(robot, eng.mats).use(character, eng.mats);
  if (P.get('talk')) eng.talk = new TalkClient(P.get('talk'), eng);
  const url = P.get('world') || '../worlds/contradiction_garden.world.json';
  const res = await fetch(url);
  if (!res.ok) throw new Error(`world ${url}: HTTP ${res.status}`);
  await eng.load(await res.json(), { view: P.get('view') || undefined, mode: P.get('mode') || undefined, eye: P.get('eye') || undefined });
  window.__engine = eng;
  if (P.get('presence')) eng.presence = new Presence(eng, P.get('presence'));
  if (P.has('lowspec')) eng.setLowSpec(P.get('lowspec') !== '0');
  if (eng.selftest) {
    if (!selftests[eng.selftest]) throw new Error('unknown selftest ' + eng.selftest);
    const bytes = new TextEncoder().encode(JSON.stringify(await selftests[eng.selftest](eng)));   // UTF-8, then base64
    let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    const b64 = btoa(bin), part = 200000;                 // long results go out in numbered parts (console line limits)
    if (b64.length <= part) console.log('WE_RESULT:' + b64);
    else for (let i = 0, n = Math.ceil(b64.length / part); i < n; i++) console.log(`WE_RESULT_PART:${i}/${n}:` + b64.slice(i * part, (i + 1) * part));
  }
  if (HEADLESS) eng.step(+(P.get('t') || 0));
  else { hud(eng); guide(eng); enableXR(eng).then(x => { eng.xr = x; }); if (P.has('perf')) perf(eng, performance.now()); eng.start({ autoLowSpec: !P.has('lowspec') }); }
  window.__done = true; console.log(`WE_VIEWPORT:${innerWidth},${innerHeight}`); say('done');
} catch (e) {
  window.__err = String((e && e.message) || e); say('err:' + window.__err);
  const d = document.createElement('pre'); d.style.cssText = 'position:fixed;inset:auto 10px 10px 10px;background:#fff;color:#b00;padding:8px;white-space:pre-wrap';
  d.textContent = '세계를 열지 못했다: ' + window.__err; document.body.appendChild(d);
}
