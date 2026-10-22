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
        if load in config.E4_REAL_PAGES:
            return config.E4_REAL_PAGES[load]
        return f"http://127.0.0.1:{self.port}/?load={load}"

    def attach(self, debug_port: int, url: str) -> None:
        """Third-party pages can't post to us, so inject the recorder over the DevTools protocol and pull from it."""
        if config.FAKE:
            return
        self._pump_stop = threading.Event()
        threading.Thread(target=_pump, args=(self.store, debug_port, url, self._pump_stop), daemon=True).start()

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
        if getattr(self, "_pump_stop", None):
            self._pump_stop.set()
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

    def detach(self) -> None:
        if getattr(self, "_pump_stop", None):
            self._pump_stop.set()
            self._pump_stop = None
            time.sleep(1.5)  # let the pump's last pull land before the next page's frames
        self.store.last_post, self.store.visible = 0.0, ""

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


# ---------------------------------------------------------------- real pages over DevTools
# Same log as frames.html: rAF intervals and LoAF entries in epoch ms, auto-scroll when the page scrolls.
RECORDER = """(() => {
  if (window.__dartbench) return 'present';
  let frames = [], loaf = [], last = null, y = 0;
  const origin = performance.timeOrigin;
  function tick(now) {
    if (last !== null) frames.push([origin + now, now - last]);
    last = now;
    const max = document.documentElement.scrollHeight - innerHeight;
    if (max > 100) { y = (y + 2) % max; window.scrollTo(0, y); }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  try {
    new PerformanceObserver(l => { for (const e of l.getEntries()) loaf.push([origin + e.startTime, e.duration, e.blockingDuration || 0]); })
      .observe({ type: 'long-animation-frame', buffered: false });
  } catch (e) {}
  window.__dartbench = { drain() { const o = { frames, loaf, visible: document.visibilityState }; frames = []; loaf = []; return JSON.stringify(o); } };
  return 'installed';
})()"""


def _pump(store: _Store, port: int, url: str, stop: threading.Event) -> None:
    import httpx
    from websockets.sync.client import connect

    deadline = time.time() + 60
    ws_url = None
    while not ws_url and time.time() < deadline and not stop.is_set():
        try:
            tabs = httpx.get(f"http://127.0.0.1:{port}/json", timeout=2).json()
            # the page may redirect, so match on host rather than the full URL
            host = url.split("/")[2]
            ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page" and host in t.get("url", "")), None)
        except Exception:
            pass
        if not ws_url:
            time.sleep(1)
    if not ws_url:
        return
    with connect(ws_url, max_size=None, open_timeout=10) as ws:
        msg_id = 0

        def call(method: str, **params):
            nonlocal msg_id
            msg_id += 1
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
            while True:
                m = json.loads(ws.recv(timeout=10))
                if m.get("id") == msg_id:
                    return m.get("result", {})

        def evaluate(expr: str):
            return call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")

        call("Page.addScriptToEvaluateOnNewDocument", source=RECORDER)
        while not stop.is_set():
            try:
                evaluate(RECORDER)  # no-op when present; reinstalls after a navigation
                raw = evaluate("window.__dartbench.drain()")
                if raw:
                    store.add(json.loads(raw))
            except Exception:
                pass
            stop.wait(1)
