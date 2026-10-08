# -*- coding: utf-8 -*-
"""The only place the model id and the studio's private data location are decided."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


def model() -> str:
    return os.environ.get("WE_MODEL") or DEFAULT_MODEL


def data_dir() -> Path:
    """Private, per-machine data (vocabularies, sessions). Outside the repository by default so it cannot be committed."""
    return Path(os.environ.get("WE_STUDIO_DIR") or (Path.home() / ".worldengine" / "studio"))


MAX_TOKENS = int(os.environ.get("WE_MAX_TOKENS") or 16000)
MAX_TURNS = int(os.environ.get("WE_MAX_TURNS") or 8)          # tool round trips per artist message (a hard cap)
