"""Backward compatibility stub: renamed to app.cbc."""
from __future__ import annotations

from .cbc import *  # noqa: F403
from .cbc import (  # noqa: F401
    DEFAULT_PER_SECTION,
    PROVIDER,
    SECTIONS,
    build_pack,
    collect,
    collect_section,
    feed_url,
    pick_unique,
    script_for,
    source_for,
    top_n,
)
