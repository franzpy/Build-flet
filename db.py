"""Capa de persistencia SQLite (se ejecuta en el servidor Python)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from models import Category, Progress, Video

DB_PATH = Path(__file__).resolve().parent / "data" / "catalog.db"
_conn: sqlite3.Connection | None = None
_lock = threading.RLock()

DEFAULT_CATEGORIES = [
    ("Música", "#7E57C2", "MUSIC_NOTE"),
    ("Tutoriales", "#26A69A", "SCHOOL"),
    ("Documentales", "#42A5F5", "MOVIE"),
    ("Favoritos", "#EF5350", "FAVORITE"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _init_schema(_conn)
    return _conn


def _init_schema(c: sqlite3.Connection) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE,
            color   TEXT NOT NULL DEFAULT '#7E57C2',
            icono   TEXT NOT NULL DEFAULT 'LABEL'
        );
        CREATE TABLE IF NOT EXISTS videos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_id   TEXT NOT NULL UNIQUE,
            url          TEXT NOT NULL,
            titulo       TEXT NOT NULL,
            thumbnail    TEXT NOT NULL DEFAULT '',
            duracion     INTEGER NOT NULL DEFAULT 0,
            categoria_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            anadido_en   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress (
            video_id        INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
            posicion_seg    INTEGER NOT NULL DEFAULT 0,
            completado      INTEGER NOT NULL DEFAULT 0,
            actualizado_en  TEXT NOT NULL
        );
        """
    )
    for nombre, color, icono in DEFAULT_CATEGORIES:
        c.execute(
            "INSERT OR IGNORE INTO categories(nombre, color, icono) VALUES (?, ?, ?)",
            (nombre, color, icono),
        )
    c.commit()


# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------
def list_categories() -> list[Category]:
    with _lock:
        rows = conn().execute("SELECT * FROM categories ORDER BY id").fetchall()
    return [Category(r["id"], r["nombre"], r["color"], r["icono"]) for r in rows]


def add_category(nombre: str, color: str, icono: str) -> Category | None:
    nombre = nombre.strip()
    if not nombre:
        return None
    with _lock:
        c = conn()
        cur = c.execute(
            "INSERT OR IGNORE INTO categories(nombre, color, icono) VALUES (?, ?, ?)",
            (nombre, color, icono),
        )
        c.commit()
        if not cur.lastrowid:
            return None
        row = c.execute("SELECT * FROM categories WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Category(row["id"], row["nombre"], row["color"], row["icono"])


def update_category(cat_id: int, nombre: str, color: str, icono: str) -> None:
    with _lock:
        c = conn()
        c.execute(
            "UPDATE categories SET nombre=?, color=?, icono=? WHERE id=?",
            (nombre.strip(), color, icono, cat_id),
        )
        c.commit()


def delete_category(cat_id: int) -> None:
    with _lock:
        c = conn()
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------
def _to_video(r: sqlite3.Row) -> Video:
    return Video(
        id=r["id"],
        youtube_id=r["youtube_id"],
        url=r["url"],
        titulo=r["titulo"],
        thumbnail=r["thumbnail"],
        duracion=r["duracion"],
        categoria_id=r["categoria_id"],
        añadido_en=r["anadido_en"],
    )


def list_videos(categoria_id: int | None = None, search: str = "") -> list[Video]:
    sql = "SELECT * FROM videos WHERE 1=1"
    params: list = []
    if categoria_id is not None:
        sql += " AND categoria_id = ?"
        params.append(categoria_id)
    if search.strip():
        sql += " AND LOWER(titulo) LIKE ?"
        params.append(f"%{search.strip().lower()}%")
    sql += " ORDER BY id DESC"
    with _lock:
        rows = conn().execute(sql, params).fetchall()
    return [_to_video(r) for r in rows]


def get_video(video_id: int) -> Video | None:
    with _lock:
        r = conn().execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    return _to_video(r) if r else None


def add_video(
    youtube_id: str,
    url: str,
    titulo: str,
    thumbnail: str,
    duracion: int,
    categoria_id: int | None,
) -> Video | None:
    with _lock:
        c = conn()
        cur = c.execute(
            """INSERT OR IGNORE INTO videos
               (youtube_id, url, titulo, thumbnail, duracion, categoria_id, anadido_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (youtube_id, url, titulo, thumbnail, duracion, categoria_id, _now()),
        )
        c.commit()
        if not cur.lastrowid:
            return None
        row = c.execute("SELECT * FROM videos WHERE id=?", (cur.lastrowid,)).fetchone()
    return _to_video(row)


def update_video(
    video_id: int,
    titulo: str,
    duracion: int,
    categoria_id: int | None,
) -> None:
    with _lock:
        c = conn()
        c.execute(
            "UPDATE videos SET titulo=?, duracion=?, categoria_id=? WHERE id=?",
            (titulo.strip(), duracion, categoria_id, video_id),
        )
        c.commit()


def delete_video(video_id: int) -> None:
    with _lock:
        c = conn()
        c.execute("DELETE FROM videos WHERE id=?", (video_id,))
        c.commit()


# ---------------------------------------------------------------------------
# Progreso
# ---------------------------------------------------------------------------
def get_progress(video_id: int) -> Progress | None:
    with _lock:
        r = conn().execute("SELECT * FROM progress WHERE video_id=?", (video_id,)).fetchone()
    if not r:
        return None
    return Progress(r["video_id"], r["posicion_seg"], r["completado"], r["actualizado_en"])


def save_progress(video_id: int, posicion_seg: int, completado: int = 0) -> None:
    with _lock:
        c = conn()
        c.execute(
            """INSERT INTO progress(video_id, posicion_seg, completado, actualizado_en)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 posicion_seg=excluded.posicion_seg,
                 completado=excluded.completado,
                 actualizado_en=excluded.actualizado_en""",
            (video_id, max(0, int(posicion_seg)), int(completado), _now()),
        )
        c.commit()
