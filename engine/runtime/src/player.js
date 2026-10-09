// Exhibition player (T-02): the whole work on one screen, for a gallery wall or a phone.
//   - the world (3D, sound, interaction) plus its other media (works.json: images, drawings and sounds its plugins
//     made), shown as a strip: tapping a picture opens it large, tapping a sound plays or pauses it
//   - "전체 화면": the page goes fullscreen and asks the screen to stay awake (where the browser allows both)
//   - left alone for idle_s seconds (world.player.idle_s, default 45), it plays the artist's first tour, again and
//     again, and hides the pointer; any touch, click or key hands control back to the visitor at once
const CSS = `
.we-works{position:fixed;left:10px;bottom:max(10px,env(safe-area-inset-bottom));display:flex;gap:6px;align-items:flex-end;z-index:6;max-width:calc(100vw - 20px);overflow-x:auto}
.we-works button{min-height:44px;min-width:44px;border:0;border-radius:10px;background:#ffffffe6;color:#222;font:14px "Noto Sans KR",system-ui,sans-serif;padding:0 10px;box-shadow:0 1px 4px #0003}
.we-works img{width:64px;height:64px;object-fit:contain;background:#fff;border-radius:8px;display:block}
.we-works button.thumb{padding:2px}
.we-big{position:fixed;inset:0;background:#000d;display:flex;align-items:center;justify-content:center;z-index:9;padding:16px}
.we-big img{max-width:100%;max-height:100%;background:#fff;border-radius:6px}
.we-big p{position:absolute;bottom:12px;left:0;right:0;text-align:center;color:#fff;font:14px "Noto Sans KR",system-ui,sans-serif}
body.we-attract{cursor:none}`;

export function player(eng, opts = {}) { return (eng.player = new Player(eng, opts)); }

class Player {
  constructor(eng, { works = null, idle_s } = {}) {
    this.eng = eng; this.idle = idle_s ?? (eng.world.player && eng.world.player.idle_s) ?? 45;
    this.last = eng.realTime; this.attract = false; this.attracts = 0; this.items = [];
    this.fs = { requested: 0, ok: 0, error: null }; this.wake = { supported: 'wakeLock' in navigator, held: false, error: null };
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    this.strip = document.createElement('div'); this.strip.className = 'we-works'; document.body.appendChild(this.strip);
    const fs = document.createElement('button'); fs.textContent = '전체 화면'; fs.onclick = () => this.fullscreen(); this.strip.appendChild(fs);
    for (const ev of ['pointerdown', 'keydown', 'wheel', 'touchstart']) addEventListener(ev, () => this.poke(), { capture: true, passive: true });
    eng.on('step', () => this.tick());
    eng.on('tourEnd', () => { if (this.attract) this._tour(); });         // the attract loop: the tour again
    this.ready = works ? this.load(works) : Promise.resolve([]);
  }

  async load(url) {
    const base = new URL(url, location.href);
    const data = await fetch(base).then(r => r.json()).catch(() => ({ items: [] }));
    for (const it of data.items || []) {
      if (!it.src) { this.items.push({ ...it, ok: false }); continue; }       // refused by the world's rules: listed, not shown
      const src = new URL(it.src, base).href;
      if (/^audio\//.test(it.media_type || '')) { this.items.push({ ...it, ok: true, audio: this._sound(src, it.title) }); continue; }
      const b = document.createElement('button'), img = document.createElement('img');
      b.className = 'thumb'; b.title = it.title; b.setAttribute('aria-label', it.title + ' 크게 보기'); img.alt = it.title; img.src = src;
      b.appendChild(img); b.onclick = () => this.show(src, it.title); this.strip.appendChild(b);
      this.items.push({ ...it, ok: true, img });
    }
    await Promise.all([...this.items.filter(i => i.img).map(i => i.img.decode().catch(() => {})),
      ...this.items.filter(i => i.audio).map(i => i.audio.readyState >= 1 ? null : new Promise(r => { i.audio.onloadedmetadata = i.audio.onerror = r; setTimeout(r, 5000); }))]);
    return this.items;
  }

  _sound(src, title) {             // a sound work: one button, play / pause; it plays only after the visitor's tap
    const a = new Audio(); a.preload = 'metadata'; a.src = src; a.loop = true;
    const b = document.createElement('button'); b.textContent = '♪ ' + title; b.setAttribute('aria-label', title + ' 듣기');
    b.onclick = () => { if (a.paused) { a.play().catch(() => {}); this.eng.caption('♪ ' + title); } else a.pause(); };
    a.onplay = () => b.setAttribute('aria-pressed', 'true'); a.onpause = () => b.setAttribute('aria-pressed', 'false');
    this.strip.appendChild(b); return a;
  }

  show(src, title) {
    const d = document.createElement('div'); d.className = 'we-big'; d.onclick = () => d.remove();
    const img = document.createElement('img'); img.src = src; img.alt = title;
    const p = document.createElement('p'); p.textContent = title + ' — 누르면 닫혀요';
    d.append(img, p); document.body.appendChild(d); return d;
  }

  poke() { this.last = this.eng.realTime; if (this.attract) this.stopAttract(); }
  tick() {
    const tours = this.eng.world.tours || [];
    if (!this.attract && tours.length && !this.eng.tour && this.eng.realTime - this.last >= this.idle) this.startAttract();
  }
  startAttract() { this.attract = true; document.body.classList.add('we-attract'); this._tour(); }
  _tour() { const t = (this.eng.world.tours || [])[0]; if (t && this.eng.startTour(t.id)) this.attracts++; }
  stopAttract() { this.attract = false; document.body.classList.remove('we-attract'); this.eng.stopTour(); }

  async fullscreen() {
    this.fs.requested++;
    try { await document.documentElement.requestFullscreen({ navigationUI: 'hide' }); this.fs.ok++; this.fs.error = null; }
    catch (e) { this.fs.error = `${e.name}: ${e.message}`; }
    if (this.wake.supported && !this.wake.held) {
      try { this.wake.lock = await navigator.wakeLock.request('screen'); this.wake.held = true; this.wake.error = null; }
      catch (e) { this.wake.error = `${e.name}: ${e.message}`; }
    }
    return this.fs;
  }
}
