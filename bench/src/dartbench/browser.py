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
    def __init__(self, extra_urls: list[str] | None = None, tabs: bool = True, debug_port: int | None = None):
        # Chromium makes the first URL the active tab; the frame page must be it, or it renders hidden and rAF stops
        # a test page that is also one of the five tabs (BBC) would open twice, and the DevTools pump could attach to
        # the hidden copy
        self.urls = (extra_urls or []) + [u for u in (config.TABS if tabs else []) if u not in (extra_urls or [])]
        self.debug_port = debug_port  # DevTools, to inject the frame recorder into third-party pages
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
        debug = [f"--remote-debugging-port={self.debug_port}", "--remote-allow-origins=http://127.0.0.1"] if self.debug_port else []
        cmd = [config.BRAVE, f"--user-data-dir={config.BRAVE_PROFILE}", *FLAGS, *debug, *self.urls]
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


def _osa(script: str, lang: str = "AppleScript") -> str:
    return subprocess.run(["osascript", "-l", lang, "-e", script], capture_output=True, text=True).stdout.strip()


class Safari:
    """One Safari window on our own frame page, sized like Brave's maximised window. Safari has no separate profile
    and no DevTools protocol, so this opens a window in the user's Safari and closes only that window on exit. No
    five-tab condition: the comparison is the page itself, against Brave's run of the same page."""

    def __init__(self, url: str):
        self.url = url
        self.window_id = ""

    @staticmethod
    def available() -> bool:
        return Path(config.SAFARI).exists()

    @staticmethod
    def bounds() -> str:
        """The screen's visible frame (minus menu bar and Dock) in AppleScript's top-left coordinates."""
        js = '''ObjC.import("AppKit"); const f = $.NSScreen.mainScreen.frame, v = $.NSScreen.mainScreen.visibleFrame;
[v.origin.x, f.size.height - v.origin.y - v.size.height, v.origin.x + v.size.width, f.size.height - v.origin.y].join(",")'''
        return _osa(js, "JavaScript") or "0,25,1440,900"

    def __enter__(self) -> "Safari":
        if config.FAKE:
            return self
        self.window_id = _osa(f'''tell application "Safari"
  make new document with properties {{URL:"{self.url}"}}
  set bounds of front window to {{{self.bounds()}}}
  activate
  return id of front window
end tell''')
        time.sleep(8)
        return self

    def __exit__(self, *exc) -> None:
        if config.FAKE or not self.window_id:
            return
        _osa(f'tell application "Safari" to close (every window whose id is {self.window_id})')

    def activate(self) -> None:
        if config.FAKE or not self.window_id:
            return
        _osa(f'''tell application "Safari"
  set index of (first window whose id is {self.window_id}) to 1
  activate
end tell''')
