"""Sesión de escucha: estima la posición mientras el video está en otra app.

Como el reproductor externo no expone su posición, guardamos cuándo empezamos
y cuánto tiempo pasó. El usuario puede corregirlo con el slider.
"""

from __future__ import annotations

import time

_sessions: dict[int, dict] = {}


def start(video_id: int, posicion: int, duracion: int) -> None:
    _sessions[video_id] = {
        "inicio": max(0, int(posicion)),
        "acumulado": 0.0,
        "empezado_en": time.time(),
        "activo": True,
        "duracion": max(0, int(duracion or 0)),
    }


def position(video_id: int, duracion: int = 0) -> int:
    s = _sessions.get(video_id)
    if not s:
        return 0
    elapsed = s["acumulado"]
    if s["activo"]:
        elapsed += time.time() - s["empezado_en"]
    total = s["inicio"] + int(elapsed)
    limit = s["duracion"] or duracion or 0
    if limit and total > limit:
        total = limit
    return total


def pause(video_id: int) -> None:
    s = _sessions.get(video_id)
    if s and s["activo"]:
        s["acumulado"] += time.time() - s["empezado_en"]
        s["activo"] = False


def resume(video_id: int) -> None:
    s = _sessions.get(video_id)
    if s and not s["activo"]:
        s["empezado_en"] = time.time()
        s["activo"] = True


def finish(video_id: int, duracion: int = 0) -> int:
    pos = position(video_id, duracion)
    _sessions.pop(video_id, None)
    return pos


def is_active(video_id: int) -> bool:
    return video_id in _sessions
