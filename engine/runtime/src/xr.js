// VR entry (XR-08). Offered only when the browser says immersive VR is supported; otherwise nothing changes.
// In VR the headset drives the camera; the world, behaviours, sounds and captions run as usual.
import { VRButton } from 'three/addons/webxr/VRButton.js';

export async function xrSupport() {
  if (!('xr' in navigator) || !navigator.xr) return { api: false, vr: false };
  try { return { api: true, vr: await navigator.xr.isSessionSupported('immersive-vr') }; }
  catch (_) { return { api: true, vr: false }; }
}

export async function enableXR(eng) {
  const s = await xrSupport();
  if (!s.vr) return s;
  eng.renderer.xr.enabled = true;
  const b = VRButton.createButton(eng.renderer); b.style.zIndex = 8; document.body.appendChild(b);
  eng.xrButton = b;
  return s;
}
