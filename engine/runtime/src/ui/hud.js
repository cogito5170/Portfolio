// Minimal HUD, thumb-friendly on phones (44 px targets, bottom right) and unobtrusive on desktop.
const CSS = `
.we-hud{position:fixed;left:10px;top:max(8px,env(safe-area-inset-top));font:13px/1.4 "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif;color:#222;
  background:#ffffffd9;padding:6px 10px;border-radius:10px;max-width:calc(100vw - 20px);box-sizing:border-box;pointer-events:none}
.we-hud b{font-weight:700}.we-help{color:#555;font-size:12px}
.we-bar{position:fixed;right:10px;bottom:max(10px,env(safe-area-inset-bottom));display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;
  max-width:calc(100vw - 20px);font:14px "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif}
.we-bar button,.we-bar select{min-height:44px;min-width:44px;padding:0 12px;border:0;border-radius:10px;background:#ffffffe6;color:#222;font:inherit;box-shadow:0 1px 4px #0003}
.we-bar button[aria-pressed=true]{background:#222;color:#fff}
.we-card{position:fixed;left:10px;top:calc(max(8px,env(safe-area-inset-top)) + 84px);width:min(360px,calc(100vw - 20px));max-height:60vh;overflow:auto;
  box-sizing:border-box;background:#fffffff2;color:#222;border-radius:12px;padding:12px 14px;font:13px/1.5 "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif;box-shadow:0 2px 12px #0003}
.we-card h3{margin:0 0 4px;font-size:15px}.we-card .src{color:#555;font-size:12px;margin:6px 0}.we-card li{margin:2px 0}.we-card .no{color:#b00}
.we-talk{position:fixed;left:10px;right:10px;bottom:calc(max(10px,env(safe-area-inset-bottom)) + 120px);display:flex;gap:6px;z-index:7}
.we-talk input{flex:1;min-height:44px;border-radius:10px;border:0;padding:0 10px;font:16px system-ui,sans-serif}
.we-talk button{min-height:44px;border-radius:10px;border:0;padding:0 12px}
.we-guide{position:fixed;inset:0;background:#000a;display:flex;align-items:center;justify-content:center;z-index:9;padding:16px}
.we-guide div{background:#fff;color:#222;border-radius:14px;padding:18px;max-width:420px;font:15px/1.6 "Noto Sans KR",system-ui,sans-serif}
.we-guide button{min-height:48px;width:100%;margin-top:10px;border:0;border-radius:10px;background:#1b6ef3;color:#fff;font:inherit}
.we-perf{position:fixed;right:10px;top:max(8px,env(safe-area-inset-top));background:#000c;color:#9f9;font:12px/1.4 monospace;padding:6px 8px;border-radius:8px;z-index:8;white-space:pre}
.we-joy{position:fixed;display:none;width:0;height:0;pointer-events:none;z-index:5}
.we-joy-base{position:absolute;left:-56px;top:-56px;width:112px;height:112px;border-radius:50%;background:#ffffff40;border:2px solid #ffffffb0}
.we-joy-knob{position:absolute;left:-24px;top:-24px;width:48px;height:48px;border-radius:50%;background:#ffffffe0;box-shadow:0 1px 6px #0005}
`;

export function hud(eng) {
  const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
  const touch = matchMedia('(pointer: coarse)').matches;
  const top = document.createElement('div'); top.className = 'we-hud'; document.body.appendChild(top);
  const bar = document.createElement('div'); bar.className = 'we-bar'; document.body.appendChild(bar);
  const btn = (label, on) => { const b = document.createElement('button'); b.textContent = label; b.onclick = on; bar.appendChild(b); return b; };
  const sel = document.createElement('select');
  for (const k of Object.keys(eng.views)) sel.add(new Option(k, k));
  sel.onchange = () => eng.setView(sel.value); bar.appendChild(sel);
  const concepts = eng.world.concepts || [];
  let card = null;
  if (concepts.length) {
    card = document.createElement('div'); card.className = 'we-card'; card.hidden = true; document.body.appendChild(card);
    const eff = (eng.world.verify && eng.world.verify.concept_effects) || [];
    for (const c of concepts) {
      const sec = document.createElement('section');
      const h = document.createElement('h3'); h.textContent = '개념 · ' + c.title; sec.appendChild(h);
      const st = document.createElement('div'); st.textContent = c.statement; sec.appendChild(st);
      for (const so of c.sources) { const d = document.createElement('div'); d.className = 'src';
        d.textContent = `${{ quote: '인용', paraphrase: '의역', own: '자체', interview: '인터뷰' }[so.kind] || so.kind} — ${so.who}${so.where ? ', ' + so.where : ''}${so.note ? ' (' + so.note + ')' : ''}`; sec.appendChild(d); }
      const ul = document.createElement('ul');
      for (const r of c.rules || []) { const e = eff.find(x => x.concept === c.id && x.param === r.param); const li = document.createElement('li');
        li.textContent = `${r.why || r.param}: ${r.param} = ${JSON.stringify(r.value)} → ${e ? (e.applied ? (e.met === false ? '적용했지만 측정상 못 지킴 · ' : e.measured != null ? `지킴 (측정 ${typeof e.measured === 'number' ? +e.measured.toFixed(4) : e.measured}) · ` : '적용됨 · ') : '적용 안 됨 · ') + e.note : '이 작품에서 측정 안 됨'}`;
        if (e && (!e.applied || e.met === false)) li.className = 'no'; ul.appendChild(li); }
      sec.appendChild(ul); card.appendChild(sec);
    }
    btn('개념', () => { card.hidden = !card.hidden; });
    if (new URLSearchParams(location.search).has('card')) card.hidden = false;   // link that opens on the concept card
  }
  for (const t of eng.world.tours || []) btn('투어' + ((eng.world.tours.length > 1) ? ' · ' + (t.title || t.id) : ''), () => eng.startTour(t.id));
  for (const kind of eng.inputsWanted || []) {                          // M-03: opt-in, says when it is on
    const name = kind === 'mic' ? '마이크' : '카메라', b = btn(name + ' 켜기', async () => {
      if (eng.inputs.on[kind]) eng.inputs.disable(kind); else await eng.inputs.enable(kind);
    });
    eng.on('inputs', () => { const on = !!eng.inputs.on[kind]; b.textContent = name + (on ? ' 끄기' : ' 켜기'); b.setAttribute('aria-pressed', on); refresh(); });
  }
  btn('glTF', async () => { const { downloadGLB } = await import('../export.js'); downloadGLB(eng); });   // XR-10: take it to Blender/Unity/Godot
  const bOrbit = btn('둘러보기', () => eng.setMode('orbit')), bWalk = btn('걷기', () => eng.setMode('walk')), bFly = btn('날기', () => eng.setMode('fly'));
  const hold = (label, v) => {                                      // press and hold to rise / sink (XR-02 fly)
    const b = btn(label, () => {}); b.setAttribute('aria-label', v > 0 ? '위로' : '아래로');
    const on = e => { e.preventDefault(); if (eng.walk) eng.walk.vert = v; }, off = () => { if (eng.walk) eng.walk.vert = 0; };
    b.addEventListener('pointerdown', on); for (const ev of ['pointerup', 'pointerleave', 'pointercancel']) b.addEventListener(ev, off);
    return b;
  };
  const bUp = hold('▲', 1), bDown = hold('▼', -1);
  const bAdult = btn('어른 눈높이', () => eng.setEye('adult')), bChild = btn('아이 눈높이', () => eng.setEye('child'));
  const help = () => eng.mode === 'fly'
    ? (touch ? '왼쪽 엄지: 보는 쪽으로 날기 · 오른쪽 끌기: 시선 · ▲▼: 오르내리기' : 'WASD: 보는 쪽으로 날기 · E/Space: 위 · Q/Ctrl: 아래 · 끌기: 시선')
    : eng.mode === 'walk'
    ? (touch ? '왼쪽 엄지: 이동 · 오른쪽 끌기: 시선 · 끝까지 밀면 달리기' : 'WASD/화살표: 이동 · 끌기: 시선 · Shift: 달리기')
    : (touch ? '한 손가락: 회전 · 두 손가락: 확대/이동' : '끌기: 회전 · 휠: 확대 · 오른쪽 끌기: 이동');
  const refresh = () => {
    bOrbit.setAttribute('aria-pressed', eng.mode === 'orbit'); bWalk.setAttribute('aria-pressed', eng.mode === 'walk'); bFly.setAttribute('aria-pressed', eng.mode === 'fly');
    bUp.hidden = bDown.hidden = eng.mode !== 'fly';
    for (const [b, k] of [[bAdult, 'adult'], [bChild, 'child']]) { b.hidden = eng.mode !== 'walk'; b.setAttribute('aria-pressed', eng.eyeName === k); }
    bAdult.textContent = `어른 ${eng.world.player?.eye_heights?.adult ?? 1.7} m`; bChild.textContent = `아이 ${eng.world.player?.eye_heights?.child ?? 1.1} m`;
    sel.value = eng.viewName; sel.hidden = eng.mode !== 'orbit';
    top.innerHTML = `<b></b><div class="we-help"></div>`; top.firstChild.textContent = eng.world.name; top.lastChild.textContent = help();
    for (const k of Object.keys((eng.inputs && eng.inputs.on) || {})) { const d = document.createElement('div'); d.className = 'we-help';
      d.textContent = `● ${k === 'mic' ? '마이크' : '카메라'} 켜짐 — 이 기기 밖으로 나가지 않고, 저장하지 않아요`; top.appendChild(d); }
    if (eng.presence) { const d = document.createElement('div'); d.className = 'we-help'; d.textContent = `함께 있는 사람 ${eng.presence.count}명 (익명)`; top.appendChild(d); }
    const v = eng.world.verify && eng.world.verify['V-16'];     // a drawing robot world carries its own verification
    if (v) { const d = document.createElement('div'); d.className = 'we-help';
      d.textContent = `V-16 ${v.pass ? '통과' : '실패'} · 획 오차 최대 ${(v.stroke_err_max_m * 1e3).toFixed(3)} mm · 한계 위반 ${v.limit_violations} · 충돌 ${v.self_collisions}`; top.appendChild(d); }
  };
  for (const ev of ['mode', 'eye', 'view', 'presence']) eng.on(ev, refresh);
  refresh();
}

// First-visit guide (XR-11): what to do, in one screen. Its button is also the gesture that lets sound start.
export function guide(eng) {
  let seen = false;
  try { seen = localStorage.getItem('we-guide-seen') === '1'; } catch (_) { /* storage blocked: show it */ }
  if (seen) return;
  const touch = matchMedia('(pointer: coarse)').matches, d = document.createElement('div'); d.className = 'we-guide';
  const box = document.createElement('div');
  const lines = [eng.world.name, touch ? '한 손가락으로 돌려 보고, 두 손가락으로 가까이 가요.' : '끌어서 돌려 보고, 휠로 가까이 가요.',
    '「걷기」를 누르면 ' + (touch ? '왼쪽 엄지로' : 'WASD 로') + ' 걸어 다녀요.', '빛나는 것을 누르거나 가까이 가면 무언가 일어나요.',
    (eng.world.tours || []).length ? '「투어」를 누르면 작가가 정한 길로 안내해요.' : '', '소리는 시작을 누른 뒤에 나고, 모든 소리와 말은 자막으로도 나와요.'].filter(Boolean);
  lines.forEach((t, i) => { const p = document.createElement(i ? 'p' : 'b'); p.textContent = t; box.appendChild(p); });
  const b = document.createElement('button'); b.textContent = '시작'; b.onclick = () => { d.remove(); try { localStorage.setItem('we-guide-seen', '1'); } catch (_) { /* ignore */ } };
  box.appendChild(b); d.appendChild(box); document.body.appendChild(d);
}

// Measurement overlay (V-17, ?perf=1): numbers of THIS device. CI headless numbers are not V-17.
export function perf(eng, loadMs) {
  const d = document.createElement('div'); d.className = 'we-perf'; document.body.appendChild(d);
  let n = 0, t0 = performance.now(), fps = 0, worst = 0, last = performance.now();
  eng.on('step', () => {
    const now = performance.now(); worst = Math.max(worst, now - last); last = now; n++;
    if (now - t0 > 1000) {
      fps = n * 1000 / (now - t0); n = 0; t0 = now;
      const mem = performance.memory ? (performance.memory.usedJSHeapSize / 1048576).toFixed(0) + ' MB' : '측정 불가(이 브라우저)';
      d.textContent = `이 기기 측정값\nFPS ${fps.toFixed(1)}  최악 프레임 ${worst.toFixed(0)} ms\n첫 로딩 ${loadMs.toFixed(0)} ms\nJS 힙 ${mem}\n저사양 ${eng.lowspec ? '켜짐' : '꺼짐'}  ${eng.size[0]}×${eng.size[1]} @${eng.renderer.getPixelRatio()}x`;
      worst = 0; window.__perf = { fps, loadMs, lowspec: eng.lowspec };
    }
  });
}
