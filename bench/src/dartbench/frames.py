"""Frame-time collector: serves the test page and receives rAF intervals and long-animation-frame
entries from it. In fake mode a synthetic generator stands in for the browser."""
from __future__ import annotations

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config

PAGE = Path(__file__).parent / "static" / "frames.html"


class _Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.frames: list[tuple[float, float, str]] = []  # (epoch_ms, interval_ms, kind)
        self.last_post = 0.0
        self.visible = ""
        self.meta: dict = {}

    def add(self, payload: dict) -> None:
        with self.lock:
            self.frames += [(t, d, "raf") for t, d in payload.get("frames", [])]
            self.frames += [(t, d, "loaf") for t, d, *_ in payload.get("loaf", [])]
            self.last_post = time.time()
            self.visible = payload.get("visible", "")
            self.meta = {k: payload.get(k) for k in ("load", "dpr", "w", "h")}

    def drain(self) -> list[tuple[float, float, str]]:
        with self.lock:
            out, self.frames = self.frames, []
            return out


class FrameCollector:
    def __init__(self, port: int = config.FRAMES_PORT):
        self.port = port
        self.store = _Store()
        self._fake_state = "idle"
        self._srv = None

    def url(self, load: str = "light") -> str:
        return f"http://127.0.0.1:{self.port}/?load={load}"

    def __enter__(self) -> "FrameCollector":
        if config.FAKE:
            self._fake_thread = threading.Thread(target=self._fake_loop, daemon=True)
            self._fake_stop = threading.Event()
            self._fake_thread.start()
            return self
        store = self.store

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                try:
                    store.add(json.loads(self.rfile.read(n)))
                except Exception:
                    pass
                self.send_response(204)
                self.end_headers()

        self._srv = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
        if config.FAKE:
            self._fake_stop.set()

    def wait_for_page(self, timeout: float = 60) -> bool:
        """Posting and visible: a hidden tab still posts (setInterval) but records no frames."""
        if config.FAKE:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.healthy()[0]:
                return True
            time.sleep(0.5)
        return False

    def healthy(self) -> tuple[bool, str]:
        """The page must be posting and visible, or rAF is throttled and the data is meaningless."""
        if config.FAKE:
            return True, "fake"
        age = time.time() - self.store.last_post if self.store.last_post else 1e9
        ok = age < 3 and self.store.visible == "visible"
        return ok, f"last post {age:.1f}s ago, visibility={self.store.visible or '?'}"

    def drain(self):
        return self.store.drain()

    # ------------------------------------------------------------ fake
    def set_fake_state(self, state: str) -> None:
        self._fake_state = state

    def _fake_loop(self) -> None:
        """120 Hz with jitter; 'prefill' drops more frames than 'decode', which drops more than idle."""
        rng = random.Random(7)
        drop_p = {"idle": 0.005, "prefill": 0.12, "decode": 0.03}
        while not self._fake_stop.is_set():
            batch = []
            now = time.time() * 1000
            for _ in range(12):
                d = 8.33 + rng.gauss(0, 0.25)
                if rng.random() < drop_p.get(self._fake_state, 0.005):
                    d = 8.33 * rng.choice([2, 2, 3, 4])
                    if d > 50:
                        batch.append((now, d, "loaf"))
                now += d
                batch.append((now, d, "raf"))
            with self.store.lock:
                self.store.frames += batch
                self.store.last_post = time.time()
                self.store.visible = "visible"
            time.sleep(0.1)
