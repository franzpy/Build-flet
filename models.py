from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Category:
    id: int
    nombre: str
    color: str = "#7E57C2"
    icono: str = "LABEL"


@dataclass
class Video:
    id: int
    youtube_id: str
    url: str
    titulo: str
    thumbnail: str = ""
    duracion: int = 0
    categoria_id: int | None = None
    añadido_en: str = ""


@dataclass
class Progress:
    video_id: int
    posicion_seg: int = 0
    completado: int = 0
    actualizado_en: str = ""
