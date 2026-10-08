# -*- coding: utf-8 -*-
"""Shared shape constants (single definition, injected into the three.js runtime).

Imported from render3d `visibility.py` at se_new@02e87d5, where the same numbers were also used by the
numpy visibility model. Kept identical so scenes authored for render3d render the same here.
"""
TREE = {"cone_r": 0.35, "cone_h": 1.1, "cone_c": 0.65, "trunk_r": 0.07, "trunk_h": 0.3, "trunk_c": 0.12, "segments": 64}
PERSON = {"w": 0.5, "l": 1.7, "h": 0.15}      # lying person, flat rectangle
