"""Machine metadata and cheap system probes (memory, swap, pressure, power, thermal)."""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

import psutil

from . import config

MB = 1024 * 1024


def _run(cmd: list[str], timeout: float = 10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def sysctl(name: str) -> str:
    return _run(["sysctl", "-n", name])


def memory_pressure_level() -> int:
    """kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical."""
    try:
        return int(sysctl("kern.memorystatus_vm_pressure_level") or 0)
    except ValueError:
        return 0


def vm_counters() -> dict[str, int]:
    out = _run(["vm_stat"])
    page = 16384
    m = re.search(r"page size of (\d+) bytes", out)
    if m:
        page = int(m.group(1))
    counts = {}
    for key, name in [("Pageouts", "pageouts"), ("Swapouts", "swapouts"), ("Pageins", "pageins")]:
        m = re.search(rf"{key}:\s+(\d+)", out)
        counts[name] = int(m.group(1)) if m else 0
    counts["page_size"] = page
    return counts


def swap_used_mb() -> float:
    return psutil.swap_memory().used / MB


def power_source() -> str:
    out = _run(["pmset", "-g", "batt"])
    if "AC Power" in out:
        return "ac"
    if "Battery Power" in out:
        return "battery"
    return "unknown"


def low_power_mode() -> bool:
    return bool(re.search(r"lowpowermode\s+1", _run(["pmset", "-g"])))


def thermal_note() -> str:
    """Compact pmset thermal state. Apple Silicon reports little here; powermetrics is better (sudo)."""
    out = _run(["pmset", "-g", "therm"])
    lines = [l.strip() for l in out.splitlines() if l.strip() and "No " not in l]
    return "; ".join(lines) or "no warnings"


def gpu_cores() -> str:
    out = _run(["system_profiler", "SPDisplaysDataType"], timeout=20)
    m = re.search(r"Total Number of Cores:\s*(\d+)", out)
    return m.group(1) if m else "?"


def displays() -> list[dict]:
    try:
        data = json.loads(_run(["system_profiler", "-json", "SPDisplaysDataType"], timeout=20) or "{}")
    except json.JSONDecodeError:
        return []
    out = []
    for gpu in data.get("SPDisplaysDataType", []):
        for d in gpu.get("spdisplays_ndrvs", []):
            out.append({k: v for k, v in d.items() if k in (
                "_name", "_spdisplays_resolution", "_spdisplays_pixels", "spdisplays_main",
                "spdisplays_connection_type", "spdisplays_display_type", "_spdisplays_refresh_rate")})
    return out


def app_version(app: str) -> str:
    plist = Path(app) / "Contents" / "Info.plist"
    if not plist.exists():
        return ""
    return _run(["defaults", "read", str(plist), "CFBundleShortVersionString"])


def llama_version() -> str:
    if config.FAKE:
        return "fake"
    out = subprocess.run([config.LLAMA_SERVER, "--version"], capture_output=True, text=True).stderr
    out += subprocess.run([config.LLAMA_SERVER, "--version"], capture_output=True, text=True).stdout
    m = re.search(r"version: (.+)", out)
    return m.group(1).strip() if m else out.strip()[:120]


def heavy_processes(n: int = 8) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            procs.append({"pid": p.info["pid"], "name": p.info["name"],
                          "rss_mb": round(p.info["memory_info"].rss / MB)})
        except Exception:
            pass
    return sorted(procs, key=lambda x: -x["rss_mb"])[:n]


def environment() -> dict:
    vm = psutil.virtual_memory()
    return {
        "chip": sysctl("machdep.cpu.brand_string"),
        "ram_gb": round(int(sysctl("hw.memsize") or 0) / 1024**3, 1),
        "perf_cores": sysctl("hw.perflevel0.physicalcpu"),
        "eff_cores": sysctl("hw.perflevel1.physicalcpu"),
        "gpu_cores": gpu_cores(),
        "gpu_wired_limit_mb": sysctl("iogpu.wired_limit_mb"),
        "macos": platform.mac_ver()[0],
        "build": _run(["sw_vers", "-buildVersion"]),
        "python": platform.python_version(),
        "llama_cpp": llama_version(),
        "brave": app_version("/Applications/Brave Browser.app"),
        "power": power_source(),
        "low_power_mode": low_power_mode(),
        "thermal": thermal_note(),
        "displays": displays(),
        "mem_available_gb_at_start": round(vm.available / 1024**3, 2),
        "swap_used_mb_at_start": round(swap_used_mb()),
        "disk_free_gb": round(shutil.disk_usage(Path.home()).free / 1024**3),
        "heavy_processes_at_start": heavy_processes(),
        "fake": config.FAKE,
    }


def total_ram_mb() -> float:
    return psutil.virtual_memory().total / MB
