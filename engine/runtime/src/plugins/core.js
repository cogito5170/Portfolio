// Core plugin: primitives, light, text, terrain, path, person, arch. Everything is z up; pos is the BASE centre
// (objects stand on pos), except light/text/path which are placed exactly at pos.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { fallHeight } from '../physics.js';

const UP = g => g.rotateX(Math.PI / 2);                  // three primitives are Y-up; turn them to Z-up
const mesh = (geo, mat) => { const m = new THREE.Mesh(geo, mat); m.castShadow = m.receiveShadow = true; return m; };
const sz = (e, d) => [].concat(e.size ?? d).length === 1 ? [e.size, e.size, e.size] : [].concat(e.size ?? d);

function textTexture(text, w, h, bg, fg) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = Math.max(16, Math.round(1024 * h / w));
  const g = c.getContext('2d'); g.fillStyle = bg; g.fillRect(0, 0, c.width, c.height); g.fillStyle = fg;
  g.font = `bold ${Math.round(c.height * 0.55)}px "Noto Sans KR","WenQuanYi Zen Hei",sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, c.width / 2, c.height / 2 + 2);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export const core = {
  name: 'core',
  version: '1',
  types: {
    group: { doc: 'empty container for children', fields: {}, build: () => new THREE.Group() },
    box: {
      doc: 'box standing on pos', fields: { size: '[sx,sy,sz] m', radius: 'corner radius m', material: 'name|spec' },
      build(e, c) {
        const [x, y, z] = sz(e, [1, 1, 1]);
        const g = e.radius ? new RoundedBoxGeometry(x, y, z, 2, e.radius) : new THREE.BoxGeometry(x, y, z);
        g.translate(0, 0, z / 2); return mesh(g, c.mats.get(e.material));
      },
    },
    cylinder: {
      doc: 'vertical cylinder', fields: { radius: 'm', radius_top: 'm (default = radius)', height: 'm', segments: 'int' },
      build(e, c) { const h = e.height ?? 1, r = e.radius ?? 0.5; const g = UP(new THREE.CylinderGeometry(e.radius_top ?? r, r, h, e.segments || 48)); g.translate(0, 0, h / 2); return mesh(g, c.mats.get(e.material)); },
    },
    cone: {
      doc: 'vertical cone', fields: { radius: 'm', height: 'm' },
      build(e, c) { const h = e.height ?? 1; const g = UP(new THREE.ConeGeometry(e.radius ?? 0.5, h, e.segments || 48)); g.translate(0, 0, h / 2); return mesh(g, c.mats.get(e.material)); },
    },
    sphere: {
      doc: 'sphere resting on pos', fields: { radius: 'm' },
      build(e, c) { const r = e.radius ?? 0.5; const g = new THREE.SphereGeometry(r, 48, 32); g.translate(0, 0, r); return mesh(g, c.mats.get(e.material)); },
    },
    capsule: {
      doc: 'vertical capsule', fields: { radius: 'm', height: 'total height m' },
      build(e, c) { const r = e.radius ?? 0.3, h = Math.max(e.height ?? 1.5, 2 * r); const g = UP(new THREE.CapsuleGeometry(r, h - 2 * r, 8, 24)); g.translate(0, 0, h / 2); return mesh(g, c.mats.get(e.material)); },
    },
    torus: {
      doc: 'torus lying flat (rot to stand it up)', fields: { radius: 'm', tube: 'm', arc_deg: 'deg (default 360)' },
      build(e, c) { const t = e.tube ?? 0.1; const g = new THREE.TorusGeometry(e.radius ?? 0.5, t, 24, 96, (e.arc_deg ?? 360) * Math.PI / 180); g.translate(0, 0, t); return mesh(g, c.mats.get(e.material)); },
    },
    plane: {
      doc: 'horizontal surface at pos.z (floors); textures tile by size_m', fields: { size: '[sx,sy] m' },
      build(e, c) { const [x, y] = [].concat(e.size ?? [10, 10]); const m = mesh(new THREE.PlaneGeometry(x, y), c.mats.tiled(e.material ?? 'ground', x, y)); m.castShadow = false; return m; },
    },
    ground: {
      doc: 'ground under the whole world (4x its extent)', fields: { margin: 'factor (default 4)' },
      build(e, c) {
        const { min, max } = c.extent, k = e.margin ?? 4, W = (max[0] - min[0]) * k, D = (max[1] - min[1]) * k;
        const m = mesh(new THREE.PlaneGeometry(W, D), c.mats.tiled(e.material ?? 'ground', W, D)); m.castShadow = false;
        m.position.set((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, -0.01); return m;
      },
    },
    text: {
      doc: 'flat sign facing -y (readable from the south); rot [0,0,deg] turns it', fields: { text: 'str', size: '[w,h] m', background: 'css colour', color: 'css colour' },
      build(e) {
        const [w, h] = [].concat(e.size ?? [2, 0.5]), t = textTexture(e.text ?? '', w, h, e.background ?? '#ffffff', e.color ?? '#222222');
        const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.15, side: THREE.DoubleSide }));
        m.rotation.x = Math.PI / 2; const g = new THREE.Group(); g.add(m); return g;
      },
    },
    light: {
      doc: 'point or spot light at pos', fields: { kind: 'point|spot', color: 'css', intensity: 'number', distance: 'm', target: '[x,y,z] (spot)' },
      build(e) {
        const col = new THREE.Color(e.color ?? '#fff1dc');
        if (e.kind === 'spot') { const s = new THREE.SpotLight(col, e.intensity ?? 30, e.distance ?? 0, (e.angle_deg ?? 30) * Math.PI / 180, 0.4, 2); s.castShadow = true;
          const g = new THREE.Group(); g.add(s); if (e.target) { s.target.position.set(e.target[0] - e.pos[0], e.target[1] - e.pos[1], e.target[2] - e.pos[2]); g.add(s.target); } return g; }
        return new THREE.PointLight(col, e.intensity ?? 7, e.distance ?? 9, 2);
      },
    },
    terrain: {
      doc: 'heightfield z[j][i] at (i*mpp, j*mpp); vertex colours by height unless colors given', fields: { z: '[[...]]', mpp: 'm per sample', colors: '[[[r,g,b]]]?' },
      build(e, c) {
        const Z = e.z, ny = Z.length, nx = Z[0].length, mpp = e.mpp ?? 1;
        const zs = Z.flat(), zmin = Math.min(...zs), zr = Math.max(1e-6, Math.max(...zs) - zmin);
        const pos = new Float32Array(nx * ny * 3), col = new Float32Array(nx * ny * 3), idx = [];
        const pal = t => { const a = [0.34, 0.45, 0.24], b = [0.46, 0.43, 0.39], s = [0.86, 0.88, 0.92], u = Math.min(1, Math.max(0, (t - 0.4) / 0.4)), v = Math.min(1, Math.max(0, (t - 0.82) / 0.12));
          return a.map((x, k) => (x * (1 - u) + b[k] * u) * (1 - v) + s[k] * v); };
        for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const k = j * nx + i; pos.set([i * mpp, j * mpp, Z[j][i]], 3 * k); col.set(e.colors ? e.colors[j][i] : pal((Z[j][i] - zmin) / zr), 3 * k); }
        for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i, b = a + 1, cc = a + nx, d = cc + 1; idx.push(a, b, cc, b, d, cc); }
        const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3)); g.setIndex(idx); g.computeVertexNormals();
        return mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 }));
      },
    },
    path: {
      doc: 'tube through points (relative to pos)', fields: { pts: '[[x,y,z],...]', radius: 'm' },
      build(e, c) {
        const curve = new THREE.CatmullRomCurve3(e.pts.map(p => new THREE.Vector3(...p)));
        return mesh(new THREE.TubeGeometry(curve, Math.min(600, e.pts.length * 8), e.radius ?? 0.04, 8, false), c.mats.get(e.material ?? 'metal'));
      },
    },
    person: {
      doc: 'stylised standing person facing +x', fields: { height: 'm (default 1.68)', color: 'css (top)' },
      build(e) {
        const h = e.height ?? 1.68, g = new THREE.Group();
        const cloth = new THREE.MeshStandardMaterial({ color: e.color ?? '#64b5f6', roughness: 0.85 }), pants = new THREE.MeshStandardMaterial({ color: 0x3a4250, roughness: 0.9 });
        const skin = new THREE.MeshStandardMaterial({ color: 0xe8c7a8, roughness: 0.8 });
        const part = (geo, mat, x, y, z) => { UP(geo); const m = mesh(geo, mat); m.position.set(x, y, z); g.add(m); return m; };
        part(new THREE.CapsuleGeometry(0.07 * h / 1.68, h * 0.4, 4, 10), pants, 0, -0.09, h * 0.25);
        part(new THREE.CapsuleGeometry(0.07 * h / 1.68, h * 0.4, 4, 10), pants, 0, 0.09, h * 0.25);
        part(new THREE.CapsuleGeometry(0.17 * h / 1.68, h * 0.26, 6, 14), cloth, 0, 0, h * 0.62).scale.set(0.7, 1, 1);
        part(new THREE.SphereGeometry(0.11 * h / 1.68, 20, 14), skin, 0, 0, h * 0.9);
        return g;
      },
    },
    sound: {
      doc: 'a sound source in space (no audio files); starts only after the visitor touches/clicks once; caption required',
      fields: { caption: 'str (required)', recipe: 'tone|chord|noise|pulse', freq: 'Hz', freqs: '[Hz]', wave: 'sine|square|sawtooth|triangle', rate: 'Hz (pulse)', volume: '0..1', visible: 'bool' },
      build(e, c) {
        const g = new THREE.Group();
        if (e.visible !== false) { const m = new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 12), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x9fe8ff, emissiveIntensity: 1.5 })); g.add(m); }
        if (c.audio) c.audio.register(g, e);
        return g;
      },
    },
    arch: {
      doc: 'round arch: two piers and a semicircular head, opening along y', fields: { width: 'opening m', height: 'spring height m', depth: 'm', thickness: 'pier m' },
      build(e, c) {
        const w = e.width ?? 2, h = e.height ?? 2.4, d = e.depth ?? 0.6, t = e.thickness ?? 0.5, mat = c.mats.get(e.material), g = new THREE.Group();
        for (const s of [-1, 1]) { const p = mesh(new THREE.BoxGeometry(t, d, h), mat); p.position.set(s * (w / 2 + t / 2), 0, h / 2); g.add(p); }
        const shape = new THREE.Shape(); const R = w / 2 + t, r = w / 2;
        shape.absarc(0, 0, R, 0, Math.PI, false); shape.lineTo(-r, 0); shape.absarc(0, 0, r, Math.PI, 0, true); shape.lineTo(R, 0);
        const head = new THREE.ExtrudeGeometry(shape, { depth: d, bevelEnabled: false, curveSegments: 48 });
        head.rotateX(Math.PI / 2); head.translate(0, d / 2, h);
        g.add(mesh(head, mat)); return g;
      },
    },
  },
  behaviors: {
    // Behaviours run every frame with the object's base transform kept in obj.userData.base.
    spin(o, b, t) { const ax = b.axis || 'z', w = (b.deg_per_s ?? 30) * Math.PI / 180; o.rotation[ax] = o.userData.base.rot[ax] + w * t; },
    bob(o, b, t) { o.position.z = o.userData.base.pos.z + (b.amp ?? 0.1) * Math.sin(2 * Math.PI * (b.hz ?? 0.5) * t); },
    fall(o, b, t, dt, eng) {     // dropped from `height` above its place; gravity from rules.physics (XR-03)
      o.position.z = o.userData.base.pos.z + fallHeight(t, b.height ?? 2, eng ? eng.phys.g : 9.81, b.restitution ?? 0.5);
    },
    orbit(o, b, t) {
      const c = b.center || [o.userData.base.pos.x, o.userData.base.pos.y], r = b.radius ?? 1, a = 2 * Math.PI * t / (b.period_s ?? 8);
      o.position.x = c[0] + r * Math.cos(a); o.position.y = c[1] + r * Math.sin(a); if (b.face) o.rotation.z = a + Math.PI / 2;
    },
  },
};
