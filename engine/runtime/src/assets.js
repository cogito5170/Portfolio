// Imported files (E-02) by name: "asset:<name>" -> a URL this page may read, or null.
//   template: where this page gets them ("/api/asset/{name}?t=..." in the artist's studio, "../assets/{name}" in a
//             published site). No template (a visitor of an unpublished work): nothing resolves, bodies show a
//             placeholder and sounds keep their captions.
//   local:    files the artist just picked in this browser (object URLs) -- they never leave the browser.
export class Assets {
  constructor(template = null) { this.template = template; this.local = new Map(); this.missing = new Set(); this.loaded = []; }
  url(ref) {
    if (typeof ref !== 'string' || !ref.startsWith('asset:')) return null;
    const n = ref.slice(6);
    if (this.local.has(n)) return this.local.get(n);
    if (!this.template) { this.missing.add(n); return null; }
    return this.template.replace('{name}', encodeURIComponent(n));
  }
}
