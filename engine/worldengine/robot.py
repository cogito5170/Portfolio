# -*- coding: utf-8 -*-
"""Articulated bodies. The reference kinematics live in <repo>/kinematics (URDF parser, FK, planar IK, limit check);
this module loads them by file path and turns a URDF into the chain JSON the runtime animates.

    chain = load_chain("kinematics/planar_3_dof.urdf")
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
