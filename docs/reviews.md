# Design reviews: questions, answers and what changed

The questions this project was challenged with, the answers given at the time, what the data says, and what
was changed or planned because of them. Most come from reviews with a professor of wireless communications;
the rest are questions I asked myself while building it. Kept because the reasoning behind a design is as much a
part of the work as the code.

---

## Review 1 (2026-11-19): what the Mac's numbers mean

**"RSSI is a relative value in dB, not dBm. RSSI is interpreted too differently."**
- *Answer:* in the 802.11 standard RSSI is a vendor-defined relative index; macOS reports it in dBm (Apple's
  documentation for CoreWLAN's `rssiValue`), converted by the chip's driver and not calibrated.
- *Changed:* absolute values are treated as approximate and only comparisons on the same Mac as reliable; no
  calculation mixes two sources (the same link read by wdutil, CoreWLAN and the scan differed by up to 5 dB).

**"Think in SINR, not only SNR."**
- *Answer:* added, with the CCA rule of 802.11: another network on the same channel heard above -82 dBm shares
  airtime (the two take turns), a weaker one adds to the noise.
- *What the data said:* in the living area the other router on the same channel, counted as noise, gives a SINR
  of about 0 dB, yet the Mac used 256-QAM there: the routers take turns instead of interfering.

**"Behind a repeater you cannot see which modulation the hop between routers uses. Is that why you judged from
what the Mac sends?"**
- *Answer:* the Mac's side was used because it is all `wdutil` shows. The three routers turned out to be linked
  by cable, so the Mac-to-router link is the only wireless hop; the router's own modulation is seen indirectly
  through the download speed.

**"Walls: go by the measured values. Which walls are what cannot be known from a MacBook."**
- *Changed:* the coverage maps interpolate the measurements (the wall model had failed its test anyway, 12-14 dB
  error). The door-path model that came later is used to explain a dead spot, not in any verdict.

## Review 2 (2026-11-23): why build it, and why with an LLM

**"Clicking the Wi-Fi menu already shows the strongest network on top. Why build this?"**
- *Answer given:* even on the strongest network the connection sometimes failed; I wanted something that tells
  me why and what to do.
- *What the data adds:* signal strength is not connection quality. In my room the signal was at its best
  (-46 dBm, 256-QAM, 433 Mb/s link) while 13% of the pings arrived 20-100 ms late; the cause was AirDrop, shown
  in six real games. The menu shows full bars either way. It also does not show whether a problem is on the Wi-Fi
  or the internet line, which routers share a channel, or whether a game or a call will work; and macOS does not
  move between networks with different names by itself.

**"Why an LLM at all? The functions are few. A deep-learning or classification model could do this."**
- *Answer given:* an LLM understands plain language best, so one question can trigger the signal reading, the
  ping test and the advice; that input and output suit people without the background.
- *The part that needed saying more clearly:* the LLM does not make the decision. Verdicts come from rules set by
  experiments and by published requirements (Microsoft Teams for calls, Netflix for 4K), which is close to what a
  classifier would do, and explainable. The LLM understands the question and explains the result, and code checks
  every number it writes against the measurements.
- *Why not train a classifier:* there is no labelled data to train it on (about fifty measured places and six
  games). With so little data, rules from physics and published standards are more reliable and can say why.
  Once users' answers to "did it actually cut out?" accumulate, the thresholds could become a small classifier,
  with the LLM still the interface.
- *Why an LLM is still the right interface for the project:* the network agent is one part of a single assistant
  that also summarises documents with page citations, reads images and equations, and turns worded engineering
  problems into calculations; those need a language model. Small models (4B and 1.7B) run on the Mac, so nothing
  leaves it.

**"Isn't a chatbot enough for this?"** (my own follow-up)
- *For the network part, largely yes, and that is by design.* A chatbot alone would not carry the rest of the
  assistant (summarising papers with page citations, reading equations from page images, turning worded
  engineering problems into calculations), while one large model for everything would be slow and wasteful on a
  laptop. So the work is split into tiers, and each job goes to the lightest tier that passed its tests:

  | Tier | Used for | Typical time |
  |---|---|---|
  | Code and rules | Routing by keywords, measuring, every verdict and the network card, all arithmetic, checking the numbers in each answer | milliseconds to the length of the measurement |
  | `qwen3:1.7b` | Routing only when the keyword rules tie | under 1 s |
  | `qwen3:4b-instruct` | Short answers about the Mac and its network, written from measurements | 2-5 s |
  | `qwen3:8b` | General questions, choosing tools (the `--fast` profile) | seconds |
  | `qwen3-vl:8b-instruct` | Reading images and document pages | 10-60 s per question |
  | `qwen3:14b` | Documents and planning image questions, where search and citation needed the larger model | 1-2 min per question |

- *What the logs show for the network agent:* it sits at the light end. In the final live run all 15 questions
  were routed by the rules (the 1.7B router was never needed) and the card is built by code; the 4B model wrote
  only the two or three sentences under it.
- *What is left to measure, experiment L1:* whether even that light model earns its place in the network
  answers. (1) 30 new phrasings of network questions (typos, slang, an unknown game, "and for a call?"), routed
  by rules alone against rules plus the model; (2) the same measurements shown as the card alone and as the card
  with the model's text, to people without the background. If the model adds little, the network agent answers
  with the template by default (the fallback already exists) and calls the model only when the rules do not
  understand.

**"Walls, diffraction and interference need not be modelled; what the receiver gets is what counts."**
- *Agreed, and already so:* the maps and the verdicts use only what the Mac received. The one blind spot of the
  receiver's view: the Mac reports only its own sending modulation, so the router's side is judged through the
  download speed.

---

## Limits stated first

- The game rule (a ping 20 ms over the usual counts as a jump) was set with one player and one game.
- Pings go to the router and to a public server (1.1.1.1), not to the game's server; ICMP pings are not the
  game's own UDP traffic, which is why six real matches were measured as well.
- Every threshold comes from one home with three routers; another home is the next test.
- The door-path model was proposed after the walks that it fits; a new walk is its real test.
- RSSI is uncalibrated; comparisons are reliable, absolute values approximate.
