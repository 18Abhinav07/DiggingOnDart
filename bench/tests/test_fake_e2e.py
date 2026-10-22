"""End to end against the fake llama-server: paced prefill, then a quick run of every experiment
into a throwaway database, then the report and dashboard views over it."""
import os
import subprocess
import sys

import pytest

from dartbench import config


@pytest.fixture
def fake_server(monkeypatch):
    monkeypatch.setattr(config, "FAKE", True)
    from dartbench.server import LlamaServer
    with LlamaServer(config.MODELS["7B-Q4_K_M"]) as srv:
        yield srv


def test_complete_streams(fake_server):
    c = fake_server.complete("hello " * 200, n_predict=8)
    assert c.ttft_ms is not None and c.ttft_ms >= 0
    assert c.timings["predicted_n"] == 8


def test_paced_prefill_reuses_cache(fake_server):
    prompt = "x" * 1000
    c = fake_server.complete(prompt, n_predict=4, pace=(128, 0))
    # nonce + prompt, split into 128-token chunks, then one final streamed request
    n_ids = len(fake_server.tokenize(prompt)) + len(fake_server.tokenize(f"[{0}]\n")) - 1
    assert c.timings["chunks"] >= n_ids // 128
    # each chunk only prefills the new tokens: the total stays about the prompt length, not quadratic
    assert c.timings["prompt_n"] <= n_ids + 32


def test_paced_trials_start_cold(fake_server):
    a = fake_server.complete("y" * 600, n_predict=2, pace=(200, 0))
    b = fake_server.complete("y" * 600, n_predict=2, pace=(200, 0))
    assert b.timings["prompt_n"] >= 0.9 * a.timings["prompt_n"]


@pytest.mark.slow
def test_quick_run_all(tmp_path):
    env = {**os.environ, "DARTBENCH_FAKE": "1", "DARTBENCH_DB": str(tmp_path / "e2e.db")}
    r = subprocess.run([sys.executable, "-m", "dartbench.cli", "run", "all", "--quick", "--label", "e2e"],
                       env=env, capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "0 errors" in r.stdout, r.stdout[-3000:]
    check = (
        "from dartbench.db import DB; from dartbench import analysis as a, dashboard as d;"
        "db=DB(); v=a.e4_view(db); assert v['conditions'], 'no E4';"
        "assert v['decision']['verdict'] in ('scheduler','gate'), v['decision'];"
        "assert a.e3_view(db) and a.e2_view(db) and a.e1b_view(db) and a.e0_table(db);"
        "print('views ok', v['decision']['verdict'])"
    )
    v = subprocess.run([sys.executable, "-c", check], env=env, capture_output=True, text=True, timeout=120)
    assert v.returncode == 0, v.stdout + v.stderr
