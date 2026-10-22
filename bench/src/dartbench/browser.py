"""Launch and quit a dedicated Brave instance (its own profile) with the papers' five-tab condition."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import psutil

from . import config

FLAGS = [
    "--no-first-run", "--no-default-browser-check", "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    "--disable-features=CalculateNativeWinOcclusion", "--start-maximized", "--new-window",
    "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
]


class Browser:
    def __init__(self, extra_urls: list[str] | None = None, tabs: bool = True):
        # Chromium makes the first URL the active tab; the frame page must be it, or it renders hidden and rAF stops
        self.urls = (extra_urls or []) + (list(config.TABS) if tabs else [])
        self.proc: subprocess.Popen | None = None

    @staticmethod
    def available() -> bool:
        return Path(config.BRAVE).exists()

    def __enter__(self) -> "Browser":
        if config.FAKE:
            return self
        config.BRAVE_PROFILE.mkdir(parents=True, exist_ok=True)
        self.quit_stale()
        # quit() kills Brave, so it treats every launch as a crash recovery and restores the old tabs on top of ours
        shutil.rmtree(config.BRAVE_PROFILE / "Default" / "Sessions", ignore_errors=True)
        cmd = [config.BRAVE, f"--user-data-dir={config.BRAVE_PROFILE}", *FLAGS, *self.urls]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
        time.sleep(12)  # five real pages; let them load and settle
        return self

    def __exit__(self, *exc) -> None:
        self.quit()

    def processes(self) -> list[psutil.Process]:
        out = []
        for p in psutil.process_iter(["cmdline"]):
            try:
                if any(str(config.BRAVE_PROFILE) in a for a in (p.info["cmdline"] or [])):
                    out.append(p)
            except psutil.Error:
                pass
        return out

    def footprint_mb(self) -> float:
        total = 0.0
        for p in self.processes():
            try:
                total += p.memory_info().rss / 1024 / 1024
            except psutil.Error:
                pass
        return total

    def quit(self) -> None:
        if config.FAKE:
            return
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=10)
            except Exception:
                pass
        self.quit_stale()

    def quit_stale(self) -> None:
        for p in self.processes():
            try:
                p.kill()
            except psutil.Error:
                pass
        time.sleep(1)
