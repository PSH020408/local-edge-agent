# Document test set

Questions about three study documents, answered by the document planner (`agent/document_planner.py`). The files are course materials and personal slides; they are kept in `evals/documents/files/` and not committed.

| File | What it is | What it tests |
|---|---|---|
| `ofdm_sync_lecture.pdf` | 36 lecture slides on OFDM synchronization, exported from PowerPoint; English with Korean notes | Text extraction, finding pages across languages, equations that come out of the text layer as scattered symbols, figures |
| `expectation_note.pdf` | One page written in LaTeX on the expected value | Equations that are only readable from the rendered page |
| `arm_vs_riscv_slides.pptx` | 15 slides comparing an ARM and a RISC-V microcontroller in air purifiers | PowerPoint text, tables and assembly code |

Questions, key facts and the pages that hold each answer are in `cases.toml` (16 questions and 3 hallucination checks). Run them all with:

```bash
python scripts/run_eval_set.py --set documents --fast
```

Scoring, by reading each answer in the report:

- ✅ correct, every claim cited to a page that holds it
- ⚠️ mostly correct, or correct with a missing or wrong citation
- ❌ wrong, invented content, or a claim the document does not make
- Hallucination checks: the answer must say the document does not cover it

## Run 25 — first run (2026-11-06)

`run_eval_set.py --set documents --fast` (8B main model, 14B planner and answers, `qwen3-vl:8b-instruct` for pages). 19 cases in 19.2 minutes.

| # | Result | Notes |
|---|---|---|
| D01 Synchronization types and causes | ✅ | All four types and the causes, cited p.2 |
| D02 Cases A, B, C | ✅ | Guard interval, phase shift, no ISI, equalization; C causes ISI |
| D03 Why Case C is worse | ✅ | ISI and ICI, phase and amplitude change, re-synchronization [p.15] |
| D04 Desired signal term in LaTeX | ⚠️ | Formula correct ((N−τ)/N X_{n,p} e^{j2πpτ/N}), but the explanation misses the attenuation and the ICI term |
| D05 Normalized CFO | ⚠️ | Integer and fractional parts correct; the denominator written as f_s instead of the subcarrier spacing |
| D06 5G SSB | ✅ | PSS, SSS, PBCH; base station ID, frequency and synchronization information |
| D07 PSS vs CP synchronization | ✅ | Sequence and cell ID vs auto-correlation without cell ID; Wi-Fi, vehicles, IoT |
| D08 van de Beek | ✅ | Fractional frequency offset from the correlation of the copied guard interval |
| D09 Whole-lecture summary | ✅ | Time and frequency synchronization, cases, ICI, synchronization order, 5G NR methods, with page ranges |
| D10 Three practice questions | ⚠️ | Two correct; the third gave the van de Beek estimate as (2/π)·arg γ, an equation the slides were never read for |
| E01 Meaning of equation (5) | ✅ | Expectation as the limit of repeated-experiment averages |
| E02 Equation (2) in LaTeX | ✅ | Exact, although the vision reading had been cut (see below) |
| P01-P04 ARM vs RISC-V | ✅ ✅ ✅ ✅ | Chips and architectures, threshold 35 and modes 3/1, floating point vs RAM, Wi-Fi vs standby power |
| DH1-DH3 Not in the document | 3/3 | All three said the document does not cover it, but each got a false "no citations" warning; DH2 took 258 s through the whole-document path |

Main questions: ✅ 13, ⚠️ 3, ❌ 0. Hallucination checks 3/3.

Problems found in the traces and fixed:

| Problem | Fix |
|---|---|
| The vision model read p.13's equations correctly but wrapped them in `\documentclass`, `\usepackage` and itemize blocks | Prompt asks for one `$$ … $$` per line and no LaTeX document; code strips the scaffolding |
| `\begin{equation}` once per equation was taken for a loop, so the expectation note's page reading was cut to its first line | The repetition guard ignores LaTeX structure lines |
| Equation pages were read for plain-text questions (D01: 20 s on p.7) | Equations are read only when the question asks about an equation or figure; figure-only pages are always read |
| "Not in the document" answers were flagged for missing citations | Such answers need no citation; the answer lists the pages that were checked |
| A question about something absent went to the whole-document path (DH2, 258 s) | The whole-document path is only for summaries and practice questions |
| A practice answer wrote an equation from a page that was never read (D10) | An answer with equations citing an unread equation page gets a warning |

## Run 26 — rerun after the Run 25 fixes (2026-11-06)

19 cases in 11.2 minutes (Run 25: 19.2).

| # | Run 25 | Run 26 | Notes |
|---|---|---|---|
| D01 | ✅ | ✅ | 23 s instead of 51 s: no unneeded page reading |
| D02 | ✅ | ✅ | A false "equation not read" warning for a "$\tau$" symbol |
| D03 | ✅ | ⚠️ | Shorter answer: no re-synchronization, ICI called "부호 간 간섭" |
| D04 | ⚠️ | ⚠️ | Formula correct, explanation still misses the attenuation |
| D05 | ⚠️ | ⚠️ | Same |
| D06 | ✅ | ⚠️ | Answered only the second half: the SSB contents (PSS, SSS, PBCH on p.30) were left out |
| D07-D09 | ✅ | ✅ | |
| D10 | ⚠️ | ✅ | Three correct practice questions with correct pages, no equations |
| E01, E02 | ✅ | ✅ | The page reading now contains the equations (Run 25: cut to one line) |
| P01-P04 | ✅ | ✅ | |
| DH1-DH3 | 3/3 | 3/3 | No false warnings; each lists the pages checked; DH2 3.6 s instead of 258 s |

Main questions: ✅ 12, ⚠️ 4, ❌ 0 (Run 25: 13, 3, 0). Hallucination checks 3/3. (First written as ✅ 14, ⚠️ 4, a counting error; see the correction under Run 28.)

Fixes: the equation warning now needs an actual equation (a fraction, a sum or an equals sign inside math), and the answer prompt asks for every part of the question and every listed point. The second is a prompt rule, so it is not guaranteed; omissions are the remaining weakness. The set has now been used for two rounds of fixes, so the next measure is a holdout of new documents.

## Holdout — Run 27 (2026-11-07)

Three new documents, never used during development (`holdout.toml`): a Korean biology lecture made in Keynote (27 slides, 10 image-only), a Korean economics lecture (25 slides, many percentages) and an English deep learning lecture (11 slides, a figure on each). The code was frozen at commit `12d35a0` and was run once. 24 cases in 15.1 minutes.

| # | Result | Notes |
|---|---|---|
| GA1 DNA fingerprinting and samples | ✅ | |
| GA2 VNTR vs STR repeat units | ✅ | Read from an image-only slide: hundreds of bp vs 2-6 bp |
| GA3 PCR in clinical diagnosis | ✅ | |
| GA4 Role of DNA fingerprinting in the Narborough case | ⚠️ | Correct, but also attributed "the first DNA evidence admitted in US history" to this case; on the slide that is a separate bullet about a Florida case |
| GA5 CODIS loci and match probability | ✅ | 20 STR loci, 1 in 2 trillion |
| GA6 Biometric technologies on the slides | ❌ | The answer is on an image-only slide (p.7: fingerprint, iris, face, hand veins). Image-only slides have no text, so their index line was empty and the page was never selected; the answer described DNA fingerprinting instead |
| GA7 Growth hormone genes per E. coli cell | ❌ | "102개": the text layer turns 10² into 102. The number check cannot catch it, because "102" is in the extracted text |
| GA8 Five-line summary | ✅ | |
| GB1-GB7 German economy | ✅ ✅ ✅ ✅ ✅ ✅ ✅ | Every percentage and count correct (9.4%, 90%, 12%, 3rd, 60%, 29/139/62) with the right pages |
| GB8 Three practice questions | ⚠️ | One answer said cars are "over 90% of German industry sales"; the slide says vehicles are 9.4% of exports and cars over 90% of that. The relation was lost between the chunk summaries and the final answer |
| GC1 RNN problems | ✅ | |
| GC2 Positional encoding formulas | ✅ | Read from the image: sin and cos with 10000^{2i/d_model} |
| GC3 Attention weight of "dog" | ❌ | The vision model transcribed all four attention vectors correctly but without the words they belong to, so the answer said the document does not cover it (a safe failure: nothing was invented) |
| GC4 Encoder block | ✅ | |
| GC5 Decoder Linear and Softmax | ✅ | |
| HH1-HH3 Not in the document | 3/3 | |

**Main questions: ✅ 16, ⚠️ 2, ❌ 3 (76% correct). Hallucination checks 3/3.**
For comparison, the development set after two rounds of fixes (Run 26): ✅ 13, ⚠️ 3, ❌ 0 (81% correct, after the correction under Run 28).

The share of correct answers held on unseen documents, but the holdout showed three failure types that the development set had not:

1. **Image-only pages cannot be found.** Page selection reads an index of page text; a slide that is a picture has none.
2. **Superscripts are lost in the text layer** (10² → 102), and the result looks like a valid number.
3. **Figure transcriptions lose the labels** that tie numbers to words (attention rows without their words).

Two smaller errors came from the language model combining separate statements (GA4, GB8). No answer invented a fact that is absent from the documents.

### Fixes after Run 27

| Failure | Fix | Kind |
|---|---|---|
| Image-only pages cannot be found (GA6) | A page with a picture and under 80 characters of text gets a three-sentence caption from the vision model, the first time the document is used. Captions are saved in `logs/cache/pages/<document>_captions.json` (invalidated when the file changes) and go into the selection index ("picture: …") and into the page context | Code |
| Superscripts lost (GA7) | Raised digits are found from the character boxes in the PDF text layer (bottom raised by over a quarter of the character before, top not above it, glyph smaller) and written with a caret: "10^2개", "10^11". On the six PDFs only the genetics p.6 changed. The answer prompt explains the caret; the number check accepts a power written out (10^2 → 100) | Code |
| Number check skipped Korean counters | "102개" was never checked because "개" counted as part of the word; numbers followed by Korean text are now checked. On the 43 answers of Runs 26-27 this changes only GA7, which is now flagged | Code |
| Figure numbers without labels (GC3) | The vision prompt asks for each value as "label: value" and never values without labels | Prompt |
| Separate bullets combined (GA4, GB8) | The answer prompt says to keep separate points separate and each number with its item | Prompt |

The holdout documents have now been seen, so Run 28 on them is a check of the fixes, not a holdout result. The next holdout uses new documents.

## Run 28 — check of the Run 27 fixes (2026-11-07)

The development set and the holdout documents, now seen, with the fixes above. Not a holdout result.

**Correction to earlier runs.** The Run 26 table holds ✅ 12 and ⚠️ 4, not ✅ 14, ⚠️ 4 as first written. D05 was graded ⚠️ in Runs 25 and 26 for "f_s instead of the subcarrier spacing", but the slide itself defines f_s as the subcarrier spacing (p.20: Δf = f_off / f_s = f_off / (1/T_s)), so those answers were correct. Corrected totals: Run 25 ✅ 14, ⚠️ 2; Run 26 ✅ 13, ⚠️ 3.

### Development set: 19 cases in 18.3 minutes

| # | Run 26 | Run 28 | Notes |
|---|---|---|---|
| D01, D02 | ✅ ✅ | ✅ ✅ | No false equation warning on D02 |
| D03 | ⚠️ | ✅ | ISI and ICI, simple equalization is not enough, re-synchronization [p.15] |
| D04 | ⚠️ | ⚠️ | Formula correct; the explanation calls N−τ "the effective symbol length" and leaves out the attenuation and the ICI term |
| D05 | ✅ (regraded) | ✅ | Subcarrier spacing, integer and fractional CFO |
| D06 | ⚠️ | ✅ | PSS, SSS, PBCH and the information carried |
| D07 | ✅ | ⚠️ | Left out that CP-based synchronization is used in Wi-Fi ("other systems") |
| D08-D10 | ✅ ✅ ✅ | ✅ ✅ ✅ | |
| E01, E02 | ✅ ✅ | ✅ ✅ | |
| P01-P04 | ✅ | ✅ | |
| DH1-DH3 | 3/3 | 3/3 | |

Main questions: ✅ 14, ⚠️ 2, ❌ 0 (Run 26 corrected: 13, 3, 0). Hallucination checks 3/3.

### Holdout documents (seen): 24 cases in 25.2 minutes

| # | Run 27 | Run 28 | Notes |
|---|---|---|---|
| GA6 Biometric technologies | ❌ | ⚠️ | The captioned picture page was selected. Fingerprint, face and vein recognition correct, but iris recognition (홍채) was called retina (망막), and the fingerprint method was described as ridges and valleys; the slide says end points and branch points. The caption and reading were written in English, so the Korean labels were translated, not copied |
| GA7 Genes per E. coli cell | ❌ | ✅ | 10^2 copies [p.6] |
| GC3 Attention weight of "dog" | ❌ | ✅ | Itself, 0.91 [p.8] |
| GA4 Narborough case | ⚠️ | ⚠️ | The Florida bullet is still attributed to this case: the "keep separate points separate" rule did not change it |
| GB8 Practice questions | ⚠️ | ⚠️ | No longer the 90% error; now all 3.6 million SMEs are described as world-market leaders ("hidden champions"), two separate points merged |
| GC2 Positional encoding | ✅ | ✅ | Correct, but with a false "no citations" warning: the answer cited "[p.7, read by the vision model]" |
| Other 15 cases | ✅ | ✅ | |
| HH1-HH3 | 3/3 | 3/3 | HH2 got a false "no citations" warning: "정보는 제공되지 않았다" was not recognised as "not in the document" |

Main questions: ✅ 18, ⚠️ 3, ❌ 0 (Run 27: 16, 2, 3). Hallucination checks 3/3.

The two code fixes did what they were for (GA7, and GA6 is now found). The prompt rule against merging separate points did not fix GA4 or GB8. The label rule fixed GC3, but a single case is weak evidence for a prompt change.

Cost: picture-only pages were captioned once, about 4 minutes for the 17 pages of the biology lecture and under 30 seconds for the others; later runs read them from the cache. The development set took 18.3 minutes instead of 11.2. Part of it is the captions; most of it is that captioned pages are now selected and then read in full (D05 read four pages, 120 s instead of 16 s).

Bugs in the checks found in this run and fixed:

| Bug | Fix |
|---|---|
| A citation copied with the page note, "[p.7, read by the vision model]", was not counted (GC2 false warning; p.14 missing from the GA3 source line) | The citation pattern accepts that note |
| "정보는 제공되지 않았다" not recognised as a "not in the document" answer (HH2) | More phrasings added |
| Empty "$$ $$" pairs in figure readings | Removed by the transcription cleaner |

Remaining weaknesses, left for the next holdout to measure rather than tuned on these cases: separate points merged by the answer model (GA4, GB8), omissions (D04, D07), and translated rather than copied labels in figure readings (GA6).

## Run 29 — second holdout: two research papers (2026-11-07)

`run_eval_set.py --set documents --cases evals/documents/holdout2.toml --fast`, code frozen at `df47eb8`, run once. 24 cases in 11.1 minutes. A slide deck sent for this holdout was identical to the development file `arm_vs_riscv_slides.pptx` and was not used.

| # | Result | Notes |
|---|---|---|
| PA1 What PEAF is, two tasks | ✅ | |
| PA2 Three operations, L- vs N-PEAF | ✅ | |
| PA3 What Learn-PEAF adds | ⚠️ | Low pass filter; PCEN left out |
| PA4 Table 1 power figures | ❌ | Selected p.4 instead of p.2, then answered "not in the document" |
| PA5 Energy efficiency, frame rates | ❌ | Selected p.4-5, "not in the document" |
| PA6 Equation (1) in LaTeX | ❌ | p.2 was selected but cut: three pages shared the 10,000-character budget, each cut to its first 3,300 characters, and equation (1) is at the end of p.2. "Not in the document" |
| PA7 Table 3 accuracies | ❌ | Selected p.4 instead of p.3; claimed the paper gives no figures for Table 3 |
| PA8 WWD test set | ❌ | Selected p.4 instead of p.3; "not described", and expanded WWD as "Word-World Detection", an invention |
| PA9 Most power-efficient WWD feature | ✅ | |
| PA10 Limitations | ✅ | |
| PA11 Five-line summary | ✅ | Whole-document path, 253 s |
| VA1 Filters and decimation ratios | ❌ | Filters and the 16, 2, 2 ratios correct, but claims the droop correction filter does not decimate; Figure 1 shows it decimating by 2 (96 to 48 kHz) |
| VA2 Sampling frequency, OSR, Nyquist | ✅ | |
| VA3 N, M, R | ❌ | Selected p.6 instead of p.3, "not in the document" |
| VA4 G_max and B_max formulas | ❌ | Selected p.4-5 instead of p.3; "not in the document" (predicted: the equations are not flagged) |
| VA5 Three speed-up methods | ✅ | From the conclusions [p.6] |
| VA6 MCLA and CIC speeds | ✅ | 220, 163 and 107 MHz with the right pages |
| VA7 SNR before and after | ❌ | Selected p.2 and p.6 instead of p.5; "no figures given" |
| VA8 Figure 4 bit widths | ❌ | Selected p.5 and answered from Figure 6 ("all 25 bit"), which is a different figure |
| VA9 Half band coefficients | ❌ | Selected p.3 instead of p.2, "not mentioned" |
| VA10 Practice questions | ⚠️ | Two correct; the second states a wrong transfer function, from a page whose equation was never read and is not flagged, so no warning was given |
| PH1, VH1, VH2 | 3/3 | VH2's flag is the question's own "mm²" repeated in the answer, a poor avoid entry |

**Main questions: ✅ 8, ⚠️ 2, ❌ 11 (38% correct). Hallucination checks 3/3.** The lecture holdout (Run 27) was 76%.

### Why

1. **Page selection is blind on paper pages.** The index line for a page is its first text line and the next 140 characters. On a slide that is the topic; on a paper page of 5,000 characters it is the middle of a sentence carried over from the page before. Tables, section headings and figure captions further down the page never reach the selection model. In 7 of 24 cases the model asked for the whole document, which the code refused, and the keyword fallback was used. Wrong pages caused 9 of the 11 failures.
2. **The context budget cuts dense pages.** 10,000 characters are split evenly over the selected pages, so with three paper pages each is cut to its first third (PA6).
3. **"Not in the document" is a safe exit.** Given the wrong pages, the answer model said the document does not cover it, and the code accepted that and listed the wrong pages as checked. Nine of the eleven failures are false "not in the document" answers. The hallucination checks reward this answer, so they cannot catch it; only the questions whose answer is in the document do.
4. **Predicted before the run:** vector figures and equations are not flagged (VA4, VA10). The superscript case (PA5) was never reached because the page was not selected.

None of these showed up on slides, where one page is one topic with a title and is short enough to fit the budget.

### Fixes after Run 29

| Failure | Fix | Kind |
|---|---|---|
| Page selection blind on paper pages (9 cases) | A PDF whose median page has 1,500 characters or more is read as a paper (the lecture PDFs have medians under 400; slide decks are never papers). Papers are split into passages of about a paragraph, starting at every heading, table caption and figure caption; labels drawn inside a figure stay with its caption. The planner model picks passages from an index of [id], page, section and first words, and names keywords in the document's language; BM25 keyword search adds up to three more passages | Code |
| Pages cut to fit the context (PA6) | Papers get whole passages, most relevant first, until the 10,000 characters are used; nothing is cut in the middle | Code |
| False "not in the document" (9 cases) | A short "not covered" answer triggers a keyword search of the pages (slides) or passages (papers) not yet given, and one more answer with them. If no other page matches, the answer stands. Applies to all documents | Code |
| Vector figures and equations not flagged (VA4, VA10) | In papers only: a figure caption or 50 or more drawn paths marks a figure; a line ending in "(n)" next to "=", math symbols or scattered one-letter lines marks equations (Word's Symbol font comes out as private-use characters) | Code |
| 10^12 missed (PA5, predicted) | A superscript may rise up to half a character height above the character before it (was a quarter). On the eight test documents this adds only PEAF p.2 | Code |

The slide path is unchanged except for the second search, and the paper rules switch on only for dense PDFs. Run 30 checks all three sets: the development set and the first holdout must stay at ✅ 14 and ✅ 18 with no ❌; the papers have now been seen, so their score is a check, not a holdout result.

## Run 30 — regression check after the Run 29 fixes (2026-11-08)

All three sets with the same code, one command. Gate decided before the run: the two lecture sets must stay at ✅ 14 and ✅ 18 or above with no ❌, and 3/3 on the "not in the document" checks.

| Set | Before | Run 30 | Time |
|---|---|---|---|
| Development (16 + 3) | ✅ 14, ⚠️ 2, ❌ 0 (Run 28) | ✅ 16, ⚠️ 0, ❌ 0; 3/3 | 13.2 min (18.3) |
| First holdout, lectures (21 + 3) | ✅ 18, ⚠️ 3, ❌ 0 (Run 28) | ✅ 19, ⚠️ 2, ❌ 0; 3/3 | 10.5 min (25.2, with the captions made then) |
| Second holdout, papers (21 + 3) | ✅ 8, ⚠️ 2, ❌ 11 (Run 29) | ✅ 19, ⚠️ 0, ❌ 2; 3/3 | 14.5 min (11.1) |

The gate passed. The papers have been seen, so their score is a check of the fixes, not a holdout result.

Changes on the lecture sets: D04 now explains the (N−τ)/N scaling, D07 now includes Wi-Fi, GB8's practice questions are correct. GA4 (the Florida bullet attributed to the Narborough case) and GA6 (iris called retina) are unchanged ⚠️. The second search ran on DH1, HH1 and HH2, found other pages with the question's words, and the answer stayed "not in the document" each time.

Papers, per case:

| # | Run 29 | Run 30 | Notes |
|---|---|---|---|
| PA1, PA2, PA9, PA10, PA11 | ✅ | ✅ | |
| PA3 What Learn-PEAF adds | ⚠️ | ❌ | Answered vaguely ("learnable elements, inspired by LEAF") from the introduction; the passage with the low pass filter and PCEN was not chosen |
| PA4 Table 1 | ❌ | ✅ | The Table 1 passage was chosen |
| PA5 Efficiency and frame rates | ❌ | ✅ | 36.5 · 10^12 OPS/W. False number warning on "30": the paper writes "30f ps" |
| PA6 Equation (1) | ❌ | ✅ | Read by the vision model; the page is now flagged |
| PA7 Table 3 | ❌ | ✅ | |
| PA8 WWD test set | ❌ | ✅ | |
| VA1 Filters and ratios | ❌ | ❌ | Still says the droop correction filter does not decimate, and gives the modulator a 16:1 ratio. Figure 1 shows CIC 16, first half band 2, droop correction 2, second half band 2. The ratios are only in the figure, and the question has no figure word, so the page was not read by the vision model |
| VA2, VA5, VA6 | ✅ | ✅ | |
| VA3, VA4, VA7, VA8, VA9 | ❌ | ✅ | VA4 read by the vision model; VA8 from the figure labels kept with the FIGURE 4 caption |
| VA10 Practice questions | ⚠️ | ✅ | No wrong equation this time |
| PH1, VH1, VH2 | 3/3 | 3/3 | VH1's key-fact miss and VH2's flag are faults of the case file (Korean phrasing not listed; "mm²" repeats the question) |

Fixed after the run, in the checks only (no answer changes): a number glued to a unit in the source ("30f ps") counts as present, and summaries of papers name each cited page by its first section instead of its first line.

Remaining for the next holdout: facts that are only in a figure when the question does not mention a figure (VA1), passage choice for short questions with few distinctive words (PA3), and the two lecture ⚠️ (GA4, GA6).

## Run 31 — third holdout: two long survey and tutorial papers (2026-11-08)

`run_eval_set.py --set documents --cases evals/documents/holdout3.toml --fast`, code frozen at `416364e`, run once. 27 cases in 32.3 minutes.

| # | Result | Notes |
|---|---|---|
| SA1 Two ISAC gains | ⚠️ | Both named, but integration gain explained as "higher performance, less mutual interference" instead of shared resources, and coordination gain from a networked-sensing example on p.26 instead of mutual assistance between S&C |
| SA2 IEEE 802.11bf | ✅ | Found by the second search after a first "not covered" |
| SA3-SA11 | ✅ | Table II rows, Fig. 11, Fig. 13 and Fig. 17 settings, equation (55), handover, Release 17 accuracy across the page break, Huawei |
| SA12 Structure of the paper | ⚠️ | Answered from the structure paragraph (not the whole-document path): Sec. V described as "more on signal processing" instead of receive signal processing, Sec. VIII left out |
| SH1, SH2 | 2/2 | |
| RA1 Layer 0 | ⚠️ | "The physical medium" from p.13; leaves out that it is seen as uncontrollable and that the RIS extends protocol design to it (p.2) |
| RA2 SNR loss with four phase shifts | ❌ | "Not in the document" after the second search; the answer is on p.17 |
| RA3 Fig. 4 | ✅ | |
| RA4 Fig. 6 simulation setup | ❌ | "Not in the document"; the answer is on p.23 |
| RA5 STM 96-98% and NLOS | ❌ | Says the percentage is not given; the NLOS part (4% in the narrowband case) is correct |
| RA6 Doppler cloaking | ⚠️ | Correct content, but expands RIS as "Reflective Intelligent Surface", a name the paper never uses |
| RA7 Channel estimation at the receiver | ❌ | "At the receiver" is right but cited to p.7; "sufficient to estimate the end-to-end channel h(t)" is wrong (the paper: the cascade matrix V, p.24) |
| RA8-RA10 | ✅ | |
| RA11 Equation (31) | ✅ | Correct; the warning that p.16 was not read is accurate |
| RA12 Practice questions | ⚠️ | 929 s (26 parts). PEB expanded as "Predicted Error Bound" (it is the position error bound) |
| RH1 | 1/1 | |

**Main questions: ✅ 15, ⚠️ 5, ❌ 4 (62.5% correct). Hallucination checks 3/3.** By paper: ISAC 10 of 12, RIS 5 of 12.

### Predictions written before the run

| Prediction | What happened |
|---|---|
| The 80-passage index cap hides passages from Korean questions (ISAC, 199 passages) | Not seen: the ISAC questions found their passages, once through the second search (SA2) |
| IEEE-style and unnumbered headings not recognised | Yes: section names in the source lines are often wrong ("p.4 (7. Human Computer)"); cosmetic |
| Whole-document tasks are slow | Yes: RA12 took 15.5 minutes |
| "10−7" not marked as a superscript | Did not matter: the answer copied "10−7" |

### Causes found in the trace

1. **Passages cut by the budget count as checked.** Up to 8 chosen and 3 keyword passages are offered, but only those fitting 10,000 characters are given; the rest are dropped silently. The second search then skips every passage that was offered, including the dropped ones. In RA2 and RA4 the passage holding the answer (p.17 and p.23) was most likely offered, dropped, and never searched again: the second search went to other pages.
2. **Index lines show the first 110 characters of a passage.** The RIS paper has long one-column passages; the answer to RA4 is in the middle of a passage that starts with "To evaluate the quality of the heuristic STM solution".
3. **Expansions from the model's own knowledge.** "Reflective Intelligent Surface", "Predicted Error Bound": not in the paper, and not caught because the number check only looks at numbers.
4. **A real fact cited to the wrong page.** RA7 cited p.7 for a sentence on p.24; the citation check only verifies that the page was given.
5. **Whole-document tasks scale with length.** 26 parts for 43 pages.

### Fixes after Run 31

| Failure | Fix | Kind |
|---|---|---|
| Passages left out by the budget counted as read (RA2, RA4) | Only the passages actually given count as read. Passages left out are reported ("n passage(s) did not fit") and are the first ones the second search returns to | Code |
| Index lines hid the middle of long passages (RA4) | Each index line adds what the passage contains after its first words: figure, table and equation references, quantities with units and acronyms ("… contains: Fig. 6, 3 GHz, 150 kHz") | Code |
| Practice questions only from p.35-38, 15.5 minutes (RA12) | Found while tracing: the key points of 26 parts were far longer than the 8,192-token context, so the model saw only the last parts. Key points are now merged in steps until they fit (estimated tokens), parts of a paper are twice as large (12,000 characters), and each part gives at most 8 one-line points in the document's language | Code |
| Invented acronym expansions (RA6, RA12, PA8) | Code flags an expansion of an acronym the document uses when the document never writes that expansion. The answer prompt says not to spell out abbreviations the pages do not spell out | Code + prompt |
| A sentence cited to the wrong page (RA7) | For English sentences, code compares the sentence's three-word sequences with the cited page and the other given pages, and flags a citation when the wording is on another page | Code |
| Words hyphenated at line ends ("au\x02dio") | pdfium marks them with \x02; the loader joins them, which also helps keyword search | Code |

Both new checks were tried on the 161 answers of Runs 28-31 before being kept. Expansions flagged: WWD "Word-World Detection", RIS "Reflective Intelligent Surface", PEB "Predicted Error Bound", RRH "remotely radio head" (the paper: remote), and OFDM "Orthogonal Frequency Division Multiplexing" (correct, but the lecture never spells it out). Citations flagged: RA7 only, after Korean sentences were excluded (a Korean answer had added an expansion of SINR that matched another page).

The third holdout has now been seen. Run 32 checks all four sets; the gate: development ✅ 15 or more, first and second holdouts ✅ 18 or more, no ❌ on the lecture sets, 3/3 on every "not in the document" check.

## Run 32 — regression check after the Run 31 fixes (2026-11-08)

All four sets, one command, 51 minutes in total (Run 30 and 31 together: 70 minutes).

| Set | Before | Run 32 | Gate | Time |
|---|---|---|---|---|
| Development | ✅ 16, ⚠️ 0 (Run 30) | ✅ 14, ⚠️ 2, ❌ 0; 3/3 | ✅ 15 or more: **missed by one** | 11.1 min |
| First holdout, lectures | ✅ 19, ⚠️ 2 | ✅ 19, ⚠️ 2, ❌ 0; 3/3 | passed | 8.5 min |
| Second holdout, papers | ✅ 19, ❌ 2 | ✅ 19, ⚠️ 1, ❌ 1; 3/3 | passed | 9.7 min |
| Third holdout, long papers (now seen) | ✅ 15, ⚠️ 5, ❌ 4 (Run 31) | ✅ 18, ⚠️ 3, ❌ 3; 3/3 | check only | 21.5 min (32.3) |

Development set, the two ⚠️:
- D04: the formula is right, but the explanation calls the desired term "the signal under perfect synchronization", leaving out the (N−τ)/N attenuation. The same item was ⚠️ in Runs 25, 26 and 28 and ✅ in Run 30: it varies between runs.
- D06: lists what the SSB carries but leaves out what it contains (PSS, SSS, PBCH), with the same pages and page readings as Runs 28 and 30, where both parts were answered. On the slide, PSS, SSS and PBCH appear only as abbreviations in a figure. The new prompt rule ("do not spell out an abbreviation unless the pages do") may have made the model skip them, or this is run-to-run variation; repeated runs of D04 and D06 decide which.

Third holdout changes: RA2, RA4 and RA5 are now correct (the passages that had been left out by the budget, and the long passage with Fig. 6); RA6 now writes "Reconfigurable"; the practice questions took 308 s instead of 929 s and draw on p.1, p.15 and p.20 instead of p.35-38 only. New failures: SA8 (equation (55)) answered "not in the document" because neither the planner model nor the keyword search found p.20; RA11 wrote the bound without the √ρ term of the direct path (the vision model read p.15, where the bound without the direct path is). RA7 still cites the wrong page; the page with the right sentence was among the passages left out, so the new citation check had nothing to compare with.

Second holdout: PA10 now lists other points from the Discussion and leaves out the stated limitations (simplified IAF, simulated chips), ⚠️.

### D04 and D06 repeated three times (same code as Run 32)

| Case | Repeat 1 | Repeat 2 | Repeat 3 |
|---|---|---|---|
| D04 | ✅ explains (N−τ)/N as the factor that scales the desired signal | ⚠️ "nearly the same as the original signal" | ⚠️ names the factor without saying it attenuates |
| D06 | ⚠️ contents (PSS, SSS, PBCH) left out | ✅ | ✅ |

D06 answered both parts in two of three repeats, with the same abbreviations spelled out, so the new abbreviation rule does not suppress them: Run 32's miss was run-to-run variation. D04's formula is right every time and its explanation varies, as it has since Run 25. The gate miss in Run 32 (✅ 14 against 15) is within this variation, so the code is kept as it is and frozen for the fourth holdout. Lesson for later gates: a single run cannot separate a one-case drop from variation; a drop is only counted when repeats confirm it.

