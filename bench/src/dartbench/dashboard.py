"""Local dashboard: a stdlib HTTP server with JSON endpoints over the results database and one static page."""
from __future__ import annotations

import json
import math
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analysis as A
from . import config
from .db import DB

PAGE = Path(__file__).parent / "static" / "dashboard.html"


def _clean(o):
    """JSON-safe: NaN/inf to null."""
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def overview(db: DB, scope: str) -> dict:
    sessions = db.query("""
        SELECT s.id, s.experiment, s.label, s.started_at, s.ended_at, s.status, s.params_json,
               COUNT(t.id) FILTER (WHERE t.warmup=0) AS trials,
               COUNT(t.id) FILTER (WHERE t.warmup=0 AND t.error IS NOT NULL) AS errors,
               MAX(t.t_end) AS last_trial
        FROM sessions s LEFT JOIN trials t ON t.session_id = s.id
        GROUP BY s.id ORDER BY s.id DESC""")
    for s in sessions:
        p = json.loads(s.pop("params_json") or "{}")
        s["quick"] = bool(p.get("quick"))
        # a session marked running with no activity for 10 min was killed without cleanup
        last = s["last_trial"] or s["started_at"]
        if s["status"] == "running" and time.time() - last > 600:
            s["status"] = "stale"
    env = db.query("SELECT env_json FROM sessions ORDER BY id DESC LIMIT 1")
    e4 = A.e4_view(db, scope)
    return {"sessions": sessions, "records": A.records(db), "decision": e4["decision"],
            "env": json.loads(env[0]["env_json"]) if env else {}, "fake": config.FAKE,
            "db": config.DB_PATH.name, "limits": config.LIMITS, "claims": config.DART_CLAIMS, "now": time.time()}


def trials(db: DB, q: dict) -> list[dict]:
    where, args = ["1=1"], []
    for key, col in (("exp", "experiment"), ("cond", "condition"), ("session", "session_id")):
        if q.get(key):
            where.append(f"{col}=?")
            args.append(q[key])
    if q.get("errors") == "1":
        where.append("error IS NOT NULL")
    if q.get("warmup") != "1":
        where.append("warmup=0")
    limit = min(int(q.get("limit", 500)), 5000)
    return db.query(f"""SELECT id, session_id, experiment, condition, model, quant, draft_model, ctx_tokens, task,
                        ballast_gb, ngl, ubatch, cache, trial_idx, warmup, t_start, ttft_ms, prompt_n, prompt_tps,
                        gen_n, gen_tps, draft_n, draft_accepted, peak_footprint_mb, peak_rss_mb, peak_sys_used_mb,
                        min_avail_mb, swap_start_mb, swap_end_mb, swapouts, pageins, pressure_max, thermal,
                        decode_j, cpu_w, gpu_w, stop_reason, error
                        FROM trials WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?""", (*args, limit))


def mem(db: DB, tid: int) -> dict:
    t = db.query("SELECT t_start, t_first, t_end FROM trials WHERE id=?", (tid,))
    s = db.query("SELECT t, rss_mb, footprint_mb, sys_used_mb, avail_mb, swap_mb FROM mem_samples WHERE trial_id=? ORDER BY t", (tid,))
    return {"trial": t[0] if t else {}, "samples": s}


def by_index(db: DB, exp: str, cond: str) -> list[dict]:
    """Every run of one condition across sessions, in order: the drift view."""
    return db.query("""SELECT id, session_id, trial_idx, t_start, ttft_ms, gen_tps, peak_footprint_mb, thermal
                       FROM trials WHERE experiment=? AND condition=? AND warmup=0 AND error IS NULL ORDER BY t_start""",
                    (exp, cond))


def route(db: DB, path: str, q: dict):
    scope = q.get("scope", "auto")
    if path == "/api/overview":
        return overview(db, scope)
    if path == "/api/configs":
        return A.config_table(db, q.get("exp", "E1"), scope)
    if path == "/api/trials":
        return trials(db, q)
    if path == "/api/mem":
        return mem(db, int(q["id"]))
    if path == "/api/runs":
        return by_index(db, q.get("exp", "E1"), q.get("cond", ""))
    if path == "/api/compare":
        return A.session_compare(db, q.get("exp", "E1"))
    if path == "/api/e0":
        return A.e0_table(db)
    if path == "/api/e1b":
        return A.e1b_view(db, scope)
    if path == "/api/e2":
        return A.e2_view(db, scope)
    if path == "/api/e3":
        return A.e3_view(db, scope)
    if path == "/api/e4":
        return A.e4_view(db, scope)
    if path == "/api/e4/series":
        return A.frame_series(db, q.get("cond", config.E4_PRIMARY), scope)
    if path == "/api/e5":
        return A.e5_view(db, scope)
    if path == "/api/e6":
        return [r for r in A.config_table(db, "E6", scope) if r.get("j_per_tok")]
    return None


def export(out: Path, series_points: int = 1200) -> Path:
    """The dashboard as one static file: every endpoint the page reads, precomputed and inlined, so it opens from
    disk or GitHub Pages with no server. Per-trial memory traces are left out (they are the bulk of the database)."""
    db = DB()
    snap: dict = {}

    def put(path: str, **q):
        key = path + ("?" + "&".join(f"{k}={v}" for k, v in sorted(q.items())) if q else "")
        snap[key] = route(db, path, {k: str(v) for k, v in q.items()})

    for p in ("/api/overview", "/api/e0", "/api/e1b", "/api/e2", "/api/e3", "/api/e4", "/api/e5", "/api/e6"):
        put(p)
    put("/api/configs", exp="E1")
    put("/api/compare", exp="E1")
    for r in snap["/api/configs?exp=E1"]:
        put("/api/runs", exp="E1", cond=r["condition"])
    for c in snap["/api/e4"]["conditions"]:
        snap[f"/api/e4/series?cond={c['condition']}"] = A.frame_series(db, c["condition"], "auto", series_points)
    snap["/api/trials"] = trials(db, {"limit": "5000", "errors": ""}) + trials(db, {"limit": "5000", "errors": "1"})
    snap["_meta"] = {"exported": time.time(), "db": config.DB_PATH.name}
    page = PAGE.read_text().replace("<script>\n", "<script>\nwindow.SNAPSHOT = " +
                                    json.dumps(_clean(snap), default=str, separators=(",", ":")).replace("</", "<\\/")
                                    + ";\n", 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out


def serve(port: int = config.DASHBOARD_PORT, open_browser: bool = True) -> None:
    db = DB()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                data = route(db, u.path, q)
            except Exception as e:
                return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
            if data is None:
                return self._send(404, b'{"error":"not found"}', "application/json")
            self._send(200, json.dumps(_clean(data), default=str).encode(), "application/json")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/"
    print(f"dashboard on {url} reading {config.DB_PATH} (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
