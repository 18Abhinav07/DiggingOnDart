"""Memory ballast: a separate process holding N GB of incompressible bytes, standing in for other
apps and tabs.

macOS compresses idle memory, so zeros or repeated patterns would barely register. Random bytes do
not compress. By default the ballast re-reads one byte per page every few seconds, so it behaves like
a live working set instead of being quietly swapped out once the model loads.
"""
from __future__ import annotations

import subprocess
import sys
import time

import psutil

CHUNK_MB = 256
PAGE = 16384


def _child(gb: float, touch_s: float) -> None:
    import os
    chunks = []
    target = int(gb * 1024 / CHUNK_MB)
    for _ in range(target):
        chunks.append(os.urandom(CHUNK_MB * 1024 * 1024))
    print(f"READY {len(chunks) * CHUNK_MB}", flush=True)
    while True:
        if touch_s > 0:
            for c in chunks:
                _ = c[::PAGE]  # touches every page
            time.sleep(touch_s)
        else:
            time.sleep(3600)


class Ballast:
    def __init__(self, gb: float, touch_s: float = 3.0, fake: bool = False):
        self.gb, self.touch_s, self.fake = gb, touch_s, fake
        self.proc: subprocess.Popen | None = None
        self.alloc_s: float | None = None

    def __enter__(self) -> "Ballast":
        if self.gb <= 0:
            return self
        t0 = time.time()
        gb = 0.05 if self.fake else self.gb  # keep the dry run cheap
        self.proc = subprocess.Popen([sys.executable, "-m", "dartbench.ballast", str(gb), str(self.touch_s)],
                                     stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        if not line.startswith("READY"):
            self.stop()
            raise RuntimeError(f"ballast failed to allocate {gb} GB: {line!r}")
        self.alloc_s = time.time() - t0
        time.sleep(2)  # let the compressor/swapper settle
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def rss_mb(self) -> float | None:
        if not self.proc or self.proc.poll() is not None:
            return None
        try:
            return psutil.Process(self.proc.pid).memory_info().rss / 1024 / 1024
        except psutil.Error:
            return None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
            time.sleep(2)  # swap and compressor need a moment to drain


if __name__ == "__main__":
    _child(float(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 3.0)
