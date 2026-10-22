# Local inference vs. the compositor: a Dart Browser replication

Dart's DBR-2026-05 warns that "a model that starves the compositor" makes the browser unusable, and the research
agenda lists speculative decoding that yields to the compositor as an open problem. This repo measures that effect
on a MacBook Pro (M4 Pro, 24 GB), reruns Dart's published TTFT and memory numbers, and proposes a fix for Stage 2.

**Headline.** While a local 7B model **prefills** a 4k-token prompt, a GPU-heavy page drops **64%** of its frames
(WebGL Aquarium: **83%**). **Decode drops ~0%.** Capping llama.cpp's prefill batch at 64 tokens brings the drops
down to **1.3%** (Aquarium: 0%) and costs **+9–11% TTFT**. The contention comes from prefill's large Metal
submissions, not from token generation.

- Findings report: [`docs/index.html`](docs/index.html). Full dashboard: [`docs/dashboard.html`](docs/dashboard.html) (one static file; clone and open it, no server)
- Raw data: `bench/results/m4pro-24gb.db.gz` (SQLite; `gunzip` it to `bench/results/bench.db` to use `dartbench report` / `dashboard`)
- Full report with every table: [`bench/reports/report.md`](bench/reports/report.md)
- Stage 2 design: [`docs/stage2.md`](docs/stage2.md)
- Harness docs: [`bench/README.md`](bench/README.md)

## Run it yourself

```sh
git clone <this repo> && cd dart-application
./reproduce.sh            # 7B at batch 512 vs 64, shader page + Aquarium in Brave (~15 min)
./reproduce.sh --safari   # also Safari, and CPU-only inference against a CPU-bound page (+35 min)
./reproduce.sh --demo     # whole pipeline on simulated data, no model or GPU (~2 min)
```

You need Apple Silicon, Brave, [uv](https://docs.astral.sh/uv/), and Homebrew. The script offers to install
llama.cpp and downloads the 4.7 GB model. Keep the Mac on AC power and leave it alone while it runs. It writes to its
own database, then opens `bench/reports/dashboard-mine.html` so you can compare it with the published run.

## Stage 1: what we measured vs. what Dart says

| Dart's claim | Our measurement (M4 Pro, 24 GB) | Verdict |
|---|---|---|
| A model can "starve the compositor" (DBR-2026-05) | 7B prefill: shader page drops 63.7% (p95 48 ms frames), Aquarium 82.7%, MotionMark Arcs 30.4%. Decode: 0–0.1% | **Confirmed, and pinned to prefill** |
| Bigger models are worse | Shader page at batch 512: 3B 69%, 7B 63.7%, 14B 72.3%. At batch 64: 3B 0%, 7B 1.3%, 14B 31% | Every size starves at the default; 14B still does at 64 |
| Text pages are fine | BBC article and our light page: 0% at every setting | **Confirmed**: it's GPU-heavy pages |
| TTFT at 4k: 3B 210 ms, 9B 640 ms, 14B 1490 ms | Cold: 3B 5.1 s, 7B 11.4 s, 14B 23.7 s. Warm prefix cache: 45 / 79 / 159 ms | Dart's numbers only fit a cached prompt (or 18–24× this prefill rate) |
| Under 900 ms cold TTFT at 4k | No model passes; 3B is closest at 5.0 s | **Not reproducible** cold |
| 7–9B Q4_K_M on 16 GB | 7B Q4: 43.7 tok/s decode, 21% of RAM; Q8: 29.8 tok/s, 34% | **Confirmed**: fits easily |
| Memory pressure causes a decode cliff | 7B with 14–18 GB ballast: 1.06× slower; 14B with 8 GB: 1.15×. Swap starts at 8–14 GB | No cliff on 24 GB |
| Quantisation speeds up prefill | pp512: Q8 410 tok/s vs Q2_K 374 | Lower bits **don't** prefill faster on Metal |

How we pinned it to prefill: each trial records prefill and decode as separate windows on the same frame timeline.
CPU-only inference (`-ngl 0`) on the shader page drops 0.1%, so the GPU is the shared resource. Pacing prefill
(64-token chunks, a 16 ms gap) also gets drops to 0%.

### Follow-ups: a second engine, and the CPU side

| Condition (7B Q4, 4k prompt) | Prefill drops | Decode drops | TTFT |
|---|---|---|---|
| **Safari**, shader page, batch 512 | **14.5%** (p95 32 ms vs 17 ms budget) | 0% | 12.1 s |
| Safari, shader page, batch 64 | **0%** | 0% | 12.8 s (+6%) |
| Safari, light page, batch 512 | 0.1% | 0% | 11.5 s |
| Brave, CPU-bound MotionMark Multiply, idle baseline | 2.8–4% | — | — |
| Multiply, GPU inference | 5.8% | 9.5% | 11.1 s |
| **Multiply, CPU-only inference, 8 threads** | **22.4%** | **30.1%** | 127 s |
| Multiply, CPU-only, 4 threads | 8.2% | 18.1% | 186 s (+46%) |

- **WebKit shows the same mechanism.** Prefill drops frames and decode doesn't, and a batch of 64 fixes it. Safari
  is smaller at 14.5% vs 64% partly because Safari runs at 60 Hz, a 17 ms budget, where Brave runs at 120 Hz.
  Safari also has half as many deadlines per second to miss.
- **Moving inference to the CPU doesn't help.** On a page that's CPU-bound instead of GPU-bound, CPU inference
  starves the main thread during prefill *and* decode. Capping threads halves the drops and adds 46% to TTFT.
  DBT-2026-09's cap on background embedding (12% of a core) points the same way: the scheduler needs to watch both
  the GPU queue and CPU cores, not just the batch size.

**Run integrity.** 19 sessions, 717 trials, 0 errors, 6.2 h. Each page is judged against its own no-model baseline.
A frame counts as dropped when it takes longer than 1.5× that page's median idle frame.

### Caveats

- Dart's beta isn't downloadable, so **Brave (Chromium) stands in for Dart**. Safari is the second engine.
- One machine. DBR-2026-05 asks for slower hardware, and an M1 or M2 with 8–16 GB should be worse.
- We didn't measure speculative decoding against frame timing. Speculative decoding adds prefill-shaped verify
  batches, so Stage 2 measures it.
- E6 (energy) was skipped because powermetrics needs sudo.

## Stage 2

A **compositor-aware inference scheduler**. It reads frame deadlines from the browser, sizes each prefill
submission to fit the slack left before the next vsync, and backs off when frames start missing. A fixed 64-token
batch already shows the drops can be removed for ~10% TTFT. A scheduler can win back most of that cost on light
pages and still protect heavy ones. Problem, design and success criteria: [`docs/stage2.md`](docs/stage2.md).

---
Abhinav Pangaria · built with Claude Code
