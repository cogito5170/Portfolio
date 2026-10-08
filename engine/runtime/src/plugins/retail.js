// Retail plugin: the store fixtures of se_new render3d (shelves, islands, checkouts, stairs ...), kept as one
// entity type so the bundled layouts (hongdae, store_module) still render in the runtime. Nothing in the core
// depends on it. The look (including the yellow accent) is this plugin's theme -- a world can override any of
// it with materials named "retail.<name>".
//
//   {"type": "retail.store", "scene": <render3d scene: bounds, y_axis, shell, boxes, columns, signs, people>,
//    "cutaway": "auto"|true|false}
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const SOLID = new Set(['wall_shelf', 'island', 'gondola', 'checkout', 'figure', 'media', 'stock', 'kiosk', 'stair', 'elevator', 'window', 'bin', 'block']);

export const retail = {
  name: 'retail',
  version: '1',
  materials: {
    floor: { color: '#ffffff', roughness: 0.38, texture: { kind: 'speckle', colors: ['#e9e4da', '#cfc6b6', '#b9ae9b', '#f7f3ec', '#d8cfbf', '#a79c8a', '#f2d98a'], px: 1024, size_m: 4 } },
    wall: { color: '#efe7da', roughness: 0.9 },
    wood: { color: '#ffffff', roughness: 0.55, texture: { kind: 'wood', colors: ['#d8b98f', '#caa678'] } },
    white: { color: '#fbfaf7', roughness: 0.45 },
    accent: { color: '#fee500', roughness: 0.5 },
    dark: { color: '#2b2b2b', roughness: 0.6 },
    column: { color: '#ece8e0', roughness: 0.7 },
    glass: { kind: 'physical', color: '#cfe8f2', roughness: 0.05, opacity: 0.18 },
    steel: { color: '#bfc4c8', roughness: 0.25, metalness: 0.9 },
    stock: { color: '#d9d4cb', roughness: 0.9 },
    belt: { color: '#2f6fb0', roughness: 0.6 },
    media: { color: '#ffffff', emissive_intensity: 0.9, texture: { kind: 'gradient', colors: ['#7fd3ff', '#ffe36e', '#ff9fb6'], emissive: true } },
    ground: { color: '#d9d6cf', roughness: 1 },
    ceiling: { color: '#f2f0ec', roughness: 1 },
  },
  types: {
    'retail.store': {
      doc: 'a render3d store scene (fixtures by box type)', fields: { scene: 'render3d scene', cutaway: 'auto|true|false' },
      build(e, c) { return buildStore(e.scene, c, e.cutaway ?? 'auto'); },
    },
  },
};

function buildStore(S, c, cutaway) {
  const VIEW = c.view, [BW, BD, BH] = S.bounds, NORTH = S.y_axis === 'north';
  const sv = (S.views || {})[VIEW];
  const CUT = cutaway === 'auto' ? (VIEW !== 'top' && !(sv && sv.pos[2] < BH * 0.9) && S.shell) : !!cutaway;
  // Legacy frame: three-native (y up) with z mirrored for north-up plans. Undo the engine's root turn here.
  const G = new THREE.Group(); G.rotation.x = Math.PI / 2; if (NORTH) G.scale.z = -1;
  const rnd = c.rnd, R = n => c.mats.get('retail.' + n);
  const M = { floor: c.mats.tiled('retail.floor', BW, BD), wall: R('wall'), wood: R('wood'), white: R('white'), yellow: R('accent'), dark: R('dark'),
    column: R('column'), glass: R('glass'), steel: R('steel'), stock: R('stock'), belt: R('belt'), media: R('media') };
  const pm = [0xffd6e0, 0xffe7a3, 0xbfe3ff, 0xc9f2d0, 0xe3d4ff, 0xffc9a6, 0xfff3c4, 0xf9b8b8, 0xd2c1a8, 0xfee500, 0xff8c69].map(x => new THREE.MeshStandardMaterial({ color: x, roughness: 0.75 }));
  const plushM = [0xc8813b, 0xffb6c1, 0xfee500, 0xf5f0e6, 0x9b6b43, 0xffffff, 0xa7d8f0].map(x => new THREE.MeshStandardMaterial({ color: x, roughness: 0.95 }));
  function canvasTex(w, h, draw) {
    const cv = document.createElement('canvas'); cv.width = w; cv.height = h; draw(cv.getContext('2d'), w, h);
    const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
  }
  for (const b of S.boxes || []) if (SOLID.has(b.type)) c.collide(b.x0, b.y0, b.x1, b.y1, b.h ?? 1);
  for (const [cx, cy] of S.columns || []) c.collide(cx - 0.3, cy - 0.3, cx + 0.3, cy + 0.3, BH);

  const add = m => { m.castShadow = true; m.receiveShadow = true; G.add(m); return m; };
  const box = (x0, y0, x1, y1, z0, z1, mat, r = 0) => {
    const g = r > 0 ? new RoundedBoxGeometry(x1 - x0, z1 - z0, y1 - y0, 2, r) : new THREE.BoxGeometry(x1 - x0, z1 - z0, y1 - y0);
    const m = new THREE.Mesh(g, mat); m.position.set((x0 + x1) / 2, (z0 + z1) / 2, (y0 + y1) / 2); return add(m);
  };
  function sign(text, x, y, z, w, h, rotY, bg = '#FEE500', fg = '#222') {
    const t = canvasTex(1024, Math.round(1024 * h / w), (g, cw, ch) => { g.fillStyle = bg; g.fillRect(0, 0, cw, ch); g.fillStyle = fg;
      g.font = `bold ${Math.round(ch * 0.55)}px "Noto Sans KR","WenQuanYi Zen Hei",sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, cw / 2, ch / 2 + 2); });
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.15 }));
    m.position.set(x, z, y); m.rotation.y = rotY; if (NORTH) m.scale.x = -1; G.add(m); return m;
  }
  function products(x0, y0, x1, y1, z, kind = 'mix', density = 1) {
    const n = Math.floor((x1 - x0) * (y1 - y0) * 28 * density);
    for (let i = 0; i < n; i++) {
      const px = x0 + 0.06 + rnd() * (x1 - x0 - 0.12), py = y0 + 0.06 + rnd() * (y1 - y0 - 0.12);
      if (kind === 'plush' || (kind === 'mix' && rnd() < 0.35)) { const r = 0.07 + rnd() * 0.06; const m = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), plushM[Math.floor(rnd() * plushM.length)]); m.scale.set(1, 0.9, 0.85); m.position.set(px, z + r * 0.9, py); add(m); }
      else { const bw = 0.06 + rnd() * 0.12, bh = 0.05 + rnd() * 0.18, bd = 0.05 + rnd() * 0.1; const m = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), pm[Math.floor(rnd() * pm.length)]); m.position.set(px, z + bh / 2, py); m.rotation.y = (rnd() - .5) * .3; add(m); }
    }
  }
  function bearFigure(cx, cy, s, mat) {
    const g = new THREE.Group(), sp = (r, x, y, z, m = mat, sc = [1, 1, 1]) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r * s, 36, 24), m); o.position.set(x * s, y * s, z * s); o.scale.set(...sc); o.castShadow = true; g.add(o); return o; };
    sp(0.5, 0, 0.55, 0, mat, [1, 1.1, 0.9]); sp(0.62, 0, 1.45, 0, mat, [1.05, 0.92, 0.95]); sp(0.17, -0.42, 1.95, 0); sp(0.17, 0.42, 1.95, 0);
    const eye = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.3 }); sp(0.045, -0.2, 1.5, -0.57, eye); sp(0.045, 0.2, 1.5, -0.57, eye);
    sp(0.16, 0, 1.33, -0.56, new THREE.MeshStandardMaterial({ color: 0xf6efe2, roughness: 0.9 }), [1.3, 0.8, 0.7]); sp(0.15, -0.52, 0.75, -0.1, mat, [1, 1.6, 1]); sp(0.15, 0.52, 0.75, -0.1, mat, [1, 1.6, 1]);
    g.position.set(cx, 0, cy); G.add(g); return g;
  }
  function person(x, y, color, h = 1.68, face = 0) {
    const g = new THREE.Group(), cloth = new THREE.MeshStandardMaterial({ color, roughness: 0.85 }), pants = new THREE.MeshStandardMaterial({ color: 0x3a4250, roughness: 0.9 });
    const l1 = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, h * 0.4, 4, 10), pants); l1.position.set(-0.09, h * 0.25, 0); const l2 = l1.clone(); l2.position.x = 0.09;
    const t = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, h * 0.26, 6, 14), cloth); t.position.y = h * 0.62; t.scale.z = 0.7;
    const hd = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 14), new THREE.MeshStandardMaterial({ color: 0xe8c7a8, roughness: 0.8 })); hd.position.y = h * 0.9;
    const hr = new THREE.Mesh(new THREE.SphereGeometry(0.115, 20, 14, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x2a1d15, roughness: 0.9 })); hr.position.y = h * 0.9 + 0.01;
    for (const m of [l1, l2, t, hd, hr]) { m.castShadow = true; g.add(m); } g.position.set(x, 0, y); g.rotation.y = face; G.add(g);
  }

  // ---------------- Interior shell
  if (S.shell) {
    const fl = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD), M.floor); fl.rotation.x = -Math.PI / 2; fl.position.set(BW / 2, 0, BD / 2); fl.receiveShadow = true; G.add(fl);
    if (VIEW === 'aerial' || VIEW === 'top') { const gr = new THREE.Mesh(new THREE.PlaneGeometry(BW * 4, BD * 4), new THREE.MeshStandardMaterial({ color: 0xd9d6cf, roughness: 1 })); gr.rotation.x = -Math.PI / 2; gr.position.set(BW / 2, -0.02, BD / 2); gr.receiveShadow = true; G.add(gr); }
    const wallH = CUT ? 1.1 : (VIEW === 'top' ? 0.4 : BH);
    box(-0.25, 0, 0, BD, 0, wallH, M.wall); box(BW, 0, BW + 0.25, BD, 0, wallH, M.wall); box(-0.25, BD, BW + 0.25, BD + 0.25, 0, CUT ? 3.2 : wallH, M.wall);
    const doors = S.boxes.filter(b => b.type === 'door'); let segs = [[0, BW]];
    for (const d of doors) { const n = []; for (const [a, b] of segs) { if (d.x1 <= a || d.x0 >= b) n.push([a, b]); else { if (d.x0 > a) n.push([a, d.x0]); if (d.x1 < b) n.push([d.x1, b]); } } segs = n; }
    for (const [a, b] of segs) { box(a, -0.06, b, 0, 0, CUT ? 1.1 : BH, M.glass);
      if (!CUT) for (let x = a; x <= b + 0.01; x += (b - a) / Math.max(1, Math.round((b - a) / 2.5))) box(x - 0.03, -0.08, x + 0.03, 0.02, 0, BH, M.dark); }
    if (!CUT) for (const d of doors) { box(d.x0 - 0.05, -0.1, d.x0 + 0.05, 0.05, 0, 2.6, M.dark); box(d.x1 - 0.05, -0.1, d.x1 + 0.05, 0.05, 0, 2.6, M.dark); box(d.x0, -0.1, d.x1, 0.05, 2.6, BH, M.dark); }
    for (const [cx, cy] of S.columns) box(cx - 0.3, cy - 0.3, cx + 0.3, cy + 0.3, 0, CUT ? 3.0 : BH, M.column);
    if (!CUT && VIEW !== 'top') {
      const c = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD), new THREE.MeshStandardMaterial({ color: 0xf2f0ec, roughness: 1 })); c.rotation.x = Math.PI / 2; c.position.set(BW / 2, BH, BD / 2); G.add(c);
      const lm = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff4e0, emissiveIntensity: 2.2 });
      for (let x = 2; x < BW; x += 3) for (let y = 1.5; y < BD; y += 3) { const l = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.02, 20), lm); l.position.set(x, BH - 0.01, y); G.add(l); }
    }
    for (let x = 3; x < BW; x += 6) for (let y = 3.5; y < BD; y += 7) { const p = new THREE.PointLight(0xfff1dc, 7, 9, 2); p.position.set(x, BH - 0.3, y); G.add(p); }
  }

  // ---------------- Fixtures
  for (const i of S.boxes) {
    const vertical = (i.y1 - i.y0) > (i.x1 - i.x0), cx = (i.x0 + i.x1) / 2, cy = (i.y0 + i.y1) / 2;
    switch (i.type) {
      case 'wall_shelf': {
        box(i.x0, i.y0, i.x1, i.y1, 0, 0.12, M.dark);
        if (vertical) { const bx = i.x0 < BW / 2 ? i.x0 : i.x1 - 0.04; box(bx, i.y0, bx + 0.04, i.y1, 0, i.h, M.wood); }
        else { const by = i.y1 > BD - 1 ? i.y1 - 0.04 : i.y0; box(i.x0, by, i.x1, by + 0.04, 0, i.h, M.wood); }
        for (const z of [0.12, 0.55, 0.95, 1.35, 1.75].filter(z => z < i.h - 0.2)) { box(i.x0 + .02, i.y0 + .02, i.x1 - .02, i.y1 - .02, z, z + 0.03, M.white); products(i.x0 + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, z + .03, z > 1.2 ? 'plush' : 'mix', 1.1); }
        box(i.x0, i.y0, i.x1, i.y1, i.h - 0.04, i.h, M.wood); break; }
      case 'island': {
        box(i.x0 + .08, i.y0 + .08, i.x1 - .08, i.y1 - .08, 0, Math.max(0.05, i.h - 0.35), M.white, 0.04); box(i.x0, i.y0, i.x1, i.y1, Math.max(0.05, i.h - 0.35), Math.max(0.1, i.h - 0.3), M.wood, 0.02);
        products(i.x0 + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, Math.max(0.1, i.h - 0.3), 'mix', 1.0);
        const a = (i.x1 - i.x0) * .3, b = (i.y1 - i.y0) * .3; box(i.x0 + a, i.y0 + b, i.x1 - a, i.y1 - b, Math.max(0.1, i.h - 0.3), i.h, M.wood); products(i.x0 + a, i.y0 + b, i.x1 - a, i.y1 - b, i.h, 'plush', 1.3); break; }
      case 'gondola': {
        box(i.x0, i.y0, i.x1, i.y1, 0, 0.12, M.dark);
        if (vertical) box(cx - .02, i.y0, cx + .02, i.y1, 0, i.h, M.wood); else box(i.x0, cy - .02, i.x1, cy + .02, 0, i.h, M.wood);
        for (const z of [0.12, 0.6, 1.05, 1.5].filter(z => z < i.h - 0.1)) { box(i.x0, i.y0, i.x1, i.y1, z, z + .03, M.white); products(i.x0 + .04, i.y0 + .04, i.x1 - .04, i.y1 - .04, z + .03, 'mix', 1); } break; }
      case 'bin': box(i.x0, i.y0, i.x1, i.y1, 0, i.h - 0.25, M.yellow, 0.03); products(i.x0 + .03, i.y0 + .03, i.x1 - .03, i.y1 - .03, i.h - 0.25, 'mix', 2.2); break;
      case 'window': box(i.x0, i.y0, i.x1, i.y1, 0, i.h, M.white, 0.03); products(i.x0 + .2, i.y0 + .1, i.x1 - .2, i.y1 - .1, i.h, 'plush', 0.9); bearFigure(cx, cy, 0.45, plushM[0]); break;
      case 'checkout': {
        const cm = i.zone === 'cafe' ? M.wood : M.white;
        box(i.x0, i.y0, i.x1, i.y1, 0, i.h, cm, 0.04); box(i.x0 - .02, i.y0 - .02, i.x1 + .02, i.y1 + .02, i.h, i.h + .04, M.wood);
        const n = i.n || Math.max(1, Math.round((vertical ? i.y1 - i.y0 : i.x1 - i.x0) / 1.8));
        for (let k = 0; k < n; k++) { const t = (k + .5) / n, px = vertical ? cx : i.x0 + t * (i.x1 - i.x0), py = vertical ? i.y0 + t * (i.y1 - i.y0) : cy;
          const s = box(px - .18, py - .02, px + .18, py + .02, i.h + .15, i.h + .42, M.dark); s.rotation.y = vertical ? Math.PI / 2 : 0; box(px - .02, py - .02, px + .02, py + .02, i.h, i.h + .16, M.steel); }
        break; }
      case 'figure': bearFigure(cx, cy, 1.25, plushM[0]); { const b = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.05, 0.12, 48), M.yellow); b.position.set(cx, .06, cy); add(b); } break;
      case 'media': {
        box(i.x0, i.y0, i.x1, i.y1, 0.3, i.h, M.dark);
        const m = new THREE.Mesh(new THREE.PlaneGeometry((vertical ? i.y1 - i.y0 : i.x1 - i.x0) - 0.1, i.h - 0.4), M.media);
        if (vertical) { m.position.set(i.x1 + .01, (i.h + .3) / 2, cy); m.rotation.y = Math.PI / 2; } else { m.position.set(cx, (i.h + .3) / 2, i.y0 - .01); m.rotation.y = Math.PI; }
        if (NORTH) m.scale.x = -1; G.add(m); break; }
      case 'stock': box(i.x0, i.y0, i.x1, i.y1, 0, CUT ? 2.4 : i.h, M.stock); break;
      case 'block': box(i.x0, i.y0, i.x1, i.y1, 0, i.h || 1, new THREE.MeshStandardMaterial({ color: i.color ? new THREE.Color(...i.color) : 0xcccccc, roughness: .7 })); break;
      case 'kiosk': {
        const r = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, i.h, 40), M.white); r.position.set(cx, i.h / 2, cy); add(r);
        for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2 + Math.PI / 4, s = new THREE.Mesh(new THREE.BoxGeometry(.42, .62, .03), M.media); s.position.set(cx + Math.sin(a) * .64, 1.35, cy + Math.cos(a) * .64); s.rotation.y = a; G.add(s); } break; }
      case 'room': {
        const t = 0.1, mid = cx, rm = new THREE.MeshStandardMaterial({ color: 0xffe9d6, roughness: 0.9 });
        box(i.x0, i.y0, i.x0 + t, i.y1, 0, i.h, rm); box(i.x1 - t, i.y0, i.x1, i.y1, 0, i.h, rm); box(i.x0, i.y0, mid - 1.1, i.y0 + t, 0, i.h, rm); box(mid + 1.1, i.y0, i.x1, i.y0 + t, 0, i.h, rm); box(mid - 1.1, i.y0, mid + 1.1, i.y0 + t, 2.2, i.h, rm); break; }
      case 'stair': {
        const mid = cx, n = 14, rise = Math.min(2.2, BH * 0.55), run = (i.y1 - i.y0) / n;
        for (let k = 0; k < n; k++) box(i.x0 + .05, i.y0 + k * run, mid - .05, i.y0 + (k + 1) * run, 0, (k + 1) * rise / n, M.white);
        box(mid + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, 0, .012, new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 1 }));
        box(i.x0, i.y0, i.x0 + .03, i.y1, 0, 1.1, M.glass); box(i.x1 - .03, i.y0, i.x1, i.y1, 0, 1.1, M.glass); box(i.x0, i.y1 - .03, i.x1, i.y1, 0, 1.1, M.glass); break; }
      case 'elevator': box(i.x0, i.y0, i.x1, i.y1, 0, CUT ? 2.6 : BH, M.steel); box(i.x0 + .35, i.y0 - .02, i.x1 - .35, i.y0, 0, 2.2, M.dark); break;
      case 'tables': {
        const tm = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
        for (let yy = i.y0 + 0.9; yy < i.y1 - 0.5; yy += 1.7) for (let xx = i.x0 + 0.9; xx < i.x1 - 0.5; xx += 2.2) {
          const tp = new THREE.Mesh(new THREE.CylinderGeometry(.38, .38, .04, 32), tm); tp.position.set(xx, .74, yy); add(tp);
          const lg = new THREE.Mesh(new THREE.CylinderGeometry(.04, .04, .72, 12), M.steel); lg.position.set(xx, .36, yy); add(lg);
          for (const dx of [-.62, .62]) { const st = new THREE.Mesh(new THREE.CylinderGeometry(.2, .2, .05, 24), M.wood); st.position.set(xx + dx, .45, yy); add(st); box(xx + dx + (dx > 0 ? .14 : -.2), yy - .18, xx + dx + (dx > 0 ? .2 : -.14), yy + .18, .45, .85, M.wood); } }
        break; }
      case 'queue': if ((i.x1 - i.x0) < 3.5) { const xs = [i.x0 + .05, cx, i.x1 - .05];
        for (const x of xs) for (let y = i.y0 + .3; y <= i.y1 - .2; y += 1.0) { const p = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, .95, 12), M.steel); p.position.set(x, .475, y); add(p);
          if (y + 1.0 <= i.y1 - .2 && !(x === xs[1] && y < i.y0 + .6)) box(x - .01, y, x + .01, y + 1.0, .86, .91, M.belt); } } break;
    }
  }
  for (const s of (S.signs || [])) if (VIEW !== 'top') sign(...s);
  const PC = [0xe57373, 0x64b5f6, 0x81c784, 0xffb74d, 0xba68c8, 0xf06292, 0x4db6ac, 0x7986cb, 0xa1887f, 0xffd54f, 0x90a4ae, 0x4fc3f7, 0xaed581, 0xff8a65, 0x9575cd];
  (S.people || []).forEach((p, k) => person(p[0], p[1], PC[k % PC.length], 1.55 + rnd() * .25, rnd() * 6.28));

  return G;
}
