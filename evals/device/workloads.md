# Workload set W: energy modes across everyday work

Scenarios in `agent/device/workloads.py`, runner `scripts/run_workloads.py`, reports in `logs/workloads/`.

Why: runs E1-E3 showed that High Power gives no speed over Automatic **for local LLM generation**, which is
bound by memory bandwidth. That says nothing about work bound by CPU clocks (building), GPU compute (games,
3D, training) or the media engine (video). Real applications cannot be run identically twice, so each kind of
work is reproduced as a scenario with the same hardware demand.

## Design (2026-11-17)

- **Phases that rise and fall, as in real use.** A video edit is scrubbing, previews with effects, a heavy
  export and a review; training is data preparation, then epochs of training steps, evaluation and a
  checkpoint save; a game is loading, play whose scene complexity drifts, a menu, loading again.
- **Work, not time.** Every phase is a fixed amount of work. Batch phases (export, full build, rendering,
  training) are timed until they are done; interactive phases (game frames, previews, page loads, typing)
  have a deadline per tick and count the ticks they missed. A slower mode shows as a longer batch or as
  missed deadlines; a fixed busy time would hide it.
- **The same randomness every time.** The rise and fall comes from a generator seeded with 2026, so every mode
  gets the same pattern.
- **Amounts set once at full speed.** The first run on the adapter in High Power measures how much work fits in
  the target times (`logs/workloads/calibration.json`); battery runs reuse it.

| Tier | Scenario | Phases (about 3-4 minutes at full speed) |
|---|---|---|
| 0 | idle | 2 minutes, screen on |
| 1 | document | 3 minutes of typing in bursts (2-15 ms of work per second) and pauses, an autosave every 45 s |
| 1 | music | 3 minutes of playback |
| 2 | web | page loads at random (every 12 s on average, 0.2-0.6 s on 4 cores, within 1 s), GPU scrolling, a 10 s video ad |
| 2 | video_4k_play | 4 x 45 s of 4K playback with seeks (media engine) |
| 2 | video_call | 3 minutes of 1080p real-time encoding; CPU work 10-40% of 2 cores, drifting |
| 3 | photo | import; 90 s of slider editing (a 24 MP GPU preview within 0.5 s); export of 20 photos |
| 3 | compile | edit pauses and three incremental builds; a full build of about 40 s |
| 3 | file_copy | 4 GB written and read back past the file cache |
| 4 | video_edit | scrubbing; 60 s of previews with effects (a frame within 0.1 s); a 40 s export (CPU filters, HEVC encoder); review |
| 4 | game | loading; 2 minutes at 60 fps (GPU up to 10 ms per frame, scene complexity 45-100%, 3 CPU threads); menu; loading |
| 4 | render_3d | scene preparation on one core; 60 tiles of uneven complexity on the GPU (about 90 s) |
| 4 | llm | a document of about 8,000 tokens read once; three 200-token answers with pauses (qwen3:14b) |
| 5 | training | data preparation on 8 cores; three epochs of about 25 s of training, an evaluation and a 512 MB checkpoint |
| 5 | stress | every core and the GPU at once, about 3 minutes of work |

Each tier runs on the adapter in High Power (the reference) and on battery in Low Power and Automatic (tiers
0-2) or all three modes (tiers 3-5). Measured per run: total and batch time, missed deadlines, chip power
(mean, peak) and energy from powermetrics every second, GPU busy, thermal pressure, and the whole-system power
from the battery registry (counter on the adapter; V × I and charge drop on battery, coarse:
`evals/device/energy.md`).

Limits stated before the runs: proxies not calibrated against the real applications; the 4K clip is a
synthetic pattern, easier to compress than real footage; 3-4 minutes show the first minutes of heat, not an
hour of gaming.

## Predictions, written before the first run

Load on the adapter in High Power (mean over the scenario, peak in brackets):

| Scenario | CPU (of 14 cores) | GPU busy | Chip W | System W |
|---|---|---|---|---|
| idle | ~2% | ~5% | ~0.2 | 5-6 (measured) |
| document | ~1% (7%) | ~5% | ~0.3 | ~6 |
| music | ~1% | ~5% | ~0.3 | ~6 |
| web | ~3% (25%) | ~10% | ~1.5 (12) | ~8 |
| video_4k_play | ~3% | low (decoder) | 1-2 | 8-10 |
| video_call | ~4% | low | 2-3 | ~10 |
| photo | ~10% (57%) | ~35% (90%) | 8 (30) | 20 (55) |
| compile | ~35% (95%) | ~0% | 15 (40) | 25 (55) |
| file_copy | ~5% | 0% | ~3 | ~12 |
| video_edit | ~15% (50%) | ~30% (90%) | 10 (25) | 25 (45) |
| game | ~6% | ~50% (60%) | 15 (20) | 35 (45) |
| render_3d | ~2% | ~95% | 25-35 | 50-60 |
| llm | ~5% | ~60% (100%) | 15 (32) | 40 (80, measured) |
| training | ~10% (57%) | ~80% (95%) | 25 (30) | 55 (70) |
| stress | 100% | 100% | 60-70, heat limit | 90-100 |

Mode effects on battery:
- Tiers 0-2: the same power in Low Power and Automatic within 1-2 W; no missed deadlines in either.
- Photo previews, game frames and video-edit previews: no misses in Automatic and High Power, some in Low Power.
- Batch phases (export, builds, rendering, training): Low Power 30-50% longer; High Power equal to Automatic
  except in stress, once thermal pressure rises.

## Quick check (2026-11-17 08:37, adapter, a tenth of the work)

Every scenario of tiers 4 and 5 ran without an error. Chip power and GPU busy were in the predicted range for
render_3d (24 W, 81%), llm (27 W, 89%) and training (21 W, 69%). Three defects, fixed before the full runs:

| Seen | Cause | Fix |
|---|---|---|
| game: GPU 6% busy, 2 W | the per-frame GPU budget was scaled down with the durations in the quick check | budgets per tick are not scaled |
| stress: 64 s for 18 s of work per core, GPU 29% busy | equal shares on all 14 cores waited for the 4 slower efficiency cores; the thread feeding the GPU had no core left | work cut into small pieces handed out as cores free up; 12 CPU workers, 2 cores left for the GPU; GPU products queued 8 at a time |
| no system power | runs under a minute see fewer than two registry publications | none needed: full runs last 3-4 minutes |

## W-adapter — all tiers on the adapter, High Power (2026-11-17 09:24-10:20)

Commit `11fa6d5`. Calibration (once, at full speed): a 2048 x 2048 GPU product 2.81 ms (about 6 TFLOP/s),
4K export 54 frames/s, one training step 97 ms, one C file 0.13 s. The music was a 440 Hz tone, not music.

| Scenario | Time s | Chip W mean (peak) | GPU busy % | System W | Deadlines missed | Prediction (chip W mean) |
|---|---|---|---|---|---|---|
| idle | 120 | 0.29 (4.5) | 4 | 8.4 | - | ~0.2 ✅ |
| document | 181 | 0.24 (9.4) | 2 | 7.2 | 0 of 180 | ~0.3 ✅ |
| music | 180 | 0.09 (2.1) | 2 | 7.4 | - | ~0.3 ✅ |
| web | 181 | 1.19 (18.6) | 5 | 8.2 | 0 of 180 | ~1.5 ✅ |
| video_4k_play | 232 | 0.08 (0.7) | 2 | 7.3 | - | 1-2 (lower) |
| video_call | 181 | 3.99 (5.4) | 2 | 13.2 | 0 of 180 | 2-3 (higher) |
| photo | 104 | 7.43 (43.0) | 18 | 15.2 | 0 of 180 | ~8 ✅ |
| compile | 65 | 8.79 (34.8) | 2 | - | - | ~15 (lower) |
| file_copy | 17 | 0.20 (2.0) | 2 | - | - | ~3 (lower) |
| video_edit | 141 | 4.23 (17.3) | 14 | 22.3 | 1 of 600 | ~10 (lower) |
| game | 176 | 5.02 (25.8) | 36 | 25.8 | 1 of 8,400 | ~15 (lower) |
| render_3d | 97 | 25.2 (35.7) | 91 | - | - | 25-35 ✅ |
| llm | 93 | 19.8 (33.3) | 68 | - | - | ~15 ✅ |
| training | 95 | 24.3 (37.4) | 90 | - | - | ~25 ✅ |
| stress | **658** | 32.5 (68.7) | 27 | 59.8 | - | 60-70 (**heat limit**) |

What the reference shows:
1. **Light work costs almost nothing above the screen.** Documents, music, web and 4K playback drew 7-8 W for
   the whole Mac, the same as idle within the noise; the chip drew under 1.2 W on average. 4K decoding on the
   media engine added nothing measurable (0.08 W at the chip). A video call was the one light task above idle
   (13 W: the encoder plus 2 busy cores). For light work, battery life is set by the screen and the base load,
   not by the energy mode.
2. **Everyday heavy work comes in bursts.** Photo editing peaked at 43 W but averaged 7 W; building peaked at
   35 W and averaged 9 W. The mean is what drains the battery; the peak is what the user waits for.
3. **Sustained GPU work sits at 20-25 W of chip power** (render 25 W, training 24 W, LLM 20 W, GPU 68-91% busy)
   with thermal pressure still nominal after about 95 s. Training slowed slightly from epoch to epoch (25.4,
   26.8, 27.4 s per epoch: +8% in 80 s), the first sign of heat.
4. **Everything at once hits the heat limit.** The stress scenario's work, 180 s at full speed for every core
   and the GPU, took 658 s: thermal pressure reached heavy, the chip held about 32 W on average (peak 69 W) and
   the GPU ran at half its clock (672 MHz against 1,348 MHz in the render). On this 14-inch machine, sustained
   combined load is capped by heat at roughly a third of its burst speed.
5. Predictions: right for the light tiers and for sustained GPU work; too high for compile, file copy, video
   edit and game, whose heavy phases are shorter than planned (the full build took 16 s, not 40 s: one file
   compiles faster in a parallel build than alone, which the calibration measured).

Changes before the battery runs: the stress work is a third (60 s at full speed for each part) and times its
CPU and GPU parts separately; every run stores a 5-second time series of chip power, GPU clock and thermal
pressure (the curves the feedback controller will be designed from); system power uses every publication
inside the run (runs under 2 minutes had none). Stress is run again on the adapter with the new size.

