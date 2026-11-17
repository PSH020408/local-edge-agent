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

