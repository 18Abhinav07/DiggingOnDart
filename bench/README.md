# dartbench

Reruns the performance claims in Dart's DBR-2026-05 (quantisation) and DBR-2025-01 (speculative decoding) on an
M4 Pro with 24 GB, and adds E4: does local inference make the browser drop frames? E4 decides Stage 2.

| | What it measures |
|---|---|
| E0 | llama-bench raw prefill/decode: the ceiling for everything else |
| E1 | cold TTFT, decode tok/s and memory per model/quant at 2k/4k/6k with Brave open, against Dart's limits (900 ms, 18 tok/s, 60% RAM) |
| E1b | cold prompt vs warm prefix cache: is Dart's 640 ms at 4k a cold number? |
| E2 | decode and TTFT under incompressible memory ballast: where does paging start and what does it cost? |
| E3 | speculative decoding (0.5B/1.5B drafts, draft length 4 and 16) per task and memory level |
| E4 | rAF frame intervals and long animation frames in Brave during prefill and decode |
| E4x | E4 on real pages (WebGL Aquarium, MotionMark Multiply/Arcs, BBC) plus paced-prefill chunk/gap sweeps |
| E4y | the shader page in Safari (WebKit), and CPU-only inference against the CPU-bound Multiply page, 8 vs 4 threads |
| core | the four conditions `reproduce.sh` runs: 7B at batch 512 vs 64, shader page and Aquarium |
| E5 | 12 min back-to-back: thermal sustain |
| E6 | joules per token (powermetrics) |

## Morning run

```sh
cd ~/Desktop/dart-application/bench
# 1. plug in to AC, quit every app you can (Slack, Docker, IDEs, other browsers), reboot if swap > 1 GB
sudo -v                                 # caches sudo for powermetrics (E6 energy)
uv run dartbench check                  # every line should be ok; FAIL blocks the run
uv run dartbench estimate               # expected minutes per experiment
uv run dartbench run all --quick        # 15-30 min smoke test; check the dashboard looks sane
./run_all.sh                            # the full run: `run all --energy`, logged to results/logs/
```

- **Don't touch the Mac during E4** (it runs first). Brave opens its own profile and scrolls a WebGL page;
  mouse movement or another window in front invalidates the frame data.
- The run resumes. Ctrl-C (or a crash) keeps every finished trial; rerun the same command to continue.
- `uv run dartbench dashboard` serves http://127.0.0.1:8600 while a run writes (refreshes every 5 s).
- `uv run dartbench report` writes `reports/report.md`, `trials.csv` and `frames_summary.csv`.
- `uv run dartbench export --out ../docs/dashboard.html` writes the dashboard as one static file (no server).
- `DARTBENCH_DB=results/other.db` points every command at another database; `reproduce.sh` uses `results/mine.db`.
- `--allow-missing` runs with only the models downloaded so far; `--allow-battery` skips the AC check.
  Use both only for previews: battery throttles the GPU.

## Fake mode

`DARTBENCH_FAKE=1` swaps llama-server for a simulator and Brave for a synthetic frame stream, writing to
`results/fake.db`. `DARTBENCH_FAKE=1 uv run dartbench run all --quick` exercises the whole pipeline in about 2 min.
`uv run pytest` runs the tests.

## Things the harness learned the hard way

- llama.cpp 0.7 defaults `--spec-type` to `none`: `-md` loads a draft model and never uses it. The harness passes
  `--spec-type draft-simple`.
- Draft length matters more than the draft model: on one battery smoke test, max 4 drafted tokens gave 1.10x and
  max 16 gave 0.42x. E3 measures both.
- Memory is the process's physical footprint (what Activity Monitor shows), not RSS: Metal buffers are not in RSS.
