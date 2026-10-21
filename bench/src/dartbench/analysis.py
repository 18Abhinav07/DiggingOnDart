"""Turns stored trials and frames into the numbers the report and dashboard show."""
from __future__ import annotations

import json
import math
import statistics as st
from collections import defaultdict

from . import config
from .db import DB


# ------------------------------------------------------------------ basics
def pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def summarize(vals) -> dict:
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return {"n": 0}
    out = {"n": len(v), "median": st.median(v), "p25": pct(v, .25), "p75": pct(v, .75), "mean": st.fmean(v),
           "min": min(v), "max": max(v)}
    out["iqr"] = out["p75"] - out["p25"]
    out["sd"] = st.stdev(v) if len(v) > 1 else 0.0
    out["cv"] = out["sd"] / out["mean"] if out["mean"] else None
    return out


def ram_mb() -> float:
    from .sysinfo import total_ram_mb
    return total_ram_mb()


def session_ids(db: DB, exp: str, scope: str = "auto") -> list[int]:
    """Sessions to analyse. 'auto' prefers full runs and falls back to quick ones."""
    rows = db.query("SELECT id, params_json FROM sessions WHERE experiment=?", (exp,))
    full = [r["id"] for r in rows if not json.loads(r["params_json"] or "{}").get("quick")]
    quick = [r["id"] for r in rows if json.loads(r["params_json"] or "{}").get("quick")]
    if scope == "full":
        return full
    if scope == "quick":
        return quick
    if scope == "all":
        return full + quick
    return full or quick


def trials(db: DB, exp: str, scope: str = "auto", ok_only: bool = True) -> list[dict]:
    ids = session_ids(db, exp, scope)
    if not ids:
        return []
    q = f"SELECT * FROM trials WHERE experiment=? AND warmup=0 AND session_id IN ({','.join('?' * len(ids))})"
    if ok_only:
        q += " AND error IS NULL"
    return db.query(q + " ORDER BY id", (exp, *ids))


def mem_mb(t: dict) -> float | None:
    """Memory the model needs: mapped weights + the server's own footprint (KV cache, compute buffers).
    llama.cpp mmaps the GGUF and Metal reads those pages in place, so they are file-backed and absent from
    phys_footprint; every layer is touched per token, so the whole file is resident while it runs."""
    fp = t.get("peak_footprint_mb") or t.get("peak_rss_mb")
    return (fp or 0) + (t.get("model_mb") or 0) if fp or t.get("model_mb") else None


def e2e_tps(t: dict) -> float | None:
    """Generated tokens per wall-clock second including prefill: what a user waits through."""
    if t.get("gen_n") and t.get("t_end") and t.get("t_start") and t["t_end"] > t["t_start"]:
        return t["gen_n"] / (t["t_end"] - t["t_start"])
    return None


# ------------------------------------------------------------------ per-config tables
def config_table(db: DB, exp: str, scope: str = "auto") -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trials(db, exp, scope):
        groups[t["condition"]].append(t)
    total = ram_mb()
    out = []
    for cond, ts in groups.items():
        f = ts[0]
        row = {"condition": cond, "model": f["model"], "size_b": f["size_b"], "quant": f["quant"],
               "ctx": f["ctx_tokens"], "ballast_gb": f["ballast_gb"], "draft": f["draft_model"], "task": f["task"],
               "n": len(ts),
               "ttft": summarize([t["ttft_ms"] for t in ts]),
               "prompt_tps": summarize([t["prompt_tps"] for t in ts]),
               "gen_tps": summarize([t["gen_tps"] for t in ts]),
               "e2e_tps": summarize([e2e_tps(t) for t in ts]),
               "mem_mb": summarize([mem_mb(t) for t in ts]),
               "sys_used_mb": summarize([t["peak_sys_used_mb"] for t in ts]),
               "swapouts": sum(t["swapouts"] or 0 for t in ts),
               "pageins": sum(t["pageins"] or 0 for t in ts),
               "swap_delta_mb": summarize([(t["swap_end_mb"] or 0) - (t["swap_start_mb"] or 0) for t in ts]),
               "pressure_max": max((t["pressure_max"] or 0) for t in ts),
               "load_s": f["load_s"], "model_mb": f["model_mb"]}
        if any(t["draft_n"] for t in ts):
            dn = sum(t["draft_n"] or 0 for t in ts)
            row["accept"] = sum(t["draft_accepted"] or 0 for t in ts) / dn if dn else None
        if any(t["decode_j"] for t in ts):
            row["j_per_tok"] = summarize([t["decode_j"] / t["gen_n"] for t in ts if t["decode_j"] and t["gen_n"]])
            row["prefill_j_per_ktok"] = summarize([t["prefill_j"] / t["prompt_n"] * 1000 for t in ts
                                                   if t["prefill_j"] and t["prompt_n"]])
            row["cpu_w"] = summarize([t["cpu_w"] for t in ts])
            row["gpu_w"] = summarize([t["gpu_w"] for t in ts])
        row["mem_frac"] = (row["mem_mb"].get("median") or 0) / total if total else None
        row["pass"] = {
            "ttft": _lt(row["ttft"].get("median"), config.LIMITS["ttft_ms"]),
            "gen_tps": _gt(row["gen_tps"].get("median"), config.LIMITS["gen_tps"]),
            "mem": _lt(row["mem_frac"], config.LIMITS["mem_frac"]),
        }
        row["pass"]["all"] = all(v for v in row["pass"].values() if v is not None) if all(
            v is not None for v in row["pass"].values()) else None
        row["drift"] = drift(ts)
        out.append(row)
    return sorted(out, key=lambda r: (r["size_b"] or 0, r["quant"] or "", r["ctx"] or 0, r["ballast_gb"] or 0,
                                      r["condition"]))


def _lt(v, lim):
    return None if v is None else v < lim


def _gt(v, lim):
    return None if v is None else v > lim


def drift(ts: list[dict]) -> dict:
    """Late vs early runs for one config: catches thermal throttling and cache effects within a config."""
    ts = sorted(ts, key=lambda t: (t["trial_idx"] or 0, t["id"]))
    if len(ts) < 6:
        return {}
    h = len(ts) // 3
    out = {}
    for key in ("ttft_ms", "gen_tps"):
        early = st.median([t[key] for t in ts[:h] if t[key] is not None] or [0])
        late = st.median([t[key] for t in ts[-h:] if t[key] is not None] or [0])
        out[key] = (late / early - 1) * 100 if early else None
    return out


# ------------------------------------------------------------------ experiment-specific views
def e0_table(db: DB) -> list[dict]:
    rows = db.query("SELECT model, size_b, quant, n_prompt, n_gen, avg_ts, stddev_ts FROM llama_bench ORDER BY size_b, quant, n_gen, n_prompt")
    by: dict[str, dict] = {}
    for r in rows:
        d = by.setdefault(r["model"], {"model": r["model"], "size_b": r["size_b"], "quant": r["quant"]})
        key = f"tg{r['n_gen']}" if r["n_gen"] else f"pp{r['n_prompt']}"
        d[key] = r["avg_ts"]
        d[key + "_sd"] = r["stddev_ts"]
    for d in by.values():
        # implied cold TTFT at 4k from raw prefill speed: a floor the server path cannot beat
        if d.get("pp4096"):
            d["implied_ttft_4k_ms"] = 4000 / d["pp4096"] * 1000
    return list(by.values())


def e1b_view(db: DB, scope="auto") -> list[dict]:
    rows = config_table(db, "E1b", scope)
    by: dict[str, dict] = {}
    for r in rows:
        kind = "warm" if r["condition"].endswith("warm") else "cold"
        d = by.setdefault(r["model"], {"model": r["model"]})
        d[kind] = r["ttft"]
        d[kind + "_prompt_n"] = None
    for t in trials(db, "E1b", scope):
        kind = "warm" if t["condition"].endswith("warm") else "cold"
        by[t["model"]].setdefault(kind + "_new_tokens", []).append(t["prompt_n"])
    out = []
    for d in by.values():
        for k in ("cold", "warm"):
            nt = d.pop(k + "_new_tokens", [])
            d[k + "_prompt_n"] = st.median(nt) if nt else None
        if d.get("cold", {}).get("median") and d.get("warm", {}).get("median"):
            d["speedup"] = d["cold"]["median"] / d["warm"]["median"]
        out.append(d)
    return out


def e2_view(db: DB, scope="auto") -> list[dict]:
    rows = config_table(db, "E2", scope)
    errors = [t for t in trials(db, "E2", scope, ok_only=False) if t["error"]]
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["model"]].append(r)
    out = []
    for model, rs in by.items():
        rs.sort(key=lambda r: r["ballast_gb"])
        base = next((r for r in rs if r["ballast_gb"] == 0), rs[0])
        b_tps, b_ttft = base["gen_tps"].get("median"), base["ttft"].get("median")
        knee = None
        for r in rs:
            tps = r["gen_tps"].get("median")
            r["tps_penalty_x"] = b_tps / tps if b_tps and tps else None
            r["ttft_penalty_x"] = (r["ttft"].get("median") / b_ttft) if b_ttft and r["ttft"].get("median") else None
            if knee is None and r["tps_penalty_x"] and r["tps_penalty_x"] > 1.2:
                knee = r["ballast_gb"]
        failed = sorted({t["ballast_gb"] for t in errors if t["model"] == model})
        out.append({"model": model, "levels": rs, "knee_gb": knee, "failed_at_gb": failed})
    return out


def e3_view(db: DB, scope="auto") -> list[dict]:
    rows = config_table(db, "E3", scope)
    base = {(r["task"], r["ballast_gb"]): r for r in rows if not r["draft"]}
    out = []
    for r in rows:
        b = base.get((r["task"], r["ballast_gb"]))
        # the label in the condition carries the draft length: "draft=0.5B-Q8_0/n4 summarise ballast0"
        label = r["condition"].split()[0].removeprefix("draft=")
        d = {"draft": label if r["draft"] else "none", "task": r["task"], "ballast_gb": r["ballast_gb"],
             "gen_tps": r["gen_tps"].get("median"), "e2e_tps": r["e2e_tps"].get("median"),
             "accept": r.get("accept"), "sys_used_frac": (r["sys_used_mb"].get("median") or 0) / ram_mb(),
             "mem_mb": r["mem_mb"].get("median"), "n": r["n"]}
        if b and r["draft"]:
            bt, be = b["gen_tps"].get("median"), b["e2e_tps"].get("median")
            d["speedup"] = d["gen_tps"] / bt if bt and d["gen_tps"] else None
            d["e2e_speedup"] = d["e2e_tps"] / be if be and d["e2e_tps"] else None
        out.append(d)
    return sorted(out, key=lambda d: (d["ballast_gb"], d["task"], d["draft"]))


def e5_view(db: DB, scope="auto") -> dict:
    ts = trials(db, "E5", scope)
    if not ts:
        return {}
    t0 = ts[0]["t_start"]
    series = [{"min": (t["t_start"] - t0) / 60, "gen_tps": t["gen_tps"], "ttft_ms": t["ttft_ms"],
               "thermal": t["thermal"], "gpu_w": t["gpu_w"]} for t in ts]
    first = [s["gen_tps"] for s in series if s["min"] < 1 and s["gen_tps"]]
    last = [s["gen_tps"] for s in series if s["min"] > series[-1]["min"] - 1 and s["gen_tps"]]
    out = {"series": series, "n": len(series), "minutes": series[-1]["min"]}
    if first and last:
        out["first_min_tps"], out["last_min_tps"] = st.median(first), st.median(last)
        out["sustained_drop_pct"] = (1 - out["last_min_tps"] / out["first_min_tps"]) * 100
    return out


# ------------------------------------------------------------------ E4 frames
def e4_view(db: DB, scope="auto") -> dict:
    sids = session_ids(db, "E4", scope)
    if not sids:
        return {"conditions": [], "decision": decide(None)}
    conds: dict[str, dict] = {}
    for sid in sids:
        phases = db.query("SELECT * FROM phases WHERE session_id=? ORDER BY t0_ms", (sid,))
        frames = db.query("SELECT t_ms, dur_ms, kind FROM frames WHERE session_id=? ORDER BY t_ms", (sid,))
        raf = [(f["t_ms"], f["dur_ms"]) for f in frames if f["kind"] == "raf"]
        loaf = [(f["t_ms"], f["dur_ms"]) for f in frames if f["kind"] == "loaf"]
        # frame budget per page load, from the no-model idle baseline
        budgets = {}
        for p in phases:
            if p["condition"].startswith("no-model"):
                vals = _in(raf, p["t0_ms"], p["t1_ms"])
                if vals:
                    budgets[p["condition"].split()[-1]] = st.median(vals)
        for p in phases:
            c = conds.setdefault(p["condition"], {"condition": p["condition"], "phases": defaultdict(list),
                                                  "loaf": defaultdict(list), "dur_s": defaultdict(float)})
            c["phases"][p["phase"]] += _in(raf, p["t0_ms"], p["t1_ms"])
            c["loaf"][p["phase"]] += _in(loaf, p["t0_ms"], p["t1_ms"])
            c["dur_s"][p["phase"]] += (p["t1_ms"] - p["t0_ms"]) / 1000
            load = "heavy" if "heavy" in p["condition"] else "light"
            c["budget_ms"] = budgets.get(load) or c.get("budget_ms")
    # what each condition costs the model: the other half of the Stage 2 trade-off
    cost = {}
    for t in trials(db, "E4", scope):
        cost.setdefault(t["condition"], []).append(t)
    out = []
    for c in conds.values():
        budget = c.get("budget_ms") or (1000 / 120)
        ts = cost.get(c["condition"], [])
        row = {"condition": c["condition"], "budget_ms": budget, "phases": {},
               "ttft": summarize([t["ttft_ms"] for t in ts]), "gen_tps": summarize([t["gen_tps"] for t in ts]),
               "prompt_tps": summarize([t["prompt_tps"] for t in ts])}
        for ph, vals in c["phases"].items():
            row["phases"][ph] = frame_stats(vals, budget, c["loaf"][ph], c["dur_s"][ph])
        out.append(row)
    order = ["no-model light", "no-model heavy"] + [c[0] for c in config.E4_CONDITIONS]
    out.sort(key=lambda r: order.index(r["condition"]) if r["condition"] in order else 99)
    primary = next((r for r in out if r["condition"] == config.E4_PRIMARY), None)
    return {"conditions": out, "decision": decide(primary)}


def _in(series, t0, t1) -> list[float]:
    return [d for t, d in series if t0 <= t <= t1]


def frame_stats(intervals: list[float], budget: float, loaf: list[float] | None = None, dur_s: float = 0) -> dict:
    if not intervals:
        return {"n": 0}
    dropped = [d for d in intervals if d > config.DROP_FACTOR * budget]
    # frames lost: an interval of k budgets means k-1 frames were never shown
    lost = sum(max(0, round(d / budget) - 1) for d in dropped)
    return {"n": len(intervals), "p50": pct(intervals, .5), "p95": pct(intervals, .95), "p99": pct(intervals, .99),
            "max": max(intervals), "dropped_pct": len(dropped) / len(intervals) * 100,
            "lost_frames_pct": lost / (len(intervals) + lost) * 100,
            "fps": len(intervals) / dur_s if dur_s else None,
            "loaf_n": len(loaf or []), "loaf_per_s": (len(loaf or []) / dur_s) if dur_s else None,
            "loaf_max_ms": max(loaf) if loaf else None}


def decide(primary: dict | None) -> dict:
    """Stage 2 decision, fixed before E4 runs. Reads the primary condition only."""
    if not primary:
        return {"verdict": "pending", "why": "E4 has not run for the primary condition yet"}
    ph = primary["phases"]
    idle = ph.get("idle", {}).get("dropped_pct")
    inf = {k: ph[k] for k in ("prefill", "decode") if ph.get(k, {}).get("n")}
    if idle is None or not inf:
        return {"verdict": "pending", "why": "missing idle or inference phases"}
    worst_k = max(inf, key=lambda k: inf[k]["dropped_pct"])
    worst = inf[worst_k]
    budget = primary["budget_ms"]
    facts = {"idle_dropped_pct": idle, "worst_phase": worst_k, "worst_dropped_pct": worst["dropped_pct"],
             "worst_p95_ms": worst["p95"], "budget_ms": budget}
    if idle > config.RULE_IDLE_MAX_PCT:
        return {"verdict": "inconclusive", **facts,
                "why": f"idle already drops {idle:.1f}% of frames (> {config.RULE_IDLE_MAX_PCT}%); the baseline is too noisy"}
    if worst["dropped_pct"] > config.RULE_DROPPED_PCT or worst["p95"] > config.DROP_FACTOR * budget:
        return {"verdict": "scheduler", **facts,
                "why": (f"{worst_k} drops {worst['dropped_pct']:.1f}% of frames (idle {idle:.1f}%), "
                        f"p95 {worst['p95']:.1f} ms vs {budget:.1f} ms budget")}
    return {"verdict": "gate", **facts,
            "why": (f"inference stays smooth: worst phase {worst_k} drops {worst['dropped_pct']:.1f}% "
                    f"(idle {idle:.1f}%), p95 {worst['p95']:.1f} ms vs {budget:.1f} ms budget")}


def frame_series(db: DB, condition: str, scope="auto", max_points: int = 3000) -> dict:
    """One condition's frames over time, with phase bands, for the dashboard timeline."""
    sids = session_ids(db, "E4", scope)
    for sid in reversed(sids):
        ph = db.query("SELECT phase, t0_ms, t1_ms FROM phases WHERE session_id=? AND condition=? ORDER BY t0_ms", (sid, condition))
        if not ph:
            continue
        t0, t1 = ph[0]["t0_ms"], ph[-1]["t1_ms"]
        fr = db.query("SELECT t_ms, dur_ms FROM frames WHERE session_id=? AND kind='raf' AND t_ms BETWEEN ? AND ? ORDER BY t_ms",
                      (sid, t0, t1))
        step = max(1, len(fr) // max_points)
        # keep every dropped frame; thin only the ordinary ones
        pts = [(f["t_ms"] - t0, f["dur_ms"]) for i, f in enumerate(fr) if i % step == 0 or f["dur_ms"] > 12]
        return {"phases": [{"phase": p["phase"], "t0": p["t0_ms"] - t0, "t1": p["t1_ms"] - t0} for p in ph],
                "frames": pts}
    return {"phases": [], "frames": []}


# ------------------------------------------------------------------ cross-session
def records(db: DB) -> dict:
    ok = db.query("SELECT * FROM trials WHERE warmup=0 AND error IS NULL AND gen_tps IS NOT NULL")
    if not ok:
        return {}
    best_tps = max(ok, key=lambda t: t["gen_tps"])
    ttft_ok = [t for t in ok if t["ttft_ms"] and t["cache"] == "cold" and (t["ctx_tokens"] or 0) >= 3900]
    best_ttft = min(ttft_ok, key=lambda t: t["ttft_ms"]) if ttft_ok else None
    worst = max(ok, key=lambda t: t["ttft_ms"] or 0)
    allt = db.query("SELECT COUNT(*) n, SUM(error IS NOT NULL) e FROM trials WHERE warmup=0")[0]
    hours = db.query("SELECT SUM(COALESCE(ended_at, started_at) - started_at)/3600.0 h FROM sessions")[0]["h"]
    return {"fastest_decode": _brief(best_tps), "fastest_cold_ttft_4k": _brief(best_ttft) if best_ttft else None,
            "slowest_ttft": _brief(worst), "trials": allt["n"], "errors": allt["e"] or 0,
            "sessions": db.query("SELECT COUNT(*) n FROM sessions")[0]["n"], "hours": hours or 0,
            "tokens_generated": sum(t["gen_n"] or 0 for t in ok),
            "tokens_prefilled": sum(t["prompt_n"] or 0 for t in ok)}


def _brief(t: dict) -> dict:
    return {k: t.get(k) for k in ("id", "experiment", "condition", "ttft_ms", "gen_tps", "session_id")}


def session_compare(db: DB, exp: str = "E1") -> list[dict]:
    """Median per condition per session: shows whether reruns agree."""
    rows = db.query("""SELECT session_id, condition, ttft_ms, gen_tps FROM trials
                       WHERE experiment=? AND warmup=0 AND error IS NULL""", (exp,))
    g: dict[tuple, list] = defaultdict(list)
    for r in rows:
        g[(r["condition"], r["session_id"])].append(r)
    out = []
    for (cond, sid), ts in sorted(g.items()):
        out.append({"condition": cond, "session_id": sid, "n": len(ts),
                    "ttft_median": st.median([t["ttft_ms"] for t in ts if t["ttft_ms"]] or [0]),
                    "gen_tps_median": st.median([t["gen_tps"] for t in ts if t["gen_tps"]] or [0])})
    return out
