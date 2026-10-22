"""dartbench check | estimate | run <exp...|all> | report | dashboard"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys

from . import config, sysinfo
from .experiments import EXPERIMENTS, ORDER, run

OK, WARN, BAD = "ok  ", "WARN", "FAIL"


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def check(allow_battery: bool = False, allow_missing: bool = False) -> int:
    issues = 0

    def line(level, msg):
        nonlocal issues
        issues += level == BAD
        print(f"  [{level}] {msg}")

    print("dartbench preflight" + (" (FAKE mode)" if config.FAKE else ""))
    for name, binary in (("llama-server", config.LLAMA_SERVER), ("llama-bench", config.LLAMA_BENCH)):
        line(OK if shutil.which(binary) or config.FAKE else BAD, f"{name}: {shutil.which(binary) or 'not found'}")
    if not config.FAKE:
        line(OK, f"llama.cpp {sysinfo.llama_version()}")
    total = 0.0
    missing = []
    for k, m in config.MODELS.items():
        if m.path.exists():
            total += m.path.stat().st_size / 1024**3
        elif not config.FAKE:
            missing.append(k)
    tier1 = ["7B-Q4_K_M", "0.5B-Q8_0", "1.5B-Q8_0", "3B-Q4_K_M", "7B-Q2_K", "7B-Q8_0", "14B-Q4_K_M"]
    miss1 = [k for k in missing if k in tier1]
    line(BAD if miss1 and not allow_missing else (WARN if missing else OK),
         f"models: {len(config.MODELS) - len(missing)}/{len(config.MODELS)} present ({total:.1f} GB)"
         + (f"; missing {', '.join(missing)}" if missing else ""))
    partial = list((config.MODELS_DIR / ".cache").rglob("*.incomplete")) if (config.MODELS_DIR / ".cache").exists() else []
    if partial:
        line(WARN, f"{len(partial)} download(s) still in progress in {config.MODELS_DIR}/.cache")
    line(OK if os.path.exists(config.BRAVE) else BAD, f"Brave: {sysinfo.app_version('/Applications/Brave Browser.app') or 'not found'}")
    pw = sysinfo.power_source()
    line(OK if pw == "ac" else (WARN if allow_battery else BAD), f"power: {pw}" + ("" if pw == "ac" else " (plug in: battery throttles the GPU)"))
    line(BAD if sysinfo.low_power_mode() else OK, f"low power mode: {'ON' if sysinfo.low_power_mode() else 'off'}")
    import psutil
    vm = psutil.virtual_memory()
    avail = vm.available / 1024**3
    line(OK if avail > 16 else WARN, f"memory available: {avail:.1f} GB of {vm.total / 1024**3:.0f} GB")
    swap = sysinfo.swap_used_mb()
    line(OK if swap < 1024 else WARN, f"swap in use: {swap:.0f} MB" + ("" if swap < 1024 else " (a reboot gives a cleaner baseline)"))
    heavy = [p for p in sysinfo.heavy_processes(12) if p["rss_mb"] > 800 and p["name"] not in ("python", "python3", "kernel_task", "WindowServer")]
    if heavy:
        line(WARN, "large apps running: " + ", ".join(f"{p['name']} {p['rss_mb'] / 1024:.1f} GB" for p in heavy[:6]))
    disk = shutil.disk_usage(config.ROOT).free / 1024**3
    line(OK if disk > 20 else WARN, f"disk free: {disk:.0f} GB")
    for port in (config.SERVER_PORT, config.FRAMES_PORT):
        line(OK if _port_free(port) else WARN, f"port {port}: {'free' if _port_free(port) else 'in use (will be reclaimed)'}")
    sudo = subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0
    line(OK if sudo else WARN, "sudo cached for powermetrics (E6 energy)" if sudo else "sudo not cached: run `sudo -v` first if you want E6 energy numbers")
    th = sysinfo.thermal_note()
    line(OK if th == "no warnings" else WARN, f"thermal: {th}")
    disp = sysinfo.displays()
    if disp:
        d = disp[0]
        line(OK, f"display: {d.get('_spdisplays_resolution', d.get('_spdisplays_pixels', '?'))} {d.get('_spdisplays_refresh_rate', '')}".strip())
    print(f"\n{'READY' if issues == 0 else f'{issues} blocking issue(s)'}")
    return 1 if issues else 0


def estimate(quick: bool) -> None:
    """Rough minutes per experiment, from model sizes and conservative M4 Pro rates."""
    def rates(m):
        gb = (m.path.stat().st_size / 1024**3) if m.path.exists() else m.size_b * 0.6
        # prefill tok/s, decode tok/s, calibrated on this M4 Pro (7B-Q4 on battery: 258 / 27.5), plus AC headroom
        return 2100 / m.size_b, 130 / gb

    def trial_s(m, ctx, gen):
        pp, tg = rates(m)
        return ctx / pp + gen / tg + 2.5

    M = config.MODELS
    q = lambda n: min(n, 2) if quick else n
    est = {}
    est["e0"] = sum(3 * (7700 / rates(M[k])[0] + 128 / rates(M[k])[1]) + 20 for k in config.E0_MODELS) / 60
    ctx_runs = {4000: 3, 2000: 2} if quick else config.E1_CTX_RUNS
    est["e1"] = (sum(sum((n + 1) * trial_s(M[k], c, 256) for c, n in ctx_runs.items()) + 25 for k in
                     (["3B-Q4_K_M", "7B-Q4_K_M"] if quick else config.E1_MODELS)) + 15) / 60
    est["e1b"] = sum(q(config.E1B_RUNS) * (trial_s(M[k], 4000, 64) + 2 * trial_s(M[k], 300, 64)) + 25 for k in config.E1B_MODELS) / 60
    est["e2"] = sum(len(config.E2_BALLAST_GB) * (q(5) + 1) * trial_s(M[k], 4000, 128) * 1.8 + 60 for k in config.E2_MODELS) / 60
    est["e3"] = len(config.E3_BALLAST_GB if not quick else [0]) * (1 + 2 * (1 if quick else len(config.E3_DRAFT_MAX))) * 2 * (q(5) + 1) * trial_s(M["7B-Q4_K_M"], 2000, 220) / 60 + 5
    conds = config.E4_CONDITIONS if not quick else [c for c in config.E4_CONDITIONS if c[0] == config.E4_PRIMARY]
    e4_s = lambda c: config.E4_IDLE_S + 25 + q(config.E4_RUNS_OVERRIDE.get(c[0], 5)) * (
        trial_s(M[c[1]], 4000, 256) * (12 if c[2] == 0 else 1.5 if len(c) > 5 else 1) + config.E4_GAP_S)
    est["e4"] = (2 * 15 + sum(e4_s(c) for c in conds)) / 60
    xconds = config.E4X_CONDITIONS if not quick else [c for c in config.E4X_CONDITIONS if c[0] in config.E4_PRIMARIES]
    est["e4x"] = (len({c[4] for c in xconds}) * (15 + config.E4_IDLE_S) + sum(e4_s(c) for c in xconds)) / 60
    est["e5"] = 1 if quick else config.E5_MINUTES + 1
    est["e6"] = sum((q(5) + 1) * trial_s(M[k], 4000, 256) + 25 for k in config.E6_MODELS) / 60
    total = 0
    print(f"Estimated run time ({'quick' if quick else 'full'}), in run order:")
    for k in ORDER:
        print(f"  {k:4s} {est[k]:6.0f} min")
        total += est[k]
    print(f"  total {total:5.0f} min (~{total / 60:.1f} h). Estimates are rough; paging in E2 can stretch them.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dartbench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--allow-battery", action="store_true")
    c.add_argument("--allow-missing", action="store_true")
    e = sub.add_parser("estimate")
    e.add_argument("--quick", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("experiments", nargs="+", help=f"all, or any of {', '.join(ORDER)}")
    r.add_argument("--quick", action="store_true", help="2 runs per config, fewer configs: a 15-30 min smoke test")
    r.add_argument("--energy", action="store_true", help="sample powermetrics (needs `sudo -v` first)")
    r.add_argument("--label", default="")
    r.add_argument("--allow-battery", action="store_true")
    r.add_argument("--allow-missing", action="store_true", help="run with only the models downloaded so far; the rest are skipped")
    r.add_argument("--yes", action="store_true", help="skip the preflight prompt")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="auto", choices=["auto", "full", "quick", "all"])
    d = sub.add_parser("dashboard")
    d.add_argument("--port", type=int, default=config.DASHBOARD_PORT)
    d.add_argument("--no-open", action="store_true")
    x = sub.add_parser("export", help="write the dashboard as one static HTML file (no server needed)")
    x.add_argument("--out", default=str(config.REPORTS_DIR / "dashboard.html"))
    w = sub.add_parser("site", help="write site/data.js: every run plus frame replays, for the findings site")
    w.add_argument("--out", default=str(config.ROOT.parent / "site" / "data.js"))
    a = ap.parse_args(argv)

    if a.cmd == "check":
        sys.exit(check(a.allow_battery, a.allow_missing))
    if a.cmd == "estimate":
        estimate(a.quick)
        return
    if a.cmd == "report":
        from .report import write
        for p in write(a.scope):
            print(p)
        return
    if a.cmd == "dashboard":
        from .dashboard import serve
        serve(a.port, open_browser=not a.no_open)
        return
    if a.cmd == "export":
        from pathlib import Path
        from .dashboard import export
        print(export(Path(a.out)))
        return
    if a.cmd == "site":
        from pathlib import Path
        from .site import export
        print(export(Path(a.out)))
        return

    names = ORDER if a.experiments == ["all"] else [x.lower() for x in a.experiments]
    bad = [n for n in names if n not in EXPERIMENTS]
    if bad:
        ap.error(f"unknown experiment(s): {bad}")
    if not config.FAKE:
        if check(a.allow_battery, a.allow_missing) != 0:
            sys.exit("Preflight failed. Fix the FAIL lines above (or pass --allow-battery / --allow-missing for a test run).")
        if not a.yes:
            input("\nDon't touch the Mac during E4 (frame timing). Press Enter to start, Ctrl-C to abort. ")
    # keep display and system awake for the whole run
    caf = None if config.FAKE else subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
    try:
        stats = run(names, quick=a.quick, energy=a.energy, label=a.label)
    except KeyboardInterrupt:
        print("\nInterrupted. Completed trials are saved; rerun the same command to resume.")
        sys.exit(130)
    finally:
        if caf:
            caf.terminate()
    print(f"\nDone in {stats['minutes']} min: {stats['trials']} trials, {stats['errors']} errors.")
    if stats["skipped"]:
        print("Skipped: " + "; ".join(stats["skipped"]))
    from .report import write
    for p in write():
        print(p)


if __name__ == "__main__":
    main()
