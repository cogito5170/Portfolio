# -*- coding: utf-8 -*-
"""Articulated bodies. The reference kinematics live in <repo>/kinematics (URDF parser, FK, planar IK, limit check);
this module loads them by file path and turns a URDF into the chain JSON the runtime animates.

    chain = load_chain("kinematics/planar_3_dof.urdf")
    to_urdf(chain) -> URDF text (RB-01 export: the same serial chain, back out for ROS / Blender tools)
    chain["joints"] == [{"name", "type", "xyz", "rpy", "axis", "lower", "upper"}, ...]   # serial, file order
    tip(chain, q) -> [x, y, z]       (reference FK)

The reference treats the joints as one serial chain in file order; so does the runtime (robot.js).
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KIN_DIR = REPO / "kinematics"


def _load(name: str):
    spec = importlib.util.spec_from_file_location("wp_" + name, KIN_DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


K = _load("kinematics")
U = _load("urdf_parser")
ACTIVE = ("revolute", "continuous")


def load_chain(urdf_path) -> dict:
    r = U.parse_urdf(str(urdf_path))
    return {"name": r.name, "source": Path(urdf_path).name,
            "joints": [{"name": j.name, "type": j.type, "xyz": list(j.origin_xyz), "rpy": list(j.origin_rpy), "axis": list(j.axis),
                        "lower": j.limit_lower, "upper": j.limit_upper} for j in r.joints]}


def _num(v) -> str:
    return repr(float(v))                 # shortest text that reads back as the same float


def to_urdf(chain: dict, velocity: float = 1.5) -> str:
    """RB-01 export. A serial chain of links (base_link, then one link per joint) with each joint's origin, axis and
    limits exactly as the chain holds them; floats are written so they read back bit-identical. velocity is the
    joint-speed limit the simulation enforced (guard.check default); effort is unknown here and written as 0.
    Kinematics only: no visual or collision geometry, no masses (the chain does not have them)."""
    from xml.sax.saxutils import quoteattr
    out = ['<?xml version="1.0"?>', '<!-- exported by worldengine (RB-01): kinematics only -->',
           '<robot name=%s>' % quoteattr(chain["name"]), '  <link name="base_link"/>']
    parent = "base_link"
    for i, j in enumerate(chain["joints"]):
        child = "link_%d" % (i + 1)
        out += ['  <link name="%s"/>' % child,
                '  <joint name=%s type=%s>' % (quoteattr(j["name"]), quoteattr(j["type"])),
                '    <parent link="%s"/>' % parent, '    <child link="%s"/>' % child,
                '    <origin xyz="%s" rpy="%s"/>' % (" ".join(map(_num, j["xyz"])), " ".join(map(_num, j["rpy"]))),
                '    <axis xyz="%s"/>' % " ".join(map(_num, j["axis"]))]
        if j["type"] != "fixed":
            out.append('    <limit lower="%s" upper="%s" effort="0" velocity="%s"/>' % (_num(j["lower"]), _num(j["upper"]), _num(velocity)))
        out.append('  </joint>')
        parent = child
    out.append('</robot>')
    return "\n".join(out) + "\n"


def to_robot(chain: dict):
    """chain JSON -> the reference's Robot object (so its FK/limit check run on exactly what we ship)."""
    rb = U.Robot(chain["name"])
    for j in chain["joints"]:
        rb.joints.append(U.Joint(j["name"], j["type"], j["xyz"], j["rpy"], j["axis"], j["lower"], j["upper"]))
    return rb


def active(chain: dict) -> "list[dict]":
    return [j for j in chain["joints"] if j["type"] in ACTIVE]


def tip(chain_or_robot, q) -> "list[float]":
    rb = chain_or_robot if hasattr(chain_or_robot, "joints") and not isinstance(chain_or_robot, dict) else to_robot(chain_or_robot)
    return K.forward_kinematics(rb, list(q))


def frames(chain: dict, q) -> "list[list[float]]":
    """Positions of every joint origin plus the tip (reference FK)."""
    return K.forward_kinematics_full(to_robot(chain), list(q))


def reach(chain: dict) -> float:
    """Upper bound of reach from the first joint: the sum of origin offsets."""
    return sum(math.sqrt(sum(v * v for v in j["xyz"])) for j in chain["joints"][1:])
