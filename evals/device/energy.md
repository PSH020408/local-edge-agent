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

