# Stage 2: a frame-aware prefill scheduler

## The problem, measured
On an M4 Pro at 120 Hz, prefilling a 4k-token page with llama.cpp's default batch (ubatch 512) makes a
GPU-heavy page drop most of its frames for the whole prefill: 5 to 25 seconds depending on the model.
Every page below idles at 0% dropped with no model loaded.

| Page | 7B prefill, ubatch 512 | 7B prefill, ubatch 64 | TTFT cost of ubatch 64 |
|---|---:|---:|---:|
| Our shader page (raymarch + scroll) | 63.7% dropped, 41 fps | 1.3% | +11% |
| WebGL Aquarium, 20,000 fish | 82.7%, 39 fps | 0.0% | +9% |
| MotionMark CanvasArcs, complexity 10,000 | 30.4%, 81 fps | 0.0% | +4% |
| BBC News (scrolling) | 0.0% | 0.0% | +5.5%, for nothing |
| Light page (WebGL + scroll) | 0.0% | 0.0% | +4.5%, for nothing |

**Safari (WebKit, 60 Hz) shows the same pattern.** On the shader page at ubatch 512, 7B prefill drops 14.5%
(p95 32 ms against a 17 ms budget). Decode drops 0%. At ubatch 64 it drops 0% for +6% TTFT. The light page
stays at 0.1%. The number is smaller than Brave's partly because a 60 Hz display has half as many deadlines
to miss.

**CPU-bound pages are a second, separate resource.** MotionMark Multiply (CPU-bound DOM) drops 3–4% at idle.
With GPU inference it drops 5.8% in prefill and 9.5% in decode. Moving inference to the CPU makes it worse:

| 7B on Multiply | Prefill drops | Decode drops | TTFT |
|---|---:|---:|---:|
| GPU (Metal) | 5.8% | 9.5% | 11.1 s |
| CPU-only, 8 threads (llama.cpp default) | 22.4% | 30.1% | 127 s |
| CPU-only, 4 threads | 8.2% | 18.1% | 186 s |

CPU inference competes with the main thread in both phases. The GPU's prefill problem doesn't have that shape.
Capping threads helps but doesn't fix it, and it costs 46% TTFT. This matches DBT-2026-09's cap on
background embedding (12% of a core). So the scheduler needs a CPU budget alongside the GPU one, and
"fall back to CPU" isn't a safe mitigation.

Three more facts shape the design:
- **It is GPU contention.** CPU-only prefill keeps the heavy page at 0.1% dropped but takes 104 s.
  Decode never drops frames on GPU-heavy pages.
- **Submission size matters, pauses don't.** 128-token chunks with 16 or 50 ms gaps still drop 34–38%.
  64-token chunks drop 1.8% with no gap and 0% with a 16 ms gap.
- **The safe size moves with the model.** On the heavy page, ubatch 64 fixes 3B (69% to 0%) and 7B (64% to
  1.3%) but not 14B, which still drops 31% at ubatch 64 (72% at 512).

## What Stage 2 builds
A scheduler between the browser and the local model runtime that decides how many tokens each prefill
step submits, from the browser's own frame timing.

1. **Knob: tokens per decode call.** Embedded in-process, the caller hands llama.cpp k tokens per
   `llama_decode`, so k can change every step without reloading the model. In llama-server, ubatch is fixed
   when the model loads. Our userland version (each chunk a separate HTTP request reusing the cached
   prefix) works but costs +23% at 64 tokens against ubatch 64's +11%. Most of that gap should be request
   overhead, which in-process chunking removes. That is the first thing Stage 2 measures.
2. **Signal: missed frame deadlines** for the frontmost visible tab. In the product this comes from the
   compositor's presentation feedback. In the prototype it is the rAF recorder this benchmark already
   injects over DevTools, read in 250 ms windows.
3. **Controller: AIMD on k.** Start at the ceiling when nothing on screen animates. Halve k when a window
   shows drops above the page's idle rate. Grow k additively while frames stay clean. Floor and ceiling
   come from a per-device, per-model table that this harness measures (on this M4 Pro: 64 for 3B and 7B,
   below 64 for 14B; ceiling 1024, since ubatch 2048 makes even the light page drop 2.9%).
4. **Policy.** Only the frontmost visible tab counts. Decode runs untouched on the GPU. When the window
   is hidden, prefill runs at the ceiling. Work that has to run on CPU cores (embedding, CPU fallback) gets
   a thread budget from the same signal. It never takes the llama.cpp default of every performance core.

## The baseline it has to beat
A fixed small ubatch is the obvious alternative, and on this machine 64 is a strong one for 7B. The
scheduler earns its place in two ways the data shows:
- **No fixed value works for every model.** 64 is safe for 7B and not for 14B. A value safe for 14B
  (32 or less) costs 7B about +17% TTFT on every page (ubatch 32 on the light page: 13.3 s vs 11.4 s).
- **Most pages don't need it.** On BBC News and the light page the default is already smooth, and a fixed
  64 costs about 5% TTFT there for nothing. The scheduler pays only while a GPU-heavy page is in front.

## Deliverables
1. `dartsched`, a small C++ library over llama.cpp: chunked prefill through `llama_decode`, the AIMD
   controller, a pluggable frame signal, and the device/model table.
2. A frame-signal prototype that reads frame timing from the visible tab and feeds the controller over a
   local socket. The production hook belongs in Dart's compositor, and where it goes is Dart's call.
3. This benchmark harness as the regression suite: light, heavy, Aquarium, MotionMark and BBC pages, the
   decision rule, and a quick mode for CI.
4. A report comparing static 512, static 64 and the scheduler on two or more Macs, including one base
   M-series machine with fewer GPU cores.

## Success criteria (fixed before building)
- On every GPU-heavy page, prefill drops at most 2 points more than idle, for 3B, 7B and 14B.
- On light pages, TTFT within 2% of ubatch 512.
- On heavy pages, TTFT no worse than the smallest fixed ubatch that is smooth for that model.
- When a heavy page comes to the front mid-prefill, the controller brings drops back under the line within
  500 ms.
- If in-process chunking turns out to cost as much as the HTTP version, the report says so and the design
  falls back to a reload-free choice among two or three preloaded contexts.

## Also from Stage 1, for the capability gate
- **Cold vs cached TTFT.** 7B at 4k is 11.4 s cold and 79 ms with the page already in the KV cache (3B:
  5.1 s vs 45 ms; 14B: 23.7 s vs 159 ms). Dart's 640 ms figure only fits the cached case. No model tested
  gets a cold 4k prefill under 900 ms on this machine.
- **Memory.** On 24 GB, 18 GB of other memory slows 7B decode by 6%. Swapping starts between 8 and 14 GB
  of ballast. No 2.3× cliff appeared.
- **Quantisation.** Q8_0 prefills faster than Q2_K (410 vs 374 tok/s at pp512); low-bit quants buy memory,
  not speed, on this GPU.

## Limits
One machine. Brave stands in for Dart; Safari (60 Hz) is the second engine. Qwen 2.5 on llama.cpp 0.7.0. rAF intervals are a proxy for
compositor frames. The Stage 2 rule was amended after the first E4 run (see design.md); the original
verdict ("gate", from the light page alone) is still printed in the report. One 4-minute condition ran
while something else slowed the whole machine (decode at half speed); it is kept, labelled "disturbed",
and was rerun.
