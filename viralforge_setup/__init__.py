"""ViralForge Studio Setup — first-run installer and pack catalog."""

from __future__ import annotations

from viralforge_setup.packs import (
    CATALOG,
    PACKS,
    Pack,
    ModelSpec,
    get_pack,
    pack_components,
    pack_estimated_bytes,
)

__all__ = [
    "CATALOG",
    "PACKS",
    "Pack",
    "ModelSpec",
    "get_pack",
    "pack_components",
    "pack_estimated_bytes",
]

__version__ = "0.1.0"
