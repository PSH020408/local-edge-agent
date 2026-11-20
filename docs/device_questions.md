# User guide: asking about this Mac

The device agent answers questions about this MacBook from its own sensors: battery, charging, processor,
graphics, heat, memory, storage, ports, the work the machine can take on now, and its Wi-Fi, network and
Bluetooth connections. Ask in plain language, in
English or Korean; the answer comes in the language of the question.

```bash
source .venv/bin/activate
python main.py
you> How is my battery health?
```

Battery questions are answered in about 5 seconds; questions about performance take about 15 seconds, because
the agent first measures the processor, graphics, power and heat for 10 seconds. Network questions take 15-40
seconds (the pings run for 10 or 30 seconds; a speed test adds about 20).

---

## 1. Battery: health, lifespan and usage
<!-- agent: battery -->

**Covers:** maximum capacity and condition against Apple's service limits (80%, 1,000 cycles), charge cycles,
cell balance, battery temperature, charge and energy left, time left on battery, and why the battery drains.

**Example questions**
- `How is my battery health?`
- `Do I need to replace my battery?`
- `How many charge cycles does my battery have?`
- `Are my battery cells balanced?`
- `Is my battery temperature too high?`
- `How long will my battery last?`
- `Why is my battery draining so fast?`
- `Can I keep working on battery?`
- `How much charge is left on my battery?`

## 2. Power adapter and charging
<!-- agent: battery -->

**Covers:** time to full charge, the adapter's rating against the power it delivers, a battery that drains while
the adapter is connected (adapter at its limit, adapter delivering nothing, or charge held by macOS), and why
charging stopped.

**Example questions**
- `How long until my battery is fully charged?`
- `My charger is plugged in but the battery is going down`
- `Is my charger supplying enough power?`
- `Why did my Mac stop charging at 90%?`

## 3. Energy mode
<!-- agent: battery -->

**Covers:** the energy mode for the adapter and for the battery (Automatic, Low Power, High Power), with the
speeds measured on this Mac in each mode.

**Example questions**
- `Should I turn on High Power Mode?`
- `Which power mode should I use on battery?`

## 4. Processor (CPU)
<!-- agent: performance -->

**Covers:** CPU use across the 14 cores, the clock of each core cluster, CPU power, load average, and the
program holding the processor.

**Example questions**
- `Is my CPU busy right now?`
- `Which program is eating my CPU?`
- `What are my CPU clocks now?`
- `Why is my Mac so slow?`

## 5. Graphics (GPU)
<!-- agent: performance -->

**Covers:** GPU use, clock and power, and a GPU held at its lowest clocks by thermal management.

**Example questions**
- `Is my GPU busy?`
- `My Mac suddenly got very slow`

## 6. Thermal state and chip power
<!-- agent: performance -->

**Covers:** macOS thermal pressure, the power of the CPU, GPU and Neural Engine, and the cause of heat.

**Example questions**
- `Is my Mac overheating?`
- `Why is my Mac so hot?`

## 7. Memory (RAM)
<!-- agent: performance -->

**Covers:** memory available, compression and swap, the apps holding the most memory, and the models the
local AI keeps loaded.

**Example questions**
- `Is my memory enough?`
- `Which app is using the most memory?`
- `Is my RAM full?`

## 8. Storage (SSD)
<!-- agent: performance -->

**Covers:** free space and health of the internal SSD.

**Example questions**
- `How much storage is left?`
- `Is my SSD healthy?`

## 9. Ports and buses
<!-- agent: performance -->

**Covers:** the three USB-C ports (Thunderbolt 5 / USB4, up to 120 Gb/s each), what is connected to them, USB
devices, and the internal SSD's model.

**Example questions**
- `What is connected to my USB ports?`
- `Is anything plugged into my Thunderbolt ports?`
- `What SSD is inside my Mac?`

## 10. Data transfer speeds
<!-- agent: performance -->

**Covers:** memory bandwidth and SSD read and write speed, measured on request in about 5 seconds and compared
with this Mac's normal. The CPU and GPU share one memory, so the memory bandwidth is also the CPU-GPU transfer
speed.

**Example questions**
- `Is my memory bandwidth normal?`
- `Are the transfer speeds between RAM, SSD, CPU and GPU normal?`

## 11. Workload capacity: what the Mac can take now
<!-- agent: performance -->

**Covers:** whether everyday work fits the machine's present state, from loads measured on this Mac: documents
and web, 4K video, video calls, photo editing, coding, 4K video editing, games, 3D rendering and model training.
On battery, the time each would last. Also the local AI's own jobs.

**Example questions**
- `What can I do on this Mac right now?`
- `Can I edit 4K video now?`
- `Can I play a demanding game now?`
- `How long can I game on battery?`
- `Can I train a deep-learning model now?`
- `Is it ok to do photo editing on battery?`
- `Can I run a document question now?`
- `Can I run an image analysis now?`

## 12. Wi-Fi, network and Bluetooth
<!-- agent: network -->

**Covers:** where a slow connection comes from, hop by hop: the radio link (signal, noise, SNR, modulation),
the Wi-Fi segment (latency, spikes and loss to the router, and AirDrop's radio, AWDL, which causes latency spikes
on this Mac), the internet beyond the router, and DNS. Verdicts for games, video calls, 4K streaming, browsing
and messaging from the measured latency, loss and speed, not from the signal alone. Throughput and latency under
load, nearby networks on the same channel, and the signal of connected Bluetooth devices, when asked.
Which of the networks this Mac has joined before is best at the current place: SNR and SINR from one scan and
the link rate expected from the rate measured on this Mac; "about equal" when the difference is within the
measurement's 5 dB spread (then `scripts/wifi_trial.py` tests each one for about a minute).
Questions about a game or a call measure for 30 s; others for 10 s.

**Example questions**
- `Why is my Wi-Fi slow?`
- `Is the problem my Wi-Fi or my internet provider?`
- `What is my ping?`
- `Can I play an online game on this Wi-Fi now?`
- `Is my internet connection good enough for a video call?`
- `How fast is my internet? Can I stream 4K?`
- `Is my Wi-Fi channel crowded?`
- `Which Wi-Fi should I use here?`
- `여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어?` (the connection card in everyday words: about 1 minute)
- `여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어? 자세히` (the same with SNR, modulation, link rate and the bottleneck)
- `게임 해도 돼?` / `배그 해도 돼?` / `Can I play games now?` (any game by name, or games in general)
- `롤 지금 해도 돼? 핑이 가끔 튀어` (spikes of 20 ms or more over your usual ping in 30 s, and whether the Wi-Fi caused them)
- `여기서 어느 와이파이에 연결하는 게 좋아?`
- `Is my Bluetooth speaker signal ok?`

## 13. Out of scope
<!-- agent: performance -->

**Not measured** (no public interface on this Mac) and **left to the user's settings**. The agent says so
instead of guessing.

**Example questions**
- `What is my fan speed in rpm?`
- `What is my CPU temperature?`
- `Is my screen brightness right?`

<!-- agent: none -->
General-knowledge questions are answered by the general assistant, not by the device agent:
- `Explain how lithium-ion batteries work`
- `What is the outlook of the memory chip market?`

---

## How an answer is made

1. Keyword rules send the question to the battery, performance or network agent (a small model decides only
   when the rules tie).
2. The agent takes its readings.
3. **Code** makes the diagnosis from thresholds and rules; no language model judges the machine.
4. A small local model writes the findings as a few sentences. Every number in the answer is checked against the
   measurements, and an answer with a number that was not measured is rewritten.

`tests/test_device_questions.py` routes every example question in this guide and fails if one reaches a
different agent than its section states. Measurement details: `evals/device/`.

## Tools outside the chat

```bash
python scripts/speed_check.py              # is this Mac as fast as it normally is? (20 s)
python scripts/run_controller_test.py      # the power controller holding training at a set power (5 min)
python scripts/run_workloads.py --tier 2   # synthetic everyday workloads and their power
```
