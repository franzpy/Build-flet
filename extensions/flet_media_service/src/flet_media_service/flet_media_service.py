"""Servicio Flet que envuelve audio_service + just_audio.

Expone reproducción en segundo plano con MediaSession real: notificación con
play/pause/seek, pantalla de bloqueo y botones de auriculares.
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from flet_media_service.types import MediaPositionChangeEvent, MediaStateChangeEvent


@ft.control("MediaService")
class MediaService(ft.Service):
    on_position_change: Optional[ft.EventHandler[MediaPositionChangeEvent]] = None
    on_state_change: Optional[ft.EventHandler[MediaStateChangeEvent]] = None

    async def play(
        self,
        url: str,
        titulo: str,
        caratula: str = "",
        posicion: int = 0,
        duracion: int = 0,
    ) -> None:
        await self._invoke_method(
            "play",
            {
                "url": url,
                "titulo": titulo,
                "caratula": caratula,
                "posicion": int(posicion),
                "duracion": int(duracion),
            },
        )

    async def pause(self) -> None:
        await self._invoke_method("pause")

    async def resume(self) -> None:
        await self._invoke_method("resume")

    async def seek(self, posicion: int) -> None:
        await self._invoke_method("seek", {"posicion": int(posicion)})

    async def stop(self) -> None:
        await self._invoke_method("stop")

    async def get_position(self) -> int:
        return int(await self._invoke_method("get_position"))
