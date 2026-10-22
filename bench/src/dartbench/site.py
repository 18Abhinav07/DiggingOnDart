"""Exports every run in the database as one `data.js` file for the findings site (site/), so the site's numbers
and frame replays come straight from the same tables as the report."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import analysis as A
from . import config
from .db import DB
from .report import latest_env

# conditions the site replays frame by frame (one representative trial each)
REPLAYS = [
    "7B-Q4 gpu ub512 heavy-page", "7B-Q4 gpu ub128 heavy-page", "7B-Q4 gpu ub64 heavy-page",
    "3B-Q4 gpu ub512 heavy-page", "3B-Q4 gpu ub64 heavy-page",
    "14B-Q4 gpu ub512 heavy-page", "14B-Q4 gpu ub64 heavy-page",
    "7B-Q4 cpu-only heavy-page",
    "7B-Q4 gpu ub512 @aquarium", "7B-Q4 gpu ub64 @aquarium",
    "7B-Q4 gpu ub512 safari-heavy", "7B-Q4 gpu ub64 safari-heavy",
]
LEAD_MS = 2000     # frames kept before prefill starts
MAX_PREFILL_MS = 14000
MAX_DECODE_MS = 4000


def _r(v, nd=1):
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, dict):
        return {k: _r(x, nd) for k, x in v.items()}
    if isinstance(v, list):
        return [_r(x, nd) for x in v]
    return v


def _stat(s: dict) -> dict | None:
    return {k: s.get(k) for k in ("n", "median", "p25", "p75")} if s and s.get("n") else None


def replay(db: DB, condition: str) -> dict | None:
    """Every rAF interval of one trial: a lead-in, the prefill, and the start of decode."""
    sids = A.session_ids(db, "E4")
    for sid in reversed(sids):
        ph = db.query("SELECT trial_id, phase, t0_ms, t1_ms FROM phases WHERE session_id=? AND condition=? "
                      "AND trial_id IS NOT NULL ORDER BY t0_ms", (sid, condition))
        by_trial: dict[int, dict] = {}
        for p in ph:
            by_trial.setdefault(p["trial_id"], {})[p["phase"]] = p
        full = [t for t, d in by_trial.items() if "prefill" in d and "decode" in d]
        if not full:
            continue
        tid = full[len(full) // 2]  # a middle trial: past warm-up effects, not cherry-picked
        pre, dec = by_trial[tid]["prefill"], by_trial[tid]["decode"]
        t0 = pre["t0_ms"] - LEAD_MS
        pre_end = min(pre["t1_ms"], pre["t0_ms"] + MAX_PREFILL_MS)
        dec_end = min(dec["t1_ms"], dec["t0_ms"] + MAX_DECODE_MS)
        rows = db.query("SELECT t_ms, dur_ms FROM frames WHERE session_id=? AND kind='raf' AND t_ms >= ? AND t_ms < ? "
                        "ORDER BY t_ms", (sid, t0, dec_end))
        keep = [r for r in rows if r["t_ms"] < pre_end or r["t_ms"] >= dec["t0_ms"]]
        return {"condition": condition, "trial_id": tid,
                "prefill_ms": pre["t1_ms"] - pre["t0_ms"], "truncated": pre["t1_ms"] > pre_end,
                "phases": [["idle", 0, LEAD_MS], ["prefill", LEAD_MS, pre_end - t0],
                           ["decode", pre_end - t0, pre_end - t0 + (dec_end - dec["t0_ms"])]],
                # (time since start, interval) with prefill cut short where truncated
                "frames": [[r["t_ms"] - t0 if r["t_ms"] < pre_end else r["t_ms"] - dec["t0_ms"] + pre_end - t0,
                            r["dur_ms"]] for r in keep]}
    return None


def build(db: DB | None = None) -> dict:
    db = db or DB()
    e4 = A.e4_view(db)
    conds = []
    for c in e4["conditions"]:
        conds.append({"condition": c["condition"], "budget_ms": c["budget_ms"],
                      "load": config.E4_LOAD.get(c["condition"]) or c["condition"].split()[-1],
                      "phases": {ph: {k: s.get(k) for k in ("n", "p50", "p95", "p99", "max", "dropped_pct", "fps", "loaf_per_s")}
                                 for ph, s in c["phases"].items() if s.get("n")},
                      "ttft": _stat(c["ttft"]), "gen_tps": _stat(c["gen_tps"]), "prompt_tps": _stat(c["prompt_tps"])})
    e1 = [{"model": r["model"], "ctx": r["ctx"], "n": r["n"], "ttft": _stat(r["ttft"]), "prompt_tps": _stat(r["prompt_tps"]),
           "gen_tps": _stat(r["gen_tps"]), "mem_mb": (r.get("mem_mb") or {}).get("median"), "mem_frac": r.get("mem_frac"),
           "quant": r.get("quant"), "pass": r.get("pass")}
          for r in A.config_table(db, "E1")]
    e1b = [{"model": r["model"], "cold": _stat(r["cold"]), "warm": _stat(r["warm"]), "speedup": r.get("speedup"),
            "cold_prompt_n": r.get("cold_prompt_n"), "warm_prompt_n": r.get("warm_prompt_n")} for r in A.e1b_view(db)]
    e2 = [{"model": m["model"], "knee_gb": m.get("knee_gb"), "levels": [{"ballast_gb": l["ballast_gb"], "n": l["n"], "ttft": _stat(l["ttft"]),
                                            "gen_tps": _stat(l["gen_tps"]),
                                            **{k: l.get(k) for k in ("tps_penalty_x", "ttft_penalty_x", "swapouts",
                                                                     "pressure_max")},
                                            "swap_delta_mb": (l.get("swap_delta_mb") or {}).get("median")}
                                           for l in m["levels"]]} for m in A.e2_view(db)]
    env = latest_env(db)
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "db": config.DB_PATH.name,
           "machine": {k: env.get(k) for k in ("chip", "ram_gb", "perf_cores", "eff_cores", "gpu_cores", "macos", "llama_cpp",
                                               "brave", "displays")},
           "records": A.records(db), "decision": {k: v for k, v in e4["decision"].items() if k != "pages"},
           "e0": A.e0_table(db), "e1": e1, "e1b": e1b, "e2": e2, "e4": conds,
           "replays": [r for r in (replay(db, c) for c in REPLAYS) if r]}
    return _r(out, 2)


def export(out: Path, db: DB | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(build(db), separators=(",", ":"), default=str)
    out.write_text(f"window.DART_DATA = {data};\n")
    return out
