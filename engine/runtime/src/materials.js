// Data-driven materials. A world names its materials; entities refer to them by name or carry one inline.
//
//   {"kind": "standard"|"physical"|"basic", "color": "#rrggbb"|[r,g,b] (sRGB 0..1), "roughness", "metalness",
//    "emissive", "emissive_intensity", "opacity", "transmission", "ior", "clearcoat", "side": "double",
//    "texture": {"kind": "speckle"|"wood"|"grid"|"gradient", "colors": [...], "size_m": metres per tile},
//    "image": "asset:<name>" (the artist's own picture, E-02; stretched over each face, not tiled)}
//
// The core ships a neutral default set only. Look-and-feel belongs to the world (or to a plugin's theme), not here.
import * as THREE from 'three';

export const DEFAULTS = {
  default: { color: '#cfcac2', roughness: 0.7 },
  ground: { color: '#d9d6cf', roughness: 1.0 },
  metal: { color: '#c3c7cc', roughness: 0.25, metalness: 0.95 },
  glass: { kind: 'physical', color: '#d6ecf5', roughness: 0.05, transmission: 0.9, opacity: 0.35, ior: 1.45 },
  dark: { color: '#2b2b2b', roughness: 0.6 },
  white: { color: '#fbfaf7', roughness: 0.45 },
};

let seed = 12345;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

export function color(c, fallback = '#cccccc') {
  if (Array.isArray(c)) return new THREE.Color().setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
  return new THREE.Color(c || fallback);
}

const PAINTERS = {
  speckle(g, w, h, cols) {
    g.fillStyle = cols[0] || '#e9e4da'; g.fillRect(0, 0, w, h);
    const ink = cols.slice(1).length ? cols.slice(1) : ['#cfc6b6', '#b9ae9b', '#f7f3ec', '#d8cfbf', '#a79c8a'];
    for (let i = 0; i < 9000; i++) { const r = rnd() * 3.2 + 0.4; g.fillStyle = ink[Math.floor(rnd() * ink.length)];
      g.beginPath(); g.ellipse(rnd() * w, rnd() * h, r, r * (0.5 + rnd() * 0.6), rnd() * 3, 0, 7); g.fill(); }
  },
  wood(g, w, h, cols) {
    const grd = g.createLinearGradient(0, 0, w, 0); grd.addColorStop(0, cols[0] || '#d8b98f'); grd.addColorStop(1, cols[1] || '#caa678');
    g.fillStyle = grd; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 160; i++) { g.strokeStyle = `rgba(120,80,40,${0.04 + rnd() * 0.08})`; g.lineWidth = 1 + rnd() * 2.5; const y = rnd() * h;
      g.beginPath(); g.moveTo(0, y); for (let x = 0; x <= w; x += 32) g.lineTo(x, y + Math.sin(x / 60 + i) * 4); g.stroke(); }
  },
  grid(g, w, h, cols) {
    g.fillStyle = cols[0] || '#1b1f27'; g.fillRect(0, 0, w, h); g.strokeStyle = cols[1] || '#5ad1ff'; g.lineWidth = 3;
    for (let k = 0; k <= 8; k++) { const t = k * w / 8; g.beginPath(); g.moveTo(t, 0); g.lineTo(t, h); g.moveTo(0, t); g.lineTo(w, t); g.stroke(); }
  },
  gradient(g, w, h, cols) {
    const c = cols.length ? cols : ['#7fd3ff', '#ffe36e', '#ff9fb6'], grd = g.createLinearGradient(0, 0, w, h);
    c.forEach((x, k) => grd.addColorStop(k / Math.max(1, c.length - 1), x)); g.fillStyle = grd; g.fillRect(0, 0, w, h);
  },
};

function texture(spec) {
  const paint = PAINTERS[spec.kind];
  if (!paint || typeof document === 'undefined') return null;
  const c = document.createElement('canvas'); c.width = c.height = spec.px || 512;
  paint(c.getContext('2d'), c.width, c.height, spec.colors || []);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8;
  return t;
}

export function build(spec, lib = null) {
  spec = spec || {};
  const kind = spec.kind || (spec.transmission || spec.clearcoat ? 'physical' : 'standard');
  const Cls = { standard: THREE.MeshStandardMaterial, physical: THREE.MeshPhysicalMaterial, basic: THREE.MeshBasicMaterial }[kind] || THREE.MeshStandardMaterial;
  const o = { color: color(spec.color, DEFAULTS.default.color) };
  if (Cls !== THREE.MeshBasicMaterial) {
    o.roughness = spec.roughness ?? 0.7; o.metalness = spec.metalness ?? 0;
    if (spec.emissive) { o.emissive = color(spec.emissive); o.emissiveIntensity = spec.emissive_intensity ?? 1; }
  }
  if (Cls === THREE.MeshPhysicalMaterial) {
    if (spec.transmission !== undefined) o.transmission = spec.transmission;
    if (spec.ior !== undefined) o.ior = spec.ior;
    if (spec.clearcoat !== undefined) o.clearcoat = spec.clearcoat;
  }
  if (spec.opacity !== undefined && spec.opacity < 1) { o.transparent = true; o.opacity = spec.opacity; }
  if (spec.side === 'double') o.side = THREE.DoubleSide;
  const m = new Cls(o);
  if (spec.texture) {
    const t = texture(spec.texture);
    if (t) { m.map = t; if (spec.texture.emissive) { m.emissiveMap = t; m.emissive = new THREE.Color(0xffffff); m.emissiveIntensity = spec.emissive_intensity ?? 0.9; } m.userData.size_m = spec.texture.size_m || 0; }
  }
  if (spec.image && lib && lib.assets) {
    const url = lib.assets.url(spec.image);
    if (url) lib.pending.push(new THREE.TextureLoader().loadAsync(url).then(t => {
      t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
      m.map = t; m.color = new THREE.Color(0xffffff); m.needsUpdate = true; lib.assets.loaded.push(spec.image);
    }).catch(() => { lib.assets.missing.add(spec.image.slice(6)); }));
  }
  m.userData.spec = spec;
  return m;
}

// Library: world materials over plugin themes over core defaults. get(ref) accepts a name or an inline spec.
export class Library {
  constructor(worldMaterials = {}) { this.specs = { ...DEFAULTS }; this.world = worldMaterials || {}; this.cache = new Map(); this.missing = new Set(); this.assets = null; this.pending = []; }
  theme(prefix, specs) { for (const [k, v] of Object.entries(specs)) this.specs[`${prefix}.${k}`] = v; }
  spec(ref) {
    if (ref && typeof ref === 'object') return ref;
    if (ref in this.world) return this.world[ref];
    if (ref in this.specs) return this.specs[ref];
    if (ref !== undefined) this.missing.add(ref);
    return DEFAULTS.default;
  }
  get(ref) {
    if (ref && typeof ref === 'object') return build(ref, this);
    const key = ref ?? 'default';
    if (!this.cache.has(key)) this.cache.set(key, build(this.spec(key), this));
    return this.cache.get(key);
  }
  // A material whose texture tiles every size_m metres over a u x v metre surface.
  tiled(ref, u, v) {
    const m = this.get(ref);
    if (!m.map || !m.userData.size_m) return m;
    const c = m.clone(); c.map = m.map.clone(); c.map.repeat.set(u / m.userData.size_m, v / m.userData.size_m); c.map.needsUpdate = true;
    if (m.emissiveMap) c.emissiveMap = c.map;
    return c;
  }
}
