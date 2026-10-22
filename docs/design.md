# Stage 1 design: local inference on an M4 Pro, measured against Dart's published limits

## Why
Dart's DBR-2026-05 (quantisation) and DBR-2025-01 (speculative decoding) report limits for on-device
agents measured on four machines. Neither paper measures what the browser feels like while the model
runs. Stage 1 reruns the performance half of both papers on a fifth machine (M4 Pro, 24 GB) and adds
that missing measurement. The frame-time result (E4) decides Stage 2.

## Machine and stack
- Apple M4 Pro (8P + 4E CPU, 16-core GPU), 24 GB unified memory, macOS 27.0, on AC power.
- llama.cpp 0.7.0 (Homebrew, Metal). Dart used b4021, so absolute numbers are not like-for-like.
- Qwen 2.5 Instruct GGUF (bartowski builds). One family so drafts share a tokenizer with targets.
- Brave (Chromium-based) open with five fixed tabs, as in the papers' "browser open, five tabs".

## Experiments
| ID | Question | Design |
|----|----------|--------|
| E1 | Which configs pass Dart's limits: TTFT < 900 ms, > 18 tok/s, memory < 60% RAM? | 7B at Q2_K..Q8_0, 14B at Q4_K_M/Q5_K_M, 3B Q4_K_M; prompts of 2k/4k/6k tokens; 40 runs at 4k, 10 at 2k/6k; medians + IQR |
| E1b | How was a 640 ms TTFT at 4k measured? | Same prompts with a warm prefix cache (only a short suffix is new) vs cold |
| E2 | Where does paging start on 24 GB, and what does it cost? | Incompressible memory ballast swept upward with 7B and 14B Q4_K_M |
| E3 | Does the 60% speculative-decoding rule hold on a fifth machine? | 7B Q4_K_M target, 0.5B/1.5B drafts vs none, summarise and extract tasks, ballast sweep |
| E4 | Does local inference make the browser drop frames? | Frame-timing page (WebGL + auto-scroll) in Brave while the model runs prompt processing and generation |

## Decision rule for Stage 2 (fixed before E4 runs)
If inference pushes p95 frame time past the display's frame budget, or the dropped-frame share
goes from about 1% idle to more than 5%, Stage 2 is the frame-aware scheduler. Otherwise Stage 2 is the
capability gate, and "no stutter on M4 Pro" is reported as a finding.

### Amendment after the first E4 run (disclosed, not hidden)
The rule as written read one condition: 7B Q4_K_M at the default ubatch 512, on the light page. That
condition was smooth (0% dropped in prefill) and the automatic verdict said "gate". The same model on the
heavy page dropped 64% of frames in prefill. A rule that ignores the page users are on is the wrong rule,
so it was amended after seeing the data: it now applies to the default setting on every page that ran
(light, heavy, and the third-party pages below) and the worst page decides. The original verdict is
still printed in the report next to the amended one.

### E4 follow-up (E4x)
Two questions the first run left open, run as experiment `e4x` and stored as E4 so the views merge:
1. Do the mitigations that exist without touching the browser (smaller ubatch, paced prefill with gaps
   between chunks, CPU-only) fix the heavy page, and at what TTFT cost?
2. Is the stutter an artefact of our own shader page? Three third-party benchmark pages, each at the
   heaviest setting that still idles at 120 fps with no model loaded, plus BBC News:
   WebGL Aquarium (20,000 fish), MotionMark 1.3.1 Multiply (complexity 2000) and CanvasArcs
   (complexity 10000) in fixed-complexity mode. Third-party pages can't post to the local collector, so
   the same frame recorder is injected over the DevTools protocol and pulled once a second.

## Definitions
- TTFT: wall time from sending the request to the first streamed token. Server-reported prompt time is
  stored alongside it. Prompt cache is off unless the experiment says otherwise.
- Throughput: server-reported decode tokens/s over 256 generated tokens (EOS ignored in E1/E2).
- Memory: peak resident size of the llama-server process and peak system memory in use, sampled at
  10 Hz; swap used and pageouts before/after each trial.
- Frame budget: median frame interval measured at idle. A frame is dropped if its interval exceeds 1.5x
  the budget.

## Known limits
- Accuracy (the fourth limit) is not measured: it needs Dart's 640-item set.
- FP16 7B and 14B Q8_0 are skipped on download bandwidth; the ballast sweep covers paging instead.
- Brave stands in for Dart. requestAnimationFrame timing is a proxy for compositor timing.
- One machine, one runtime, one model family.

## Dashboard
A local dashboard (Streamlit, reading the same SQLite file) shows every session and trial, per-config
medians and spreads, trial-by-trial drift, memory timelines, cross-session comparisons and records.
