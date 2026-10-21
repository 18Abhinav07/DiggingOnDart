"""10 Hz memory sampler for one trial.

Records the server's physical footprint (the figure Activity Monitor shows, which includes Metal
buffers that plain RSS can miss) alongside RSS, system memory in use, available memory, swap and the
kernel's memory-pressure level.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import threading
import time

import psutil

from . import sysinfo

MB = 1024 * 1024


class _RusageInfoV2(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins",
        "ri_wired_size", "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
        "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time", "ri_child_pkg_idle_wkups",
        "ri_child_interrupt_wkups", "ri_child_pageins", "ri_child_elapsed_abstime",
        "ri_diskio_bytesread", "ri_diskio_byteswritten")]


try:
    _libc = ctypes.CDLL(ctypes.util.find_library("c"))
    _libc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(_RusageInfoV2)]
except Exception:  # not macOS
    _libc = None


def footprint_mb(pid: int) -> float | None:
    if _libc is None:
        return None
    info = _RusageInfoV2()
    if _libc.proc_pid_rusage(pid, 2, ctypes.byref(info)) != 0:
        return None
    return info.ri_phys_footprint / MB


def proc_pageins(pid: int) -> int | None:
    if _libc is None:
        return None
    info = _RusageInfoV2()
    if _libc.proc_pid_rusage(pid, 2, ctypes.byref(info)) != 0:
        return None
    return int(info.ri_pageins)


class MemSampler:
    """Use as a context manager around one request. samples: (t, rss, footprint, sys_used, avail, swap)."""

    def __init__(self, pid: int | None, hz: float = 10, pressure_every: int = 10):
        self.pid = pid
        self.period = 1 / hz
        self.pressure_every = pressure_every
        self.samples: list[tuple] = []
        self.pressure_max = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        try:
            self._proc = psutil.Process(pid) if pid else None
        except psutil.Error:
            self._proc = None

    def _loop(self) -> None:
        i = 0
        while not self._stop.is_set():
            t = time.time()
            rss = fp = None
            if self._proc:
                try:
                    rss = self._proc.memory_info().rss / MB
                except psutil.Error:
                    pass
                fp = footprint_mb(self.pid)
            vm = psutil.virtual_memory()
            swap = psutil.swap_memory().used / MB
            self.samples.append((t, rss, fp, (vm.total - vm.available) / MB, vm.available / MB, swap))
            if i % self.pressure_every == 0:
                self.pressure_max = max(self.pressure_max, sysinfo.memory_pressure_level())
            i += 1
            self._stop.wait(max(0.0, self.period - (time.time() - t)))

    def __enter__(self) -> "MemSampler":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def summary(self) -> dict:
        def peak(i):
            vals = [s[i] for s in self.samples if s[i] is not None]
            return max(vals) if vals else None
        avail = [s[4] for s in self.samples if s[4] is not None]
        return {"peak_rss_mb": peak(1), "peak_footprint_mb": peak(2), "peak_sys_used_mb": peak(3),
                "min_avail_mb": min(avail) if avail else None, "pressure_max": self.pressure_max}


def downsample(samples: list[tuple], max_points: int = 400) -> list[tuple]:
    if len(samples) <= max_points:
        return samples
    step = len(samples) / max_points
    return [samples[int(i * step)] for i in range(max_points)]
