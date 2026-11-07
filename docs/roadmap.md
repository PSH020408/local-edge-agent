# Roadmap

Author: PARK, SEHO

Principle: **everything runs locally** on one MacBook Pro (M4 Pro, 24 GB). No cloud models or services, including image generation.

Goal: a local agent that helps with graduate-school preparation, exam preparation, reading PDFs, papers and handouts, formula, graph and financial-statement analysis, art-style analysis, and image generation (anime and subculture styles, game illustration, realistic people, animals, objects and landscapes).

## How every stage is verified

1. Questions are asked by hand, one at a time, with `/reset` between them. No automated question sets.
2. Every observed failure gets a fix and an offline regression test (`python -m unittest discover -s tests`).
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

## Latest stage

### Stage 3 — Eyes (vision), complete

Built: `describe_image`, `read_text_in_image` (two readings compared by code), zoom by locating parts, pixel budget, repetition and length limits, image question planner (plan under a JSON schema, one vision call per part, code-assembled answer), guard messages in the terminal.

Remaining:
- [x] Answers from the wider-view retry marked as unverified
- [x] `read_text_in_image` reads only the target text; readings that differ only in punctuation are reported as such; minimum size for the tight crop
- [x] Parts with the same focus merged into one call; maximum parts 6 → 8
- [x] Coverage check: terms in the question (CS, SDA, "describe") that appear in no planned part are reported
- [x] Image questions planned by `qwen3:14b`, also in fast mode
- [x] Planning time and total time shown; the sign-location note only for photos
- [x] Recheck cases 01 and 10, then the full set (12 cases + H1-H4): Runs 20-23
- [x] One-command test run: `scripts/run_vision_set.py` (Run 22)

Done when: cases 01 and 10 are correct or honestly marked uncertain with no confident wrong answers, and the full set is recorded.

Result (Run 23): ✅ 4, ⚠️ 7, ❌ 1, hallucination checks 4/4 (Run 13: ✅ 2, ⚠️ 6, ❌ 4, 3/4).

Accuracy over speed: two profiles.
- [x] `--fast`: `qwen3:8b` main model, `qwen3:14b` planner, one look per part (about 7 minutes for the set)
- [x] `--accurate`: `qwen3:14b` with planning thinking, a second look and majority vote for factual answers, tile scan for large images, thinking vision model for counting and comparing, larger pixel budget
- [x] Experiment: model size x checking method, four profiles (`small`, `large`, `small-accurate`, `large-accurate`), one command (`run_vision_set.py --compare`) (Run 24: 14B planning is better; the accurate profile as built is worse and 3-4× slower, see evals/vision/cases.md)
- [ ] Redesign the accurate profile from the Run 24 findings
- [ ] Holdout: new images, run once, not used for tuning

## Next

### Stage 4 — Documents (PDF, handouts, papers) — in progress

Built: `agent/document_tools.py` (PDF and PowerPoint pages, tables, notes, garbled-equation detection, template removal, page rendering), `agent/document_planner.py` (page selection, vision for equation and figure pages, cited answers, citation and number checks, whole-document summaries and practice questions), `read_document` tool, test set `evals/documents/` (3 documents, 16 questions, 3 hallucination checks), `scripts/run_eval_set.py --set documents`.

- [x] First run of the document set (Run 25: ✅ 13, ⚠️ 3, ❌ 0, hallucination checks 3/3; fixes recorded in evals/documents/cases.md)
- [x] Rerun after the Run 25 fixes (Run 26: ✅ 14, ⚠️ 4, ❌ 0, 3/3, 11 minutes)
- [x] Holdout: three new lectures, run once (Run 27: ✅ 16, ⚠️ 2, ❌ 3, hallucination checks 3/3)
- [x] Fix the failure types the holdout found: picture-only pages captioned for the index, superscripts marked from character positions, figure values kept with their labels (see evals/documents/cases.md)
- [x] Check run of the fixes on the development set and the seen holdout (Run 28: development ✅ 14, ⚠️ 2; seen holdout ✅ 18, ⚠️ 3, ❌ 0)
- [ ] A new holdout after those fixes (this one has now been seen), including a two-column paper

Plan:
- Text extraction from the PDF text layer (exact, no vision needed)
- Page rendering to images for scanned pages, figures and formulas; only those go to the vision model
- Summaries per page and section with page references; long documents split to fit the context window
- Exam preparation: questions and explanations generated from a handout, each with its source page

Verify: 3-5 real study documents (lecture handout, paper, scanned page). Check that page references are correct and nothing is invented.
Done when: answers cite the right pages and no content is invented in the test documents.

### Stage 5 — Formulas
- Vision transcribes a formula to LaTeX, read twice and compared
- sympy checks that the LaTeX parses; symbols and dimensions are checked where possible
- The main model explains; any calculation goes to the math tools

Verify: formulas from papers with known LaTeX.
Done when: transcriptions match the known LaTeX or are marked uncertain.

### Stage 6 — Tables, financial statements and graphs
- Table → CSV; code checks totals and subtotals (for example assets = liabilities + equity)
- Ratios and growth rates computed by the math tools, never by the model
- Graphs: trends described; values read from a chart are marked approximate; data in the document is preferred

Verify: a public financial statement with known figures, a chart with known data.
Done when: extracted figures pass the code checks and chart values are never presented as exact.

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

Verify: speed and peak memory per model; prompt adherence checked by hand.
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
