// Game-engine / pro-tool bridge (XR-10): the scene as it is built, exported to binary glTF (.glb) with three.js's
// own GLTFExporter (vendored r170). glTF is y-up and metric, like the scene graph under the engine's root, so
// Unity, Unreal, Godot and Blender import it at true scale. Lights travel as KHR_lights_punctual; behaviours,
// sounds, triggers and captions do not (glTF has no place for them) -- they stay in the world file.
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';

export async function exportGLB(eng) {
  eng.step(0, true);                                     // make sure every matrix is current
  const lods = [];                                       // full detail, whatever the camera's distance (XR-01 LOD)
  eng.scene.traverse(o => { if (o.isLOD) { lods.push([o, o.levels.map(l => l.object.visible)]); o.levels.forEach((l, i) => { l.object.visible = i === 0; }); } });
  try {
    return await new GLTFExporter().parseAsync(eng.scene, { binary: true, onlyVisible: true, maxTextureSize: 2048 });
  } finally {
    for (const [o, vis] of lods) o.levels.forEach((l, i) => { l.object.visible = vis[i]; });
  }
}

export async function downloadGLB(eng) {
  const buf = await exportGLB(eng);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([buf], { type: 'model/gltf-binary' }));
  a.download = (eng.world.name || 'world').replace(/[^\w가-힣-]+/g, '_') + '.glb';
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
