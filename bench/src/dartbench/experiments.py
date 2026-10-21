"""E0-E6. Every experiment resumes (skips trials already stored), isolates failures per trial, and
cleans up servers, ballast and the browser on any exit."""
from __future__ import annotations

import json
import subprocess
import time
import traceback
from dataclasses import dataclass, field

from . import config, prompts, sysinfo
from .ballast import Ballast
from .browser import Browser
from .db import DB
from .energy import PowerSampler
from .frames import FrameCollector
from .sampler import MemSampler, downsample
from .server import LlamaServer, model_file_mb

M = config.MODELS


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class Runner:
    db: DB
    quick: bool = False
    energy: bool = False
    label: str = ""
    power: PowerSampler | None = None
    stats: dict = field(default_factory=lambda: {"trials": 0, "errors": 0, "skipped": []})

    def runs(self, n: int) -> int:
        return min(n, 2) if self.quick else n

    def models(self, keys: list[str]) -> list[config.Model]:
        out = []
        for k in keys:
            if M[k].available:
                out.append(M[k])
            else:
                self.stats["skipped"].append(f"{k} (file missing)")
                log(f"skip {k}: {M[k].path} not found")
        return out

    def session(self, exp: str, params: dict) -> int:
        env = sysinfo.environment()
        env["energy"] = bool(self.power and self.power.enabled)
        return self.db.start_session(exp, self.label or ("quick" if self.quick else "full"), env,
                                     {**params, "quick": self.quick})

    def remaining(self, exp: str, cond: str, n: int) -> int:
        return max(0, n - self.db.completed_runs(exp, cond))

    # ------------------------------------------------------------ one trial
    def trial(self, sid: int, srv: LlamaServer, exp: str, cond: str, prompt: str, n_tokens: int, *,
              n_predict: int, idx: int, warmup: bool = False, ignore_eos: bool = True,
              cache_prompt: bool = False, task: str = "summarise", ballast: Ballast | None = None,
              draft: config.Model | None = None, deadline_s: float | None = None,
              on_first=None, extra: dict | None = None, pace: tuple[int, float] | None = None) -> dict:
        row = {"session_id": sid, "experiment": exp, "condition": cond, "model": srv.model.key,
               "size_b": srv.model.size_b, "quant": srv.model.quant, "draft_model": draft.key if draft else None,
               "ctx_tokens": n_tokens, "task": task, "ballast_gb": ballast.gb if ballast else 0,
               "ngl": srv.ngl, "ubatch": srv.ubatch, "cache": "warm" if cache_prompt else "cold",
               "trial_idx": idx, "warmup": int(warmup), "load_s": srv.load_s,
               "model_mb": model_file_mb(srv.model) + (model_file_mb(draft) if draft else 0), **(extra or {})}
        swap0, vm0 = sysinfo.swap_used_mb(), sysinfo.vm_counters()
        sampler = MemSampler(srv.pid)
        try:
            with sampler:
                c = srv.complete(prompt, n_predict=n_predict, ignore_eos=ignore_eos, cache_prompt=cache_prompt,
                                 seed=42 + idx, on_first=on_first, deadline_s=deadline_s, pace=pace)
            tm = c.timings
            row.update({
                "t_start": c.t_send, "t_first": c.t_first, "t_end": c.t_end, "ttft_ms": c.ttft_ms,
                "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"),
                "prompt_tps": tm.get("prompt_per_second"), "gen_n": tm.get("predicted_n"),
                "gen_ms": tm.get("predicted_ms"), "gen_tps": tm.get("predicted_per_second"),
                "draft_n": tm.get("draft_n"), "draft_accepted": tm.get("draft_n_accepted"),
                "text_head": c.text[:300], "stop_reason": c.stop_reason,
            })
            if self.power and self.power.enabled and c.t_first:
                pre, dec = self.power.window(c.t_send, c.t_first), self.power.window(c.t_first, c.t_end)
                row.update({"prefill_j": pre.get("j"), "decode_j": dec.get("j"),
                            "cpu_w": dec.get("cpu_w"), "gpu_w": dec.get("gpu_w"),
                            "thermal": dec.get("thermal") or self.power.thermal_now()})
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:500]
            row["t_end"] = time.time()
            self.stats["errors"] += 1
            log(f"  ! {cond} #{idx}: {row['error']}")
        vm1 = sysinfo.vm_counters()
        row.update(sampler.summary())
        row.update({"swap_start_mb": swap0, "swap_end_mb": sysinfo.swap_used_mb(),
                    "pageouts": vm1["pageouts"] - vm0["pageouts"], "swapouts": vm1["swapouts"] - vm0["swapouts"],
                    "pageins": vm1["pageins"] - vm0["pageins"],
                    "ballast_rss_mb": ballast.rss_mb() if ballast else None})
        if not row.get("thermal"):
            row["thermal"] = sysinfo.thermal_note()
        tid = self.db.add_trial(row)
        if not warmup:
            self.db.add_mem_samples(tid, downsample(sampler.samples))
            self.stats["trials"] += 1
        row["id"] = tid
        if not row.get("error") and not warmup:
            log(f"  {cond} #{idx}: ttft {row['ttft_ms']:.0f} ms, {row['gen_tps'] or 0:.1f} tok/s, "
                f"peak {row.get('peak_footprint_mb') or row.get('peak_rss_mb') or 0:.0f} MB")
        return row

    def repeat(self, sid, srv, exp, cond, prompt, n_tokens, n, *, warmup=True, stop_if=None, **kw) -> list[dict]:
        need = self.remaining(exp, cond, n)
        if need == 0:
            log(f"  {cond}: already complete")
            return []
        done = n - need
        if warmup:
            self.trial(sid, srv, exp, cond, prompt, n_tokens, idx=-1, warmup=True, **kw)
        rows = []
        for i in range(done, n):
            r = self.trial(sid, srv, exp, cond, prompt, n_tokens, idx=i, **kw)
            rows.append(r)
            if stop_if and stop_if(r):
                log(f"  {cond}: stopping early ({stop_if.__doc__ or 'condition met'})")
                break
            time.sleep(0.5 if config.FAKE else 2)
        return rows


# ================================================================ E0: llama-bench reference
def e0(r: Runner) -> None:
    models = r.models(config.E0_MODELS)
    todo = [m for m in models if not r.db.query("SELECT 1 FROM llama_bench WHERE model=? LIMIT 1", (m.key,))]
    if not todo:
        log("E0 already complete")
        return
    sid = r.session("E0", {"models": [m.key for m in todo], "p": "512,2048,4096", "n": 128})
    status = "done"
    try:
        for m in todo:
            log(f"E0 llama-bench {m.key}")
            if config.FAKE:
                from .fake_server import rates
                pp, tg = rates(m.key, 99)
                data = [{"n_prompt": p, "n_gen": 0, "avg_ts": pp * (1 - p / 20000), "stddev_ts": pp * .01} for p in (512, 2048, 4096)]
                data.append({"n_prompt": 0, "n_gen": 128, "avg_ts": tg, "stddev_ts": tg * .01})
            else:
                reps = "2" if r.quick else "3"
                out = subprocess.run([config.LLAMA_BENCH, "-m", str(m.path), "-ngl", "99", "-fa", "auto",
                                      "-p", "512,2048,4096", "-n", "128", "-r", reps, "-o", "json"],
                                     capture_output=True, text=True, timeout=3600)
                try:
                    data = json.loads(out.stdout)
                except json.JSONDecodeError:
                    log(f"  ! llama-bench output unreadable for {m.key}: {out.stderr[-300:]}")
                    r.stats["errors"] += 1
                    continue
            for d in data:
                r.db.add_llama_bench(sid, {"model": m.key, "size_b": m.size_b, "quant": m.quant,
                                           "n_prompt": d.get("n_prompt"), "n_gen": d.get("n_gen"),
                                           "avg_ts": d.get("avg_ts"), "stddev_ts": d.get("stddev_ts"), "raw": d})
                log(f"  pp{d.get('n_prompt')} tg{d.get('n_gen')}: {d.get('avg_ts', 0):.1f} t/s")
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E1: limits matrix
def e1(r: Runner) -> None:
    ctx_runs = {4000: 3, 2000: 2} if r.quick else config.E1_CTX_RUNS
    models = r.models(config.E1_MODELS if not r.quick else ["3B-Q4_K_M", "7B-Q4_K_M"])
    sid = r.session("E1", {"models": [m.key for m in models], "ctx_runs": ctx_runs, "gen": config.E1_GEN_TOKENS,
                           "browser_tabs": len(config.TABS)})
    status = "done"
    try:
        with Browser():  # the papers' "browser open with five tabs" condition
            for m in models:
                conds = {ctx: f"{m.key} ctx{ctx}" for ctx in ctx_runs}
                if all(r.remaining("E1", c, ctx_runs[ctx]) == 0 for ctx, c in conds.items()):
                    log(f"E1 {m.key}: already complete")
                    continue
                log(f"E1 {m.key}")
                with LlamaServer(m) as srv:
                    for ctx, n in ctx_runs.items():
                        prompt, nt = prompts.build(srv, ctx)
                        r.repeat(sid, srv, "E1", conds[ctx], prompt, nt, n, n_predict=config.E1_GEN_TOKENS)
                time.sleep(3)
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E1b: warm prefix cache
def e1b(r: Runner) -> None:
    n = r.runs(config.E1B_RUNS)
    models = r.models(config.E1B_MODELS if not r.quick else ["7B-Q4_K_M"])
    sid = r.session("E1b", {"models": [m.key for m in models], "ctx": config.E1B_CTX, "runs": n})
    status = "done"
    try:
        for m in models:
            cold_c, warm_c = f"{m.key} ctx{config.E1B_CTX} cold", f"{m.key} ctx{config.E1B_CTX} warm"
            if r.remaining("E1b", cold_c, n) == 0 and r.remaining("E1b", warm_c, n) == 0:
                continue
            log(f"E1b {m.key}")
            with LlamaServer(m) as srv:
                prime, qs, nt = prompts.build_warm(srv, config.E1B_CTX)
                # cold: each distinct question with the cache off
                for i in range(n - r.remaining("E1b", cold_c, n), n):
                    r.trial(sid, srv, "E1b", cold_c, qs[i % len(qs)], nt, n_predict=config.E1B_GEN_TOKENS, idx=i)
                # warm: prime the shared page once, then ask distinct questions about it
                r.trial(sid, srv, "E1b", warm_c, prime, nt, n_predict=8, idx=-1, warmup=True, cache_prompt=True)
                for i in range(n - r.remaining("E1b", warm_c, n), n):
                    r.trial(sid, srv, "E1b", warm_c, qs[i % len(qs)], nt, n_predict=config.E1B_GEN_TOKENS,
                            idx=i, cache_prompt=True)
                    # re-prime so every warm trial starts from the same cached prefix, not the previous answer
                    r.trial(sid, srv, "E1b", warm_c, prime, nt, n_predict=1, idx=-1, warmup=True, cache_prompt=True)
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E2: paging under memory pressure
def e2(r: Runner) -> None:
    n = r.runs(config.E2_RUNS)
    ballasts = [0, 8] if r.quick else config.E2_BALLAST_GB
    models = r.models(config.E2_MODELS if not r.quick else ["7B-Q4_K_M"])
    sid = r.session("E2", {"models": [m.key for m in models], "ballast_gb": ballasts, "runs": n,
                           "ctx": config.E2_CTX, "gen": config.E2_GEN_TOKENS})
    status = "done"

    def collapsed(row):
        """throughput collapsed below 1 tok/s or the trial timed out"""
        return bool(row.get("error")) or (row.get("gen_tps") or 0) < 1.0

    try:
        for m in models:
            model_gb = model_file_mb(m) / 1024 if not config.FAKE else m.size_b * 0.6
            for gb in ballasts:
                cond = f"{m.key} ballast{gb}"
                if gb + model_gb > config.E2_MAX_TOTAL_GB:
                    log(f"E2 {cond}: skipped, {gb + model_gb:.1f} GB exceeds the safety cap")
                    r.stats["skipped"].append(f"{cond} (safety cap)")
                    continue
                if r.remaining("E2", cond, n) == 0:
                    continue
                log(f"E2 {cond}")
                try:
                    with Ballast(gb, fake=config.FAKE) as b:
                        with LlamaServer(m, tag=f"b{gb}") as srv:
                            prompt, nt = prompts.build(srv, config.E2_CTX)
                            rows = r.repeat(sid, srv, "E2", cond, prompt, nt, n, n_predict=config.E2_GEN_TOKENS,
                                            ballast=b, deadline_s=config.E2_TRIAL_DEADLINE_S, stop_if=collapsed)
                except Exception as e:
                    log(f"  ! {cond} failed to start: {e}")
                    r.db.add_trial({"session_id": sid, "experiment": "E2", "condition": cond, "model": m.key,
                                    "size_b": m.size_b, "quant": m.quant, "ballast_gb": gb, "trial_idx": 0,
                                    "warmup": 0, "error": f"setup: {e}"[:500]})
                    r.stats["errors"] += 1
                    break
                if rows and collapsed(rows[-1]):
                    log(f"  {m.key}: collapse at {gb} GB ballast; larger ballasts skipped")
                    break
                time.sleep(5)
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E3: speculative decoding
def e3(r: Runner) -> None:
    n = r.runs(config.E3_RUNS)
    ballasts = [0] if r.quick else config.E3_BALLAST_GB
    target = M[config.E3_TARGET]
    nmaxes = config.E3_DRAFT_MAX[:1] if r.quick else config.E3_DRAFT_MAX
    drafts = [(None, 0)] + [(d, k) for d in r.models([d for d in config.E3_DRAFTS if d]) for k in nmaxes]
    if not target.available:
        log("E3 skipped: target model missing")
        return
    sid = r.session("E3", {"target": target.key, "drafts": [d.key if d else None for d, _ in drafts], "draft_max": nmaxes,
                           "tasks": config.E3_TASKS, "ballast_gb": ballasts, "runs": n, "ctx": config.E3_CTX})
    status = "done"
    try:
        for gb in ballasts:
            log(f"E3 ballast {gb} GB")
            with Ballast(gb, fake=config.FAKE) as b:
                for d, k in drafts:
                    label = f"{d.key}/n{k}" if d else "none"
                    conds = {t: f"draft={label} {t} ballast{gb}" for t in config.E3_TASKS}
                    if all(r.remaining("E3", c, n) == 0 for c in conds.values()):
                        continue
                    with LlamaServer(target, draft=d, draft_max=k or 16, tag=f"b{gb}") as srv:
                        for task, cond in conds.items():
                            prompt, nt = prompts.build(srv, config.E3_CTX, task)
                            r.repeat(sid, srv, "E3", cond, prompt, nt, n, n_predict=256, ignore_eos=False,
                                     task=task, ballast=b, draft=d, deadline_s=600)
                    time.sleep(3)
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E4: frame time while inference runs
def e4(r: Runner) -> None:
    n = r.runs(config.E4_RUNS)
    idle_s = 6 if r.quick else config.E4_IDLE_S
    conds = [c for c in config.E4_CONDITIONS if not r.quick or c[0] == config.E4_PRIMARY]
    conds = [c for c in conds if M[c[1]].available or r.stats["skipped"].append(f"E4 {c[0]} (model missing)")]
    if not conds:
        log("E4 skipped: no models")
        return
    if not config.FAKE and not Browser.available():
        log("E4 skipped: Brave not found")
        return
    sid = r.session("E4", {"conditions": conds, "runs": n, "idle_s": idle_s, "ctx": config.E4_CTX,
                           "gen": config.E4_GEN_TOKENS, "drop_factor": config.DROP_FACTOR})
    status = "done"
    t_ms = lambda: time.time() * 1000

    try:
        with FrameCollector() as fc:
            for load in ("light", "heavy"):
                group = [c for c in conds if c[4] == load]
                if not group:
                    continue
                with Browser(extra_urls=[fc.url(load)]):
                    _activate_browser()
                    if not fc.wait_for_page():
                        raise RuntimeError("frame page never reported; is Brave showing it in front?")
                    time.sleep(3)
                    fc.drain()
                    # baseline with no model loaded at all
                    t0 = t_ms(); _phase_sleep(fc, idle_s); t1 = t_ms()
                    r.db.add_phase(sid, None, f"no-model {load}", "idle", t0, t1)
                    r.db.add_frames(sid, fc.drain())
                    for label, mkey, ngl, ub, _, *rest in group:
                        pace = rest[0] if rest else None
                        log(f"E4 {label}")
                        with LlamaServer(M[mkey], ngl=ngl, ubatch=ub, tag="e4") as srv:
                            prompt, nt = prompts.build(srv, config.E4_CTX)
                            r.trial(sid, srv, "E4", label, prompt, nt, n_predict=16, idx=-1, warmup=True)
                            time.sleep(2)
                            fc.drain()
                            t0 = t_ms(); _phase_sleep(fc, idle_s); t1 = t_ms()
                            r.db.add_phase(sid, None, label, "idle", t0, t1)
                            for i in range(n):
                                ok, why = fc.healthy()
                                if not ok:
                                    log(f"  ! frame page unhealthy ({why}); bringing Brave forward")
                                    _activate_browser(); time.sleep(2)
                                fc.set_fake_state("prefill")
                                row = r.trial(sid, srv, "E4", label, prompt, nt, idx=i,
                                              n_predict=config.E4_GEN_TOKENS,
                                              on_first=lambda t: fc.set_fake_state("decode"),
                                              extra={"task": f"frames-{load}"}, pace=pace)
                                if not row.get("error") and row.get("t_first"):
                                    r.db.add_phase(sid, row["id"], label, "prefill", row["t_start"] * 1000, row["t_first"] * 1000)
                                    r.db.add_phase(sid, row["id"], label, "decode", row["t_first"] * 1000, row["t_end"] * 1000)
                                fc.set_fake_state("idle")
                                g0 = t_ms(); _phase_sleep(fc, config.E4_GAP_S); g1 = t_ms()
                                r.db.add_phase(sid, None, label, "gap", g0, g1)
                            r.db.add_frames(sid, fc.drain())
                        time.sleep(3)
                        fc.drain()
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


def _phase_sleep(fc: FrameCollector, s: float) -> None:
    fc.set_fake_state("idle")
    time.sleep(s)


def _activate_browser() -> None:
    if config.FAKE:
        return
    subprocess.run(["osascript", "-e", 'tell application "Brave Browser" to activate'], capture_output=True)


# ================================================================ E5: thermal soak
def e5(r: Runner) -> None:
    m = M[config.E5_MODEL]
    if not m.available:
        log("E5 skipped: model missing")
        return
    minutes = 1 if r.quick else config.E5_MINUTES
    if config.FAKE:
        minutes = 0.1
    cond = f"{m.key} soak{config.E5_CTX}"
    if r.db.completed_runs("E5", cond) and not r.quick:
        log("E5 already complete")
        return
    sid = r.session("E5", {"model": m.key, "minutes": minutes, "ctx": config.E5_CTX})
    status = "done"
    try:
        log(f"E5 soak {m.key} for {minutes} min (back-to-back requests, no gaps)")
        with LlamaServer(m, tag="soak") as srv:
            prompt, nt = prompts.build(srv, config.E5_CTX)
            end = time.time() + minutes * 60
            i = 0
            while time.time() < end:
                r.trial(sid, srv, "E5", cond, prompt, nt, n_predict=256, idx=i, extra={"task": "soak"})
                i += 1
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


# ================================================================ E6: energy per token
def e6(r: Runner) -> None:
    if not (r.power and r.power.enabled):
        log("E6 skipped: run with --energy after `sudo -v` so powermetrics can sample")
        r.stats["skipped"].append("E6 (no powermetrics)")
        return
    n = r.runs(config.E6_RUNS)
    models = r.models(config.E6_MODELS if not r.quick else ["7B-Q4_K_M"])
    sid = r.session("E6", {"models": [m.key for m in models], "runs": n, "ctx": config.E6_CTX})
    status = "done"
    try:
        # idle power with nothing loaded, so per-token energy can be reported net of the baseline
        t0 = time.time(); time.sleep(10); t1 = time.time()
        idle = r.power.window(t0, t1)
        r.db.add_trial({"session_id": sid, "experiment": "E6", "condition": "idle baseline", "trial_idx": 0,
                        "warmup": 0, "t_start": t0, "t_end": t1, "cpu_w": idle.get("cpu_w"),
                        "gpu_w": idle.get("gpu_w"), "decode_j": idle.get("j")})
        for m in models:
            cond = f"{m.key} ctx{config.E6_CTX}"
            if r.remaining("E6", cond, n) == 0:
                continue
            log(f"E6 {m.key}")
            with LlamaServer(m, tag="energy") as srv:
                prompt, nt = prompts.build(srv, config.E6_CTX)
                r.repeat(sid, srv, "E6", cond, prompt, nt, n, n_predict=256)
            time.sleep(5)
    except BaseException:
        status = "aborted"
        raise
    finally:
        r.db.end_session(sid, status)


EXPERIMENTS = {"e0": e0, "e1": e1, "e1b": e1b, "e2": e2, "e3": e3, "e4": e4, "e5": e5, "e6": e6}
# E4 first: it decides Stage 2 and needs a fresh, cool machine. E5 last-but-one: it heats the machine.
ORDER = ["e4", "e0", "e1", "e1b", "e3", "e2", "e6", "e5"]


def run(names: list[str], *, quick: bool, energy: bool, label: str) -> dict:
    db = DB()
    power = PowerSampler(enabled=energy).start() if energy else None
    if energy and not (power and power.enabled):
        log("energy requested but `sudo -n powermetrics` is unavailable; run `sudo -v` first. Continuing without.")
    r = Runner(db, quick=quick, energy=energy, label=label, power=power)
    t0 = time.time()
    try:
        for name in names:
            log(f"==== {name.upper()} ====")
            try:
                EXPERIMENTS[name](r)
            except KeyboardInterrupt:
                raise
            except Exception:
                log(f"!! {name} crashed:\n{traceback.format_exc()}")
                r.stats["errors"] += 1
    finally:
        if power:
            power.stop()
    r.stats["minutes"] = round((time.time() - t0) / 60, 1)
    return r.stats
