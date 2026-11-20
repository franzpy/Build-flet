"""Proxy HTTP local para retransmitir el stream de YouTube al móvil.

Los URLs de googlevideo están ligados a la IP que los pidió (la del servidor),
así que el teléfono no puede usarlos directamente. Este proxy los abre desde el
servidor y los envía al cliente, reenviando Range para permitir seeking.
"""

from __future__ import annotations

import shutil
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import youtube

PORT = 8557
_started = False
_lock = threading.Lock()

_HEADERS = ["Content-Type", "Content-Length", "Accept-Ranges", "Content-Range"]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _resolve(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/stream/"):
            return None
        video_id = path[len("/stream/") :].strip("/")
        return video_id if len(video_id) == 11 else None

    def _open(self, video_id: str):
        url, headers = youtube.get_stream(video_id)
        req = urllib.request.Request(url, headers=headers)
        rng = self.headers.get("Range")
        if rng:
            req.add_header("Range", rng)
        return urllib.request.urlopen(req, timeout=30)

    def do_HEAD(self):
        video_id = self._resolve()
        if not video_id:
            self.send_error(404)
            return
        try:
            with self._open(video_id) as resp:
                self.send_response(resp.status)
                for h in _HEADERS:
                    if h in resp.headers:
                        self.send_header(h, resp.headers[h])
                self.end_headers()
        except Exception as ex:
            self.send_error(502, str(ex)[:120])

    def do_GET(self):
        video_id = self._resolve()
        if not video_id:
            self.send_error(404)
            return
        try:
            with self._open(video_id) as resp:
                self.send_response(resp.status)
                for h in _HEADERS:
                    if h in resp.headers:
                        self.send_header(h, resp.headers[h])
                self.send_header("Connection", "close")
                self.end_headers()
                shutil.copyfileobj(resp, self.wfile, 64 * 1024)
        except Exception as ex:
            try:
                self.send_error(502, str(ex)[:120])
            except Exception:
                pass


def start() -> None:
    """Arranca el proxy en un hilo daemon (idempotente)."""
    global _started
    with _lock:
        if _started:
            return
        server = ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _started = True


def local_ip() -> str:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def stream_url(video_id: str) -> str:
    return f"http://{local_ip()}:{PORT}/stream/{video_id}"
