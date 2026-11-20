"""Utilidades de YouTube: IDs, metadatos, streams y URLs de delegación."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request

import yt_dlp

_ID_PATTERNS = [
    r"(?:youtube\.com/watch|m\.youtube\.com/watch)[?&#/]+.*?\bv=([\w-]{11})",
    r"youtu\.be/([\w-]{11})",
    r"youtube\.com/(?:shorts|embed|live|v)/([\w-]{11})",
    r"youtube\.com/watch\?v=([\w-]{11})",
]

_STREAM_CACHE: dict[str, tuple[str, dict, float]] = {}
_STREAM_LOCK = threading.Lock()
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.youtube.com/",
}


def extract_video_id(url: str) -> str | None:
    url = (url or "").strip()
    if re.fullmatch(r"[\w-]{11}", url):
        return url
    for pattern in _ID_PATTERNS:
        m = re.search(pattern, url, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_metadata(url: str, video_id: str) -> dict:
    result = {
        "titulo": video_id,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "duracion": 0,
    }
    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 10,
            "noplaylist": True,
            # El Python embebido de Android a veces no encuentra el bundle de CA.
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=False)
        if info:
            result["titulo"] = (info.get("title") or result["titulo"])[:200]
            result["duracion"] = int(info.get("duration") or 0)
            # Usar siempre la miniatura JPEG estable (las maxres .webp fallan en móvil).
            return result
    except Exception:
        pass

    try:
        qs = urllib.parse.urlencode({"url": canonical_url(video_id), "format": "json"})
        with urllib.request.urlopen(
            f"https://www.youtube.com/oembed?{qs}", timeout=10
        ) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        result["titulo"] = (info.get("title") or result["titulo"])[:200]
        if info.get("thumbnail_url"):
            result["thumbnail"] = info["thumbnail_url"]
    except Exception:
        pass
    return result


def get_stream(video_id: str) -> tuple[str, dict]:
    """Devuelve una URL progresiva (audio+video) y las cabeceras necesarias.

    El cliente `android` de yt-dlp es el que expone el formato 18 (progresivo).
    La URL se cachea 4 horas porque expira.
    """
    with _STREAM_LOCK:
        cached = _STREAM_CACHE.get(video_id)
        if cached and cached[2] > time.time():
            return cached[0], dict(cached[1])

    opts = {
        "format": "18/best[acodec!=none][vcodec!=none]/best",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "nocheckcertificate": True,
    }
    url = ""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=False)
        url = (info.get("url") or "") if info else ""
    except Exception as ex:
        raise RuntimeError(str(ex)[:200])

    if not url:
        raise RuntimeError("No se pudo resolver el stream")

    headers = dict(_HEADERS)
    with _STREAM_LOCK:
        _STREAM_CACHE[video_id] = (url, headers, time.time() + 4 * 3600)
    return url, headers


def watch_url(video_id: str, seconds: int = 0) -> str:
    url = canonical_url(video_id)
    if seconds and seconds > 0:
        url += f"&t={int(seconds)}s"
    return url


def vlc_url(video_id: str, seconds: int = 0) -> str:
    return f"vlc://{urllib.parse.quote(watch_url(video_id, seconds), safe=':/?=&')}"


def fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
