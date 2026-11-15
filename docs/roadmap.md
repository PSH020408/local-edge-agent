# Roadmap

Author: PARK, SEHO

Principle: **everything runs locally** on one MacBook Pro (M4 Pro, 24 GB). No cloud models or services, including image generation.

Goal: a local agent that helps with graduate-school preparation, exam preparation, reading PDFs, papers and handouts, formula, graph and financial-statement analysis, art-style analysis, and image generation (anime and subculture styles, game illustration, realistic people, animals, objects and landscapes).

## How every stage is verified

1. Questions come from case files and run with one command (`scripts/run_eval_set.py`). Every answer is read and graded against the page images and the expected answer written before the run; the grade and its reason are recorded per case. From Stage 6 on, each run is also published with its answers (`scripts/export_run.py` → `evals/documents/runs/`), so every grade can be checked.
2. Every observed failure gets a fix and an offline regression test (`python -m unittest discover -s tests`).
   A drop of one case is counted only when repeated runs confirm it (answers vary between runs).
3. Holdout questions are never used for tuning; fixes are measured on new, unseen questions.
4. Results go to `docs/benchmarks.md` as a numbered run; enforced constraints go to `docs/guardrails.md`.
5. A stage is finished when its "done when" line is met, then it is committed and pushed.

## Done

| Stage | What | Runs | Commit |
|---|---|---|---|
| 0 Foundation | Ollama on macOS, `qwen3:8b` / `qwen3:14b`, agent loop with tool calling, JSONL traces, speed benchmarks | 1-2 | 8ec9cdc |
| 1 Time | Current time, time zones, date arithmetic, date differences, natural-language dates | 3-5 | 6966262 |
| 2 Math | Engineering calculator (numpy, scipy, sympy), unit-aware calculation (pint), loop guards | 6-10 | 44f5c99 |
| 3 Vision | Separate vision model as a tool, zoom, two-reading verification, image question planner, one-command test set | 11-24 | b4c74bc |
| 4 Documents | PDF and PowerPoint reading, page and passage search, vision for equations and figures, cited answers with code checks, four holdouts | 25-33 | c20fa03 |
| 5 Formulas | Numbered and unnumbered equations located, cropped, read twice and checked against the image; equations given first in document answers; Greek letters and equation numbers searched; answers that change an equation flagged; a fifth holdout | 34-41 | ea2a9b2 |

## Latest stage

### Stage 5 — Formulas, complete

Built: `agent/formula_tools.py` (an equation located by its number in the text layer, or a displayed equation without a number found from its layout; two crops at different margins, two readings by the vision model compared after normalising the LaTeX, the more complete reading kept, a third call that checks the result against the image, a structure check), its use in `agent/document_planner.py` (equations named in a question, or found by rare words for a formula question, are read and given first with the passages next to them; the answer states each reading's status; an answer that changes an equation is flagged; Greek letters and equation numbers are search keywords), `scripts/run_formula_set.py` and 28 reference LaTeX transcriptions written from the page images in `evals/formulas/`, and an equation question set in `evals/documents/equations.toml`.

- [x] Formula reader: locate, crop twice, read twice, compare by code; structure check (sympy's LaTeX parser was tried and not used: it drops parts of paper formulas silently)
- [x] Development set of 28 numbered equations graded by code (Runs 34-36: whole-page reading exact 17-19 of 28, two crops 20 → 23 → 26 of 28)
- [x] Third call that checks the chosen reading against the image; the more complete of two readings kept (Run 36)
- [x] Formula reader in document answers (Run 37: equation set ✅ 12 of 14, the four earlier equation failures fixed; Run 38: all five document sets passed their gates)
- [x] Unnumbered displayed equations, lists of equation numbers, rare-word ranking (Runs 39-40: equation set ✅ 16 of 18, then the two misses fixed)
- [x] Fifth holdout, one two-column paper, run once (Run 41: ✅ 11, ⚠️ 5, ❌ 0; "not in the document" 3/3; ten confirmed readings, all exact)
- [ ] Symbol table per document: not built. In every test the symbols were explained correctly from the text next to the equation once the equation and that text were given together; it stays an option if a later test needs it
- [ ] Dimension checks of formulas: not built (no test needed them)

Holdouts, each run once on unseen documents:

| Run | Documents | Fully correct | Wrong | "Not in the document" checks |
|---|---|---|---|---|
| 27 | Three lecture decks | 76% | 3 | 3/3 |
| 29 | Two short papers, before passage search | 38% | 11 | 3/3 |
| 31 | Two long papers | 62.5% | 4 | 3/3 |
| 33 | Two one-column papers with equations, tables and figures | 74% | 3 | 2/2 |
| 41 | One two-column paper with 13 numbered equations | 69% | 0 | 3/3 |

Formula reading: a reading confirmed by two crops was exact 46 times of 47 on the development formulas (Runs 35-36) and 10 times of 10 on the unseen paper (Run 41).

Done when: transcriptions match the known LaTeX or are marked uncertain. Met: every confirmed reading but one matched; the readings that did not were marked "close", "disagree" or "check failed", and the answers said so.

Carried over:
- Stage 3: redesign the accurate profile from the Run 24 findings; a vision holdout on new images
- Stage 5: the page description offers its own transcription of an equation that was read, and the answer sometimes takes it (RV1, EQ4); braces that mark a count are read as exponents (RV4); inline formulas come from the text layer (RV8); the third check call raises false alarms and its catches are unmeasured; the model's passage selection sometimes fails to parse
- Stage 4 items closed by Stage 5: Greek letters and equation numbers are searched, equation-heavy explanations are given with the equation (MR2, MR4 fixed), unnumbered formulas are read from the page (BS3). Still open: the vision model can miss a chart when asked for "equations and figures" (BS9)

## Next

### Stage 6 — Tables, financial statements and graphs
- Table → CSV; code checks totals and subtotals (for example assets = liabilities + equity)
- Ratios and growth rates computed by the math tools, never by the model
- Graphs: trends described; values read from a chart are marked approximate; data in the document is preferred

Verify: a public financial statement with known figures, a chart with known data.
Done when: extracted figures pass the code checks and chart values are never presented as exact.

- [x] Development set: 24 pages of a Korean annual report, a US 10-K, two Korean results decks, and synthetic charts and tables with known values (`evals/documents/tables.toml`, `scripts/make_chart_set.py`)
- [x] Baseline on the Stage 5 code (Run 42: ✅ 11, ⚠️ 3, ❌ 9 of 23, 48%; "not in the document" 3/3)
- [x] Fixes for the four causes: picture pages always read; charts and pictured tables transcribed as tables, with values read from an axis marked ~; statement totals checked by code (`agent/table_tools.py`); calculations done by code ([calc: ...]) and written arithmetic recomputed; numbers with several thousands separators kept whole
- [x] Rerun of the development set (Run 43: ✅ 18, ⚠️ 2, ❌ 3 of 23, 78%; one "not in the document" check failed; gate not passed)
- [x] Fixes from Run 43: computed numbers explained and rounding slips corrected in any format; chart pages read for any question; charts read as [none] asked again; page readings cached; a related figure no longer given for the asked item
- [ ] Rerun of the development set (Run 44)
- [ ] Regression check of the earlier document sets
- [ ] Holdout, run once: a Korean half-year report, a second 10-K, two more results decks, a paper with tables

### Stage 7 — Visual reasoning experiment
- Thinking variant of the vision model (`qwen3-vl:8b`) vs the instruct variant on counting, charts, sheet music and fine details (cases 02, 06, 08, 11)
- Thinking turned on for the planner
- Measure accuracy against time; decide a fast mode and an accurate mode

Done when: both modes are measured and the defaults are chosen from the numbers.

### Stage 8 — Painter (image generation)
- Local image runner (ComfyUI) controlled through its API as an agent tool
- Painter models chosen by purpose: anime-specialised SDXL models for anime, subculture and game illustration; FLUX or Z-Image models for realistic images
- Two modes: **original creation** from a text description, and **reference-based** generation (image-to-image, style reference)
- Memory management: language and vision models are unloaded while painting and loaded again afterwards
- Speed and memory measured per model and size

Verify: speed and peak memory per model; prompt adherence checked by reading the outputs.
Done when: both modes work from the agent and the speed table is recorded.

### Stage 9 — See, paint, check
- The vision model analyses reference images and writes a style sheet (line weight, colouring, proportions, shading, palette)
- The painter generates from the style sheet and the request
- The vision model checks the result against the request (hands, colours, character details); a failed check repaints, with a limit
- LoRA for the user's own style or a recurring character; pose control (ControlNet)
- Copyright: style references are genre styles or the user's own work, not a living artist's style copied for use

Verify: a character drawn several times stays consistent; the check catches planted errors.
Done when: the loop improves results in the recorded comparison.

### Stage 10 — Motion and media
- `make_gif` (Pillow) and `clip_video` (ffmpeg)

### Stage 11 — Files and document generation
- Read, write and edit files with confirmation; docx, pdf and pptx output; automatic file classifier

### Stage 12 — Portfolio
- README with the architecture diagram and results tables, demo recordings, project write-up
