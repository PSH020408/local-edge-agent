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

## Walk 1: router on the floor, Mac on its 5 GHz network (2026-11-18)

25 points in ascending order, the Mac linked to its own router (5 GHz, channel 44, 80 MHz) throughout: its link
signal at point 19 was -63.5 dBm while another home router in that room was heard at -32 dBm, and the width stayed
80 MHz. **The home has three routers of the same model** (AC1200, Wi-Fi 5, Realtek), one per bedroom, all on the
floor; this was learned during the walk.

**Valid:** the link at 24 points (signal, SNR, MCS, rate, latency) and three download tests.
**Not valid, and why:**
- Router beacons: the compiled helper's scan returned no network names, so "the router's beacon" was the
  strongest unnamed network at each point (often another home router). Fixed: scans through the Swift
  interpreter return the names (check of 2026-11-18: 9 of 9 named, against 0 of 6), and every home network is
  recorded by name.
- Bluetooth: macOS gives no signal for a connected classic-audio speaker. Fixed: a Bluetooth LE scan follows a
  device that advertises (an iPhone next to the router, heard at -37 dBm).
- Point 22: the Mac switched to a 2.4 GHz network and lost the link. Fixed: a point where the Mac leaves its
  network is marked invalid and can be measured again (`--redo`).
- The link rate from CoreWLAN (72 Mb/s at MCS 6) did not match the MCS; wdutil's rate (263 Mb/s) does and is used.

**Link adaptation measured.**

| Signal dBm | SNR dB | MCS (Mac to router) | Rate Mb/s | Router p95 ms | Points |
|---|---|---|---|---|---|
| -37 to -60 | 33-56 | 9 (256-QAM 5/6) | 433 | 3.4-6.4 | 8 |
| -61 to -67 | 27-32 | 7-8 | 292-390 | 4.0-6.4 | 6 |
| -70 to -71 | 22-23 | 5-6 | 234-263 | 3.8-4.3 | 3 |
| -78 to -82 | 12-15 | 1-2 | 58-97 | 5.5-46 | 5 |
| -87 | 7 | 1 | 30 | 243 | 1 |

The modulation steps down with the signal, while the latency stays near 3-7 ms down to MCS 1 and breaks only at
SNR 7 (a balcony): a messenger or a call keeps working almost to the edge of coverage, while the speed falls much
earlier (download 362, 270, 193 and 73 Mb/s at four points from the router outwards). Rate adaptation is per
direction: at point 20 the Mac sent at MCS 1 (65 Mb/s) while the download reached 73 Mb/s, and next to the router
the download (362 Mb/s) exceeded what one spatial stream at 433 Mb/s carries, so the router sends with two
streams while the Mac sends with one.

**Gate: not passed.** Multi-wall model fitted on 20 points: n = 3.09, 4.5 dB per wall; held-out RMSE 13.8 dB
(4 points), worse than interpolation (7.2 dB) and free space (10.4 dB); with interpolated residuals, 11.7 dB. The
walls are not alike: through the wall behind the router the kitchen was -70 dBm at 1.25 m, while the dining area,
reached past the open door, was -55 dBm at 2.7 m. One loss per wall cannot hold both. As decided before the walk,
the map is drawn by interpolation, and the model is not used for predictions. Next: the walks with all three
routers' beacons give six signals at the same points, enough to test wall classes (structural against partition)
by leave-one-out error before the held-out points are scored.

## Bluetooth LE pre-test (2026-11-19, `scripts/ble_pretest.py`)

The iPhone that the walk follows (advertising, Settings > Bluetooth open, screen on), 1 m from the Mac on a desk,
60 s: 96 packets (1.6 per second), longest silence 3.5 s; median -41 dBm, SD 2.4 dB (the Wi-Fi link: 1.15 dB),
range -49 to -38. Means of 5 s windows were within 3.2 dB of the whole, 10 s within 2.7 dB, 20 s within 0.8 dB
(two windows only). The walk's 20 s per point (two placements of 10 s, about 30 packets) is kept; the packet count
is recorded per point, and a point with very few packets marks the edge of Bluetooth range.

## Walk 2: router on the floor, Mac on its 5 GHz network, with all home networks and Bluetooth (2026-11-19)

25 points again, with named scans and the iPhone advertising next to AP-A.

- **Repeatability:** the link signal at the 24 points measured in both walks differed by -0.9 dB on average,
  RMS 3.0 dB, at most 8.0 dB (point 19). This is the measurement's own noise: no model can be checked to better
  than about 3 dB at single points.
- **Channels: two routers share both channels.** AP-A (Room A) and AP-B (Primary bedroom) are both on channel 44
  (80 MHz) on 5 GHz and on channel 11 (40 MHz) on 2.4 GHz; AP-C (Room B) is on 149 and 2. Where both are heard
  (the living area: -55 to -62 dBm from each), they take turns on the same air.
- **Scans are incomplete:** one scan heard 2-6 of the 6 home networks (4.2 on average); AP-A's 2.4 GHz network
  was missing at 1 m. From walk 3 on, two scans per point are merged.
- **Bluetooth LE:** 19-40 packets per point down to about -95 dBm; 8 packets at -97 dBm (Room C); none at the
  Entry, the far side of the Primary bedroom, the Dressing room, Bath 2 and Balcony 1. The iPhone on the floor next
  to AP-A reaches through about two walls.
- **Point 22 (Bath 2):** the Mac left AP-A's 5 GHz network again (-89 dBm on 2.4 GHz, then no link): it is beyond
  AP-A's 5 GHz coverage, recorded as out of range rather than measured again.
- The network names on 5 GHz carry a " 5g" suffix, so the Mac's own router's beacons were not matched in this
  walk; they are in the all-networks record and the plan now names them exactly.

## Review with a professor of wireless communications (2026-11-19)

Points raised and how they were checked:

- **"RSSI is a relative value in dB, not dBm."** True of the 802.11 standard, where RSSI is a vendor-defined index.
  macOS reports `rssiValue` in dBm (Apple's documentation), converted by the chip maker's driver and not
  calibrated. Decision: absolute values are treated as approximate, comparisons on the same Mac as reliable, and
  only one source is used in any calculation. Written into [docs/wifi_method.md](../../docs/wifi_method.md).
- **"SINR, not only SNR."** Added, with the CCA rule of 802.11: co-channel networks heard above -82 dBm take turns
  (shared airtime), weaker ones add to the noise. Walk 2: in the living area the worst-case SINR (AP-B as noise)
  is -9 to 14 dB, yet the Mac used MCS 6-9; AP-A and AP-B hear each other at -53 to -62 dBm, so they take turns
  instead of interfering. Where the interferer was just below -82 dBm (Entry, Room C), SINR fell 7-11 dB below the
  SNR and both points had latency spikes (p95 77-78 ms).
- **"Behind a repeater the modulation of the hop between routers is not visible."** The three routers are
  connected by cable, so the Mac-to-router link is the only wireless hop. The MCS read on the Mac is the Mac's
  side only because that is all wdutil shows; the router's side is seen through the download speed.
- **Walls:** take the measured values as the basis; which walls are load-bearing is not known and a MacBook alone
  cannot find it. Matches the rejected wall model (held-out 12-14 dB): the maps stay interpolated from
  measurements.

## Network choice: replay of walk 2 (2026-11-19, `scripts/wifi_choice_check.py`)

Rule ([agent/device/wifi_choice.py](../../agent/device/wifi_choice.py)), from the scan only: SINR per network, the link
rate expected at that SINR from the walks' rate-against-SNR table; switch when another network is better by more
than 5 dB SINR and at least 10% faster, test both when within 5 dB, else stay. Replayed on the beacons recorded at
each point, against the latency of the network actually joined (AP-A 5 GHz):

| Advice | Points without spikes (p95 <= 50 ms) | Points with spikes or loss |
|---|---|---|
| stay | 12 | 0 |
| try | 1 | 0 |
| switch | 6 | 5 |
| own network not heard | 0 | 1 |

- All 5 points with spikes, and the point where the link was lost, were advised to leave AP-A; no point advised to
  stay had spikes.
- Bath 1, the Entry and Room C, the places where the Wi-Fi drops in daily use, were advised to switch to AP-C.
- Not independent: the rate table comes from the same walks. It shows that AP-A was poor where a switch was
  advised, not that the advised network is better there.

**Next, W4 (trial):** at three places advised to switch (Entry, Room C, Primary bedroom) and one "try" place
(Living area, west), join each candidate for about a minute (`scripts/wifi_trial.py`) and compare download, upload
and p95 with the ranking. Gate, written before the run: at the switch places, the advised network has a higher
download than AP-A and a p95 of 50 ms or less in at least 2 of 3; the try place is reported, not graded.

## Through the walls or around them? (2026-11-19, `scripts/coverage_paths.py`)

Question from the review: in an apartment of reinforced concrete, does the signal reach other rooms through the
walls or around them, through doors and corridors, bending at door frames? Two geometries per point from the
base drawing: the straight line with the walls it crosses, and the shortest route through open space and open
doors (Dijkstra on the floor grid, pulled taut; `coverage.DoorPaths`) with its bends in right angles.

| AP-A link, held-out points (5, 9, 12, 18) | Walk 1 | Walk 2 |
|---|---|---|
| Straight line, one loss per wall | 13.7 dB | 11.9 dB |
| IDW interpolation | 7.2 dB | 6.2 dB |
| Door path, loss per bend | **3.1 dB** | **4.4 dB** |
| Both paths, power sum | 6.6 dB | 5.5 dB |

- Leave-one-out on all 24 points: 4.7 and 5.4 dB for the door path, 10.0 for the wall model.
- Fitted: n 2.9-3.3, 10-12 dB per right-angle bend; the through-wall path, when fitted beside it, about 30 dB per
  wall (so it adds almost nothing).
- Bath 1 (below Room A): measured -78.5 / -80.3 dBm; door path -76.7 / -79.5; through the wall -64.3 / -65.9.
  Kitchen behind the router's wall (1.2 m): measured -69.9 / -70.8; door path -69.8 / -73.6; through the wall
  -45.6 / -48.9.
- Not the same for every router: for AP-B and AP-C (beacons, 13-23 points) the door path did not beat the wall
  model, and the fitted wall loss was 4-16 dB: some walls around them are lighter partitions. "Ignore the walls"
  holds around AP-A, not everywhere.
- Caveats: the door-path model was proposed after the walks, so this is not a pre-registered pass; 4 held-out
  points; the Entry's opening is closed in the drawing (its route snaps 1.1 m). Next check: the points of a new walk
  or of the trial W4.
