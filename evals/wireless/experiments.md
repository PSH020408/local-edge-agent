# Wireless experiments (Stage 8)

Measurements that decide how the Wi-Fi agent reads the link and how long it measures. Network names,
addresses and device names stay in `logs/` and are not published.

## Probe (2026-11-17, `scripts/probe_wireless.py`)

Home network: 5 GHz channel 44, 80 MHz, 802.11ac, one spatial stream, MCS 9, 433 Mb/s.

| Source | Time per reading | Gives | Used for |
|---|---|---|---|
| CoreWLAN (compiled Swift helper) | about 2 ms | link signal, noise, channel, band, width, PHY mode, rate | every link reading and the coverage model |
| CoreWLAN scan | 12.9 s | signal, channel and width of every nearby network (11 of 11 with signal) | channel and network choice, on request |
| `wdutil info` (sudo) | 0.2 s once the password is cached | channel utilisation (CCA), spatial streams, MCS, guard interval | link details |
| `system_profiler SPAirPortDataType` | 12.6 s | the link; nearby networks without signal (1 of 9) | not used |
| ping, `dig`, `networkQuality` | 4 s, under 1 s, 18 s | latency, jitter, loss; DNS time; throughput and latency under load | path tests |
| `system_profiler SPBluetoothDataType` | under 0.1 s | connected devices; signal of a connected mouse (-53 dBm) | Bluetooth |

The same link read at the same moment: -44 dBm (wdutil), -48 (CoreWLAN), -43 (scan). Values from different
sources are not mixed; CoreWLAN is the reference.

## W1: how long to measure (2026-11-17, `scripts/wifi_experiment.py`)

Predictions written before the run: signal updated about once a second, σ 1-2 dB at a fixed place, 10-30 s
for ±1 dB; median latency stable within 10 s, 95th percentile and spike share only after about 30 s.

**Signal at a fixed place** (CoreWLAN, 10 Hz, 60 s): mean -44.1 dBm, σ 1.15 dB, range -48 to -41. The
reading updates about every 0.22 s (faster than predicted); readings are correlated over 0.67 s. Averaging
needed for a 95% interval of ±1 dB: 6.7 s by the formula; measured, 10-second means stayed within 0.32 dB of
the 60-second mean (5-second means within 1.21 dB).

| Window | Worst error of the mean signal |
|---|---|
| 1 s | 2.35 dB |
| 5 s | 1.21 dB |
| 10 s | 0.32 dB |
| 30 s | 0.08 dB |

**Latency to the router at rest** (5 Hz, 60 s, 300 pings, none lost): median 3.8 ms, but 95th percentile
145 ms, maximum 347 ms, and 17% of replies above 50 ms. Spikes come in short bursts of consecutive replies
(queued while the radio is away from the channel) and do not cluster at multiples of the beacon interval.

| Window | Median, worst error | p95, worst error | Spike share, worst error |
|---|---|---|---|
| 5 s | 0.42 ms | 95 ms | 0.15 |
| 10 s | 0.38 ms | 58 ms | 0.05 |
| 20 s | 0.10 ms | 23 ms | 0.04 |
| 30 s | 0.06 ms | 5 ms | 0.01 |

**AWDL on, off, on** (30 s each): p95 173 → 80 → 60 ms, spike share 0.19 → 0.10 → 0.07. The spikes fell after
AWDL was switched off but kept falling after it was switched back on, so the drop cannot be credited to AWDL:
the spikes vary over time by themselves. Without the third phase this would have been reported as an AWDL
effect. W2 repeats the comparison in pairs in random order.

**Driver readings:** CCA 2% at rest, 59-92% under load from the Mac's own traffic, so channel utilisation
counts the Mac's own transmissions: congestion from other networks is read only while the Mac is idle. Still
one spatial stream. wdutil takes 0.2 s per reading once the password is cached (6.3 s in the probe included
the password prompt).

**Under load** (networkQuality): 181 Mb/s down, 178 Mb/s up, responsiveness 455 round trips per minute
(about 130 ms of latency under load, against 12 ms at rest); pings to the router: median 11.6 ms, p95 74 ms.

**Decisions**

| Measurement | Duration | Reason |
|---|---|---|
| Signal for a diagnosis | 10 s | ±0.3 dB at a fixed place |
| Signal per point of the coverage walk | 10-15 s, moving within about 30 cm | averages the fast fading of a 6 cm wavelength; σ per point is recorded to check it |
| Latency, quick check ("why is my Wi-Fi slow?") | 10 s | median and spike share within 0.4 ms and 0.05 |
| Latency, verdict for calls and games | 30 s | the 95th percentile needs it (5 ms against 58 ms at 10 s) |
| Channel utilisation | while idle | the Mac's own traffic raises it |

## W2: is AWDL the cause of the spikes? (gate written before the run)

AWDL switched on and off in 8 pairs of 20 s, the order inside each pair drawn at random, so a drift over time
cancels. AWDL is named as a cause only if the spike share is lower with AWDL off in at least 7 of 8 pairs
(one-sided sign test, p = 0.035) and lower by at least 0.05 on average. Otherwise the agent reports the spikes
and where they occur (the Wi-Fi segment) without naming a cause.

**Result (2026-11-17):** the gate is met. Spike share lower with AWDL off in 7 of 8 pairs, by 0.103 on average
(SD 0.112); jitter lower in 8 of 8 (−20.6 ms on average).

| Pair | Order | Spikes on | Spikes off | p95 on, ms | p95 off, ms | Jitter on, ms | Jitter off, ms | AWDL at the end of "off" |
|---|---|---|---|---|---|---|---|---|
| 1 | on-off | 0.21 | 0.00 | 167.1 | 3.2 | 57.1 | 0.15 | down |
| 2 | off-on | 0.08 | 0.00 | 67.6 | 3.2 | 15.9 | 0.24 | down |
| 3 | off-on | 0.08 | 0.00 | 60.1 | 3.3 | 13.6 | 0.34 | down |
| 4 | off-on | 0.07 | 0.00 | 59.7 | 3.3 | 14.5 | 0.18 | down |
| 5 | on-off | 0.07 | 0.11 | 60.9 | 76.9 | 14.9 | 14.6 | down |
| 6 | on-off | 0.07 | 0.00 | 69.1 | 3.1 | 15.3 | 0.18 | down |
| 7 | off-on | 0.36 | 0.04 | 168.8 | 23.9 | 54.0 | 7.1 | **up again** |
| 8 | off-on | 0.09 | 0.06 | 64.0 | 56.2 | 14.7 | 12.2 | **up again** |

In five of the six pairs where AWDL stayed down, the link to the router was clean: p95 about 3.2 ms against
60-170 ms, jitter 0.2 ms against 14-57 ms, no reply above 50 ms. In pairs 7 and 8 macOS had switched AWDL back
on during the "off" phase, so those comparisons are weaker than they look and the effect is, if anything,
understated. Pair 5 is the one exception with AWDL down (its state was read only at the end of the phase).

**Consequences for the agent**
- AWDL state is read with every latency check (`ifconfig awdl0`, no rights needed).
- Spikes on the router hop with AWDL active → AWDL is named as the likely cause, with this experiment as the
  evidence; advice: for a call or a game, turn AirDrop off and Handoff / Universal Control off, or switch AWDL
  off for the session (with confirmation; macOS may switch it back on, as in pairs 7 and 8).
- Spikes with AWDL down → reported without a cause.

## W3: one hour at rest, the baseline (2026-11-17, 21:52-22:52, `scripts/wifi_log.py`)

60 rounds of one minute, the Mac plugged in and idle at its usual place; the rest of the home used the
network as usual.

| Minutes | Signal dBm | Router median ms | Router p95 ms | Router spikes % | Internet p95 ms | DNS ms | CCA % |
|---|---|---|---|---|---|---|---|
| 0-10 | -46.4 | 3.7 | 58.4 | 7.6 | 64.9 | 12.7 | 1.9 |
| 10-20 | -46.8 | 3.7 | 53.3 | 7.2 | 59.4 | 7.5 | 2.0 |
| 20-30 | -46.7 | 3.6 | 51.8 | 6.2 | 55.3 | 7.3 | 1.3 |
| 30-40 | -46.6 | 3.6 | 58.3 | 7.4 | 62.0 | 7.2 | 1.8 |
| 40-50 | -46.7 | 3.6 | 58.4 | 6.4 | 66.1 | 11.2 | 1.7 |
| 50-60 | -46.7 | 3.7 | 58.6 | 7.0 | 62.4 | 11.3 | 1.2 |

- The link is steady: signal -46.6 dBm within ±0.4 dB over the hour; noise -94 dBm, so SNR about 47 dB.
- AWDL was active in all 60 rounds, so W3 cannot compare states; the steady state of this Mac is AWDL on, with
  about 7% of replies to the router above 50 ms and a p95 near 56 ms, against 3.2 ms with AWDL off in W2.
- Internet p95 follows the router p95, so the spikes are added on the Wi-Fi segment, not by the provider.
- DNS 6-9 ms, with four of 60 lookups at 44-50 ms (one slow lookup per round raises the 10-minute mean).
- Channel: the home router at about -41 dBm and one other network at -79 to -83 dBm on channel 44; CCA 1-4%.
- Throughput (4 tests): 135-329 Mb/s down, 165-234 up; responsiveness 257-671 round trips per minute, so a
  single test is a noisy reading of latency under load.

## Coverage walk: plan, predictions and gate (written before the walk, 2026-11-18)

**Setup.** The home's floor plan stays in `logs/home/` (not published). Scale from the router room's measured
width: 3.0 m over 155 px, 1.94 cm per px. Walls are extracted from the plan image (dark pixels, 3x3 opening,
specks under 120 px dropped). The router stands on the floor (0.1 m); the Mac is measured on a chair (0.45 m).
25 points, 1.0-10.7 m from the router through 0-5 walls; 5 held out before the walk by a seeded draw
(points 5, 9, 12, 18, 22). All interior doors open. AWDL off during the walk (W2), so the latency at a point
shows the radio conditions. A Bluetooth speaker next to the router gives the Bluetooth signal at the same points.

**Check of the pipeline on a simulated walk** (known n = 3.0, 8 dB per wall, 3 dB shadowing on the home plan):
fitted n = 3.14 and 7.4 dB per wall; held-out RMSE 3.3 dB for the multi-wall model against 9.2 (distance only),
14.6 (free space) and 14.1 (interpolation).

**Predictions.** 5 GHz: n 2.5-3.5, 5-12 dB per interior wall. 2.4 GHz: smaller wall loss than 5 GHz.
Bluetooth: weakest of the three, lost through two or more walls beyond 7-10 m. MCS falls from 9 near the
router to 0-3 in the far rooms, roughly following the standard's sensitivity table.

**Gate.** The multi-wall model counts as validated if its held-out RMSE is at most 5 dB for 5 GHz and lower
than all three baselines. If not, the map is shown as interpolation only and the model is not used for
predictions.

**Door test.** Three points in line with the router room's door (D1-D3), measured with the door open and
closed: the loss of a closed door.
