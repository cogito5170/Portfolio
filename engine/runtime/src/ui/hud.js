// Minimal HUD, thumb-friendly on phones (44 px targets, bottom right) and unobtrusive on desktop.
const CSS = `
.we-hud{position:fixed;left:10px;top:max(8px,env(safe-area-inset-top));font:13px/1.4 "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif;color:#222;
  background:#ffffffd9;padding:6px 10px;border-radius:10px;max-width:calc(100vw - 20px);box-sizing:border-box;pointer-events:none}
.we-hud b{font-weight:700}.we-help{color:#555;font-size:12px}
.we-bar{position:fixed;right:10px;bottom:max(10px,env(safe-area-inset-bottom));display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;
  max-width:calc(100vw - 20px);font:14px "Noto Sans KR","WenQuanYi Zen Hei",system-ui,sans-serif}
.we-bar button,.we-bar select{min-height:44px;min-width:44px;padding:0 12px;border:0;border-radius:10px;background:#ffffffe6;color:#222;font:inherit;box-shadow:0 1px 4px #0003}
.we-bar button[aria-pressed=true]{background:#222;color:#fff}
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
  };
  for (const ev of ['mode', 'eye', 'view']) eng.on(ev, refresh);
  refresh();
}
