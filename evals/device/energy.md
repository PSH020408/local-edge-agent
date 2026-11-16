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

