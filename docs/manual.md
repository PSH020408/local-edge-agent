# User manual

Local Edge Agent is an assistant that runs entirely on your MacBook. You type a question in plain words, in
English or Korean; it calculates, reads your images and documents, checks the Mac's own sensors and measures
its Wi-Fi and Bluetooth, then answers in the language of the question. Every model runs on the Mac through
Ollama: no question, file or measurement leaves the machine.

This manual follows the order in which the agent was built. Each chapter says what you can ask, how to ask it,
what you get back, and, briefly, why it works the way it does.

**Contents**
1. [Install](#1-install)
2. [Start a session](#2-start-a-session)
3. [Stages 1-2: engineering math and time](#3-stages-1-2-engineering-math-and-time)
4. [Stage 3: images](#4-stage-3-images)
5. [Stages 4-6: documents](#5-stages-4-6-documents-pdf-and-powerpoint)
6. [Stage 7: this Mac](#6-stage-7-this-mac)
7. [Stage 8: Wi-Fi, network and Bluetooth](#7-stage-8-wi-fi-network-and-bluetooth)
8. [Troubleshooting](#8-troubleshooting)
9. [Privacy and safety](#9-privacy-and-safety)

---

## 1. Install

**You need:** a Mac with Apple silicon (developed on an M4 Pro with 24 GB of memory), Homebrew, Python 3.11 or
later, Apple's Command Line Tools (`xcode-select --install`: the Wi-Fi and Bluetooth readers are small Swift
programs compiled on first use), and about 25 GB of free disk space for the models.

| Step | Command | Why |
|---|---|---|
| 1. Get the code | `git clone https://github.com/PSH020408/local-edge-agent.git && cd local-edge-agent` | |
| 2. Install Ollama | `./scripts/setup_ollama.sh` | Ollama runs the language models on the Mac's GPU |
| 3. Download the models | see the table below | Each job uses the smallest model that passed its tests |
| 4. Python environment | `python3 -m venv .venv && source .venv/bin/activate` | Keeps the agent's libraries apart from the system's |
| 5. Libraries | `pip install -r requirements.txt` | NumPy, SciPy, SymPy and Pint for the math tools; Pillow, pypdfium2 and python-pptx for images and documents. The agent core itself uses only the Python standard library |
| 6. Check | `python -m unittest discover -s tests` | About 460 offline tests, no model or network needed: confirms the install |
| 7. The `edge` command | `./scripts/install_shell.sh` | Starts the agent from any folder by typing `edge`, or a Korean question straight at the prompt (section 2) |
| 8. First start | `edge` (or `python main.py`) | |

| Model | Size | Used for | Why this one |
|---|---|---|---|
| `qwen3:8b` | about 5 GB | general questions, choosing tools | Fast enough for a conversation, reliable at calling tools |
| `qwen3:14b` | about 9 GB | documents, planning image questions | Search across pages and citation needed the larger model |
| `qwen3-vl:8b-instruct` | about 6 GB | reading images and document pages | The vision model that read equations and charts best in the tests |
| `qwen3:4b-instruct` | about 2.5 GB | answers about the Mac and its network | Writes a short answer from measurements in 2-5 s; the thinking variant wrote out its reasoning instead |
| `qwen3:1.7b` | about 1.4 GB | sorting a question when the keyword rules tie | Under 1 s |

Pull each with `ollama pull <model>`.

**Optional: administrator rights for two commands.** Some Mac answers are more complete with them; without
them, the agent says what it could not measure instead of guessing.

| Rule | What it gives | Set up with |
|---|---|---|
| `powermetrics` without a password | CPU, GPU and Neural Engine frequency and power, second by second (heat and performance answers) | `echo "$(whoami) ALL=(root) NOPASSWD: /usr/bin/powermetrics" \| sudo tee /etc/sudoers.d/powermetrics && sudo chmod 440 /etc/sudoers.d/powermetrics && sudo visudo -c` |
| `pmset -b powermode 0/1/2` without a password | Switching the battery energy mode for a long job | the same pattern with `/usr/bin/pmset -b powermode 0, /usr/bin/pmset -b powermode 1, /usr/bin/pmset -b powermode 2` in `/etc/sudoers.d/powermode` |

Both rules are limited to exactly those commands and are removed by deleting the file. Wi-Fi measurements ask
for your password once per session instead (`sudo -v`), because Apple's Wi-Fi tool, `wdutil`, needs it.

---

## 2. Start a session

```bash
edge                          # the menu below
edge 배터리 상태 어때?           # answered at once, then the session goes on in the detected mode
배터리 상태 어때?               # the same without "edge" (Korean questions only, see below)
```

Without the shell command: `source .venv/bin/activate && python main.py` (the same options).

**The menu.** `edge` alone shows what the agent does, one mode per kind of question:

| No. | Mode | What it covers | Engine |
|---|---|---|---|
| 1 | Device diagnosis (this Mac) | battery health and charging, energy mode, CPU/GPU load, heat, memory, storage and ports | sensor readings + `qwen3:4b` |
| 2 | Network diagnosis (Wi-Fi, Bluetooth) | connection quality, whether a game, call or 4K stream will work, which router to join, Bluetooth dropouts | measurements (ping, speed, scan) + `qwen3:4b` |
| 3 | Image analysis | describing photos, boards and circuits, charts, handwriting and signs, equations to LaTeX | `qwen3-vl:8b` + `qwen3:14b` planning |
| 4 | Documents and papers (PDF, PPT) | summaries, equations explained, tables and financial statements, exam questions, page citations | `qwen3:14b` + page reading |
| 5 | Engineering calculation | units, dB and link budgets, circuits, complex numbers, dates and time zones | tools + `qwen3:8b` / `qwen3:14b` |
| 6 | Free question (auto) | any question; the mode is chosen for you | keyword routing |

- Type a number to enter a mode, or type a question straight away (mode 6). The prompt shows the mode
  (`edge·network>`); `/menu` shows the menu again, `?` examples, `/reset` a new conversation, `/exit` ends.
- *Why modes:* inside a mode the question skips routing and goes straight to that mode's agent, and choosing the
  mode loads its models into memory in the background while you type, so the first answer does not wait for a
  model to load (20-40 s for the larger ones). Routing is still applied inside a mode where it matters: a battery
  question asked in the network mode is answered as a battery question.
- **Files:** drag a file onto the terminal to put its path in the question: `~/Downloads/paper.pdf 요약해줘`.
  A file outside the project folder is copied into `inbox/` first (the file tools read only inside the project),
  and the question is rewritten to that copy. Only files named in the question are copied.
- Ask in English or Korean; the answer comes back in the same language. English questions start with `edge`.
- **Typing a question without `edge`:** zsh calls a hook when the first word is not a command; the hook passes
  the line to the agent only when that word is Korean, so a typo like `gti status` still says "command not
  found". The installer also sets `no_nomatch`, so a `?` at the end is not read as a file pattern. Quotes and
  brackets are still read by the shell: use `edge` with the question in quotes for those. Remove the hook with
  `./scripts/install_shell.sh --no-hook`, everything with `--remove`.
- Options: `--mode network` starts in a mode, `--once` answers and exits (for scripts).
- **Which model answers:** each kind of question has its own (the Mac and its network: a 4B model over code;
  images and documents: the vision model and the 14B planner). For everything else the model is chosen per
  question: the light `qwen3:8b`, or the heavy `qwen3:14b` when the question looks hard (four or more quantities,
  several parts, a derivation or a comparison) or the light model could not finish. A line under your question
  shows which one and why, e.g. `model: qwen3:14b (heavy: 4 quantities)`. *Why:* most everyday questions are
  lookups and single conversions that the light model answers in seconds; the heavy one is slower and takes
  more memory, so it is called only when needed.
- **Options:** `--fast` and no flag both choose per question; `--model qwen3:14b` fixes one model; `--accurate` is
  a recorded experiment (second looks and votes) that was 3-4 times slower and less accurate, kept for comparison.

**How every answer is made.** A keyword router sends the question to the right agent; code does the exact work
(computes, reads twice and compares, measures, diagnoses); a local model writes the answer from that result;
code then checks that every number in the answer appears in the measurements or the document, rewrites once
if not, and falls back to a template. *Why:* a small local model explains well but cannot be trusted with
arithmetic or facts it was not given.

---

## 3. Stages 1-2: engineering math and time

**What you can ask:** calculations with physical units (the result's dimension is checked), decibels and link
budgets, complex numbers, number bases, physical constants, unit conversion; the current time, time zones,
date arithmetic.

**Try:**
- `A 1,200 kg car brakes from 90 km/h to 0 in 40 m. What is the braking force?`
- `A 2 W transmitter, +10 dBi antenna, 100 dB path loss, +3 dBi receive antenna: received power in dBm?`
- `What is the equivalent resistance of 100 Ω, 220 Ω and 470 Ω in parallel?`
- `What time is it in New York when it is 9 am in Seoul?` · `What date is 100 days after March 3?`

**What you get:** the result with its unit and the steps, computed by the tool.

**Why it works this way:** the model only chooses the tool and its inputs; the tool computes. A link-budget
miss in testing (watts read as dBm) led to the unit check and more decibel conversions.

**Tested:** 6 of 7 unseen engineering problems right.

---

## 4. Stage 3: images

**How to ask:** put the image path in the question.

**What you can ask:** what an image shows; text in it (signs, labels, handwriting); formulas as LaTeX; charts;
circuit boards and diagrams; counting and comparing.

**Try:**
- `board.jpg What microcontroller is this board built around?`
- `formulas.png Transcribe these formulas in LaTeX and explain each one.`
- `ber_chart.png Which modulation needs the lowest Eb/N0 for a bit error rate of 10^-6?`

**What you get:** a description, with text read twice at two zoom levels and compared by code. If the image
does not show something, the answer says "not shown".

**Why:** one reading of small text is often wrong; two readings that agree are rarely wrong together, and a
disagreement is reported instead of guessed.

**Tested:** 12 questions: 4 fully right, 7 mostly right, 1 wrong; 4 of 4 questions about things not in the
image answered "not shown".

---

## 5. Stages 4-6: documents (PDF and PowerPoint)

**How to ask:** put the document path in the question.

**What you can ask:** summaries, explanations and practice questions from lecture slides and papers; numbered
equations; tables, financial statements and charts, with ratios, totals and growth computed by code.

**Try:**
- `notes/lecture4.pdf Make three exam questions with answers and the source pages.`
- `papers/paper.pdf Write equation (3) in LaTeX and explain each symbol.`
- `reports/annual.pdf Compute the operating margin for 2025.`

**What you get:** every statement with its page, `[p.N]`. A question the document does not answer gets "not in
the document", only after a second search.

**Why:** citations let you check each claim in seconds; searching by passage instead of by page raised the
paper holdout from 38% to 74% fully correct.

**Tested:** lecture slides 76% fully correct on unseen documents; 28 equations read with 0 wrong; "not in the
document" 20 of 20.

---

## 6. Stage 7: this Mac

**How to ask:** about the machine, in plain words. No file path needed.

| Topic | Try |
|---|---|
| Battery health | `Do I need to replace my battery?` |
| Charging | `My charger is plugged in but the battery is going down` |
| Energy mode | `Which power mode should I use on battery?` |
| CPU, GPU, heat | `Which program is eating my CPU?` · `Why is my Mac so hot?` |
| Memory, storage, ports | `Which app is using the most memory?` · `What is connected to my USB ports?` |
| Work that fits now | `Can I edit 4K video now?` · `게임 돌려도 돼?` |

**What you get:** in 5-15 s, a diagnosis from the sensors: the state, the cause if there is a problem, what to
do. For example, battery health against Apple's limits (80% capacity, 1,000 cycles), or for a kind of work
"yes", "with care" or "not now", and on battery for how long.

**Why:** the agent reads the same registries and counters macOS uses (battery, power, thermal pressure, memory,
storage, and `powermetrics` when allowed), captures 10 s of readings for performance questions, and compares
them with limits and with this Mac's own normal. Answers about energy modes use speeds measured on this Mac.

**Limits:** fan speed and chip temperature have no public interface on this Mac; the agent says so.

Full list of questions per component: [device_questions.md](device_questions.md).

---

## 7. Stage 8: Wi-Fi, network and Bluetooth

**How to ask:** in plain words, about what you want to do. Run `sudo -v` once first (Apple's Wi-Fi tool needs
the password). Add `자세히` (in detail) to any question for the engineering view.

| You want to know | Try | Time |
|---|---|---|
| Which Wi-Fi to use here and what works on it | `여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어?` | about 1 min |
| Whether you can play now (any online game) | `게임 해도 돼?` · `배그 핑 괜찮아?` · `Can I play games now?` | 35 s |
| A video call | `화상 통화 해도 괜찮을까?` | 50 s |
| Speed, 4K | `인터넷 속도 어때? 4K 스트리밍 돼?` | 30 s |
| Why it is slow | `와이파이 왜 이렇게 느려?` · `Is the problem my Wi-Fi or my internet provider?` | 15 s |
| Your ping | `핑 몇이야?` | 15 s |
| Bluetooth | `에어팟 자꾸 끊겨` · `블루투스 스피커 신호 괜찮아?` | 15 s |

**What you get:** a card first, then two or three sentences.

```text
와이파이: Home-A-5G · 신호 매우 좋음 · 인터넷 속도 받기 260 / 보내기 158 Mb/s
핑: 평소 7 ms, 자주 튐 (8번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅   4K ✅   10 GB 받기 약 5분
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임 팁: AirDrop을 끄세요 (시스템 설정 → 일반 → AirDrop 및 연속성)
```

How to read it:
- **Signal** (excellent, good, fair, weak) comes from the signal-to-noise ratio. *Why these bands:* on this Mac
  the fastest modulation (256-QAM) was used from about 33 dB and the slowest from below 15 dB.
- **Ping** is the usual delay and how often it jumps. *Why "how often" and not the average:* in a game a short
  jump loses the fight, not the average; a ping 20 ms over your usual counts as a jump.
- **Verdicts** follow what each use needs: calls from Microsoft Teams' requirements (delay under 100 ms, jitter
  under 30 ms, loss under 1%, 1.5 Mb/s each way), 4K from Netflix's 15 Mb/s, games from the jumps, large files
  as a time.
- **Why it jumps / what to do:** the cause the measurements point to. "AirDrop" comes from experiments in a real
  home: with AirDrop set to Everyone, 13-26% of the pings arrived 20-100 ms late, in six real League of Legends
  matches as well; Handoff, iPhone widgets and AirPlay made no difference, so the tip names AirDrop only.
- **Recommendation:** another saved network that is clearly better here (by more than the 5 dB a repeated
  measurement varies). Networks whose password the Mac has not saved are listed but not recommended.
- **Bluetooth** answers list connected and paired devices with battery, which are in range, and why audio or a
  mouse cuts out: low battery, weak signal, or the Mac's Wi-Fi on 2.4 GHz, the band Bluetooth also uses.

With `자세히` the card shows the chain behind the verdicts: signal (dBm) → SNR and SINR → modulation (MCS) →
link rate, the bottleneck (the Wi-Fi link or the line beyond the router), and every network heard here.

More real answers: [examples/network.md](examples/network.md).

**Tools for a closer look** (in the terminal, `sudo -v` first):

| Command | What it does |
|---|---|
| `python scripts/wifi_here.py --label "Room A" --quick` | The card for this place, other networks predicted, no disconnection |
| `python scripts/wifi_here.py --label "Room A"` | Joins each strong saved network for about a minute and compares them in a table; ends on the best |
| `python scripts/game_watch.py --label lol --minutes 25` | Runs during a game: every ping jump, live, and whether it started on the Wi-Fi or beyond the router |
| `python scripts/game_watch.py --label lol --awdl off` | The same with AirDrop's radio kept off during the game (back on at the end) |
| `python scripts/continuity_test.py` | Tests each Apple Continuity feature in turn (about 20 min) |
| `python scripts/wifi_walk.py --plan logs/home/plan.json` | A coverage survey on your own floor plan, point by point |

**Why the Wi-Fi part is built this way:** the radio values (signal, modulation, link rate) explain and predict,
but what you feel is delay, loss and speed, so the verdicts come from those. Every rule was set by an experiment
written down before it ran, with its prediction and pass mark: [evals/wireless/experiments.md](../evals/wireless/experiments.md).
The method, the assumptions and their limits: [wifi_method.md](wifi_method.md).

**Limits:** the signal is what macOS reports, not calibrated (comparisons are reliable, absolute values
approximate); the Mac shows only its own sending modulation; the game rule is calibrated on one player and one
game.

---

## 8. Troubleshooting

| Symptom | What to do |
|---|---|
| An error about connecting to Ollama | Ollama is not running: open the Ollama app or run `ollama serve` |
| The first answer takes 20-40 s | The model is loading into memory; the next answers are faster. Choosing a mode from the menu loads it while you type |
| `zsh: no matches found` | The question has a `?` and was typed without the installed `edge`: run `./scripts/install_shell.sh` and open a new tab, or put the question in quotes |
| A Korean question says "command not found" | The hook is not loaded: open a new terminal tab; if another tool also defines `command_not_found_handler` in `~/.zshrc`, the later one wins |
| "Run `sudo -v` first" | Wi-Fi measurements need your password; it is remembered for about 5 minutes |
| "연결된 와이파이" instead of the network's name | Newer macOS hides it from `wdutil`; the agent then reads it through CoreWLAN, which may ask to allow Location Services for Terminal |
| A Bluetooth permission window | Allow Terminal to use Bluetooth (needed for the iPhone signal scan) |
| An answer seems wrong | Ask again with `자세히` to see the measurements behind it |

---

## 9. Privacy and safety

- Everything runs on the Mac; nothing is sent to a cloud service.
- File tools work only inside the workspace folder, and anything that changes a file asks first.
- The Mac readers only read. The single setting the agent can change is the battery energy mode, and only through
  the limited rule above.
- Measurement logs, the floor plan and the real names of networks and devices stay in `logs/`, which is not
  uploaded; examples in this repository use replaced names.
