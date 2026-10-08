# -*- coding: utf-8 -*-
"""worldengine -- one scene (JSON) -> interactive three.js page, headless PNG and (optionally) a 2D plan.

Provenance: imported from cogito5170/se_new@02e87d5 `render3d/` (the "gentle_monster" 3D tool) and evolved
here into the experience runtime of the World Platform (SPEC.md v0.4, sections XR-*). What was kept, what was
dropped and why is in engine/README.md.

    scene.py      the scene format + check() (say what is wrong, never silently fix it)
    layout.py     interior layout (items: shelves, islands, stairs, ...) -> scene
    shapes.py     shared shape constants (tree, person) used by the renderer
    fog.py        Beer-Lambert fog helpers
    html.py       self-contained three.js r170 page (PBR, soft shadows, orbit control)
    headless.py   that page -> PNG in headless Chromium (playwright or the Chromium CLI); vendored three.js
    plan.py       2D plan PNG (needs matplotlib)
    mpl3d.py      non-photoreal 3D fallback (needs matplotlib)
    pipeline.py   runs the above once and records **which backend produced each image**

Coordinates: metres. x = east; y = scene["y_axis"] ("north" for floor plans, "south" for DEM rows); z = up.
"""
