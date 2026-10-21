"""llama-server lifecycle and a streaming completion client that records wall-clock timings."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import config


@dataclass
class Completion:
    t_send: float
    t_first: float | None
    t_end: float
    text: str
    timings: dict = field(default_factory=dict)
    stop_reason: str = ""

    @property
    def ttft_ms(self) -> float | None:
        return None if self.t_first is None else (self.t_first - self.t_send) * 1000


def parse_sse_line(line: str) -> dict | None:
    """One 'data: {...}' line from /completion streaming; None for keep-alives and junk."""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    body = line[5:].strip()
    if not body or body == "[DONE]":
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


class LlamaServer:
    """Context manager: start llama-server for one configuration, wait until healthy, stop on exit."""

    def __init__(self, model: config.Model, *, ctx: int = 8192, ngl: int = 99, ubatch: int = 512,
                 draft: config.Model | None = None, draft_max: int = 16, draft_min: int = 0,
                 extra: list[str] | None = None, tag: str = ""):
        self.model, self.ctx, self.ngl, self.ubatch = model, ctx, ngl, ubatch
        self.draft, self.draft_max, self.draft_min = draft, draft_max, draft_min
        self.extra = extra or []
        self.base = f"http://127.0.0.1:{config.SERVER_PORT}"
        self.proc: subprocess.Popen | None = None
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}-{model.key}{'-' + draft.key if draft else ''}{'-' + tag if tag else ''}"
        self.log_path = config.LOGS_DIR / f"{name}.log"
        self.client = httpx.Client(base_url=self.base, timeout=httpx.Timeout(600, connect=5))
        self.load_s: float | None = None

    def cmd(self) -> list[str]:
        if config.FAKE:
            c = [sys.executable, "-m", "dartbench.fake_server", "--port", str(config.SERVER_PORT),
                 "--model", self.model.key]
            if self.draft:
                c += ["--draft", self.draft.key]
            return c + ["--ngl", str(self.ngl), "--ubatch", str(self.ubatch)]
        c = [config.LLAMA_SERVER, "-m", str(self.model.path), "-c", str(self.ctx), "-ngl", str(self.ngl),
             "-ub", str(self.ubatch), "-b", str(max(2048, self.ubatch)), "-np", "1", "-fa", "auto",
             "--host", "127.0.0.1", "--port", str(config.SERVER_PORT), "--no-webui", "--metrics"]
        if self.draft:
            c += ["-md", str(self.draft.path), "-ngld", str(self.ngl if self.ngl else 0),
                  "--spec-draft-n-max", str(self.draft_max), "--spec-draft-n-min", str(self.draft_min)]
        return c + self.extra

    def __enter__(self) -> "LlamaServer":
        _kill_port_holder(config.SERVER_PORT)
        t0 = time.time()
        log = open(self.log_path, "w")
        log.write("# " + " ".join(self.cmd()) + "\n")
        log.flush()
        self.proc = subprocess.Popen(self.cmd(), stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, env={**os.environ})
        deadline = t0 + 300
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited with {self.proc.returncode}; see {self.log_path}")
            try:
                r = self.client.get("/health", timeout=2)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    self.load_s = time.time() - t0
                    return self
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.25)
        self.stop()
        raise TimeoutError(f"llama-server not healthy after 300 s; see {self.log_path}")

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def stop(self) -> None:
        self.client.close()
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=15)
        except Exception:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
            except Exception:
                pass
        # Give the OS a moment to return the model's pages before the next configuration loads.
        time.sleep(1.5)

    # ------------------------------------------------------------------ API
    def tokenize(self, text: str) -> list[int]:
        r = self.client.post("/tokenize", json={"content": text, "add_special": False, "parse_special": True})
        r.raise_for_status()
        return r.json()["tokens"]

    def detokenize(self, tokens: list[int]) -> str:
        r = self.client.post("/detokenize", json={"tokens": tokens})
        r.raise_for_status()
        return r.json()["content"]

    def complete(self, prompt: str, *, n_predict: int, ignore_eos: bool = True, cache_prompt: bool = False,
                 seed: int = 42, on_first=None, deadline_s: float | None = None) -> Completion:
        """Stream a completion. on_first(t) is called the moment the first token arrives (for E4 phases)."""
        body = {"prompt": prompt, "n_predict": n_predict, "stream": True, "temperature": 0.0, "top_k": 1,
                "seed": seed, "ignore_eos": ignore_eos, "cache_prompt": cache_prompt, "timings_per_token": False}
        parts: list[str] = []
        t_first = None
        final: dict = {}
        timed_out = False
        t_send = time.time()
        with self.client.stream("POST", "/completion", json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                ev = parse_sse_line(line)
                if ev is None:
                    continue
                if ev.get("content"):
                    if t_first is None:
                        t_first = time.time()
                        if on_first:
                            on_first(t_first)
                    parts.append(ev["content"])
                if ev.get("stop"):
                    final = ev
                    break
                if deadline_s and time.time() - t_send > deadline_s:
                    timed_out = True
                    break
        t_end = time.time()
        if timed_out:
            raise TimeoutError(f"completion exceeded {deadline_s:.0f} s ({len(parts)} tokens streamed)")
        if t_first is None and final:
            t_first = t_end  # zero-content completion; treat end as first token
        return Completion(t_send, t_first, t_end, "".join(parts), final.get("timings", {}),
                          final.get("stop_type", "") or str(final.get("stopped_eos", "")))


def _kill_port_holder(port: int) -> None:
    """A crashed earlier run can leave a server bound to our port."""
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        for pid in out.split():
            os.kill(int(pid), signal.SIGKILL)
        if out.strip():
            time.sleep(1)
    except Exception:
        pass


def model_file_mb(model: config.Model) -> float:
    p = Path(model.path)
    return p.stat().st_size / 1024 / 1024 if p.exists() else 0.0
