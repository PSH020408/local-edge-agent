# Wi-Fi and Bluetooth measurement: what is read, what is assumed, what was found

How the network agent turns what a MacBook's radios report into answers about coverage, about which of the home's
networks to use, and about which work a connection can carry. Every quantity is marked as measured, assumed, or not
yet measured. Details of each experiment: [evals/wireless/experiments.md](../evals/wireless/experiments.md).

## 1. What the Mac provides

| Source | Values | How they are used |
|---|---|---|
| Wi-Fi chip, through macOS CoreWLAN | RSSI (dBm), noise (dBm), channel, band and width of the link | Read 10 times a second for 10 s at two placements 30 cm apart, then averaged; SNR computed from them |
| Wi-Fi driver, through `wdutil` (Apple's diagnostic tool, administrator rights) | MCS index, spatial streams, transmit rate, channel utilisation (CCA), network name | Recorded once per point; the MCS index gives the modulation and coding through the 802.11ac table |
| Wi-Fi scan (CoreWLAN) | Beacon RSSI, channel and width of every nearby network | Two scans per point (one hears about 4 of the 6 home networks): coverage maps, SINR, choice of network |
| Bluetooth chip, through CoreBluetooth | RSSI of each advertising packet of an iPhone next to the router | Median over 20 s per point; the packet count marks the edge of range |
| `ping` to the router and the internet, 5 per second | Round-trip time | Median, 95th percentile, share above 50 ms, loss |
| `networkQuality` (Apple's tool) | Download and upload throughput | Recorded as reported |

**What "RSSI" means here.** In the IEEE 802.11 standard, RSSI is a relative index whose scale each chip maker
defines; it is not a power. macOS reports it differently: Apple documents CoreWLAN's `rssiValue` as an
"RSSI measurement (dBm)", a value the chip maker's driver converts to dBm. It is not calibrated against a
measuring instrument, so **absolute values are approximate, while comparisons made with the same Mac (between places,
between networks, between days) are reliable.** Everything below relies on comparisons, and on one source: the same
link read at the same moment differed by up to 5 dB between wdutil, CoreWLAN and the scan, so values from different
sources are never mixed in one calculation.

**Computation.**
- SNR [dB] = signal [dBm] − noise [dBm]. Both are powers relative to 1 mW on a log scale, so their difference is
  a ratio in dB.
- SINR [dB] = signal − (noise + interference), with the powers added in mW. The interference is the other networks
  heard on the same channel, split by the CCA level of the standard (−82 dBm on the primary 20 MHz channel):
  - **heard above −82 dBm:** the two networks hear each other and take turns (CSMA/CA). They do not lower each
    other's SINR; they share airtime. Counted as "shared", not added to the noise.
  - **heard below −82 dBm:** a radio cannot defer to it, so it overlaps and adds to the noise.
  - The **worst case**, every co-channel network added to the noise, is reported as well, as a bound.

**RSSI is the total power of one network's signal at the antenna,** through every path: through walls, reflected,
diffracted around door frames. Every propagation effect is therefore in the measured number, but the measurement
alone cannot split it into its causes.

**An advertising packet** is the short "I am here" broadcast a Bluetooth Low Energy device sends whether or not it
is connected; the Mac only listened, without connecting to the iPhone.

## 2. Physical effects: considered, not considered, not needed

### Considered

| Effect | Why it matters indoors | Seen in | Assumption | How it was handled |
|---|---|---|---|---|
| Distance loss | Walls and obstacles make the signal fall faster than in free space (n = 2) | RSSI | Distance is counted along the way the signal travels (below) | Distances from the floor plan (scale from a measured 3 m room width); the rate fitted to the measurements: n ≈ 3 |
| Walls: through or around? | Apartment walls are largely reinforced concrete; signal can pass through a wall or go around it through doors and corridors, bending at door frames (diffraction, reflection) | RSSI | Around AP-A, signal through the concrete walls is negligible | Through the walls: one loss per wall failed its held-out test (12-14 dB against a 5 dB gate). Around them: the shortest route through open space and open doors, with a loss per bend, passed it (section 3). The maps still interpolate the measurements (IDW), as decided before the walks; a professor of wireless communications agreed that measured values are the right basis when the walls are unknown |
| Fast fading | Reflections make the signal change within centimetres | RSSI fluctuation | Averaging in time and over two placements removes it | 10 Hz for 10 s at two placements 30 cm apart (the 5 GHz wavelength is 6 cm); at a fixed place, 10 s means stayed within ±0.3 dB |
| Thermal noise | The floor of reception: the signal must exceed it by enough SNR to be decoded at a given MCS | Noise | The chip's noise value is correct | Theory: −174 dBm/Hz + 10·log10(80 MHz) ≈ −95 dBm, plus a few dB of receiver noise; measured −92 to −94 dBm |
| Co-channel interference | Two of the three routers use the same channels (5 GHz channel 44, 2.4 GHz channel 11) | Scan (other networks' beacons), CCA | Interferers below −82 dBm add to the noise; stronger ones share airtime | SINR computed per network and per point (section 3); shared networks counted |

### Not considered

| Effect | Why it matters indoors | Status | Alternative |
|---|---|---|---|
| Which walls are concrete | Light partitions let signal through; concrete stops it | Around AP-A the walls cost about 30 dB each; around AP-B and AP-C the fits give 4-16 dB, so some of their walls are lighter | The building's structural drawings |
| Router-to-Mac modulation | The router picks its own MCS for what it sends | Not readable on the Mac (wdutil shows the Mac's side only) | Measured indirectly through the download speed; a packet capture could read it from frame headers (not tried) |
| Airtime actually used by the other networks | Shared airtime only costs when the other network is busy | CCA was 0-5% with the home idle | Measure under load |

### Not needed

| Effect | Why |
|---|---|
| Propagation time | About 33 ns over 10 m, against network latency in milliseconds |
| Doppler shift | The Mac stood still while measuring |
| Link between the routers | The three routers are connected by cable, so the Mac-to-router link is the only wireless hop |

## 3. Results

Two survey walks, 25 points each (48 valid points), the Mac joined to its own router (AP-A) on 5 GHz, AirDrop's
radio (AWDL) switched off during the walks because it causes latency spikes on this Mac (experiment W2).

| Quantity | Range |
|---|---|
| RSSI of the link | −86.9 to −36.8 dBm |
| Noise | −94 to −92 dBm |
| SNR | 7.1 to 56.2 dB |
| SINR (walk 2, from the scan; interference below −82 dBm added) | 3.7 to 55.0 dB |
| SINR, worst case (every co-channel network added) | −45 to 48 dB |

**Modulation against SNR** (the MCS the Mac uses for what it sends)

| SNR | RSSI | Modulation | Transmit rate |
|---|---|---|---|
| 33 dB and above | −60 dBm and above | almost always 256-QAM 5/6 (MCS 9) | 433 Mb/s |
| 20-32 dB | −72 to −58 dBm | 64-QAM to 256-QAM 3/4 (MCS 5-8) | 234-390 Mb/s |
| 15 dB and below | −79 dBm and below | QPSK (MCS 1-2) | 65 Mb/s and below |

- Spatial streams: 1 at every point (Mac to router). The download next to the router reached 433 Mb/s, which
  suggests two streams from the router to the Mac.
- The transmit rate reported by the driver matched the 802.11ac rate of the reported MCS at 36 of 48 points (75%);
  the MCS is a single reading of a value that changes packet by packet.

**SNR or SINR?** In the living area the other router on channel 44 (AP-B) is as strong as the Mac's own router.
Taking it as noise gives a worst-case SINR of −9 to 14 dB there, which would allow no more than the slowest
modulation; the Mac used MCS 6-9 (64-QAM to 256-QAM). The worst case is wrong because the routers hear each other
(−56 to −62 dBm, far above −82 dBm) and take turns: the cost of the shared channel is airtime, not SINR. Two
cautions: the MCS read on the Mac is for what the Mac sends, so the interference that matters for it is at the
router's receiver, not at the Mac; and with the home idle (CCA 0-5%) there was little traffic to share airtime with.

Where an interferer was just below −82 dBm, SINR and SNR part (both from the scan, so one source):

| Point | SNR | SINR | p95 to the router |
|---|---|---|---|
| Entry (16) | 15 dB | 4 dB | 77 ms |
| Room C (18) | 26 dB | 18 dB | 78 ms |

Room C is the one point where an SNR above 25 dB still had latency spikes; its SINR was lower. Two points are a
hint, not a result.

**Through the walls or around them?** For AP-A, four models were fitted to the link signal and scored on the
points held out before the walks ([scripts/coverage_paths.py](../scripts/coverage_paths.py)):

| Model | Held-out RMSE, walk 1 | Walk 2 |
|---|---|---|
| Straight line, one loss per wall | 13.7 dB | 11.9 dB |
| Interpolation of the measurements (IDW) | 7.2 dB | 6.2 dB |
| **Door path:** shortest route through open space and doors, a loss per bend | **3.1 dB** | **4.4 dB** |
| Both paths (power sum) | 6.6 dB | 5.5 dB |

Door path fitted: n ≈ 3, about 10-12 dB per right-angle bend; the through-wall part, where fitted, cost about
30 dB per wall, so little passes through them. This explains Bath 1, directly below Room A: through the wall it
is 3.7 m away and would get about −65 dBm; around it, out of Room A's door, along the hall and in through the
bathroom door, it is 6.4 m with almost two right-angle bends, predicted −79 dBm; measured −80 dBm. The kitchen
right behind the router's wall (1.2 m) is the same case: −71 dBm measured, −74 predicted, −49 through the wall.
Limits: the model was chosen after seeing the walks, the held-out set has 4 points, and for AP-B and AP-C it did
not help (their walls are lighter: 4-16 dB each). The Entry's opening is drawn closed in the base drawing, so
its route there is approximate.

**Latency to the router** (ping, the Wi-Fi segment)
- Strong signal (most points): median about 3 ms, 95th percentile 3-6 ms, no reply above 50 ms, no loss.
- Weak signal (some points between about −69 and −86 dBm): the median stays near 3 ms, but the 95th percentile
  rises to 77-119 ms with 12-14% of replies above 50 ms; loss of 6% at −86 dBm; 243 ms at the weakest point
  (SNR 7). Occasional spikes, not the average, are what break games and calls.
- Every point at or above −68 dBm (SNR about 25 dB) met a real-time criterion of p95 latency 50 ms or less.

**Throughput** (networkQuality)
- Download falls from 433 Mb/s next to the router to 81 Mb/s at the far side of the home.
- Upload stays near 100 Mb/s until the signal is weak, then drops to 16-23 Mb/s at −80 dBm.
- The same point can differ a lot between days (73 against 150 Mb/s), because the internet line and other
  users in the home are part of the measurement.

**Bluetooth LE** (iPhone on the floor next to the router): heard down to about −95 dBm, through about two walls;
no packets in the far rooms.

## 4. Against a published design guideline

Cisco's site-survey guidance for voice over Wi-Fi recommends −67 dBm at the cell edge and a noise floor no higher
than −92 dBm for an SNR of 25 dB, with neighbouring access points on different channels
([Cisco, Site Survey and RF Design Validation](https://www.cisco.com/en/US/docs/wireless/technology/vowlan/troubleshooting/8_Site_Survey_RF_Design_Valid.html)).
The threshold measured here, −68 dBm with SNR about 25 dB and a noise floor of −92 to −94 dBm, agrees closely.
Two routers sharing a channel goes against the same guidance. That guideline is for enterprise voice, not for
games or streaming.

## 5. Which network to use here

The places where the Wi-Fi drops (bathroom, entry, Room C) are where another router is 20-28 dB stronger than the
Mac's own. The home's networks have different names, so macOS does not move between them by itself. The agent
therefore advises, in two steps, so the connection is dropped only when it has to be
([agent/device/wifi_choice.py](../agent/device/wifi_choice.py)):

1. **Ranking from one scan (no disconnection).** For every network the Mac has joined before: SNR, SINR (rule
   above) and the link rate expected at that SINR from the rate-against-SNR table measured in the walks
   (other widths scaled by their data subcarriers; 2.4 GHz capped at 64-QAM).
2. **Decision.**
   - *stay*: the joined network is the best, or the best one would not be at least 10% faster;
   - *switch*: another network's SINR is higher by more than the measurement's spread (5 dB; repeated points
     differed by 3 dB RMS between days) and it is faster;
   - *try*: within the spread. Join each candidate for about a minute and keep the best
     ([scripts/wifi_trial.py](../scripts/wifi_trial.py)): link MCS, 30 s of pings, and download and upload. The
     download includes what the scan cannot show: the router's own modulation for what it sends. Each join drops
     the connection for a few seconds, so this runs only on request, never during a call.

**Check against walk 2** ([scripts/wifi_choice_check.py](../scripts/wifi_choice_check.py)): the advice at each point
from its recorded beacons, against how the joined network actually behaved there.

| Advice | Points without latency spikes | Points with spikes or loss |
|---|---|---|
| stay | 12 | 0 |
| try | 1 | 0 |
| switch | 6 | 5 |
| (own network not heard) | 0 | 1 |

Every point with spikes or loss was advised to switch, and none of the points advised to stay had them. The three
places where the Wi-Fi drops in daily use were all advised to switch to the router in Room B (AP-C). Limits: the
rate table comes from the same walks, and the check shows that the joined network was poor where a switch was
advised, not yet that the other network is better there; the trial (W4) tests that.

## 6. Status of each claim

| Measured and checked | Assumed for simplicity | Not measured yet |
|---|---|---|
| RSSI stable at a fixed place (±1 dB) | The chip's RSSI and noise are correct in absolute terms | Loss of a closed door |
| Repeat measurements differ by 3 dB RMS | Co-channel networks above −82 dBm take turns | Router-to-Mac modulation (only through download speed) |
| Noise floor −92 to −94 dBm | The router radiates equally in all directions | Interference under load (CCA was 0-5% idle) |
| AWDL causes the latency spikes | The signal varies smoothly between points (maps) | Whether the advised network is faster (trial W4) |
| AP-A's signal goes around walls, not through them | | The door-path model at new points (it was chosen after the walks) |
| Two routers share their channels | | Whether −68 dBm holds at other times |
| The routers are linked by cable | | |

## 7. Games, Apple's Continuity features and the connection card (added 2026-11-21)

- **Games are judged by steadiness, not the average.** A spike is a ping 20 ms or more above the player's usual
  ping; the share of late pings catches a steady pattern that merges into one long event. Pings at 10 Hz in the
  agent, 20 Hz during a game (`scripts/game_watch.py`), to the router and the internet at once, so each spike is
  placed on the Wi-Fi link or beyond the router.
- **AirDrop is the only Continuity setting that matters for the ping** (C1 twice without a game, G1 six real LoL
  matches): set to Everyone, 13-26% of the pings arrived 20-100 ms late and the router's p99 rose from 4-5 ms to
  87 ms; Handoff, iPhone widgets and AirPlay Receiver showed no effect. Day to day the four stay on; before a game
  the agent says to turn AirDrop off.
- **The card** speaks plain words by default (signal "excellent / good / fair / weak" from the SNR bands of the
  walks, "1 in 4 pings late", "may stutter") and shows the radio chain and the evidence on request ("자세히").
- **Bluetooth:** on or off, connected and paired devices, battery, in range (a paired device macOS reports a
  signal for), and three causes of dropouts the agent checks: battery 20% or less, signal below -80 dBm, and the
  Mac's Wi-Fi on 2.4 GHz, the band Bluetooth uses.
