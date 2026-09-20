from __future__ import annotations

from typing import Protocol, runtime_checkable

from trendforge.domain.models import Project, Shot


@runtime_checkable
class VideoBackend(Protocol):
    """Add a new generator by dropping a module in trendforge/plugins and registering it."""

    id: str
    name: str

    def available(self) -> bool: ...

    def generate_shot(self, project: Project, shot: Shot) -> str:
        """Return a filesystem path to an MP4 clip."""
        ...
