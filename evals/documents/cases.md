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

Main questions: ✅ 14, ⚠️ 4, ❌ 0 (Run 25: 13, 3, 0). Hallucination checks 3/3.

Fixes: the equation warning now needs an actual equation (a fraction, a sum or an equals sign inside math), and the answer prompt asks for every part of the question and every listed point. The second is a prompt rule, so it is not guaranteed; omissions are the remaining weakness. The set has now been used for two rounds of fixes, so the next measure is a holdout of new documents.
