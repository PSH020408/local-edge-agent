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

