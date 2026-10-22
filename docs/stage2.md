# Stage 2: ship the fix, then build only as much scheduler as small Macs need

Stage 1 found a cheap fix that works on this machine, and evidence that it stops working as the GPU gets slower
relative to the model. The plan is in that order: ship the fix, test the small-Mac prediction, and add machinery
only when a measurement says the simpler step failed.

## The problem, measured
On an M4 Pro at 120 Hz, prefilling a 4k-token page with llama.cpp's default batch (ubatch 512) makes a
GPU-heavy page drop most of its frames for the whole prefill: 5 to 25 seconds depending on the model.
Every page below idles at 0% dropped with no model loaded. Frames are requestAnimationFrame intervals, a proxy
for the page's own rendering rather than compositor presentation.

| Page | 7B prefill, ubatch 512 | 7B prefill, ubatch 64 | TTFT cost of ubatch 64 |
|---|---:|---:|---:|
| Our shader page (raymarch + scroll) | 63.7% dropped, 41 fps | 1.3% | +11% |
| WebGL Aquarium, 20,000 fish | 82.7%, 39 fps | 0.0% | +9% |
| MotionMark CanvasArcs, complexity 10,000 | 30.4%, 81 fps | 0.0% | +4% |
| BBC News (scrolling) | 0.0% | 0.0% | +5.5%, for nothing |
| Light page (WebGL + scroll) | 0.0% | 0.0% | +4.5%, for nothing |

What shapes the design:
- **It is GPU contention.** CPU-only prefill keeps the heavy page at 0.1% dropped but takes 104 s.
  Decode never drops frames on GPU-heavy pages.
- **Submission size matters, pauses don't.** 128-token chunks with 16 or 50 ms gaps still drop 34–38%.
  64-token chunks drop 1.8% with no gap and 0% with a 16 ms gap.
- **The safe size moves with the model.** On the heavy page, ubatch 64 fixes 3B (69% to 0%) and 7B (64% to
  1.3%) but not 14B, which still drops 31% at ubatch 64 (72% at 512).
- **Safari (WebKit, 60 Hz) shows the same pattern.** 7B prefill drops 14.5% on the shader page at ubatch 512
  (p95 32 ms against a 17 ms budget), decode 0%, and ubatch 64 brings it to 0% for +6% TTFT.
- **CPU is a second resource.** On MotionMark Multiply (CPU-bound), GPU inference drops 5.8% / 9.5%
  (prefill / decode). CPU-only inference drops 22.4% / 30.1% with 8 threads and 8.2% / 18.1% with 4, for
  +46% TTFT. "Fall back to CPU" isn't a safe mitigation.

## Step 1. The immediate fix: prefill in 64-token batches
Set `n_ubatch = 64` for 3B and 7B, and 32 or less for 14B. On the M4 Pro this takes every GPU-heavy page to
about 0% dropped, for +9–11% TTFT on heavy pages and about +5% on pages that were already smooth. Decode is left
alone. This harness is the regression test.

## Step 2. The thesis: 64 probably fails on a base M1 or M2
Batch 64 works here because each GPU kernel finishes quickly enough for the page to get the GPU back in time.
A 7B batch-64 step takes about 200 ms in total (4,000 tokens in 12.8 s, 64 per step), and the page still stays
smooth. So the total length of a step isn't what matters; the length of each kernel inside it is, and that
scales with tokens per batch times model width, divided by GPU speed.

14B prefills 2.07× slower than 7B on this machine (23.7 s vs 11.4 s cold at 4k). That's the same ratio as an M4
Pro to a 10-core base M2/M3 in llama.cpp's Apple Silicon numbers (7B Q4_0 pp512, discussion #4167). So **14B on
the M4 Pro stands in for 7B on a base M2 or M3**, and at batch 64 it still drops 31%.

This is a prediction, not a measurement. Two effects pull in opposite directions: base Airs have 60 Hz displays,
which doubles the frame budget, and a smaller GPU also renders the page more slowly, leaving less headroom.
`./reproduce.sh` on a real Air settles it in 15 minutes.

Small fixed values cost much more on slow machines: batch 32 already costs 7B +17% TTFT here, and a cold 4k
prefill on an M1 is 35–40 s before any penalty. A constant small enough for the slowest machine taxes every
other machine all the time.

## Step 3. A per-device, per-model table, plus a mode switch
- **Table.** The largest safe batch for each chip class and model, measured by this harness. On this M4 Pro:
  64 for 3B and 7B, ≤32 for 14B. For unknown chips, time one batch at startup and divide a per-kernel time
  budget by the measured per-token cost.
- **Mode switch.** Small batch only while a GPU-heavy page is in front; the full batch (up to 1,024, since
  2,048 drops 2.9% even on the light page) when the window is hidden or the page is light. BBC News and the
  light page stop paying ~5% for nothing.
- **The knob.** In-process, the caller hands `llama_decode` k tokens per call, so k can change every step
  without reloading the model. llama-server fixes ubatch at load. The userland version (one HTTP request per
  chunk, reusing the cached prefix) costs +23% at 64 tokens against ubatch 64's +11%. Whether in-process
  chunking closes that gap is the first measurement.

## Step 4. An adaptive controller, only if needed
If a table entry still drops frames on real pages, add feedback: read missed deadlines for the frontmost tab
in 250 ms windows, halve k when drops rise above the page's idle rate, and grow it back additively while frames
stay clean. The table gives the floor and ceiling. In the product the signal comes from the compositor's
presentation feedback; in the prototype it's the rAF recorder this benchmark already injects.

**Stop rule:** if the table alone is safe on a base M1 for less than 10% extra TTFT, ship the table and don't
build the controller.

## Step 5. Everything else that competes with the frame
- **Speculative decoding.** Verify batches of 4–16 tokens are well under the safe size, so I predict they're
  safe. Worth checking, because Dart's agenda lists speculative decoding that yields to the compositor as open.
- **Background embedding** gets the same frame signal. DBT-2026-09 caps it at 12% of a core.
- **A CPU thread budget** for anything on CPU cores, instead of llama.cpp's default of every performance core.
- **To compare against:** prefill on the Neural Engine, which doesn't share the GPU, if model and tooling allow.

## Success criteria (fixed before building)
- **Smooth.** On every GPU-heavy page, prefill drops at most 2 points more than idle, for 3B, 7B and 14B, on
  the M4 Pro and on a base M-series Air.
- **Free.** On light pages, TTFT within 2% of ubatch 512.
- **Cheap.** On heavy pages, TTFT no worse than the smallest fixed ubatch that's smooth for that model and machine.
- **Fast.** When a heavy page comes to the front mid-prefill, drops recover within 500 ms.
- **Honest.** If in-process chunking costs as much as the HTTP version, the report says so, and the design
  switches between two or three preloaded contexts instead.

## Deliverables
1. The ubatch-64 change, with this harness as its regression test.
2. The device/model table, measured on at least two Macs, one of them a base M-series Air.
3. `dartsched`, a small C++ layer over llama.cpp: chunked prefill through `llama_decode`, the mode switch, a
   pluggable frame signal, and the controller only if step 4 is triggered.
4. A frame-signal prototype on the rAF recorder. The production hook belongs in Dart's compositor, and where it
   goes is Dart's call.
5. A report comparing ubatch 512, fixed 64, the table and (if built) the controller.

## Also from Stage 1, for the capability gate
- **Cold vs cached TTFT.** 7B at 4k is 11.4 s cold and 79 ms with the page already in the KV cache (3B:
  5.1 s vs 45 ms; 14B: 23.7 s vs 159 ms). Dart's 640 ms figure only fits the cached case. No model tested
  gets a cold 4k prefill under 900 ms on this machine.
- **Memory.** On 24 GB, 18 GB of other memory slows 7B decode by 6%. Swapping starts between 8 and 14 GB
  of ballast. No 2.3× cliff appeared.
- **Quantisation.** Q8_0 prefills faster than Q2_K (410 vs 374 tok/s at pp512); low-bit quants buy memory,
  not speed, on this GPU.

## Limits
One machine. Brave stands in for Dart; Safari (60 Hz) is the second engine. Qwen 2.5 on llama.cpp 0.7.0. rAF
intervals are a proxy for compositor frames. The base-M2 numbers are a prediction from the 14B proxy, not a
measurement. The decision rule was amended after the first E4 run (see design.md); the original verdict ("gate",
from the light page alone) is still printed in the report. One 4-minute condition ran while something else slowed
the whole machine (decode at half speed); it is kept, labelled "disturbed", and was rerun.
