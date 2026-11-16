# Energy per energy mode on battery

Script: `scripts/measure_job_energy.py`. Reports in `logs/energy/` (not committed). The same generation (fixed
prompt, seed, 800 tokens) runs in Low Power, Automatic and High Power on battery; the battery mode is restored
after each run.

## E1 — qwen3:14b, one run per mode (2026-11-16, 90% charge)

| Mode | Time (s) | Tokens/s | Wh (V × I integrated) | Wh (drop of the charge left) |
|---|---|---|---|---|
| Low Power | 56.9 | 14.1 | 0.058 | 0.603 |
| Automatic | 31.8 | 25.3 | 0.252 | 0.000 |
| High Power | 31.8 | 25.3 | 0.467 | 0.608 |

Predictions written before the run: High Power fastest, Low Power slowest; the least energy per token in Low
Power, the most in High Power, unless the base power of the machine dominates the longer run.

**Speed: High Power gave nothing over Automatic** (25.3 tokens/s in both); Low Power was 44% slower. The speed
figures come from Ollama's own timing and are reliable. Generating a token reads every weight of the model once,
so the speed is set by memory bandwidth, not by the clock: about 9 GB of weights × 25.3 tokens/s is about
230 GB/s, close to the M4 Pro's 273 GB/s. Higher clocks (High Power) cannot make a bandwidth-bound job faster;
lower clocks (Low Power) can make it slower.

**Energy: not usable.** The two methods disagree by up to ten times (Low Power: 0.058 against 0.603 Wh), and the
charge drop reads 0 for a 32-second run. The battery registry refreshes its values only every few seconds, so on
runs of 30-60 s the meter mostly integrates the state before the run. The two-method check did its job: it showed
that this measurement cannot be trusted. Next: `scripts/gauge_rate.py` measures how often each value refreshes,
including the telemetry accumulators (`AccumulatedSystemLoad` with its sample count, a running sum kept by the
power controller), and the runs are made long enough for the refresh interval.

Consequence for the policy table, from the speed alone: on battery a heavy generation gets Automatic, not
High Power; High Power cannot speed it up.

Open: the prompt of E1 was short. Reading a long prompt (a document question) is a different kind of work: all
prompt tokens are processed together as matrix products, which is bound by compute rather than bandwidth, so
High Power may help there. The next run measures a long-prompt job too before the table is settled.

## How often the battery registry refreshes (`scripts/gauge_rate.py`, 2026-11-16)

One read per second for 60 s: **every value changed exactly once**, and `UpdateTime` moved by 60 s. The battery
registry publishes new values once a minute. The power controller samples more often than it publishes: its
running sum of the system load (`AccumulatedSystemLoad`) went up by 59 samples in those 60 s, one per second.
On battery the published load equalled V × I of the battery (9.29 W both), so the sum measures the energy the
battery delivers.

| Value | Refresh | Use |
|---|---|---|
| Voltage, current, charge left, system load | every 60 s, one instant | state, not energy |
| Running sum of the system load and its sample count | sampled every second, published every 60 s | energy between two publications: (sum after − sum before), in mW·s |

Changes made from this:
- **Energy** (`power_policy.measure`): the job starts right after a publication and the next publication after
  the job closes the window; the energy is the difference of the running sum, minus the idle power (from the
  minute before) for the part of the window after the job. A check compares the number of load samples with
  the window's length, so a missed publication is caught.
- **Sampler**: reads the battery registry every 60 s instead of every 10 s (it stored the same values six
  times), and stores the running sum and the system load as well.
- **Run E2** (next): the generation job again, and a job that reads a long prompt (about 8,000 tokens), where
  High Power may help. Each run uses a different first line, because Ollama reuses a cached prompt and would
  skip the reading.

## E2 — qwen3:14b, generation and a long prompt, one run per mode (2026-11-16, 91% charge)

| Job | Mode | Time (s) | Read (tokens/s) | Written (tokens/s) | Counter mean W | Idle W | Wh |
|---|---|---|---|---|---|---|---|
| Generation, 800 tokens | Low Power | 57.1 | 147 | 14.1 | 25.0 | 4.2 | 0.397 |
| | Automatic | 31.8 | 185 | 25.4 | 4.1 | 5.1 | 0.037 |
| | High Power | 31.9 | 187 | 25.4 | 6.0 | 4.8 | 0.054 |
| Long prompt, 7,684 tokens read | Low Power | 60.1 | 137 | 12.5 | 27.3 | 3.9 | 0.456 |
| | Automatic | 38.6 | 213 | 22.7 | 13.4 | 4.8 | 0.143 |
| | High Power | 38.6 | 213 | 22.7 | 12.8 | 5.1 | 0.138 |

Predictions: generation the same in Automatic and High Power (**yes**, 25.4 both, as in E1); the long prompt
faster in High Power (**no**: 213 tokens/s in both). Low Power was 35-45% slower in every job.

**High Power gave no speed on battery for either kind of work.** Reading a prompt is compute-bound, yet it was
no faster. Apple describes High Power Mode as letting the fans run faster so that intensive work can be
sustained: it matters when the chip would otherwise be slowed down by heat, which a 30-40 s job does not
reach. High Power is therefore a question for long jobs (many minutes), not for single questions.

**Energy: still not usable, although every check said "ok".** A 14B generation cannot draw 4.1 W, less than
the machine at idle. Low Power runs (25-27 W) look plausible, Automatic and High Power runs do not. One
explanation fits all six: the counter's publications lag, so the energy of a job lands in a later window
than the one measured. The sample-count check cannot see a lag. Added: a check that the job's mean power
is above the idle power, and `scripts/gauge_step.py`, a step-response test (idle, one minute of load,
idle, with powermetrics as an independent reference) that measures the lag before the counter is used again.

## Step test on the adapter (`scripts/gauge_step.py`, 2026-11-16 23:49)

Idle, one minute of qwen3:14b generation (151-210 s), idle. Publications came every 60 s with extra ones in
between (25-42 s after some), and the sample count always matched the elapsed time.

| Window (s) | Counter mean W | Chip W (powermetrics), same window | Chip W, window before |
|---|---|---|---|
| 86-111 | 6.4 | 0.1 | 0.1 |
| 111-171 (job from 151) | 26.4 | 10.7 | 0.1 |
| 171-231 (job to 210) | 54.5 | 15.9 | 10.9 |
| 231-273 | 6.7 | 0.1 | 11.1 |

**No lag on the adapter**: the counter rose in the same windows as the chip and fell back right after. With
6.5 W idle for the rest of each window, the system drew about 66-80 W during generation (a publication at
171 s showed 73 W), while the chip itself (CPU + GPU + Neural Engine) drew about 25-32 W. More than half the
power of a 14B generation is outside the CPU and GPU: memory, which a bandwidth-bound job keeps busy, the
display, the SSD and conversion losses. powermetrics alone would understate the job's energy by half.

So the low E2 results are a battery-side effect: on battery the load comes from the battery gauge, whose
current reading is averaged, so a short burst arrives late or smeared. `power_policy.measure` now keeps the
window open, one publication at a time, until the counter is back near idle; energy that arrives late is
still counted. To confirm: the same step test on battery.

## Step test on battery (2026-11-17 00:00)

| Window (s) | Counter mean W | Chip W, same window | Chip W, window before |
|---|---|---|---|
| 92-152 | 4.9 | 2.2 | 0.1 |
| 152-212 (job 151-195) | 6.4 | 16.9 | 2.1 |
| 212-272 | 5.2 | 0.1 | 16.8 |
| 272-331 | 5.1 | 0.1 | 0.1 |

Prediction: on battery the energy arrives late, in the window after the job. **No**: it never arrived. During
the job the counter rose by 1.5 W while the chip alone drew 17 W; the window after stayed at idle. On battery
the system counter does not measure the load of a job, so it cannot be used there at all, late or not.

The battery gauge's own coulomb counter (the charge left, in mAh) is the measurement on battery. It is an
integral kept by the gauge chip itself; E1's charge-drop figure for High Power (0.608 Wh for 31.8 s, about
69 W) agrees with the 66-80 W the system counter measured for the same generation on the adapter.
`power_policy.measure` now uses the system counter on the adapter and the charge drop on battery, with
the same settle rule. Resolution on battery: 1 mAh, about 0.0125 Wh, so a job should use at least 0.3 Wh
(a few dozen seconds of a 14B model) for an error under 5%.

## E3 — qwen3:14b generation, charge drop on battery (2026-11-17 07:01, 94% charge)

| Mode | Time (s) | Tokens/s | Idle W | Job mean W | Wh | Windows |
|---|---|---|---|---|---|---|
| Low Power | 56.8 | 14.2 | **−4.5** | 37.8 | 0.596 | 2 |
| Automatic | 31.8 | 25.4 | 4.5 | 56.9 | 0.503 | 2 |
| High Power | 32.3 | 25.1 | 3.8 | 99.4 | 0.892 | 2 |

Predictions: Automatic and High Power about equal (**no**: 0.50 against 0.89 Wh); Low Power within 15% of
Automatic (not decidable, see below).

- **Low Power is invalid.** The idle minute before it read −4.5 W: the charge left went up while nothing ran.
  The gauge's charge figure is an estimate that it corrects now and then (from the cell voltage), not a pure
  sum of current, and a correction inside a window shows up as energy. The negative idle was then subtracted,
  which added energy to the job. A check now flags any idle reading under 0.5 W.
- **High Power disagrees with itself.** E1's charge drop for the same job in High Power was 0.608 Wh; E3 gives
  0.892 Wh. With 1 mAh steps (0.0125 Wh) the difference is 23 steps, so it is the gauge's estimation, not its
  resolution.
- **What holds**: speed is the same as in E1 and E2 to within 1%, and Automatic's 57 W during generation
  agrees with the 66-80 W the system counter measured on the adapter (minus the display and the rest at idle).

On battery, a 30-60 s job's energy (about 0.5 Wh, 0.8% of the battery) is within the gauge's estimation noise.
Two ways out: measure the modes on the adapter, where the system counter followed the load second by second
(it needs the adapter's mode to be switched for the test and restored afterwards), or run each mode several
times for several minutes on battery so that the job uses several Wh.

