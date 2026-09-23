"""ViralForge native cinema engine (Wan 2.2 TI2V + stitch, no Maestro app)."""

from trendforge.cinema.director import CinemaDirector, CinemaResult
from trendforge.cinema.plans import robot_boxing_episode
from trendforge.cinema.wan_backend import DiffusersWanBackend, DryRunWanBackend

__all__ = [
    "CinemaDirector",
    "CinemaResult",
    "DiffusersWanBackend",
    "DryRunWanBackend",
    "robot_boxing_episode",
]
