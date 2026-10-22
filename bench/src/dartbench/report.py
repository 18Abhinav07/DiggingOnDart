"""reports/report.md (findings vs Dart's published figures) and CSV exports."""
from __future__ import annotations

import csv
import json
import time

from . import analysis as A
from . import config
from .db import DB, TRIAL_COLS

C = config.DART_CLAIMS


def f(v, fmt="{:.0f}", dash="–"):
    return dash if v is None else fmt.format(v)


def yn(v):
    return "–" if v is None else ("pass" if v else "**fail**")


def med(s, fmt="{:.0f}"):
    if not s or not s.get("n"):
        return "–"
    if s["n"] >= 3:
        return f"{fmt.format(s['median'])} ({fmt.format(s['p25'])}–{fmt.format(s['p75'])})"
    return fmt.format(s["median"])


def latest_env(db: DB) -> dict:
    r = db.query("SELECT env_json FROM sessions ORDER BY id DESC LIMIT 1")
    return json.loads(r[0]["env_json"]) if r else {}


def interp_9b(rows: list[dict], ctx: int = 4000) -> float | None:
    """Linear interpolation of Q4_K_M cold TTFT between 7B and 14B at 9B. Prefill cost scales close to
    linearly with parameter count, so this is a fair estimate, but only an estimate."""
    pick = {r["size_b"]: r["ttft"].get("median") for r in rows
            if r["quant"] == "Q4_K_M" and r["ctx"] == ctx and r["ttft"].get("n")}
    if 7.0 in pick and 14.0 in pick:
        return pick[7.0] + (pick[14.0] - pick[7.0]) * (9 - 7) / (14 - 7)
    return None


def build(db: DB | None = None, scope: str = "auto") -> str:
    db = db or DB()
    env = latest_env(db)
    L = []
    w = L.append
    w("# Stage 1 results: local inference on an M4 Pro, against Dart's published limits\n")
    w(f"Generated {time.strftime('%Y-%m-%d %H:%M')}. Data: `{config.DB_PATH.name}`"
      + (" (**FAKE DRY RUN: numbers are synthetic**)" if config.FAKE else "") + ".\n")
    if env:
        w(f"Machine: {env.get('chip')}, {env.get('ram_gb')} GB, {env.get('perf_cores')}P+{env.get('eff_cores')}E CPU, "
          f"{env.get('gpu_cores')}-core GPU, macOS {env.get('macos')} ({env.get('build')}). "
          f"llama.cpp {env.get('llama_cpp')}. Brave {env.get('brave')}. Power: {env.get('power')}"
          f"{', low power mode ON' if env.get('low_power_mode') else ''}.\n")

    # ---------------------------------------------------------------- decision
    e4 = A.e4_view(db, scope)
    d = e4["decision"]
    w("## Stage 2 decision\n")
    w(f"**{d['verdict'].upper()}**: {d['why']}.\n")
    w(f"Rule (fixed before E4 ran): on `{config.E4_PRIMARY}`, if prefill or decode drops more than "
      f"{config.RULE_DROPPED_PCT:.0f}% of frames, or its p95 frame interval exceeds {config.DROP_FACTOR}× the idle "
      f"budget, build the frame-aware scheduler. If idle itself drops more than {config.RULE_IDLE_MAX_PCT:.0f}%, "
      "the result is inconclusive. Otherwise build the capability gate.\n")
    if d.get("pages") and len(d["pages"]) > 1:
        w(f"Amended after the first E4 run: the light page alone read **{d['original']['verdict']}**, while the heavy "
          "page dropped most of its frames, so the rule now applies to the default setting on every page that ran and "
          "the worst page decides. Per page:\n")
        for c, pd in d["pages"].items():
            w(f"- `{c}`: {pd['verdict']}. {pd['why']}.")
        w("")

    # ---------------------------------------------------------------- headline
    e1 = A.config_table(db, "E1", scope)
    w("## Headline numbers\n")
    est9 = interp_9b(e1)
    heads = []
    for r in e1:
        if r["ctx"] == 4000 and r["quant"] == "Q4_K_M" and r["size_b"] in (7.0, 14.0):
            heads.append(f"- {r['model']} at 4k tokens: cold TTFT {med(r['ttft'])} ms, decode {med(r['gen_tps'], '{:.1f}')} tok/s.")
    if heads:
        L += heads
        w("")
    if est9:
        w(f"- Interpolated 9B Q4 cold TTFT at 4k: **{est9:.0f} ms**, against Dart's {C['ttft_9b_q4_4k_ms']:.0f} ms "
          f"(ratio {est9 / C['ttft_9b_q4_4k_ms']:.2f}×). Dart's paper does not name the machine, model, or whether the "
          "prompt cache was warm; E1b shows what a warm cache does to the same measurement.\n")
    r14 = next((r for r in e1 if r["size_b"] == 14.0 and r["quant"] == "Q4_K_M" and r["ctx"] == 4000), None)
    if r14 and r14["ttft"].get("n"):
        w(f"- 14B Q4 at 4k: {r14['ttft']['median']:.0f} ms here vs Dart's {C['ttft_14b_q4_4k_ms']:.0f} ms.\n")

    # ---------------------------------------------------------------- E1
    w("## E1: which configurations pass Dart's limits\n")
    w(f"Limits from DBR-2026-05: TTFT < {config.LIMITS['ttft_ms']:.0f} ms, decode > {config.LIMITS['gen_tps']:.0f} tok/s, "
      f"model memory < {config.LIMITS['mem_frac']*100:.0f}% of RAM. Accuracy, the fourth limit, needs Dart's 640-item set and is not measured. "
      "Cells show the median and the interquartile range. Brave is open with five tabs throughout.\n")
    w("| Config | Ctx | n | TTFT ms | Prefill tok/s | Decode tok/s | Memory MB (% RAM) | TTFT | Decode | Mem | All | Drift TTFT / tps |")
    w("|---|---:|---:|---:|---:|---:|---:|:-:|:-:|:-:|:-:|---:|")
    for r in e1:
        dr = r["drift"]
        w(f"| {r['model']} | {r['ctx']} | {r['n']} | {med(r['ttft'])} | {med(r['prompt_tps'])} | {med(r['gen_tps'], '{:.1f}')} | "
          f"{f(r['mem_mb'].get('median'))} ({f((r['mem_frac'] or 0)*100, '{:.0f}%')}) | {yn(r['pass']['ttft'])} | "
          f"{yn(r['pass']['gen_tps'])} | {yn(r['pass']['mem'])} | {yn(r['pass']['all'])} | "
          f"{f(dr.get('ttft_ms'), '{:+.0f}%')} / {f(dr.get('gen_tps'), '{:+.0f}%')} |")
    w("\nDrift compares the last third of a configuration's runs with the first third. A large positive TTFT drift, or a negative decode drift, points to thermal throttling.\n")
    passing = [r["model"] for r in e1 if r["ctx"] == 4000 and r["pass"]["all"]]
    if e1:
        w(f"At 4k tokens, these pass all three measured limits on this machine: {', '.join(passing) or 'none'}.\n")

    # ---------------------------------------------------------------- E0
    e0 = A.e0_table(db)
    if e0:
        w("## E0: raw llama-bench throughput (reference, no server, no browser)\n")
        w("| Model | pp512 | pp2048 | pp4096 | tg128 | Implied cold TTFT at 4k (ms) |")
        w("|---|---:|---:|---:|---:|---:|")
        for r in e0:
            w(f"| {r['model']} | {f(r.get('pp512'))} | {f(r.get('pp2048'))} | {f(r.get('pp4096'))} | {f(r.get('tg128'), '{:.1f}')} | {f(r.get('implied_ttft_4k_ms'))} |")
        w("\nThe implied TTFT is 4000 tokens divided by the raw prefill rate. It is a floor that no cold request through the server can beat on this machine.\n")

    # ---------------------------------------------------------------- E1b
    e1b = A.e1b_view(db, scope)
    if e1b:
        w("## E1b: cold prompt vs warm prefix cache, same 4k page\n")
        w("| Model | Cold TTFT ms | Warm TTFT ms | Tokens actually processed (cold / warm) | Speed-up |")
        w("|---|---:|---:|---:|---:|")
        for r in e1b:
            w(f"| {r['model']} | {med(r.get('cold'))} | {med(r.get('warm'))} | {f(r.get('cold_prompt_n'))} / {f(r.get('warm_prompt_n'))} | {f(r.get('speedup'), '{:.1f}×')} |")
        w("\nWhen the page is already in the KV cache, only the new question is processed. A TTFT figure is only meaningful once it says which of the two it measures.\n")

    # ---------------------------------------------------------------- E2
    e2 = A.e2_view(db, scope)
    if e2:
        w("## E2: memory pressure and paging\n")
        w(f"Incompressible ballast (a stand-in for other apps and tabs) is allocated before the model loads. Dart reports a {C['swap_penalty_x']}× penalty once the model pages.\n")
        for m in e2:
            w(f"**{m['model']}**: knee (decode > 1.2× slower) at {f(m['knee_gb'], '{:.0f} GB', 'none observed')} of ballast"
              + (f"; failed or collapsed at {m['failed_at_gb']} GB" if m["failed_at_gb"] else "") + ".\n")
            w("| Ballast GB | n | TTFT ms | Decode tok/s | Decode penalty | TTFT penalty | Swap Δ MB | Swapouts | Pressure |")
            w("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for r in m["levels"]:
                w(f"| {r['ballast_gb']:.0f} | {r['n']} | {med(r['ttft'])} | {med(r['gen_tps'], '{:.1f}')} | {f(r['tps_penalty_x'], '{:.2f}×')} | "
                  f"{f(r['ttft_penalty_x'], '{:.2f}×')} | {f(r['swap_delta_mb'].get('median'))} | {r['swapouts']} | {r['pressure_max']} |")
            w("")

    # ---------------------------------------------------------------- E3
    e3 = A.e3_view(db, scope)
    if e3:
        w("## E3: speculative decoding\n")
        w(f"Dart reports up to {C['spec_best_x']}× ({C['spec_blended_x']}× blended), with acceptance {C['spec_accept_summarise']} on summarise and "
          f"{C['spec_accept_extract']} on extract, and a rule to turn it off above {C['spec_mem_threshold']*100:.0f}% memory in use.\n")
        w("| Ballast GB | Task | Draft | n | Decode tok/s | Speed-up | End-to-end speed-up | Acceptance | System memory used |")
        w("|---:|---|---|---:|---:|---:|---:|---:|---:|")
        for r in e3:
            w(f"| {r['ballast_gb']:.0f} | {r['task']} | {r['draft']} | {r['n']} | {f(r['gen_tps'], '{:.1f}')} | {f(r.get('speedup'), '{:.2f}×')} | "
              f"{f(r.get('e2e_speedup'), '{:.2f}×')} | {f(r.get('accept'), '{:.2f}')} | {f(r['sys_used_frac']*100, '{:.0f}%')} |")
        hi = [r for r in e3 if r.get("speedup") and r["sys_used_frac"] > C["spec_mem_threshold"]]
        lo = [r for r in e3 if r.get("speedup") and r["sys_used_frac"] <= C["spec_mem_threshold"]]
        if hi and lo:
            import statistics as st
            w(f"\nMedian speed-up at or below 60% memory in use: {st.median([r['speedup'] for r in lo]):.2f}×. "
              f"Above 60%: {st.median([r['speedup'] for r in hi]):.2f}×.\n")
        w("")

    # ---------------------------------------------------------------- E4
    if e4["conditions"]:
        w("## E4: what the browser feels while the model runs\n")
        w("Brave shows a frame-timing page (WebGL plus continuous scroll) in front, with the five tabs open behind it. "
          f"A frame counts as dropped when its interval exceeds {config.DROP_FACTOR}× the no-model idle median (the budget). "
          "LoAF counts long-animation-frame entries (> 50 ms) per second.\n")
        w("| Condition | Phase | Frames | p50 ms | p95 ms | p99 ms | Max ms | Dropped | Frames lost | LoAF/s |")
        w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for c in e4["conditions"]:
            for ph in ("idle", "prefill", "decode", "gap"):
                s = c["phases"].get(ph)
                if not s or not s.get("n"):
                    continue
                w(f"| {c['condition']} | {ph} | {s['n']} | {s['p50']:.2f} | {s['p95']:.2f} | {s['p99']:.2f} | {s['max']:.0f} | "
                  f"{s['dropped_pct']:.1f}% | {s['lost_frames_pct']:.1f}% | {f(s['loaf_per_s'], '{:.2f}')} |")
        b = e4["conditions"][0]["budget_ms"]
        w(f"\nBudget measured at idle: {b:.2f} ms (about {1000 / b:.0f} Hz).\n")

    # ---------------------------------------------------------------- E5 / E6
    e5 = A.e5_view(db, scope)
    if e5.get("n"):
        w("## E5: sustained load\n")
        w(f"{e5['n']} back-to-back requests over {e5['minutes']:.1f} min. Decode was {f(e5.get('first_min_tps'), '{:.1f}')} tok/s in the first minute and "
          f"{f(e5.get('last_min_tps'), '{:.1f}')} tok/s in the last, a change of {f(e5.get('sustained_drop_pct'), '{:.1f}%')}. "
          "Short benchmarks can hide this.\n")
    e6 = [r for r in A.config_table(db, "E6", scope) if r.get("j_per_tok")]
    if e6:
        w("## E6: energy per token (CPU + GPU package power, from powermetrics)\n")
        w("| Config | Decode J/token | Prefill J/1k tokens | CPU W | GPU W | Decode tok/s |")
        w("|---|---:|---:|---:|---:|---:|")
        for r in e6:
            w(f"| {r['model']} | {med(r['j_per_tok'], '{:.3f}')} | {med(r.get('prefill_j_per_ktok'), '{:.1f}')} | {med(r.get('cpu_w'), '{:.1f}')} | "
              f"{med(r.get('gpu_w'), '{:.1f}')} | {med(r['gen_tps'], '{:.1f}')} |")
        w("")

    # ---------------------------------------------------------------- integrity
    rec = A.records(db)
    if rec:
        w("## Run integrity\n")
        w(f"{rec['sessions']} sessions, {rec['trials']} measured trials, {rec['errors']} errors, {rec['hours']:.1f} h of runs. "
          f"{rec['tokens_prefilled']:,} prompt tokens and {rec['tokens_generated']:,} generated tokens.\n")
        errs = db.query("SELECT experiment, condition, error, COUNT(*) n FROM trials WHERE error IS NOT NULL GROUP BY 1,2,3")
        for e in errs[:20]:
            w(f"- {e['experiment']} {e['condition']}: {e['error']} (×{e['n']})")
        if errs:
            w("")

    # ---------------------------------------------------------------- method
    w("## Method and limits\n")
    w("- Each configuration runs one warm-up request and then the measured runs. The prompt cache is off except in E1b's warm arm. "
      "Sampling is greedy with a fixed seed. EOS is ignored in E1, E2 and E4, so every run generates the same number of tokens. "
      "E3 lets generation stop naturally, because acceptance depends on the text.")
    w("- TTFT is wall time from sending the request to the first streamed token, which includes HTTP and tokenisation. Server-side prompt time is stored too.")
    w("- Memory is the llama-server process's physical footprint (proc_pid_rusage, which includes Metal buffers), sampled at 10 Hz.")
    w("- Models are Qwen 2.5 Instruct GGUF builds (bartowski). Dart's papers do not name their models, so model size is the comparable axis, not the exact model.")
    w("- Frame timing uses requestAnimationFrame intervals, which proxy what the user sees. Brave stands in for Dart, and both are Chromium-based.")
    w("- One machine. Numbers are for this M4 Pro, not for Dart's four machines.\n")
    return "\n".join(L)


def write(scope: str = "auto") -> list[str]:
    db = DB()
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "-fake" if config.FAKE else ""
    md = config.REPORTS_DIR / f"report{suffix}.md"
    md.write_text(build(db, scope))
    tcsv = config.REPORTS_DIR / f"trials{suffix}.csv"
    rows = db.query("SELECT * FROM trials ORDER BY id")
    with open(tcsv, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["id"] + TRIAL_COLS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)
    fcsv = config.REPORTS_DIR / f"frames_summary{suffix}.csv"
    with open(fcsv, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["condition", "phase", "n", "p50", "p95", "p99", "max", "dropped_pct", "lost_frames_pct", "loaf_per_s", "budget_ms"])
        for c in A.e4_view(db, scope)["conditions"]:
            for ph, s in c["phases"].items():
                if s.get("n"):
                    wr.writerow([c["condition"], ph, s["n"], s["p50"], s["p95"], s["p99"], s["max"], s["dropped_pct"],
                                 s["lost_frames_pct"], s["loaf_per_s"], c["budget_ms"]])
    return [str(md), str(tcsv), str(fcsv)]
