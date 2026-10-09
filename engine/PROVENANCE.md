# Provenance

Files in this directory that came from elsewhere, with the exact source blob. Checked by `tests/test_provenance.py`
(vendored files: our blob hash must equal the upstream blob hash below).

## se_new@02e87d590e0a1a38ca989df105b7abcb78c08c02 `render3d/` → `engine/worldengine/`

| ours | source | source blob | status |
|---|---|---|---|
| `worldengine/__init__.py` | `render3d/__init__.py` | `55fff95e0ba57650d5e8a3148ebc97898bafbada` | modified: docstring rewritten (SAR description removed, provenance added) |
| `worldengine/__main__.py` | `render3d/__main__.py` | `aa0708347ffc516b397983d876d0861c68f525cc` | modified: rewritten: SAR commands (vv, sar, ab, anim) removed; example/layout kept; world, serve, draw added |
| `worldengine/fog.py` | `render3d/fog.py` | `13e1877859952b6355cdd531bcb8ba1ddaf5eea7` | modified: rename + one note line saying the SAR paths refer to se_new |
| `worldengine/headless.py` | `render3d/headless.py` | `21b7294f6026f47f5ff794e7609733e4fa396263` | modified: rewritten: Chromium CLI backend, vendored three.js, runtime rendering (render_world), self-test results |
| `worldengine/html.py` | `render3d/html.py` | `7016be444b157293439b68fe6e47135bc1489a1e` | modified: rename; tree constants imported from shapes.py instead of SAR visibility.py; default title |
| `worldengine/layout.py` | `render3d/layout.py` | `b53e12c4ba89a9f897666c0d1ec92f7f41154aaa` | identical after `render3d`→`worldengine` |
| `worldengine/mpl3d.py` | `render3d/mpl3d.py` | `9f8c9538610ca85fecbbc7f785ad7b684825ed2f` | identical after `render3d`→`worldengine` |
| `worldengine/pipeline.py` | `render3d/pipeline.py` | `a369a24defa7dd0d708000222feab61387fa430a` | modified: missing matplotlib/numpy recorded as 없음 + reason instead of crashing |
| `worldengine/plan.py` | `render3d/plan.py` | `eec1d358897c20e86ea47aa2119b9c78b90f6bc9` | identical |
| `worldengine/scene.py` | `render3d/scene.py` | `76e8eef39cb0cb9f7bdb48859a0ca5995b4b3609` | identical |
| `worldengine/examples/README.md` | `render3d/examples/README.md` | `2488f8a326b4d28adf9247e8894782d52db1ec33` | modified: title line only |
| `worldengine/examples/hongdae.json` | `render3d/examples/hongdae.json` | `98642b1ba56932f0bb8bb37dd131bfb1bb1e894e` | identical |
| `worldengine/examples/store_module.json` | `render3d/examples/store_module.json` | `5fb652db582f7fbe30078926ab310e0d90276cd4` | identical |
| `worldengine/shapes.py` | `render3d/visibility.py` (TREE, PERSON constants only) | `3b3f65520c23a675c3ace41d0a99f6f48aef3ed7` | new file; values copied unchanged |

Not taken (SAR mission V&V, depends on se_new `sar/`): camera.py, discord_cmd.py, mission_anim.py, sar_bridge.py, scene3d_ab.py, visibility.py (except the constants above), vv.py, vv_scene3d.py, the handoff note (.md).

## three.js r170 → `engine/vendor/three/` (MIT, `vendor/three/LICENSE`)

Tag `r170` = commit `beab9e845f9e5ae11d648f55b24a0e910b56a85a`. All files are byte-identical to upstream.

| file | upstream blob |
|---|---|
| `LICENSE` | `d33709fbf00f10b928bae20baf72a5c6da92d03a` |
| `build/three.module.js` | `6bc781491ae24ffd29ee22c8f019cdb67c2c61b7` |
| `examples/jsm/controls/OrbitControls.js` | `7360aab9b347eb677b0ea1a18655c5b86626d29d` |
| `examples/jsm/controls/PointerLockControls.js` | `184c43f60cbf4d0d7ad1e03725e9dbe36e95f20e` |
| `examples/jsm/environments/RoomEnvironment.js` | `9d6056621065748b3da2d516debaa3f6ec5d7125` |
| `examples/jsm/geometries/RoundedBoxGeometry.js` | `8baa16822365c47ba55695ee439b4981e89d1c65` |
| `examples/jsm/postprocessing/EffectComposer.js` | `110eabc8e6025e01cce12da0c99269a4c457d656` |
| `examples/jsm/postprocessing/MaskPass.js` | `b30811c8d4ca86d4adaa1e8b9050e7d776e138d3` |
| `examples/jsm/postprocessing/OutputPass.js` | `63febaf1e78585d86391fc4aed1be5e34ce7948e` |
| `examples/jsm/postprocessing/Pass.js` | `a81582d13de21a6b13216959396daf0d6f8dc294` |
| `examples/jsm/postprocessing/RenderPass.js` | `c60e92d333501e09a44ccd7313e6be909d89bfb9` |
| `examples/jsm/postprocessing/ShaderPass.js` | `597016c9935e254a186ec810288ee8772dc2718a` |
| `examples/jsm/postprocessing/UnrealBloomPass.js` | `48a244051df0ff0d392f3fabba708b39ad36a200` |
| `examples/jsm/shaders/CopyShader.js` | `8c3f2cd443cd4c96edc9c2c04dc760f374d954c9` |
| `examples/jsm/shaders/LuminosityHighPassShader.js` | `0df9f3e7b248280de1c53292337934ac8dffcdea` |
| `examples/jsm/shaders/OutputShader.js` | `289ac10088f0924fe0d8507d5c74e7f349bc5308` |
| `examples/jsm/exporters/GLTFExporter.js` | `4661958d176c38ccacc45b24ab014cf441c0068c` |
| `examples/jsm/webxr/VRButton.js` | `10c362eb86a867ea2e211de4b82d6830808b9518` |
| `examples/jsm/loaders/GLTFLoader.js` | `af826a55d33d38d723ba509b52303594f44a025e` |
| `examples/jsm/utils/BufferGeometryUtils.js` | `cc3e4ef8ea6f15c52e7cf132b7292632f6dcad10` |

## Not copied, used in place

`<repo>/kinematics/` (URDF parser, FK, planar IK, trajectory check, test vectors) is merged on main from another branch;
`worldengine/robot.py` loads it by path and `runtime/tests/kinematics.test.mjs` reads its `test_vectors.json`. Nothing from it is duplicated here.
