# Roadmap

Author: PARK, SEHO

Principle: **everything runs locally** on one MacBook Pro (M4 Pro, 24 GB). No cloud models or services, including image generation.

Goal: a local agent that helps with graduate-school preparation, exam preparation, reading PDFs, papers and handouts, formula, graph and financial-statement analysis, art-style analysis, and image generation (anime and subculture styles, game illustration, realistic people, animals, objects and landscapes).

## How every stage is verified

1. Questions come from case files and run with one command (`scripts/run_eval_set.py`); every answer is read and graded by hand.
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

## Latest stage

### Stage 4 — Documents (PDF, handouts, papers), complete

Built: `agent/document_tools.py` (PDF and PowerPoint text, tables, notes, superscripts, template removal, garbled-equation, vector-figure and numbered-equation detection, passages), `agent/document_planner.py` (page selection for slides, passage search for papers, captions for picture-only pages, vision for equation and figure pages, cited answers, a second search before "not in the document", checks of citations, numbers, acronym expansions and citation pages, whole-document summaries and practice questions merged to fit the context), `read_document` tool, four case files in `evals/documents/`.

- [x] First run of the document set (Run 25: ✅ 13, ⚠️ 3, ❌ 0, hallucination checks 3/3; fixes recorded in evals/documents/cases.md)
- [x] Rerun after the Run 25 fixes (Run 26: ✅ 14, ⚠️ 4, ❌ 0, 3/3, 11 minutes)
- [x] Holdout: three new lectures, run once (Run 27: ✅ 16, ⚠️ 2, ❌ 3, hallucination checks 3/3)
- [x] Fix the failure types the holdout found: picture-only pages captioned for the index, superscripts marked from character positions, figure values kept with their labels (see evals/documents/cases.md)
- [x] Check run of the fixes on the development set and the seen holdout (Run 28: development ✅ 14, ⚠️ 2; seen holdout ✅ 18, ⚠️ 3, ❌ 0)
- [x] A new holdout after those fixes: two research papers (Run 29: ✅ 8, ⚠️ 2, ❌ 11, 38%; hallucination checks 3/3). Page selection and the context budget fail on dense paper pages
- [x] Retrieval for papers: search passages (headings, table and figure captions, paragraphs) instead of whole pages; give the model passages, not cut pages
- [x] Before accepting "not in the document", search the whole text for the question's terms and retry
- [x] Flag vector figures and numbered equations in PDFs (papers only)
- [x] Regression check (Run 30): development ✅ 16, first holdout ✅ 19, papers ✅ 19 of 21; the lecture sets did not drop
- [x] A third holdout (new papers), run once (Run 31: ✅ 15, ⚠️ 5, ❌ 4, 62.5%; hallucination checks 3/3)
- [x] Fix from Run 31: passages dropped by the budget must not count as checked; index lines that show what a long passage contains; expansions and terms not in the document flagged; faster whole-document tasks for long papers
- [x] Regression check on all four sets (Run 32): lecture holdout and short papers held; development ✅ 14, one below the gate, traced to run-to-run variation by three repeats of D04 and D06
- [x] Fourth holdout: two one-column papers with equations, tables and figures, run once (Run 33: ✅ 14, ⚠️ 2, ❌ 3, 74%; hallucination checks 2/2)

Holdouts, each run once on unseen documents:

| Run | Documents | Correct | "Not in the document" checks |
|---|---|---|---|
| 27 | Three lecture decks | 76% | 3/3 |
| 29 | Two short papers, before passage search | 38% | 3/3 |
| 31 | Two long papers | 62.5% | 3/3 |
| 33 | Two one-column papers with equations, tables and figures | 74% | 2/2 |

Done when: answers cite the right pages and no content is invented in the test documents. Met for the "not in the document" checks in every run; the remaining wrong answers are misreadings of the pages, listed below, and the code flags most of them (unread equations, numbers, expansions, citation pages).

Carried over:
- Stage 3: redesign the accurate profile from the Run 24 findings; a vision holdout on new images
- Stage 4: keyword search ignores Greek letters and equation numbers (a question about φ, α in equation (3) found nothing); explanations of equation-heavy passages are misread (operators swapped, a count of 5 read as 3); the vision model can miss a chart when asked for "equations and figures"; formulas from the text layer are wrong when it loses exponents (π^(1/4) read as π⁴). These go to Stage 5.

## Next

### Stage 5 — Formulas
- Vision transcribes a formula to LaTeX, read twice and compared
- sympy checks that the LaTeX parses; symbols and dimensions are checked where possible
- The main model explains; any calculation goes to the math tools
- From Stage 4: search by symbols and equation numbers; a formula in an answer is always read from the page image, never from the text layer; a symbol table per document (what each symbol stands for, with its page)

Verify: formulas from papers with known LaTeX, including the equations in the document test sets.
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
