"""Optional third-party backends. Import and register from here."""

from __future__ import annotations

BACKENDS: dict[str, object] = {}


def register(backend: object) -> None:
    ident = getattr(backend, "id", None)
    if not ident:
        raise ValueError("Backend needs an id")
    BACKENDS[str(ident)] = backend
