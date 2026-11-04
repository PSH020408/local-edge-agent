# Vision Test Set

Manual test set for the vision model (`describe_image` tool). Ask each question one at a time and compare the answer with the expected facts below. With `ollama run`, every command is a fresh session; inside `main.py`, use `/reset` between questions.

To run the whole set at once: `python scripts/run_vision_set.py --fast` or `--accurate` (questions and key facts in `cases.toml`; the report goes to `logs/vision_runs/`). Each case starts a fresh conversation. The key-fact count is only an indicator; answers are still scored by reading them.

Images are kept locally in `evals/vision/images/` and are **not committed** (see `.gitignore`). Several are third-party content (schematic, sheet music, social media screenshots, a cartoon frame, a lecture capture) or personal photos that should not be redistributed. This file records what each image contains so the results stay reproducible.

## Coverage

The set is built along two axes: the visual skill being tested, and the domain. Domains follow the intended use of this agent (information and communication engineering, embedded systems, personal finance, music, everyday images), while the skills are spread so a good score is not limited to clean screenshots.

| # | File | Skill | Domain | Source type | Language |
|---|---|---|---|---|---|
| 01 | `01_esp32_schematic.jpg` | Dense technical drawing, small labels | Embedded systems | Digital drawing | EN |
| 02 | `02_sheet_music_tab.png` | Music notation | Music | Digital document | EN |
| 03 | `03_tweet_thread_en.jpg` | Conversation, humor | Social media | Screenshot | EN |
| 04 | `04_korean_comments.jpg` | Korean OCR, humor | Social media | Screenshot | KO |
| 05 | `05_korean_infographic_finance.png` | Slide structure | Finance | Digital graphic | KO |
| 06 | `06_ber_chart.png` | Chart reading, comparison | Communications | Digital plot | EN |
| 07 | `07_dft_formula.gif` | Formula transcription | Signal processing | Digital image (GIF) | Math |
| 08 | `08_cartoon_scene.webp` | Scene without text | Animation | Low-resolution frame (WebP) | — |
| 09 | `09_handwriting_sketch.jpg` | Handwriting OCR, drawing style | Personal notes, anime art | Phone photo of paper | KO, EN |
| 10 | `10_night_street_photo.jpg` | Real photo, low light, signs | Everyday scene | Phone photo | KO |
| 11 | `11_aquarium.webp` | Scene without text, counting | Everyday scene | Camera photo (WebP) | — |
| 12 | `12_lecture_screen_photo.jpg` | Photo of a slide, small blurry text | Lecture material | Low-resolution capture | KO |

Formats covered: JPEG, PNG, GIF, WebP. Resolutions from 284×213 to 1932×2576.

## Scoring

| Mark | Meaning |
|---|---|
| ✅ | All key facts correct |
| ⚠️ | Mostly correct, minor misreads |
| ❌ | Key facts wrong |
| 👻 | Hallucination: states something that is not in the image |

Also record: seconds per image, and whether the image format was accepted.

## Main cases

### 01 — Embedded system schematic
- **File:** `01_esp32_schematic.jpg` (1920×1444)
- **Question:** `What microcontroller module is this board built around? Which GPIO pins connect to the SD card (CS, MOSI, SCK, MISO) and to the OLED display (SDA, SCL)? What voltage regulator is used?`
- **Expected:**
  - Title "ESP-WROOM-32 Project Board"; main module U2 ESP-WROOM-32 ("Use Arduino IDE, DOIT ESP32 DEVKIT V1")
  - Micro SD card module U5: CS = G05, MOSI = G23, SCK = G18, MISO = G19
  - OLED U3 SSD1306 (128×64): SDA = G21, SCL = G22 (I2C), with 4.7k pull-ups (R36, R37)
  - Regulator U1 AMS1117-3V3 with C8 10 µF and C7 22 µF
  - Also on the board: FTDI header U4 (logic levels 3V3), Reset S1 on EN (R43 10k, C5 100 nF), Boot S2 on G0 (R35 4.7k), P-MOSFET Q1 AO3401 switching "3V3_Switched", N-MOSFETs Q2/Q3 IRLML2502
  - Title block: Project ESP32DEV, File Root.sch, Jan. 20, 2022, Rev 1.0
- **Check:** small pin labels; whether pin numbers and GPIO names are mixed up

### 02 — Sheet music and tablature
- **File:** `02_sheet_music_tab.png` (495×700)
- **Question:** `What song is this sheet music for? Give the title, artist, instrument, tempo, key signature and the chords in the intro.`
- **Expected:**
  - "Wonderwall", Oasis, words and music by Noel Gallagher, for Guitar/Ukulele
  - Tempo ♩ = 90; three sharps (A major / F♯ minor)
  - Intro (section A) chords: F♯m7, A, Esus4, B7sus4
  - Ukulele tuning G C E A (standard C tuning); page 1/5
- **Note:** lyrics are not scored; check only that the verse begins with "Today".

### 03 — English conversation screenshot
- **File:** `03_tweet_thread_en.jpg` (758×660)
- **Question:** `Summarize this conversation. Who says what, and why is it funny?`
- **Expected:**
  - "John 'take your care' Fury" (@joshuaS_10): Paul should stay retired, he is a better commentator than fighter
  - Paul Felder (verified, @felderpaul): would you say that to my face, man to man?
  - John: no, you would beat me up, that is why I said it on Twitter
  - Felder: "Fair enough"
  - Humor: the critic openly admits he is only brave online, and the fighter accepts the honesty
  - 5:14 PM, Jul 5, 2020; 145 Retweets, 1.7K Likes

### 04 — Korean comment thread
- **File:** `04_korean_comments.jpg` (492×406)
- **Question:** `이 댓글들을 읽어 주고, 대화의 흐름과 왜 웃긴지 설명해 줘.`
- **Expected:**
  - Header "전체 리플 [4]", sorted by "등록순"
  - ㅇㄱ (175.197), 01.23 00:20: "어머니 마음 타들어가는 속도보다 빠를까?"
  - 트알레, 00:21: "너희 엄마랑 우리 엄마랑 대결해볼까"
  - ㅇㄱ, 00:21: "비긴걸로하자"
  - 트알레, 00:22: "그래"
  - Humor: a mom-insult escalates into "mom versus mom", and both immediately settle for a draw

### 05 — Korean infographic
- **File:** `05_korean_infographic_finance.png` (986×656)
- **Question:** `이 이미지는 무엇을 설명하는 자료야? 각 항목과 하위 내용을 정리해 줘.`
- **Expected:**
  - Title "재무제표"
  - 손익계산서: 매출, 비용, 순이익
  - 재무상태표: 자산, 부채, 자본
  - 현금흐름표: 영업활동, 투자활동, 재무활동
  - Bar chart 매출, 순이익, 비용 with legend; calculator, document with an upward arrow, ₩ coin, pie chart

### 06 — Engineering chart
- **File:** `06_ber_chart.png` (717×591)
- **Question:** `What does this chart show? Which modulation needs the lowest Eb/N0 to reach log10(Pb) = -6, and which needs the highest?`
- **Expected:**
  - Title "Probability of BER Error log10(Pb) Vs Eb/N0"; x-axis Eb/N0 (dB) −4 to 24; y-axis log10(Pb) 0 to −8
  - 10 schemes: BPSK, QPSK, 8-PSK, 16-PSK, 32-PSK, D-BPSK, D-QPSK, 4-QAM, 16-QAM, 64-QAM
  - Lowest: BPSK / QPSK / 4-QAM (overlapping, about 10.5 dB); highest: 32-PSK (about 22 dB)
  - Higher-order modulation needs more Eb/N0 for the same error rate

### 07 — Mathematical formula
- **File:** `07_dft_formula.gif` (478×288, GIF)
- **Question:** `Transcribe these formulas in LaTeX and explain what each one computes.`
- **Expected:**
  - DFT (FFT): X(k) = Σ_{n=0}^{N−1} x(n) · e^{−j(2π/N)nk}, k = 0, 1, …, N−1
  - IDFT (IFFT): x(n) = (1/N) Σ_{k=0}^{N−1} X(k) · e^{j(2π/N)nk}, n = 0, 1, …, N−1
  - Key details: minus sign in the DFT exponent; plus sign and 1/N in the IDFT
- **Check:** whether GIF input is accepted

### 08 — Cartoon scene without text
- **File:** `08_cartoon_scene.webp` (284×213, WebP)
- **Question:** `What is happening in this picture? How does the character feel?`
- **Expected:**
  - A cartoon man (Peter Griffin, Family Guy) sitting on a sidewalk, clutching his knee, in exaggerated pain
  - Suburban street, mailbox, lawn, house; a well-known meme
- **Check:** whether WebP input is accepted; no invented text or extra characters

### 09 — Handwriting and sketch
- **File:** `09_handwriting_sketch.jpg` (592×337, phone photo of paper)
- **Question:** `Transcribe all the handwritten text exactly, then describe the drawing: style, character features and pose.`
- **Expected text:**
  - "handwriting 손글씨" written three times in different styles; the third is a messy cursive
  - "저 손글씨 잘 못씁니다TT"
  - "평소에는 이렇게 씁니다TT"
- **Expected drawing:**
  - Pen sketch of a chibi-style anime girl with dragon horns, maid-style headband and frills, smiling, one hand raised with a finger up
  - Bonus (not required): resembles Tohru from *Miss Kobayashi's Dragon Maid*
- **Check:** Korean handwriting accuracy; whether the deliberately messy third line is read as "handwriting"

### 10 — Night street photo
- **File:** `10_night_street_photo.jpg` (1932×2576, phone photo)
- **Question:** `Describe this photo. Where and when was it likely taken? Read any signs you can see.`
- **Expected:**
  - Night; an empty multi-lane road seen from a low angle on a crosswalk; double yellow center line; red-paved lane with white arrows on the left
  - Street lights, a traffic signal at the top left, high-rise apartment buildings on both sides, young trees, shops on the right
  - Korean signage, so likely a new residential district in South Korea; young leaves suggest spring
  - Main sign: "푸르지오강남" and "(031)715-1544". The 031 area code places it in Gyeonggi-do
  - The sign is small in the full photo; reading it reliably needs a zoomed region (for example `0.7,0.42,1,0.56`)
- **Check:** low-light reading; no invented sign text

### 11 — Aquarium
- **File:** `11_aquarium.webp` (2324×1139, WebP)
- **Question:** `Describe this aquarium. How many fish can you see, and what is in the layout?`
- **Expected:**
  - Planted aquarium (aquascape) with a black background
  - Driftwood and dark volcanic rocks on a sand bed; stem plants, grass-like plants, floating plants at the surface
  - Small livebearer fish (guppy/endler type); about 10 to 13 visible (any answer in this range is correct)
  - Pipes or equipment on the left side
- **Check:** counting; no invented species certainty

### 12 — Photo of a lecture screen
- **File:** `12_lecture_screen_photo.jpg` (386×518, low resolution)
- **Question:** `이 강의 화면의 제목과 주제를 읽어 줘. 읽을 수 없는 부분은 읽을 수 없다고 말해 줘.`
- **Expected:**
  - Heading: "[2027 경영·금융(구 상업) 임용] OK teacher! 옥티의 교과교육학 완성반 보강자료(2026. 9. 4.)"
  - Subtitle: "경영·금융(구 상업) 임용 교과교육학 출제범위 변경에 대한 안내"
  - Sections "Ⅰ. 상업임용_옥티의 교과교육학 완성반_(1) …" and "Ⅱ. 상업임용_옥티의 교과교육학 완성반_(2) …"
  - Topic: a notice about changes to the exam scope for the business and finance teacher certification exam
  - The instructor's face is blurred; the body text is too small to read reliably
- **Check:** the model should say the small body text is unreadable instead of inventing it

## Hallucination checks

Questions about things that are **not** in the image. The correct answer is that the information is not shown.

| # | Image | Question | Correct answer |
|---|---|---|---|
| H1 | 04 | `가장 추천을 많이 받은 댓글은 뭐야?` | No like or recommendation counts are shown |
| H2 | 06 | `What is the BER of 128-QAM at 10 dB?` | 128-QAM is not in the chart |
| H3 | 01 | `What is the value of resistor R50?` | There is no R50 (resistors go up to R47) |
| H4 | 11 | `What brand is the filter in this aquarium?` | No brand is visible |

## Planned additions

| Case | Skill |
|---|---|
| Source code screenshot (C for embedded) | Exact code transcription |
| Stock price chart | Numbers, dates, candlesticks |
| Real financial statement table | Dense numbers, rows and columns |

## Results

### Run 13 — first full run through the agent (2026-11-04)

Main model `qwen3:8b` (`main.py --fast`), vision `qwen3-vl:8b-instruct`, `max_side` 1280. Questions asked in Korean, one at a time.

| # | Case | Result | Tool used | Notes |
|---|---|---|---|---|
| 01 | Schematic | ❌ | describe_image (full) | MCU, regulator, CS = G05, SDA = G21 correct; MOSI, SCK, MISO, SCL wrong (G18, G19, G17, G23) |
| 02 | Sheet music | ⚠️ | describe_image | Title, band, instrument, tempo correct; key signature given as "C Tuning"; listed the chord-diagram row instead of the intro chords |
| 03 | English conversation | ❌ | describe_image | Main model's summary mixed up who criticized whom; missed "Fair enough" and the actual joke |
| 04 | Korean comments | ❌ 👻 | read_text_in_image, then describe_image | Comments transcribed correctly; humor explanation invented ("상사의 어머니", "in-law") |
| 05 | Korean infographic | ✅ | describe_image | All sections, items and legend correct |
| 06 | Engineering chart | ⚠️ | describe_image | Lowest = BPSK correct; highest given as 64-QAM (should be 32-PSK) |
| 07 | Formula (GIF) | ✅ | describe_image | Both formulas exact, including signs and 1/N |
| 08 | Cartoon (WebP) | ❌ | describe_image | Knee pain read as "surprise or tiredness"; hands "near the chest" |
| 09 | Handwriting and sketch | ⚠️ | describe_image | All five handwritten lines exact, including the messy third line; horns correct; hand gesture and headband inaccurate |
| 10 | Night street photo | ⚠️ | describe_image (full) | Scene correct; sign misread as "푸르지오 건담 070-715-1544" (no zoom used) |
| 11 | Aquarium (WebP) | ⚠️ | describe_image | Layout correct; counted 7-8 fish (10-13 visible) |
| 12 | Lecture screen photo | ⚠️ | read_text_in_image | Readings differed; reported UNCERTAIN with both readings (correct behavior), content mostly wrong |
| H1 | Likes not shown | ✅ | describe_image | "Not shown" |
| H2 | 128-QAM not in chart | ✅ | describe_image | Not in chart, listed the schemes that are |
| H3 | R50 does not exist | ❌ 👻 | read_text_in_image (not found), then describe_image | Invented "R50 is 10k" after the locate step correctly returned nothing |
| H4 | Filter brand not visible | ✅ | read_text_in_image (not found), then describe_image | "Not shown" |

Main cases: ✅ 2, ⚠️ 6, ❌ 4. Hallucination checks: 3/4.

**Failure causes and fixes (Run 14)**

| Cause | Cases | Fix |
|---|---|---|
| Fine detail read from a downscaled full view | 01, 10 | `describe_image(focus=...)`: the vision model locates the part, which is cropped, enlarged and answered from |
| Small source image | 08 | Full images with a longer side below 768 px are enlarged up to 2x (token cost has a floor around 1,150) |
| Question translated to English, answer re-translated and embellished by the main model | 03, 04, 08 | Tool description: pass the user's question unchanged; system prompt: do not add interpretations the tool did not return |
| "Not found" ignored, value requested again | H3 | Not-found result says it usually means the item is absent and not to ask describe_image for a value |
| Wrong tool for a whole comment thread | 04 | read_text_in_image is described as one short item only |
| Model limits (not fixed by tools) | 02, 06, 11 | Candidates for a thinking-variant comparison |

### Run 21 — full set through the image planner (2026-11-05)

Fast mode (`qwen3:8b`), image questions planned by `qwen3:14b`, vision `qwen3-vl:8b-instruct`. English questions as listed above for the English cases.

| # | Case | Run 13 | Run 21 | Notes |
|---|---|---|---|---|
| 01 | Schematic | ❌ | ⚠️ | MCU, SD card 4/4 and AMS1117-3V3 correct; OLED wrong (G23/G23) but marked "not verified" |
| 02 | Sheet music | ⚠️ | ❌ | Split into six readings: artist read as "Guitar/Ukulele Oarc", key signature reading repeated the request, only the first intro chord |
| 03 | English conversation | ❌ | ✅ | Who said what and "Fair enough" correct; the joke explained weakly |
| 04 | Korean comments | ❌ 👻 | ❌ | The whole-image part was fully correct, but "flow" and "why funny" were zoomed into the first comment and answered wrongly; a false "not planned" note |
| 05 | Korean infographic | ✅ | ✅ | Correct, but the same content three times |
| 06 | Engineering chart | ⚠️ | ❌ | "Lowest" and "highest" were zoomed into small corners; lowest reported as not shown, highest as D-QPSK (32-PSK expected) |
| 07 | Formula (GIF) | ✅ | ⚠️ | Both formulas correct in content, but the readings differed in headings and layout, so both were marked uncertain |
| 08 | Cartoon (WebP) | ❌ | ❌ | "Yawning" instead of knee pain (model limit) |
| 09 | Handwriting and sketch | ⚠️ | ⚠️ | The repetition guard cut the transcription after the first "handwriting 손글씨"; the whole-image part had all five lines |
| 10 | Night street photo | ⚠️ | ❌ | "any signs" located a small unreadable sign instead of the main one (Korean question in Run 20 was ✅) |
| 11 | Aquarium (WebP) | ⚠️ | ❌ | "How many fish" was zoomed into one fish: "One fish" |
| 12 | Lecture screen photo | ⚠️ | ⚠️ | Both readings garbled and marked uncertain (low resolution) |
| H1 | Likes not shown | ✅ | ✅ | |
| H2 | 128-QAM not in chart | ✅ | ✅ | |
| H3 | R50 does not exist | ❌ 👻 | ✅ | NOT FOUND, no guessed value |
| H4 | Filter brand not visible | ✅ | ✅ | |

Main cases: ✅ 2, ⚠️ 5, ❌ 5 (Run 13: ✅ 2, ⚠️ 6, ❌ 4). Hallucination checks: 4/4 (Run 13: 3/4).

The planner fixed dense images and hallucinations but made simple and whole-image questions worse. Runs 18-20 tuned it on cases 01 and 10 only; three of the Run 19-20 changes caused failures here (target-only reading prompt, the "describe" coverage check, the bracket cleanup).

### Run 22 — full set after the Run 21 fixes, first automated run (2026-11-05)

`python scripts/run_vision_set.py --fast`: 16 cases in 7.2 minutes. Same models as Run 21.

| # | Case | Run 13 | Run 21 | Run 22 | Notes |
|---|---|---|---|---|---|
| 01 | Schematic | ❌ | ⚠️ | ⚠️ | MCU, SD 4/4, AMS1117-3V3 correct; OLED wrong (pins 32/37) but marked "not verified" |
| 02 | Sheet music | ⚠️ | ❌ | ⚠️ | Title, tempo 90 and intro chords F#m7, A, Esus4, B7sus4 correct (plus an extra "A#"); artist and instrument boxes both read "Guitar/Ukulele"; key signature "no readable text" |
| 03 | English conversation | ❌ | ✅ | ✅ | One whole-image call; facts correct, the joke still explained weakly |
| 04 | Korean comments | ❌ 👻 | ❌ | ⚠️ | All four comments and the draw correct, no invented relations; first line misread as "mother's emotions"; answer looped once |
| 05 | Korean infographic | ✅ | ✅ | ✅ | One call, 13 s |
| 06 | Engineering chart | ⚠️ | ❌ | ⚠️ | Lowest BPSK correct; highest 64-QAM (32-PSK expected): same as Run 13 |
| 07 | Formula (GIF) | ✅ | ⚠️ | ⚠️ | Both formulas correct; heading lines and LaTeX vs plain text made the readings "differ" |
| 08 | Cartoon (WebP) | ❌ | ❌ | ❌ | "Yawning" (model limit) |
| 09 | Handwriting and sketch | ⚠️ | ⚠️ | ⚠️ | All five lines exact; peace sign instead of one finger, bow instead of headband |
| 10 | Night street photo | ⚠️ | ❌ | ✅ | Sign CONFIRMED "푸르지오강남 (031)715-1544"; no city claimed |
| 11 | Aquarium (WebP) | ⚠️ | ❌ | ⚠️ | "At least 7 fish" (10-13 visible); layout correct |
| 12 | Lecture screen photo | ⚠️ | ⚠️ | ⚠️ | Readings garbled, marked uncertain |
| H1-H4 | Hallucination checks | 3/4 | 4/4 | 4/4 | |

Main cases: ✅ 3, ⚠️ 8, ❌ 1 (Run 13: ✅ 2, ⚠️ 6, ❌ 4). Hallucination checks 4/4. No case is worse than in Run 13. The remaining ❌ (08) and the chart and counting errors (06, 11) are model limits.

### Run 23 — repeat run with the Run 22 fixes (2026-11-05)

16 cases in 6.7 minutes, same models.

| # | Case | Run 22 | Run 23 | Notes |
|---|---|---|---|---|
| 01 | Schematic | ⚠️ | ⚠️ | Same: MCU, SD 4/4, AMS1117-3V3 correct; OLED wrong but marked "not verified" |
| 02 | Sheet music | ⚠️ | ⚠️ | Title confirmed with "Guitar/Ukulele" shown as nearby text; artist and instrument both read "Guitar/Ukulele" and both flagged "check the place"; tempo 90 and intro chords correct; key signature "not shown" from the whole image (three sharps expected) |
| 03 | English conversation | ✅ | ✅ | |
| 04 | Korean comments | ⚠️ | ✅ | One whole-image call (24 s, was 57 s): four comments, the mom contest and the draw; no loop |
| 05 | Korean infographic | ✅ | ✅ | |
| 06 | Engineering chart | ⚠️ | ⚠️ | Highest given as 64-QAM again (32-PSK) |
| 07 | Formula (GIF) | ⚠️ | ⚠️ | Formula 1 confirmed with "DFT(FFT):" as nearby text; formula 2 LaTeX vs plain text |
| 08 | Cartoon (WebP) | ❌ | ❌ | "Yawning" |
| 09 | Handwriting and sketch | ⚠️ | ⚠️ | Five lines exact; peace sign instead of one finger |
| 10 | Night street photo | ✅ | ✅ | Sign confirmed |
| 11 | Aquarium (WebP) | ⚠️ | ⚠️ | "At least 7 fish" |
| 12 | Lecture screen photo | ⚠️ | ⚠️ | Uncertain readings |
| H1-H4 | Hallucination checks | 4/4 | 4/4 | H1 now a plain "not shown" answer |

Main cases: ✅ 4, ⚠️ 7, ❌ 1. Hallucination checks 4/4. The result is stable across two runs.

Remaining errors that are stated with confidence all come from the vision model's own reading of the whole image: the highest curve in a chart (06), a facial expression (08), the number of fish (11), a key signature (02) and a hand gesture (09). Tools cannot check these; they are the input for Stage 7 (thinking variant).

### Run 24 — model size × checking method (2026-11-05)

`python scripts/run_vision_set.py --compare`. The vision model (`qwen3-vl:8b-instruct`) is the same in all four profiles. "small" and "large" plan with the 8B or 14B model; "-accurate" adds a second look with a majority vote, a tile scan, the thinking vision model (`qwen3-vl:8b`) for counting and comparing, planning with thinking and a 1.9 MP pixel budget.

| # | Case | small (8B) | large (14B) | small-accurate | large-accurate |
|---|---|---|---|---|---|
| 01 | Schematic | ⚠️ OLED wrong but marked; regulator read as "AMS1117-3V" | ⚠️ OLED "G24" but marked | ⚠️ SD pins invented (G12-G15) but the check flagged it; OLED G21/G22 correct for the first time, but not confirmed | ⚠️ OLED "pin 1, 2", flagged |
| 02 | Sheet music | ⚠️ artist "Guitar/Ukulele Oasis", extra chords D, E | ⚠️ artist and instrument flagged; extra F#m | ⚠️ key signature "F major, one flat" (wrong) while the check said "not shown" | ⚠️ same key signature error, extra chords |
| 03 | English conversation | ✅ | ✅ | ⚠️ no explanation of the joke | ✅ best explanation of the joke so far |
| 04 | Korean comments | ⚠️ joke misread | ⚠️ joke misread | ⚠️ "why it is funny is not shown in the image" | ⚠️ same refusal |
| 05 | Korean infographic | ✅ | ✅ | ✅ | ✅ |
| 06 | Engineering chart | ⚠️ 64-QAM | ⚠️ 64-QAM | ⚠️ 64-QAM, both looks agreed (✔ on a wrong answer) | ⚠️ same |
| 07 | Formula (GIF) | ⚠️ formula 2 uncertain | ⚠️ an extra duplicate part | ✅ both formulas in correct LaTeX | ⚠️ four parts for two formulas |
| 08 | Cartoon (WebP) | ❌ yawning | ❌ yawning | ❌ "tired" with ✔ | ❌ "tired" with ✔ |
| 09 | Handwriting and sketch | ⚠️ peace sign | ⚠️ peace sign | ✅ five lines exact and the raised index finger correct | ❌ empty answer |
| 10 | Night street photo | ✅ | ✅ | ❌ 👻 "taken in Gangnam, Seoul" | ❌ 👻 "taken in Gangnam, Seoul" |
| 11 | Aquarium (WebP) | ❌ "exactly three fish", answered in Korean to an English question | ⚠️ "at least 7 fish" | ❌ "no goldfish", mood "not shown" | ⚠️ "seven fish" while the check said "not shown" |
| 12 | Lecture screen photo | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| H1-H4 | Hallucination checks | 4/4 | 4/4 | 4/4 | 4/4 |
| | **Main cases ✅ / ⚠️ / ❌** | 3 / 7 / 2 | 3 / 8 / 1 | 3 / 6 / 3 | 2 / 7 / 3 |
| | **Time for 16 cases** | 6.4 min | 7.5 min | 21.4 min | 30.7 min |

Findings:
- **Model size (small vs large):** the 14B planner is better. With the 8B planner, case 11 was asked in Korean although the user wrote English, and the vision model then claimed "exactly three fish". Everyday `--fast` already plans with 14B.
- **Checking method as built makes results worse, at 3-4× the time.** The thinking vision model treated "describe only what is visible" too literally: it refused inferences ("why it is funny is not shown", fish count "not shown"), returned an empty answer once (09) and, reasoning from the sign text, brought back the location claim "Gangnam, Seoul" that the standard path had removed (10).
- **The second look checks consistency, not truth.** Two looks that agree on a wrong answer (06 "64-QAM", 08 "tired") were shown with ✔, which reads as "correct". Short answers were compared with each other but not with the prose, so "not shown" in the check next to "F major" or "seven fish" in the prose passed unnoticed.
- **Useful pieces:** the second look caught invented SD card pins (01); the tile scan let the description read the sign correctly (10); the accurate profiles produced the best results so far for 01 OLED, 07 LaTeX, 09 pose and 03 humour — but not consistently.
