from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class MediaPositionChangeEvent(ft.Event["MediaService"]):
    """Posición actual en segundos."""

    position: int


@dataclass
class MediaStateChangeEvent(ft.Event["MediaService"]):
    """Estado del reproductor: playing/paused."""

    state: str
