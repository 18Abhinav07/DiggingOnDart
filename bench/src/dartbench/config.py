"""Paths, model registry, Dart's published limits, and the experiment matrix."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../bench
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
LOGS_DIR = RESULTS_DIR / "logs"
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = Path(os.environ.get("DARTBENCH_MODELS", Path.home() / "llm-models"))

FAKE = os.environ.get("DARTBENCH_FAKE") == "1"
DB_PATH = Path(os.environ.get("DARTBENCH_DB", RESULTS_DIR / ("fake.db" if FAKE else "bench.db")))

LLAMA_SERVER = os.environ.get("DARTBENCH_LLAMA_SERVER", "llama-server")
LLAMA_BENCH = os.environ.get("DARTBENCH_LLAMA_BENCH", "llama-bench")
SERVER_PORT = 8089
FRAMES_PORT = 8765
DASHBOARD_PORT = 8600

BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
BRAVE_PROFILE = ROOT / ".brave-profile"
# The "browser open with five representative tabs" condition from DBR-2026-05 and DBR-2025-01.
TABS = [
    "https://en.wikipedia.org/wiki/Web_browser",
    "https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame",
    "https://github.com/ggml-org/llama.cpp",
    "https://news.ycombinator.com/",
    "https://www.bbc.com/news",
]


@dataclass(frozen=True)
class Model:
    key: str
    file: str
    size_b: float
    quant: str
    family: str = "qwen2.5"

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.file

    @property
    def available(self) -> bool:
        return FAKE or self.path.exists()


def _m(size: str, quant: str) -> Model:
    return Model(f"{size}-{quant}", f"Qwen2.5-{size}-Instruct-{quant}.gguf", float(size[:-1]), quant)


MODELS: dict[str, Model] = {m.key: m for m in [
    _m("0.5B", "Q8_0"), _m("1.5B", "Q8_0"), _m("3B", "Q4_K_M"),
    _m("7B", "Q2_K"), _m("7B", "Q3_K_M"), _m("7B", "Q4_K_M"), _m("7B", "Q5_K_M"), _m("7B", "Q8_0"),
    _m("14B", "Q4_K_M"), _m("14B", "Q5_K_M"),
]}

# DBR-2026-05's four viability limits. Accuracy (within 5 points of FP16) needs Dart's 640-item set
# and is not measured here.
LIMITS = {"ttft_ms": 900.0, "gen_tps": 18.0, "mem_frac": 0.60}

# Figures quoted from Dart's pages, used only to label comparisons in the report.
DART_CLAIMS = {
    "ttft_9b_q4_4k_ms": 640.0,
    "ttft_14b_q4_4k_ms": 1490.0,
    "swap_penalty_x": 2.3,
    "spec_best_x": 2.1,
    "spec_blended_x": 1.6,
    "spec_accept_summarise": 0.71,
    "spec_accept_extract": 0.34,
    "spec_mem_threshold": 0.60,
}

# ---------------------------------------------------------------- experiment matrix

E0_MODELS = ["3B-Q4_K_M", "7B-Q2_K", "7B-Q3_K_M", "7B-Q4_K_M", "7B-Q5_K_M", "7B-Q8_0", "14B-Q4_K_M", "14B-Q5_K_M"]
E1_MODELS = E0_MODELS
E1_CTX_RUNS = {4000: 40, 2000: 10, 6000: 10}  # 40 runs at the paper's headline context
E1_GEN_TOKENS = 256
E1B_MODELS = ["3B-Q4_K_M", "7B-Q4_K_M", "14B-Q4_K_M"]
E1B_RUNS = 10
E1B_CTX = 4000
E1B_GEN_TOKENS = 64
E2_MODELS = ["7B-Q4_K_M", "14B-Q4_K_M"]
E2_BALLAST_GB = [0, 8, 14, 18]   # cut from 7 levels: enough to place the knee for the gate
E2_RUNS = 5
E2_CTX = 4000
E2_GEN_TOKENS = 128
E2_MAX_TOTAL_GB = 26.0   # ballast + model file; beyond this the Mac itself becomes unusable
E2_TRIAL_DEADLINE_S = 420
E3_TARGET = "7B-Q4_K_M"
E3_DRAFTS = [None, "0.5B-Q8_0", "1.5B-Q8_0"]
# max drafted tokens per step. A smoke test on battery (7B-Q4 + 0.5B, one run each) gave
# n2 0.89x, n4 1.10x, n8 0.65x, n16 0.42x vs no draft: draft length decides whether speculation pays
E3_DRAFT_MAX = [4, 16]
E3_TASKS = ["summarise", "extract"]
E3_BALLAST_GB = [0, 8, 12, 15]
E3_RUNS = 5
E3_CTX = 2000
E4_IDLE_S = 30
E4_RUNS = 5
E4_GAP_S = 4
E4_CTX = 4000
E4_GEN_TOKENS = 256
# (label, model, ngl, ubatch, page_load)
E4_CONDITIONS = [
    ("3B-Q4 gpu ub512", "3B-Q4_K_M", 99, 512, "light"),
    ("7B-Q4 gpu ub512", "7B-Q4_K_M", 99, 512, "light"),
    ("14B-Q4 gpu ub512", "14B-Q4_K_M", 99, 512, "light"),
    ("7B-Q4 cpu-only", "7B-Q4_K_M", 0, 512, "light"),
    ("7B-Q4 gpu ub128", "7B-Q4_K_M", 99, 128, "light"),
    ("7B-Q4 gpu ub2048", "7B-Q4_K_M", 99, 2048, "light"),
    ("7B-Q4 gpu ub512 heavy-page", "7B-Q4_K_M", 99, 512, "heavy"),
    # Stage 2 design inputs. ubatch is the size of one GPU submission inside llama.cpp: how small does it
    # have to be before a frame fits between submissions, and what does that cost in prefill speed?
    ("7B-Q4 gpu ub32", "7B-Q4_K_M", 99, 32, "light"),
    ("7B-Q4 gpu ub64", "7B-Q4_K_M", 99, 64, "light"),
    ("7B-Q4 gpu ub256", "7B-Q4_K_M", 99, 256, "light"),
    ("7B-Q4 gpu ub1024", "7B-Q4_K_M", 99, 1024, "light"),
    # userland paced prefill (chunk tokens, gap ms): the scheduler without touching llama.cpp. Each chunk is
    # its own request extending the cached prefix, with a gap the compositor can use
    ("7B-Q4 paced c256 g16", "7B-Q4_K_M", 99, 512, "light", (256, 16)),
    ("7B-Q4 paced c128 g16", "7B-Q4_K_M", 99, 512, "light", (128, 16)),
    ("7B-Q4 paced c64 g16", "7B-Q4_K_M", 99, 512, "light", (64, 16)),
    ("7B-Q4 paced c128 g0", "7B-Q4_K_M", 99, 512, "light", (128, 0)),
    ("7B-Q4 paced c128 g50", "7B-Q4_K_M", 99, 512, "light", (128, 50)),
]
E4_PRIMARY = "7B-Q4 gpu ub512"  # the condition the Stage 2 decision rule reads

# Follow-up after the first E4: the heavy page dropped 64% of frames in prefill while the light page dropped none,
# so the mitigations are rerun where the problem is, and on third-party pages instead of only our own.
MM = "https://browserbench.org/MotionMark1.3.1/developer.html?suite-name=MotionMark&controller=fixed&test-interval=1800&system-frame-rate=120&frame-rate=120"
E4_REAL_PAGES = {  # load key -> URL; complexities calibrated to hold 120 fps idle on the M4 Pro
    "aquarium": "https://webglsamples.org/aquarium/aquarium.html?numFish=10000",
    "mm-multiply": MM + "&test-name=Multiply&complexity=1500",
    "mm-arcs": MM + "&test-name=CanvasArcs&complexity=1500",
    "bbc": "https://www.bbc.com/news",
}
E4_DEBUG_PORT = 9223
E4X_CONDITIONS = [
    ("7B-Q4 gpu ub64 heavy-page", "7B-Q4_K_M", 99, 64, "heavy"),
    ("7B-Q4 gpu ub128 heavy-page", "7B-Q4_K_M", 99, 128, "heavy"),
    ("7B-Q4 paced c128 g16 heavy-page", "7B-Q4_K_M", 99, 512, "heavy", (128, 16)),
    ("7B-Q4 paced c64 g16 heavy-page", "7B-Q4_K_M", 99, 512, "heavy", (64, 16)),
    ("7B-Q4 paced c64 g50 heavy-page", "7B-Q4_K_M", 99, 512, "heavy", (64, 50)),
    ("7B-Q4 paced c128 g50 heavy-page", "7B-Q4_K_M", 99, 512, "heavy", (128, 50)),
    ("7B-Q4 cpu-only heavy-page", "7B-Q4_K_M", 0, 512, "heavy"),
] + [c for p in E4_REAL_PAGES for c in [
    (f"7B-Q4 gpu ub512 @{p}", "7B-Q4_K_M", 99, 512, p),
    (f"7B-Q4 gpu ub64 @{p}", "7B-Q4_K_M", 99, 64, p),
    (f"7B-Q4 paced c64 g16 @{p}", "7B-Q4_K_M", 99, 512, p, (64, 16)),
]]
E4_RUNS_OVERRIDE = {"7B-Q4 cpu-only heavy-page": 3}  # ~100 s prefill each; 3 runs show the effect
E4_LOAD = {c[0]: c[4] for c in E4_CONDITIONS + E4X_CONDITIONS}
# Amended after the first E4 (recorded in docs/design.md): the rule reads the default setting on every page,
# not only the light one, because users browse heavy pages
E4_PRIMARIES = [E4_PRIMARY, "7B-Q4 gpu ub512 heavy-page"] + [f"7B-Q4 gpu ub512 @{p}" for p in E4_REAL_PAGES]
E5_MODEL = "7B-Q4_K_M"
E5_MINUTES = 12
E5_CTX = 2000
E6_MODELS = ["3B-Q4_K_M", "7B-Q2_K", "7B-Q4_K_M", "7B-Q8_0", "14B-Q4_K_M"]
E6_RUNS = 5
E6_CTX = 4000

# Stage 2 decision rule, fixed before E4 runs (see docs/design.md).
DROP_FACTOR = 1.5          # a frame is dropped if its interval exceeds 1.5x the idle median
RULE_DROPPED_PCT = 5.0     # inference phase dropped share above this ...
RULE_IDLE_MAX_PCT = 2.0    # ... while idle stays at or below this
