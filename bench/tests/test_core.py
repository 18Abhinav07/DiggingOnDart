"""Unit tests for the pieces that have bitten us: SSE parsing, frame maths, the Stage 2 rule,
session scoping, memory accounting, and the frame page's visibility checks."""
import time

import pytest

from dartbench import analysis, config
from dartbench.browser import Browser
from dartbench.db import DB
from dartbench.frames import FrameCollector
from dartbench.server import parse_sse_line


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


# ---------------------------------------------------------------- SSE
def test_parse_sse_line():
    assert parse_sse_line('data: {"content": "hi", "stop": false}') == {"content": "hi", "stop": False}
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line(": keep-alive") is None
    assert parse_sse_line("data: {broken") is None
    assert parse_sse_line("") is None


# ---------------------------------------------------------------- frames
def test_frame_stats_counts_drops_and_lost_frames():
    budget = 8.33
    intervals = [budget] * 96 + [budget * 2] * 2 + [budget * 4] * 2  # 4 drops, 2 + 6 frames lost
    s = analysis.frame_stats(intervals, budget, loaf=[60.0], dur_s=1.0)
    assert s["n"] == 100
    assert s["dropped_pct"] == pytest.approx(4.0)
    assert s["lost_frames_pct"] == pytest.approx(8 / 108 * 100)
    assert s["loaf_n"] == 1 and s["loaf_max_ms"] == 60.0


def test_frame_stats_empty():
    assert analysis.frame_stats([], 8.33) == {"n": 0}


def _primary(idle, prefill, decode=0.0, p95=8.4):
    ph = lambda d: {"n": 100, "dropped_pct": d, "p95": p95}
    return {"budget_ms": 8.33, "phases": {"idle": ph(idle), "prefill": ph(prefill), "decode": ph(decode)}}


def test_decide_scheduler_when_inference_drops_frames():
    d = analysis.decide(_primary(idle=0.5, prefill=12.0))
    assert d["verdict"] == "scheduler" and d["worst_phase"] == "prefill"


def test_decide_gate_when_smooth():
    assert analysis.decide(_primary(idle=0.5, prefill=1.0, decode=0.5))["verdict"] == "gate"


def test_decide_scheduler_on_p95_alone():
    d = analysis.decide(_primary(idle=0.5, prefill=1.0, p95=8.33 * config.DROP_FACTOR + 1))
    assert d["verdict"] == "scheduler"


def test_decide_inconclusive_on_noisy_idle():
    assert analysis.decide(_primary(idle=config.RULE_IDLE_MAX_PCT + 1, prefill=20))["verdict"] == "inconclusive"


def test_decide_pending_without_data():
    assert analysis.decide(None)["verdict"] == "pending"
    assert analysis.decide({"budget_ms": 8.33, "phases": {}})["verdict"] == "pending"


def test_decide_pending_when_no_frames_recorded():
    """The hidden-tab failure: phases exist but hold no frames. Must not read as a verdict."""
    p = {"budget_ms": 8.33, "phases": {"idle": {"n": 0}, "prefill": {"n": 0}, "decode": {"n": 0}}}
    assert analysis.decide(p)["verdict"] == "pending"


# ---------------------------------------------------------------- sessions
def test_session_ids_scoping_and_invalid(db):
    full = db.start_session("E1", "full", {}, {})
    quick = db.start_session("E1", "q", {}, {"quick": True})
    bad = db.start_session("E1", "full", {}, {})
    db.end_session(bad, "invalid")
    assert analysis.session_ids(db, "E1") == [full]
    assert analysis.session_ids(db, "E1", "quick") == [quick]
    assert bad not in analysis.session_ids(db, "E1", "all")


def test_session_ids_falls_back_to_quick(db):
    quick = db.start_session("E3", "q", {}, {"quick": True})
    assert analysis.session_ids(db, "E3") == [quick]


# ---------------------------------------------------------------- memory
def test_mem_mb_adds_mmapped_weights():
    # Metal reads mmapped weights in place, so the footprint excludes them; the model file is added back
    assert analysis.mem_mb({"peak_footprint_mb": 675, "model_mb": 4460}) == 5135
    assert analysis.mem_mb({"peak_rss_mb": 500, "model_mb": 0}) == 500
    assert analysis.mem_mb({}) is None


# ---------------------------------------------------------------- browser / frame page
def test_frame_page_is_first_tab():
    """Chromium activates the first URL; the frame page must be it or it renders hidden (rAF stops)."""
    b = Browser(extra_urls=["http://127.0.0.1:8765/?load=light"])
    assert b.urls[0].startswith("http://127.0.0.1:8765")
    assert b.urls[1:] == list(config.TABS)


@pytest.fixture
def real_collector(monkeypatch):
    monkeypatch.setattr(config, "FAKE", False)
    return FrameCollector()


def test_healthy_rejects_hidden_page(real_collector):
    fc = real_collector
    fc.store.add({"frames": [], "visible": "hidden"})
    ok, why = fc.healthy()
    assert not ok and "hidden" in why


def test_healthy_accepts_visible_recent_page(real_collector):
    fc = real_collector
    fc.store.add({"frames": [[1.0, 8.3]], "visible": "visible"})
    assert fc.healthy()[0]


def test_healthy_rejects_stale_page(real_collector):
    fc = real_collector
    fc.store.add({"frames": [], "visible": "visible"})
    fc.store.last_post = time.time() - 10
    assert not fc.healthy()[0]


def test_wait_for_page_times_out_on_hidden(real_collector):
    fc = real_collector
    fc.store.add({"frames": [], "visible": "hidden"})
    t0 = time.time()
    assert fc.wait_for_page(timeout=1.2) is False
    assert time.time() - t0 >= 1.0


def test_store_drain_splits_raf_and_loaf(real_collector):
    fc = real_collector
    fc.store.add({"frames": [[1.0, 8.3], [9.3, 16.6]], "loaf": [[2.0, 55.0, 10.0]], "visible": "visible"})
    rows = fc.drain()
    assert [r[2] for r in rows] == ["raf", "raf", "loaf"]
    assert fc.drain() == []


# ---------------------------------------------------------------- E4 view end to end on synthetic frames
def test_e4_view_reads_phases(db):
    sid = db.start_session("E4", "full", {}, {})
    budget = 8.33
    t = 0.0
    rows = []
    # phase edges sit between frame timestamps, as they do in real runs
    def emit(n, d):
        nonlocal t
        for _ in range(n):
            t += d
            rows.append((t, d, "raf"))
    t0 = t; emit(200, budget); db.add_phase(sid, None, "no-model light", "idle", t0 + .5, t + .5)
    t0 = t; emit(200, budget); db.add_phase(sid, None, config.E4_PRIMARY, "idle", t0 + .5, t + .5)
    t0 = t; emit(80, budget); emit(20, budget * 3); db.add_phase(sid, None, config.E4_PRIMARY, "prefill", t0 + .5, t + .5)
    t0 = t; emit(100, budget); db.add_phase(sid, None, config.E4_PRIMARY, "decode", t0 + .5, t + .5)
    db.add_frames(sid, rows)
    v = analysis.e4_view(db)
    prim = next(r for r in v["conditions"] if r["condition"] == config.E4_PRIMARY)
    assert prim["phases"]["prefill"]["dropped_pct"] == pytest.approx(20.0)
    assert v["decision"]["verdict"] == "scheduler"


# ---------------------------------------------------------------- E4 follow-up: real pages, amended rule
def test_real_page_urls_and_loads():
    fc = FrameCollector()
    for key, url in config.E4_REAL_PAGES.items():
        assert fc.url(key) == url
        assert config.E4_LOAD[f"7B-Q4 gpu ub512 @{key}"] == key
    assert fc.url("heavy").startswith("http://127.0.0.1")
    assert config.E4_LOAD["7B-Q4 paced c64 g16 heavy-page"] == "heavy"


def test_decide_all_worst_page_decides():
    rows = [{"condition": config.E4_PRIMARY, **_primary(idle=0.5, prefill=1.0)},
            {"condition": "7B-Q4 gpu ub512 heavy-page", **_primary(idle=0.5, prefill=60.0)}]
    d = analysis.decide_all(rows)
    assert d["verdict"] == "scheduler" and d["condition"] == "7B-Q4 gpu ub512 heavy-page"
    assert d["original"]["verdict"] == "gate"


def test_decide_all_pending_without_rows():
    assert analysis.decide_all([])["verdict"] == "pending"


def test_e4_view_budget_per_real_page(db):
    """A real page's conditions take the budget from its own no-model baseline, not the light page's."""
    sid = db.start_session("E4", "full", {}, {})
    key = next(iter(config.E4_REAL_PAGES))
    rows, t = [], 0.0
    def emit(n, d):
        nonlocal t
        for _ in range(n):
            t += d
            rows.append((t, d, "raf"))
    t0 = t; emit(100, 8.33); db.add_phase(sid, None, "no-model light", "idle", t0 + .5, t + .5)
    t0 = t; emit(100, 16.7); db.add_phase(sid, None, f"no-model {key}", "idle", t0 + .5, t + .5)
    t0 = t; emit(100, 16.7); db.add_phase(sid, None, f"7B-Q4 gpu ub512 @{key}", "idle", t0 + .5, t + .5)
    db.add_frames(sid, rows)
    v = analysis.e4_view(db)
    row = next(r for r in v["conditions"] if r["condition"] == f"7B-Q4 gpu ub512 @{key}")
    assert row["budget_ms"] == pytest.approx(16.7)
    assert row["phases"]["idle"]["dropped_pct"] == 0
