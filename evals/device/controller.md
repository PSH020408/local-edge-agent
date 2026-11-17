# Power feedback controller: recorded tests

Controller `agent/device/controller.py` (PI on chip power, actuating the duty of the job), test
`scripts/run_controller_test.py`: real MLX training (the trainer of the workload set), 10 s idle, 60 s at full
speed, then held at 65% and 40% of the full power for 90 s each. Reports in `logs/controller/`.

## C1 — first hardware test (2026-11-17 11:44, adapter)

Idle 0.02 W, training at full speed 28.6 W (10.3 steps/s). Kp 0.0105, Ki 0.0058 per W.

| Phase | Steps/s | Mean chip W | J per step | Settling s (±10%) | Steady error W | Ripple W |
|---|---|---|---|---|---|---|
| full speed | 10.27 | 27.31 | 2.66 | - | - | - |
| held at 18.6 W | 6.83 (66%) | 18.26 | 2.67 | 15.2 | -0.03 | 2.91 |
| held at 11.5 W | 4.46 (43%) | 11.69 | 2.62 | 60.0 | -0.18 | 1.37 |

Predictions: settling within 15 s (**18.6 W: 15.2 s, just over; 11.5 W: see below**), steady error within 10%
(**yes: 0.03 and 0.18 W**), speed roughly in proportion to power (**yes: 66% and 43% of the steps for 65% and
40% of the power**), the same energy per step in every phase (**yes: 2.62-2.67 J**).

- **The target is held.** The mean power over each phase was within 0.2 W of its target.
- **Pacing does not save energy per step.** The work runs at full clock and rests between chunks, so each step
  costs the same 2.6-2.7 J; the controller trades speed for power, not efficiency. Saving energy per step
  would need lower clocks (the energy mode), which the PI loop does not touch.
- **The 60 s for 11.5 W is an artifact of the metric.** The power entered the ±10% band after about 9 s and
  stayed there except for one excursion 0.05 W past the band at 59 s; with a ±1.15 W band and 1.4 W of ripple,
  "the last time outside the band" is decided by noise. The report now also gives the first entry into the
  band and the share of time inside it.
- **Two defects in the loop itself**, from the trace:
  1. Each step started from the old duty, and the integral had to travel the whole way: the power fell to 12 W
     for an 18.6 W target before recovering. Fix: feedforward of the duty the target needs,
     (target − idle) / (full − idle); the integral now only corrects the plant's nonlinearity (18.6 W needed a
     duty of 0.74, where the linear estimate is 0.65).
  2. The sensor delivers a sample about every 1.25 s and the loop updated every 1.0 s, so about half the
     updates reused the last sample, doubling the effective integral gain. Fix: update only on a new sample.
  On the simulated plant the feedforward brought the step to 12 W into the band in 4.3 s instead of 12.2 s.
