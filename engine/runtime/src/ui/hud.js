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
  const bOrbit = btn('둘러보기', () => eng.setMode('orbit')), bWalk = btn('걷기', () => eng.setMode('walk'));
  const bAdult = btn('어른 눈높이', () => eng.setEye('adult')), bChild = btn('아이 눈높이', () => eng.setEye('child'));
  const help = () => eng.mode === 'walk'
    ? (touch ? '왼쪽 엄지: 이동 · 오른쪽 끌기: 시선 · 끝까지 밀면 달리기' : 'WASD/화살표: 이동 · 끌기: 시선 · Shift: 달리기')
    : (touch ? '한 손가락: 회전 · 두 손가락: 확대/이동' : '끌기: 회전 · 휠: 확대 · 오른쪽 끌기: 이동');
  const refresh = () => {
    bOrbit.setAttribute('aria-pressed', eng.mode === 'orbit'); bWalk.setAttribute('aria-pressed', eng.mode === 'walk');
    for (const [b, k] of [[bAdult, 'adult'], [bChild, 'child']]) { b.hidden = eng.mode !== 'walk'; b.setAttribute('aria-pressed', eng.eyeName === k); }
    bAdult.textContent = `어른 ${eng.world.player?.eye_heights?.adult ?? 1.7} m`; bChild.textContent = `아이 ${eng.world.player?.eye_heights?.child ?? 1.1} m`;
    sel.value = eng.viewName; sel.hidden = eng.mode === 'walk';
    top.innerHTML = `<b></b><div class="we-help"></div>`; top.firstChild.textContent = eng.world.name; top.lastChild.textContent = help();
    const v = eng.world.verify && eng.world.verify['V-16'];     // a drawing robot world carries its own verification
    if (v) { const d = document.createElement('div'); d.className = 'we-help';
      d.textContent = `V-16 ${v.pass ? '통과' : '실패'} · 획 오차 최대 ${(v.stroke_err_max_m * 1e3).toFixed(3)} mm · 한계 위반 ${v.limit_violations} · 충돌 ${v.self_collisions}`; top.appendChild(d); }
  };
  for (const ev of ['mode', 'eye', 'view']) eng.on(ev, refresh);
  refresh();
}
