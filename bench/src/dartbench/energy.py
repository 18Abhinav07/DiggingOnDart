"""Optional CPU/GPU power via `sudo -n powermetrics`. Run `sudo -v` first; without cached sudo the
sampler silently stays off and energy columns are left empty."""
from __future__ import annotations

import plistlib
import subprocess
import threading
import time

from . import config


class PowerSampler:
    def __init__(self, interval_ms: int = 200, enabled: bool = True):
        self.interval_ms = interval_ms
        self.samples: list[tuple[float, float, float, str]] = []  # (t, cpu_mw, gpu_mw, thermal)
        self.enabled = enabled and not config.FAKE and self.available()
        self.proc = None
        self._thread = None

    @staticmethod
    def available() -> bool:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0

    def start(self) -> "PowerSampler":
        if not self.enabled:
            return self
        self.proc = subprocess.Popen(
            ["sudo", "-n", "powermetrics", "--samplers", "cpu_power,gpu_power,thermal",
             "-i", str(self.interval_ms), "-f", "plist"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        time.sleep(0.5)
        return self

    def _read(self) -> None:
        buf = b""
        while self.proc and self.proc.poll() is None:
            chunk = self.proc.stdout.read1(65536) if hasattr(self.proc.stdout, "read1") else self.proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\x00" in buf:
                doc, buf = buf.split(b"\x00", 1)
                try:
                    d = plistlib.loads(doc.strip())
                except Exception:
                    continue
                p = d.get("processor", {})
                gpu = d.get("gpu", {})
                cpu_mw = float(p.get("cpu_power", p.get("cpu_energy", 0)) or 0)
                gpu_mw = float(p.get("gpu_power", gpu.get("gpu_energy", 0)) or 0)
                self.samples.append((time.time(), cpu_mw, gpu_mw, str(d.get("thermal_pressure", ""))))

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            subprocess.run(["sudo", "-n", "kill", str(self.proc.pid)], capture_output=True)
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass

    def window(self, t0: float, t1: float) -> dict:
        """Energy (J) and mean power (W) between two wall times. Each sample covers the interval before it."""
        if not self.samples or t1 <= t0:
            return {}
        dt = self.interval_ms / 1000
        inside = [s for s in self.samples if t0 < s[0] <= t1 + dt]
        if not inside:
            return {}
        cpu_w = sum(s[1] for s in inside) / len(inside) / 1000
        gpu_w = sum(s[2] for s in inside) / len(inside) / 1000
        dur = t1 - t0
        return {"j": (cpu_w + gpu_w) * dur, "cpu_w": cpu_w, "gpu_w": gpu_w,
                "thermal": inside[-1][3]}

    def thermal_now(self) -> str:
        return self.samples[-1][3] if self.samples else ""
