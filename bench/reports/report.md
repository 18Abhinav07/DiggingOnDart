# Stage 1 results: local inference on an M4 Pro, against Dart's published limits

Generated 2026-10-22 22:34. Data: `bench.db`.

Machine: Apple M4 Pro, 24.0 GB, 8P+4E CPU, 16-core GPU, macOS 27.0 (26A428). llama.cpp 0.7.0 (build 11669, commit 620d2225c). Brave 155.1.97.59. Power: ac.

## Stage 2 decision

**SCHEDULER**: 7B-Q4 gpu ub512 @aquarium: prefill drops 82.7% of frames (idle 0.0%), p95 43.6 ms vs 8.3 ms budget.

Rule (fixed before E4 ran): on `7B-Q4 gpu ub512`, if prefill or decode drops more than 5% of frames, or its p95 frame interval exceeds 1.5× the idle budget, build the frame-aware scheduler. If idle itself drops more than 2%, the result is inconclusive. Otherwise build the capability gate.

Amended after the first E4 run: the light page alone read **gate**, while the heavy page dropped most of its frames, so the rule now applies to the default setting on every page that ran and the worst page decides. Per page:

- `7B-Q4 gpu ub512`: gate. inference stays smooth: worst phase prefill drops 0.0% (idle 0.0%), p95 9.2 ms vs 8.3 ms budget.
- `7B-Q4 gpu ub512 heavy-page`: scheduler. prefill drops 63.7% of frames (idle 0.0%), p95 48.2 ms vs 8.3 ms budget.
- `7B-Q4 gpu ub512 @aquarium`: scheduler. prefill drops 82.7% of frames (idle 0.0%), p95 43.6 ms vs 8.3 ms budget.
- `7B-Q4 gpu ub512 @mm-multiply`: inconclusive. idle already drops 4.0% of frames (> 2.0%); the baseline is too noisy.
- `7B-Q4 gpu ub512 @mm-arcs`: scheduler. prefill drops 30.4% of frames (idle 0.0%), p95 27.4 ms vs 8.3 ms budget.
- `7B-Q4 gpu ub512 @bbc`: gate. inference stays smooth: worst phase prefill drops 0.0% (idle 0.0%), p95 8.8 ms vs 8.3 ms budget.

## Headline numbers

- 7B-Q4_K_M at 4k tokens: cold TTFT 11239 (11192–11393) ms, decode 43.7 (43.1–44.1) tok/s.

## E1: which configurations pass Dart's limits

Limits from DBR-2026-05: TTFT < 900 ms, decode > 18 tok/s, model memory < 60% of RAM. Accuracy, the fourth limit, needs Dart's 640-item set and is not measured. Cells show the median and the interquartile range. Brave is open with five tabs throughout.

| Config | Ctx | n | TTFT ms | Prefill tok/s | Decode tok/s | Memory MB (% RAM) | TTFT | Decode | Mem | All | Drift TTFT / tps |
|---|---:|---:|---:|---:|---:|---:|:-:|:-:|:-:|:-:|---:|
| 3B-Q4_K_M | 2000 | 10 | 2391 (2382–2424) | 840 (829–843) | 82.7 (78.1–84.3) | 2460 (10%) | **fail** | pass | pass | **fail** | -1% / -3% |
| 3B-Q4_K_M | 4000 | 40 | 5021 (4988–5060) | 799 (793–804) | 80.8 (72.9–81.2) | 2310 (9%) | **fail** | pass | pass | **fail** | +1% / +4% |
| 3B-Q4_K_M | 6000 | 10 | 8151 (8139–8160) | 738 (737–739) | 77.1 (76.4–77.4) | 2468 (10%) | **fail** | pass | pass | **fail** | -0% / -1% |
| 7B-Q2_K | 2000 | 10 | 5411 (5335–5424) | 370 (369–375) | 40.5 (39.2–41.6) | 3636 (15%) | **fail** | pass | pass | **fail** | -1% / +8% |
| 7B-Q2_K | 4000 | 40 | 11492 (11455–11517) | 348 (348–350) | 36.9 (36.7–39.1) | 3523 (14%) | **fail** | pass | pass | **fail** | -1% / -9% |
| 7B-Q2_K | 6000 | 10 | 17497 (17443–17959) | 343 (334–344) | 39.0 (38.4–39.1) | 3525 (14%) | **fail** | pass | pass | **fail** | -0% / +2% |
| 7B-Q3_K_M | 2000 | 10 | 5695 (5637–5757) | 352 (348–355) | 31.7 (31.5–31.9) | 4538 (18%) | **fail** | pass | pass | **fail** | -2% / -1% |
| 7B-Q3_K_M | 4000 | 40 | 11687 (11553–11812) | 343 (339–347) | 30.7 (30.5–30.9) | 4281 (17%) | **fail** | pass | pass | **fail** | +1% / +0% |
| 7B-Q3_K_M | 6000 | 10 | 18221 (18185–18306) | 330 (328–330) | 30.5 (30.3–30.5) | 4543 (18%) | **fail** | pass | pass | **fail** | +0% / -1% |
| 7B-Q4_K_M | 2000 | 10 | 5433 (5392–5496) | 369 (364–372) | 45.1 (44.7–45.5) | 5373 (22%) | **fail** | pass | pass | **fail** | -1% / -1% |
| 7B-Q4_K_M | 4000 | 40 | 11239 (11192–11393) | 356 (351–358) | 43.7 (43.1–44.1) | 5112 (21%) | **fail** | pass | pass | **fail** | -2% / -1% |
| 7B-Q4_K_M | 6000 | 10 | 17580 (17511–17658) | 342 (340–343) | 41.0 (40.5–42.1) | 5378 (22%) | **fail** | pass | pass | **fail** | -0% / -4% |
| 7B-Q8_0 | 2000 | 10 | 5071 (5064–5154) | 395 (389–396) | 31.1 (31.0–31.2) | 8634 (35%) | **fail** | pass | pass | **fail** | -3% / +0% |
| 7B-Q8_0 | 4000 | 40 | 10750 (10666–11048) | 373 (362–376) | 29.8 (29.3–30.2) | 8400 (34%) | **fail** | pass | pass | **fail** | -1% / +0% |
| 7B-Q8_0 | 6000 | 10 | 16834 (16788–16881) | 357 (356–358) | 29.6 (29.5–29.7) | 8638 (35%) | **fail** | pass | pass | **fail** | +0% / -0% |

Drift compares the last third of a configuration's runs with the first third. A large positive TTFT drift, or a negative decode drift, points to thermal throttling.

At 4k tokens, these pass all three measured limits on this machine: none.

## E0: raw llama-bench throughput (reference, no server, no browser)

| Model | pp512 | pp2048 | pp4096 | tg128 | Implied cold TTFT at 4k (ms) |
|---|---:|---:|---:|---:|---:|
| 3B-Q4_K_M | 909 | 843 | 769 | 92.6 | 5201 |
| 7B-Q2_K | 374 | 354 | 338 | 35.9 | 11835 |
| 7B-Q3_K_M | 378 | 370 | 352 | 32.9 | 11356 |
| 7B-Q4_K_M~battery | 253 | 273 | 258 | 27.5 | 15494 |
| 7B-Q4_K_M | 400 | 384 | 367 | 47.0 | 10901 |
| 7B-Q8_0 | 410 | 378 | 352 | 30.7 | 11377 |

The implied TTFT is 4000 tokens divided by the raw prefill rate. It is a floor that no cold request through the server can beat on this machine.

## E1b: cold prompt vs warm prefix cache, same 4k page

| Model | Cold TTFT ms | Warm TTFT ms | Tokens actually processed (cold / warm) | Speed-up |
|---|---:|---:|---:|---:|
| 3B-Q4_K_M | 5144 (5084–5162) | 45 (45–46) | 3997 / 13 | 113.5× |
| 7B-Q4_K_M | 11438 (11369–11463) | 79 (78–79) | 3997 / 13 | 145.6× |
| 14B-Q4_K_M | 23705 (23235–24071) | 159 (156–169) | 3997 / 13 | 149.2× |

When the page is already in the KV cache, only the new question is processed. A TTFT figure is only meaningful once it says which of the two it measures.

## E2: memory pressure and paging

Incompressible ballast (a stand-in for other apps and tabs) is allocated before the model loads. Dart reports a 2.3× penalty once the model pages.

**7B-Q4_K_M**: knee (decode > 1.2× slower) at none observed of ballast.

| Ballast GB | n | TTFT ms | Decode tok/s | Decode penalty | TTFT penalty | Swap Δ MB | Swapouts | Pressure |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 11292 (11171–11362) | 43.9 (43.8–44.1) | 1.00× | 1.00× | 0 | 0 | 1 |
| 8 | 5 | 10867 (10755–10930) | 44.4 (44.3–44.4) | 0.99× | 0.96× | 0 | 0 | 1 |
| 14 | 5 | 11961 (11499–12093) | 41.4 (41.0–42.6) | 1.06× | 1.06× | 325 | 1172088 | 2 |
| 18 | 5 | 12012 (11540–12323) | 41.5 (41.3–42.8) | 1.06× | 1.06× | 125 | 1331937 | 4 |

**14B-Q4_K_M**: knee (decode > 1.2× slower) at none observed of ballast.

| Ballast GB | n | TTFT ms | Decode tok/s | Decode penalty | TTFT penalty | Swap Δ MB | Swapouts | Pressure |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 24251 (24126–24715) | 22.4 (22.0–22.6) | 1.00× | 1.00× | -96 | 33028 | 2 |
| 8 | 5 | 26548 (25711–26680) | 19.5 (19.1–19.6) | 1.15× | 1.09× | -15 | 2152064 | 2 |
| 14 | 5 | 22659 (22507–22664) | 22.0 (21.8–22.2) | 1.02× | 0.93× | -76 | 2121817 | 2 |

## E4: what the browser feels while the model runs

Brave shows a frame-timing page (WebGL plus continuous scroll) in front, with the five tabs open behind it. A frame counts as dropped when its interval exceeds 1.5× the no-model idle median (the budget). LoAF counts long-animation-frame entries (> 50 ms) per second.

| Condition | Phase | Frames | p50 ms | p95 ms | p99 ms | Max ms | Dropped | Frames lost | LoAF/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no-model light | idle | 3552 | 8.30 | 9.20 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| no-model heavy | idle | 14208 | 8.30 | 9.50 | 10.30 | 16 | 0.0% | 0.0% | 0.00 |
| no-model aquarium | idle | 3493 | 8.30 | 9.20 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| no-model mm-multiply | idle | 6840 | 8.33 | 10.31 | 16.67 | 192 | 3.1% | 3.3% | 0.02 |
| no-model mm-arcs | idle | 3483 | 8.33 | 9.25 | 9.32 | 17 | 0.0% | 0.0% | 0.00 |
| no-model bbc | idle | 3490 | 8.30 | 9.30 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| no-model safari-heavy | idle | 1797 | 17.00 | 17.00 | 18.00 | 21 | 0.0% | 0.0% | 0.00 |
| no-model safari-light | idle | 1762 | 17.00 | 17.00 | 18.00 | 21 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 | idle | 3600 | 8.30 | 9.20 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 | prefill | 3140 | 8.30 | 8.50 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 | decode | 1966 | 8.30 | 9.00 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 | gap | 2389 | 8.30 | 9.30 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 | idle | 3600 | 8.30 | 9.30 | 9.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 | prefill | 6845 | 8.30 | 9.20 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 | decode | 3642 | 8.30 | 9.40 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 | gap | 2295 | 8.30 | 10.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 | idle | 3601 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 | prefill | 14270 | 8.30 | 9.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 | decode | 7098 | 8.30 | 9.22 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 | gap | 2342 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only | idle | 3601 | 8.30 | 9.20 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only | prefill | 59903 | 8.30 | 8.40 | 9.90 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only | decode | 7100 | 8.30 | 8.40 | 8.50 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only | gap | 2390 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 | idle | 3602 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 | prefill | 6937 | 8.30 | 8.60 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 | decode | 3664 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 | gap | 2350 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub2048 | idle | 3601 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub2048 | prefill | 6580 | 8.30 | 10.20 | 24.52 | 67 | 2.9% | 5.0% | 0.07 |
| 7B-Q4 gpu ub2048 | decode | 3664 | 8.30 | 9.40 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub2048 | gap | 2295 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 heavy-page | idle | 3601 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 heavy-page | prefill | 2356 | 20.60 | 48.20 | 51.35 | 56 | 63.7% | 66.6% | 0.26 |
| 7B-Q4 gpu ub512 heavy-page | decode | 4146 | 8.30 | 9.50 | 10.30 | 11 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 heavy-page | gap | 2399 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub32 | idle | 3601 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub32 | prefill | 8007 | 8.30 | 8.60 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub32 | decode | 3662 | 8.30 | 9.50 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub32 | gap | 2346 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 | idle | 3601 | 8.30 | 10.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 | prefill | 7151 | 8.30 | 8.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 | decode | 3662 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 | gap | 2339 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub256 | idle | 3601 | 8.30 | 9.30 | 9.90 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub256 | prefill | 6870 | 8.30 | 8.70 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub256 | decode | 3649 | 8.30 | 9.10 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub256 | gap | 2321 | 8.30 | 8.70 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub1024 | idle | 3600 | 8.30 | 9.10 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub1024 | prefill | 6809 | 8.30 | 9.20 | 9.40 | 34 | 0.4% | 0.5% | 0.00 |
| 7B-Q4 gpu ub1024 | decode | 3651 | 8.30 | 9.00 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub1024 | gap | 2390 | 8.30 | 9.10 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c256 g16 | idle | 3600 | 8.30 | 9.20 | 9.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c256 g16 | prefill | 7184 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c256 g16 | decode | 3654 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c256 g16 | gap | 2303 | 8.30 | 10.09 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 | idle | 3601 | 8.30 | 10.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 | prefill | 7491 | 8.30 | 10.00 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 | decode | 3653 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 | gap | 2379 | 8.30 | 9.60 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 | idle | 3602 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 | prefill | 8197 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 | decode | 3652 | 8.30 | 10.10 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 | gap | 2353 | 8.30 | 10.04 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g0 | idle | 3600 | 8.30 | 10.00 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g0 | prefill | 7072 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g0 | decode | 3653 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g0 | gap | 2370 | 8.30 | 10.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 | idle | 3601 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 | prefill | 8155 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 | decode | 3651 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 | gap | 2387 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 heavy-page | idle | 3600 | 8.30 | 9.90 | 10.30 | 16 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 heavy-page | prefill | 7569 | 8.30 | 10.00 | 16.53 | 18 | 1.3% | 1.3% | 0.00 |
| 7B-Q4 gpu ub64 heavy-page | decode | 3925 | 8.30 | 9.50 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 heavy-page | gap | 2375 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 heavy-page | idle | 3601 | 8.30 | 9.80 | 10.20 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 heavy-page | prefill | 4228 | 16.30 | 18.30 | 25.40 | 27 | 63.0% | 40.3% | 0.00 |
| 7B-Q4 gpu ub128 heavy-page | decode | 3928 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub128 heavy-page | gap | 2304 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 heavy-page | idle | 3600 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 heavy-page | prefill | 5417 | 8.90 | 17.80 | 25.10 | 27 | 38.4% | 29.1% | 0.00 |
| 7B-Q4 paced c128 g16 heavy-page | decode | 3933 | 8.30 | 9.40 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g16 heavy-page | gap | 2324 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 heavy-page | idle | 3600 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 heavy-page | prefill | 8707 | 8.30 | 9.30 | 10.30 | 17 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 heavy-page | decode | 3934 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 heavy-page | gap | 2363 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g50 heavy-page | idle | 3601 | 8.30 | 9.80 | 10.20 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g50 heavy-page | prefill | 10021 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g50 heavy-page | decode | 3931 | 8.30 | 9.20 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g50 heavy-page | gap | 2286 | 8.30 | 10.00 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 heavy-page | idle | 3600 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c128 g50 heavy-page | prefill | 6075 | 8.50 | 17.90 | 25.10 | 27 | 34.1% | 26.9% | 0.00 |
| 7B-Q4 paced c128 g50 heavy-page | decode | 3870 | 8.30 | 9.60 | 10.40 | 26 | 0.9% | 1.4% | 0.00 |
| 7B-Q4 paced c128 g50 heavy-page | gap | 2325 | 8.30 | 9.90 | 16.93 | 32 | 1.1% | 2.1% | 0.00 |
| 7B-Q4 cpu-only heavy-page | idle | 3600 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only heavy-page | prefill | 37733 | 8.30 | 8.40 | 9.30 | 42 | 0.1% | 0.3% | 0.00 |
| 7B-Q4 cpu-only heavy-page | decode | 4477 | 8.30 | 8.40 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only heavy-page | gap | 1378 | 8.30 | 9.30 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page | idle | 3600 | 8.30 | 9.30 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page | prefill | 8374 | 8.30 | 9.20 | 16.70 | 25 | 1.8% | 1.7% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page | decode | 4200 | 8.30 | 8.80 | 9.70 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page | gap | 2360 | 8.30 | 9.30 | 10.20 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c32 g0 heavy-page | idle | 3601 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c32 g0 heavy-page | prefill | 10260 | 8.30 | 9.50 | 10.30 | 18 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c32 g0 heavy-page | decode | 4523 | 8.30 | 9.49 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c32 g0 heavy-page | gap | 2375 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 heavy-page | idle | 3601 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 heavy-page | prefill | 1776 | 16.30 | 25.00 | 27.60 | 34 | 69.0% | 46.6% | 0.00 |
| 3B-Q4 gpu ub512 heavy-page | decode | 2258 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub512 heavy-page | gap | 2368 | 8.30 | 10.10 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub64 heavy-page | idle | 3600 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub64 heavy-page | prefill | 3910 | 8.30 | 9.60 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub64 heavy-page | decode | 2250 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 3B-Q4 gpu ub64 heavy-page | gap | 2325 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 heavy-page | idle | 3596 | 8.30 | 9.10 | 9.30 | 25 | 0.1% | 0.1% | 0.00 |
| 14B-Q4 gpu ub512 heavy-page | prefill | 4594 | 25.00 | 58.00 | 60.81 | 75 | 72.3% | 69.7% | 5.29 |
| 14B-Q4 gpu ub512 heavy-page | decode | 8399 | 8.30 | 8.80 | 9.30 | 12 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub512 heavy-page | gap | 2362 | 8.30 | 9.20 | 9.30 | 10 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub64 heavy-page | idle | 3600 | 8.30 | 9.20 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub64 heavy-page | prefill | 12032 | 8.40 | 17.10 | 25.00 | 42 | 31.0% | 24.7% | 0.00 |
| 14B-Q4 gpu ub64 heavy-page | decode | 7834 | 8.30 | 8.50 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 14B-Q4 gpu ub64 heavy-page | gap | 2385 | 8.30 | 9.10 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @aquarium | idle | 3600 | 8.30 | 9.20 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @aquarium | prefill | 2216 | 24.80 | 43.63 | 48.68 | 56 | 82.7% | 68.3% | 0.05 |
| 7B-Q4 gpu ub512 @aquarium | decode | 3948 | 8.30 | 10.00 | 10.30 | 18 | 0.1% | 0.1% | 0.00 |
| 7B-Q4 gpu ub512 @aquarium | gap | 2291 | 8.30 | 10.00 | 10.31 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @aquarium | idle | 3601 | 8.30 | 9.80 | 10.30 | 16 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @aquarium | prefill | 7415 | 8.30 | 9.90 | 10.30 | 17 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @aquarium | decode | 3942 | 8.30 | 9.90 | 10.30 | 17 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @aquarium | gap | 2338 | 8.30 | 9.82 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @aquarium | idle | 3601 | 8.30 | 9.90 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @aquarium | prefill | 8504 | 8.30 | 9.90 | 10.30 | 25 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @aquarium | decode | 3947 | 8.30 | 10.00 | 10.30 | 18 | 0.1% | 0.1% | 0.00 |
| 7B-Q4 paced c64 g16 @aquarium | gap | 2302 | 8.30 | 10.00 | 10.30 | 15 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @mm-multiply | idle | 3463 | 8.33 | 10.32 | 16.82 | 19 | 4.0% | 3.9% | 0.00 |
| 7B-Q4 gpu ub512 @mm-multiply | prefill | 6303 | 8.33 | 15.86 | 17.05 | 19 | 5.8% | 5.5% | 0.00 |
| 7B-Q4 gpu ub512 @mm-multiply | decode | 3222 | 8.33 | 16.67 | 18.22 | 25 | 9.5% | 8.8% | 0.00 |
| 7B-Q4 gpu ub512 @mm-multiply | gap | 2243 | 8.33 | 10.33 | 16.92 | 18 | 4.0% | 3.9% | 0.00 |
| 7B-Q4 gpu ub64 @mm-multiply | idle | 3453 | 8.33 | 10.33 | 17.00 | 19 | 4.3% | 4.1% | 0.00 |
| 7B-Q4 gpu ub64 @mm-multiply | prefill | 6597 | 8.33 | 15.05 | 16.88 | 19 | 5.4% | 5.1% | 0.00 |
| 7B-Q4 gpu ub64 @mm-multiply | decode | 3222 | 8.33 | 16.67 | 18.27 | 27 | 9.2% | 8.8% | 0.00 |
| 7B-Q4 gpu ub64 @mm-multiply | gap | 2298 | 8.33 | 10.33 | 17.01 | 19 | 4.4% | 4.2% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-multiply | idle | 3465 | 8.33 | 10.33 | 17.10 | 19 | 3.9% | 3.8% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-multiply | prefill | 7603 | 8.33 | 15.06 | 17.01 | 25 | 5.5% | 5.2% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-multiply | decode | 3223 | 8.33 | 16.67 | 18.25 | 27 | 9.8% | 9.2% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-multiply | gap | 2207 | 8.33 | 10.33 | 17.42 | 25 | 4.1% | 4.2% | 0.00 |
| 7B-Q4 gpu ub512 @mm-arcs | idle | 3600 | 8.33 | 8.78 | 9.31 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @mm-arcs | prefill | 4614 | 8.35 | 27.36 | 33.34 | 42 | 30.4% | 33.4% | 0.00 |
| 7B-Q4 gpu ub512 @mm-arcs | decode | 3596 | 8.33 | 8.73 | 9.23 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @mm-arcs | gap | 2355 | 8.33 | 8.72 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @mm-arcs | idle | 3600 | 8.33 | 8.50 | 9.18 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @mm-arcs | prefill | 7069 | 8.33 | 8.66 | 9.21 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @mm-arcs | decode | 3560 | 8.33 | 8.75 | 9.22 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @mm-arcs | gap | 2299 | 8.33 | 8.46 | 9.13 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-arcs | idle | 3601 | 8.33 | 8.64 | 9.18 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-arcs | prefill | 8018 | 8.33 | 8.61 | 9.22 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-arcs | decode | 3567 | 8.33 | 8.79 | 9.23 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @mm-arcs | gap | 2314 | 8.33 | 8.45 | 9.09 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @bbc | idle | 3600 | 8.30 | 9.30 | 9.40 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @bbc | prefill | 6620 | 8.30 | 8.80 | 10.20 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @bbc | decode | 3516 | 8.30 | 9.20 | 10.20 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 @bbc | gap | 2302 | 8.30 | 9.80 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @bbc | idle | 3602 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @bbc | prefill | 6954 | 8.30 | 9.30 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @bbc | decode | 3524 | 8.30 | 9.40 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 @bbc | gap | 2352 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @bbc | idle | 3600 | 8.30 | 10.20 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @bbc | prefill | 8038 | 8.30 | 9.20 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @bbc | decode | 3522 | 8.30 | 9.09 | 10.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g16 @bbc | gap | 2341 | 8.30 | 10.30 | 10.40 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-heavy | idle | 1802 | 17.00 | 17.00 | 18.00 | 18 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-heavy | prefill | 3597 | 16.00 | 32.00 | 36.00 | 48 | 14.5% | 12.8% | 0.00 |
| 7B-Q4 gpu ub512 safari-heavy | decode | 1904 | 17.00 | 17.00 | 18.00 | 19 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-heavy | gap | 1176 | 17.00 | 17.00 | 18.00 | 20 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 safari-heavy | idle | 1801 | 17.00 | 17.00 | 18.00 | 24 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 safari-heavy | prefill | 3812 | 17.00 | 18.00 | 18.00 | 22 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 safari-heavy | decode | 1919 | 17.00 | 18.00 | 18.00 | 19 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub64 safari-heavy | gap | 1157 | 17.00 | 18.00 | 18.00 | 19 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-light | idle | 1800 | 17.00 | 17.00 | 18.00 | 23 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-light | prefill | 3452 | 17.00 | 18.00 | 21.00 | 27 | 0.1% | 0.1% | 0.00 |
| 7B-Q4 gpu ub512 safari-light | decode | 1793 | 17.00 | 17.00 | 18.00 | 18 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 gpu ub512 safari-light | gap | 1157 | 17.00 | 17.00 | 18.00 | 18 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 cpu-only @mm-multiply | idle | 3502 | 8.33 | 10.32 | 16.67 | 18 | 2.8% | 2.7% | 0.00 |
| 7B-Q4 cpu-only @mm-multiply | prefill | 36574 | 8.34 | 16.99 | 25.00 | 27 | 22.4% | 19.8% | 0.00 |
| 7B-Q4 cpu-only @mm-multiply | decode | 5168 | 8.34 | 17.57 | 25.01 | 27 | 30.1% | 24.9% | 0.00 |
| 7B-Q4 cpu-only @mm-multiply | gap | 1380 | 8.33 | 10.34 | 16.78 | 18 | 4.2% | 4.0% | 0.00 |
| 7B-Q4 cpu-only t4 @mm-multiply | idle | 3491 | 8.33 | 10.32 | 16.87 | 19 | 3.1% | 3.0% | 0.00 |
| 7B-Q4 cpu-only t4 @mm-multiply | prefill | 41194 | 8.33 | 16.67 | 18.23 | 27 | 8.2% | 7.8% | 0.00 |
| 7B-Q4 cpu-only t4 @mm-multiply | decode | 4098 | 8.33 | 17.01 | 24.97 | 27 | 18.1% | 16.2% | 0.00 |
| 7B-Q4 cpu-only t4 @mm-multiply | gap | 922 | 8.33 | 9.58 | 16.67 | 18 | 2.6% | 2.5% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page (disturbed) | idle | 3600 | 8.30 | 9.10 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page (disturbed) | prefill | 8359 | 9.10 | 17.40 | 25.10 | 33 | 46.7% | 33.2% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page (disturbed) | decode | 8046 | 8.30 | 8.90 | 9.30 | 10 | 0.0% | 0.0% | 0.00 |
| 7B-Q4 paced c64 g0 heavy-page (disturbed) | gap | 2345 | 8.30 | 9.20 | 9.30 | 9 | 0.0% | 0.0% | 0.00 |

Budget measured at idle: 8.30 ms (about 120 Hz).

## Run integrity

19 sessions, 717 measured trials, 0 errors, 6.2 h of runs. 2,721,774 prompt tokens and 166,838 generated tokens.

## Method and limits

- Each configuration runs one warm-up request and then the measured runs. The prompt cache is off except in E1b's warm arm. Sampling is greedy with a fixed seed. EOS is ignored in E1, E2 and E4, so every run generates the same number of tokens. E3 lets generation stop naturally, because acceptance depends on the text.
- TTFT is wall time from sending the request to the first streamed token, which includes HTTP and tokenisation. Server-side prompt time is stored too.
- Memory is the llama-server process's physical footprint (proc_pid_rusage, which includes Metal buffers), sampled at 10 Hz.
- Models are Qwen 2.5 Instruct GGUF builds (bartowski). Dart's papers do not name their models, so model size is the comparable axis, not the exact model.
- Frame timing uses requestAnimationFrame intervals, which proxy what the user sees. Brave stands in for Dart, and both are Chromium-based.
- One machine. Numbers are for this M4 Pro, not for Dart's four machines.
