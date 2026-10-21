"""SQLite store shared by the runner, the report and the dashboard."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY, experiment TEXT, label TEXT, started_at REAL, ended_at REAL,
  status TEXT, env_json TEXT, params_json TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS trials (
  id INTEGER PRIMARY KEY, session_id INTEGER, experiment TEXT, condition TEXT,
  model TEXT, size_b REAL, quant TEXT, draft_model TEXT, ctx_tokens INTEGER, task TEXT,
  ballast_gb REAL, ngl INTEGER, ubatch INTEGER, cache TEXT, trial_idx INTEGER, warmup INTEGER,
  t_start REAL, t_first REAL, t_end REAL,
  ttft_ms REAL, prompt_n INTEGER, prompt_ms REAL, prompt_tps REAL,
  gen_n INTEGER, gen_ms REAL, gen_tps REAL, draft_n INTEGER, draft_accepted INTEGER,
  peak_rss_mb REAL, peak_footprint_mb REAL, peak_sys_used_mb REAL, min_avail_mb REAL, ballast_rss_mb REAL,
  swap_start_mb REAL, swap_end_mb REAL, pageouts INTEGER, swapouts INTEGER, pageins INTEGER,
  pressure_max INTEGER, thermal TEXT,
  prefill_j REAL, decode_j REAL, cpu_w REAL, gpu_w REAL,
  load_s REAL, model_mb REAL, text_head TEXT, stop_reason TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS trials_session ON trials(session_id);
CREATE INDEX IF NOT EXISTS trials_cond ON trials(experiment, condition);
CREATE TABLE IF NOT EXISTS mem_samples (
  trial_id INTEGER, t REAL, rss_mb REAL, footprint_mb REAL, sys_used_mb REAL, avail_mb REAL, swap_mb REAL
);
CREATE INDEX IF NOT EXISTS mem_trial ON mem_samples(trial_id);
CREATE TABLE IF NOT EXISTS frames (
  session_id INTEGER, t_ms REAL, dur_ms REAL, kind TEXT
);
CREATE INDEX IF NOT EXISTS frames_session ON frames(session_id, t_ms);
CREATE TABLE IF NOT EXISTS phases (
  session_id INTEGER, trial_id INTEGER, condition TEXT, phase TEXT, t0_ms REAL, t1_ms REAL
);
CREATE TABLE IF NOT EXISTS llama_bench (
  session_id INTEGER, model TEXT, size_b REAL, quant TEXT, n_prompt INTEGER, n_gen INTEGER,
  avg_ts REAL, stddev_ts REAL, raw_json TEXT
);
"""

TRIAL_COLS = [
    "session_id", "experiment", "condition", "model", "size_b", "quant", "draft_model", "ctx_tokens",
    "task", "ballast_gb", "ngl", "ubatch", "cache", "trial_idx", "warmup", "t_start", "t_first",
    "t_end", "ttft_ms", "prompt_n", "prompt_ms", "prompt_tps", "gen_n", "gen_ms", "gen_tps",
    "draft_n", "draft_accepted", "peak_rss_mb", "peak_footprint_mb", "peak_sys_used_mb", "min_avail_mb", "ballast_rss_mb",
    "swap_start_mb", "swap_end_mb", "pageouts", "swapouts", "pageins", "pressure_max", "thermal",
    "prefill_j", "decode_j", "cpu_w", "gpu_w", "load_s", "model_mb", "text_head", "stop_reason", "error",
]


class DB:
    """Thin wrapper; one connection per thread, writes serialised by a lock."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        return c

    def _write(self, sql: str, args=()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def _write_many(self, sql: str, rows) -> None:
        with self._lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def query(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # sessions
    def start_session(self, experiment: str, label: str, env: dict, params: dict) -> int:
        return self._write(
            "INSERT INTO sessions(experiment,label,started_at,status,env_json,params_json) VALUES(?,?,?,?,?,?)",
            (experiment, label, time.time(), "running", json.dumps(env), json.dumps(params, default=str)),
        )

    def end_session(self, sid: int, status: str, notes: str = "") -> None:
        self._write("UPDATE sessions SET ended_at=?, status=?, notes=? WHERE id=?", (time.time(), status, notes, sid))

    # trials
    def add_trial(self, row: dict) -> int:
        cols = [c for c in TRIAL_COLS if c in row]
        sql = f"INSERT INTO trials({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
        return self._write(sql, [row[c] for c in cols])

    def add_mem_samples(self, trial_id: int, samples: list[tuple]) -> None:
        self._write_many("INSERT INTO mem_samples VALUES(?,?,?,?,?,?,?)", [(trial_id, *s) for s in samples])

    def add_frames(self, sid: int, rows: list[tuple]) -> None:
        self._write_many("INSERT INTO frames VALUES(?,?,?,?)", [(sid, *r) for r in rows])

    def add_phase(self, sid: int, trial_id: int | None, condition: str, phase: str, t0_ms: float, t1_ms: float) -> None:
        self._write("INSERT INTO phases VALUES(?,?,?,?,?,?)", (sid, trial_id, condition, phase, t0_ms, t1_ms))

    def add_llama_bench(self, sid: int, row: dict) -> None:
        self._write(
            "INSERT INTO llama_bench VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, row["model"], row["size_b"], row["quant"], row["n_prompt"], row["n_gen"],
             row["avg_ts"], row["stddev_ts"], json.dumps(row.get("raw", {}))),
        )

    def completed_runs(self, experiment: str, condition: str) -> int:
        """Good, non-warmup trials already stored for a condition, so reruns can resume."""
        r = self.conn.execute(
            "SELECT COUNT(*) FROM trials WHERE experiment=? AND condition=? AND warmup=0 AND error IS NULL",
            (experiment, condition),
        ).fetchone()
        return r[0]
