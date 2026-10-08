// Entity types, behaviours and material themes come from plugins. The core knows none of them by name.
//
//   plugin = {name, version, types: {typeName: {fields: {...doc}, build(entity, ctx) -> Object3D}},
//             behaviors: {name: (obj, params, t, dt) => void}, materials: {name: spec}}
//
// A type's build() returns an object placed at the origin in world axes (z up); the engine applies pos/rot/scale
// and adds children. ctx = {THREE, mats, world, view, rnd, colliders, extent}.
export class Registry {
  constructor() { this.types = new Map(); this.behaviors = new Map(); this.plugins = []; }

  use(plugin, mats = null) {
    for (const [k, def] of Object.entries(plugin.types || {})) {
      if (this.types.has(k)) throw new Error(`type "${k}" already registered by ${this.types.get(k).plugin}`);
      this.types.set(k, { ...def, plugin: plugin.name });
    }
    for (const [k, fn] of Object.entries(plugin.behaviors || {})) this.behaviors.set(k, fn);
    if (mats && plugin.materials) mats.theme(plugin.name, plugin.materials);
    this.plugins.push({ name: plugin.name, version: plugin.version || '0' });
    return this;
  }

  known() { return new Set(this.types.keys()); }

  // Machine-readable catalogue for the agent layer: which types exist, their fields, and which plugin owns them.
  catalogue() {
    return [...this.types.entries()].map(([k, d]) => ({ type: k, plugin: d.plugin, fields: d.fields || {}, doc: d.doc || '' }));
  }
}
