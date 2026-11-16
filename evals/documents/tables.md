# Stage 6 test set: tables, financial statements and charts

Questions in `tables.toml`, answered by the document planner. Development documents: 24 pages cut from a
Korean annual report, a US 10-K, two Korean quarterly results decks, and a synthetic set of charts and
tables with known values (`scripts/make_chart_set.py`, true values in `evals/charts/answers.toml`). The
real documents are kept in `evals/documents/files/` and not committed. Held back for the holdout: a
Korean half-year report, a second 10-K, two more results decks and a paper with tables.

Grading, answer by answer, against the page images and the note in `tables.toml`:

- ✅ every asked value right, cited to a page that holds it; computed values right to the shown precision
- ⚠️ mostly right: one detail wrong or missing, or a computed value off in the last digit
- ❌ a wrong value or label, a false "not in the document", or invented content
- "Not in the document" checks: the answer must say so and invent nothing

The key-fact count in the report (`key facts 2/3`) only checks that given strings appear; it is a quick
indicator, not the grade.

Every run is also published with its answers and grades in `runs/` (`scripts/export_run.py`).

## Run 42 — baseline before any Stage 6 work (2026-11-15)

Code 7f75361 (Stage 5 complete). 26 cases in 35.6 minutes.

| # | Question | Grade | Notes |
|---|---|---|---|
| TA1 | Revenue, operating profit, net income | ✅ | |
| TA2 | Operating margin | ✅ | 13.07%; the number check called the computed 13.07 "not in the document" |
| TA3 | Assets = liabilities + equity | ✅ | |
| TA4 | Tax expense in parentheses | ✅ | Explained as a tax benefit |
| TA5 | Operating cash flow minus capex | ✅ | 37,792,969; the number check split "37,792,969백만원" into 37792 and 969 and flagged both |
| TB1 | Net sales, net income, growth | ⚠️ | Growth 19.48% (true 19.50%): mental arithmetic |
| TB2 | Balance sheet identity | ✅ | |
| TB3 | Gross margin percentage | ✅ | 46.9% against 46.2% |
| TB4 | Repurchases and dividends | ✅ | Took the MD&A figures ($89.3 and $15.4 billion, total $104.7 billion), which the page states; the key only listed the cash-flow figures |
| TC1 | DS and DX revenue, DS share | ✅ | 75.3%, flagged as "not in the document" although computed |
| TC2 | Quarters with an operating loss (chart) | ❌ | "2026년 4분기, −0.7": wrong quarter, the second loss (−0.6) missed. The page description answered "[none]" for the chart |
| TC3 | Debt ratio recomputed | ⚠️ | 28.95% (true 28.94%) |
| TC4 | Dividend total and per share | ✅ | |
| TD1 | Largest factor in the revenue decline (waterfall) | ❌ | "환율, 3,435": the amount belongs to volume (물량) |
| TD2 | FX effect on operating profit, margin | ❌ | FX effect given as −1,611 (the total revenue change); margin 5.4% → 5.9% right |
| TD3 | Global wholesale units and change (chart) | ❌ | "20,514천대, −10.1%": industry demand and the retail change, not wholesale (921, −11.3%) |
| TD4 | Debt ratio check | ✅ | |
| SC1 | Labelled bars (image-only page) | ❌ | "Not covered": the page has no text and was never shown to the vision model |
| SC2 | Unlabelled bars | ❌ | Same |
| SC3 | Stacked bars | ❌ | Same |
| SC4 | Dual-axis chart | ❌ | Same |
| SC5 | Negative bar, Korean | ❌ | Invented: "전자부품, 1,475억" from a page it never read (the number check flagged 1475) |
| SC6 | Table with a wrong subtotal | ⚠️ | Found gross profit 1,360 ≠ 2,310 − 1,050, then called operating income inconsistent as well, using the wrong subtotal |
| TH1-TH3 | Not in the document | 3/3 | |

**✅ 11, ⚠️ 3, ❌ 9 of 23 (48%); "not in the document" checks 3/3.**

Predictions written before the run: lookups mostly right (yes), mental arithmetic slips (yes, two),
chart pairing weak (yes, four), unlabelled values off (not reached: the raster pages were never read),
the wrong subtotal missed (no: found when the question asked to check).

Four causes:

1. Pages with no text are not read. The pages of a PDF made of images were never flagged as figures and
   were not captioned (only two of ten were), so no page description was made and the answer had no
   content: four false "not in the document" answers and one invented answer.
2. Charts lose the pairing of numbers and bars. The text layer holds the labels of a deck's charts, but
   not which number belongs to which bar or series; the page description is asked for "equations and
   figures" and answered "[none]" for chart pages.
3. Arithmetic is done by the answer model: two results off in the last digit, and every computed value
   is then flagged by the number check as not in the document.
4. The number check splits a number glued to a unit (37,792,969백만원).

### Fixes after Run 42

| Cause | Fix | Kind |
|---|---|---|
| Picture pages not read (SC1-SC5) | A page with a picture and almost no text is a picture page even when the same full-page picture box repeats on every page; a picture page that was not read is marked in the context as unreadable, so nothing is taken from it | Code |
| Charts read as "[none]", numbers paired with the wrong bars (TC2, TD1-TD3) | The page reading asks for charts as tables (category × series, values printed or estimated from the axis with ~, waterfall steps with signs) and for pictured tables cell by cell; slides with many vector paths (a waterfall chart) are flagged as figures and read | Prompt and code |
| Mental arithmetic (TB1, TC3) and computed values flagged | The answer writes [calc: expression]; code computes it. Arithmetic written out anyway ("a / b ≈ c") is recomputed and corrected. Computed results count as known numbers | Code |
| Totals | Statement totals on the pages given (assets = liabilities + equity, gross profit, operating income) are recomputed by code for every period and given to the answer as "checked by code"; a wrong subtotal is reported, and the next check uses its recomputed value (SC6) | Code |
| Number split (TA5) | Numbers with several thousands separators are read as one number | Code |

Backtest of the arithmetic check on the 196 answers of Runs 37-42: one correction (TC3, 28.95 → 28.94),
five correct results confirmed, no other answer changed.

Gate for Run 43, written before it: ✅ 17 or more of 23; no false "not in the document" on SC1-SC4;
nothing invented on SC5; SC6 does not call operating income wrong; no computed value flagged as not
in the document; "not in the document" checks 3/3.

Predictions: SC1, SC5 and SC6 right (printed labels, code check); SC2 and SC3 within a few percent
and marked approximate; SC4 needs the unlabelled 2025 bar (1,890) from the axis, so it may be off;
TC2 and TD2 right (chart tables, the waterfall now read); TD3 uncertain (a page with sixteen bar
groups); TB1 and TC3 right (calculations by code).

## Run 43 — after the Run 42 fixes (2026-11-15)

26 cases in 50.8 minutes (the first run captioned the picture pages of two documents; the captions are
cached). Answers and grades: `runs/run43.md`.

| # | Run 42 | Run 43 | Notes |
|---|---|---|---|
| TA1-TA5 | ✅ 5 | ✅ 5 | Calculations now by code; no false number warnings |
| TB1 | ⚠️ | ⚠️ | 19.49% (true 19.50%): written in LaTeX, without [calc], so the code did not compute it |
| TB2-TB4 | ✅ 3 | ✅ 3 | TB4's total computed by code but printed as "104.70" next to the model's own "104.7" |
| TC1, TC3, TC4 | ✅ 2, ⚠️ 1 | ✅ 3 | TC3 now 28.94% by code |
| TC2 | ❌ | ✅ | The chart was read as a table: 2Q −0.7, 3Q −0.6 |
| TD1 | ❌ | ✅ | The waterfall was read as a table: volume −3,435 |
| TD2 | ❌ | ❌ | The waterfall page was not read: the question did not say "chart" |
| TD3 | ❌ | ❌ | The page with sixteen bar groups was read as [none] |
| TD4 | ✅ | ✅ | |
| SC1, SC2, SC5 | ❌ 3 | ✅ 3 | Picture pages read; SC2's unlabelled bars estimated as ~48 and ~95 (true 48 and 95) |
| SC3 | ❌ | ❌ | Read now, but the 1,890 total label was taken for the Devices segment; Cloud ~400 (true 720) |
| SC4 | ❌ | ⚠️ | 2025 and 14.0% right; revenue read as 1,900 (true 1,890), 266 not called approximate |
| SC6 | ⚠️ | ✅ | The code check found the wrong gross profit and the answer kept operating income right |
| TH1, TH3 | pass | pass | |
| TH2 | pass | **fail** | Gave all memory revenue (140.7조원) as HBM revenue: the page reading now puts more numbers in the context, and the answer took the nearest one |

**✅ 18, ⚠️ 2, ❌ 3 of 23 (78%, from 48%); "not in the document" checks 2/3.**

Gate: ✅ 17 or more (met, 18); no false "not in the document" on SC1-SC4 (met); nothing invented on SC5
(met); SC6 (met); no computed value flagged (not met: TB1, TB4 and SC4 did their own arithmetic);
"not in the document" 3/3 (not met: TH2). **Gate not passed.**

Predictions: right for SC1, SC5, SC6, TB1 was predicted right and was not (no [calc]), TC2 and TD2:
TC2 right, TD2 not (the page was never read). SC2 within a few percent (exact), SC4 off as predicted,
TD3 uncertain (failed).

### Fixes after Run 43

| Problem | Fix | Kind |
|---|---|---|
| Arithmetic done by the answer without [calc] (TB1, TB4, SC4) | A number in the answer that is not in the document is explained, where possible, as one step of arithmetic on two document numbers in the same paragraph; a match at the shown precision counts as computed, one off only in the last digit is corrected (TB1 19.49 → 19.50). Sums keep the operands' decimals (104.7, not 104.70) | Code |
| A chart page not read when the question does not say "chart" (TD2) | In slides and reports, a figure page whose text is mostly numbers, and not table rows, is a chart page and is read for any question | Code |
| A chart page read as [none] (TD3) | Asked once more with a prompt for charts only | Code |
| Page readings redone for every question (TD1 took 526 s) | Readings are cached per document and page; the cache is renewed when the reading prompts change | Code |
| A related figure given for the asked item (TH2) | Answer rule: give a number only for the item asked; a figure for a larger group or another series of the chart is not the asked figure. Examples in the rule are generic, not from the test set | Prompt |

Backtest of the arithmetic explanation on the answers of Runs 37-43: TC3's 28.95 corrected to 28.94,
nine computed values explained, no other answer changed. The chart-page test marks 4 of 20 pages in
one results deck and 2 note pages of the annual report, and no page of the lecture decks.

Known limit: SC3, a stacked bar read with a total label taken for a segment, is a reading error of
the vision model; a second reading compared with the first, as for equations, is the next step if
it stays.

Gate for Run 44, written before it: ✅ 19 or more of 23; "not in the document" checks 3/3 (TH2 run
three more times if it fails, before it counts); no computed value flagged as not in the document;
no case that was ✅ in Run 43 drops to ❌ without repeats confirming it.

## Run 44 — after the Run 43 fixes (2026-11-15)

Code f1f50cb (committed before the run). 26 cases in 57.6 minutes; the page readings were made once
and cached. Answers and grades: `runs/run44.md`.

| # | Run 43 | Run 44 | Notes |
|---|---|---|---|
| TA1-TA5 | ✅ 5 | ✅ 5 | TA4 took 286 s: a note page of the annual report counts as a chart page and was read |
| TB1 | ⚠️ | ⚠️ | 19.48% (true 19.50%), flagged with 18,274: the operands are in the prose, the result two LaTeX blocks later, in two steps; the explanation looked only in the result's own paragraph |
| TB2-TB4 | ✅ 3 | ✅ 3 | TB4's total now printed once |
| TC1-TC4 | ✅ 4 | ✅ 4 | TC3's written 28.95 corrected to 28.94 by code |
| TD1 | ✅ | ✅ | |
| TD2 | ❌ | ✅ | The waterfall page is now a chart page and is read for any question: FX +1,283 |
| TD3 | ❌ | ❌ | Read now, but the wholesale bar was given as 21,823천대 (true 921); the change −11.3% is right |
| TD4 | ✅ | ✅ | |
| SC1, SC2, SC5, SC6 | ✅ 4 | ✅ 4 | |
| SC3 | ❌ | ❌ | The 1,890 total label taken for the Devices segment again |
| SC4 | ⚠️ | ⚠️ | Unchanged: revenue 1,900 (true 1,890), 266 not called approximate |
| TH1-TH3 | 2/3 | 3/3 | TH2 says HBM revenue is not given |

**✅ 19, ⚠️ 2, ❌ 2 of 23 (83%, from 78% and 48%); "not in the document" checks 3/3.**

Gate: ✅ 19 or more (met); "not in the document" 3/3 (met); no computed value flagged (not met:
TB1); no drop from ✅ to ❌ (met). **Gate not passed**, on TB1 alone.

Both remaining ❌ are readings of the vision model (a page with sixteen bar groups; a stacked bar
whose total label sits above the top segment). The vision model also wrote about the page number it
was given ("the page number is 11, not 12"): the prompt said "page n" with the PDF page index, which
is not the number printed on the page.

### Fixes after Run 44

| Problem | Fix | Kind |
|---|---|---|
| Operands of written arithmetic in an earlier paragraph, results in two steps (TB1) | The explanation looks for the two operands in the number's paragraph and the four before it, nearest first; an explained result is a known number for the next step (18,274, then 18,274 / 93,736 × 100). A result off by more than the shown precision is corrected only when it is written as a result ("= 19.48") and is within one unit of the last digit or 0.1% of the correct value; a number given as a fact is never changed | Code |
| The page index given to the vision model | The page reading prompts no longer give a page number; the cached readings are renewed | Prompt |

Backtest of the new explanation on the 15 answers of Runs 33-44 that had numbers flagged: TB1
corrected in Runs 43 and 44 (19.49 and 19.48 → 19.50) and in Run 42 (19.48 → 19.50), TC3 in Run 42
(28.95 → 28.94, as before), 13.07, 75.3, 104.7, 266, 1,260 and 510 explained; 1,475 (SC5, invented
in Run 42), the invented 10,000 (PA8) and the ECG paper's decimal-comma figures unchanged.

### Run 45 plan: tables set and full regression, one command

The prompt change renews every page reading, and the picture-page, chart-page and reading-prompt
changes of Stage 6 touch the earlier sets, which have not been run since Stage 5. All eight sets run
in one command. Gates, written before the run:

| Set | Last result | Gate |
|---|---|---|
| Tables (23 + 3) | ✅ 19, ⚠️ 2, ❌ 2 (Run 44) | ✅ 19 or more; TB1 ✅ with no flag; no computed value flagged |
| Development (16 + 3) | ✅ 15, ⚠️ 1 (Run 38) | ✅ 15 or more, no ❌ |
| First holdout, lectures (21 + 3) | ✅ 19, ⚠️ 2 (Run 38) | ✅ 18 or more, no ❌ |
| Second holdout, papers (21 + 3) | ✅ 19, ⚠️ 1, ❌ 1 (Run 38) | ✅ 18 or more |
| Third holdout, long papers (24 + 3) | ✅ 19, ⚠️ 3, ❌ 2 (Run 38) | ✅ 18 or more, SA8 and RA11 ✅ |
| Fourth holdout, papers with equations (19 + 2) | ✅ 16, ⚠️ 2, ❌ 1 (Run 38) | ✅ 16 or more |
| Equations (18) | ✅ 16, ⚠️ 1, ❌ 1 (Run 39); UN1 and UN2 fixed (Run 40) | ✅ 16 or more |
| Fifth holdout, RISC-V paper (16 + 3) | ✅ 11, ⚠️ 5, ❌ 0 (Run 41) | ✅ 11 or more, no ❌ |

Every "not in the document" check must pass. A case that drops from ✅ to ❌ is run three more times
before it counts.

Predictions: TB1 ✅; TD3 and SC3 stay ❌ (vision readings, not touched); lecture decks unchanged, as
the chart-page test marks none of their pages; the paper sets unchanged, as chart pages are read only
in documents that are not papers.

## Run 45 — tables set and full regression (2026-11-16)

Code 745310e. All eight document sets in one command: 178 questions. The first four sets ran with
the GPU held at its lowest clocks (see `docs/devlog.md`); the machine was shut down, and the last four
ran at normal speed. Model call profile of the last four sets (64 minutes of model time): `qwen3:14b`
76% of the time, of which two thirds was reading the prompt; the vision model 24%; model loading
under 1%. Tables answers and grades: `runs/run45.md`.

| Set | Last result | Run 45 | Gate |
|---|---|---|---|
| Tables (23 + 3) | ✅ 19, ⚠️ 2, ❌ 2 (Run 44) | ✅ 19, ⚠️ 2, ❌ 2; 3/3 | ✅ 19 or more, TB1 ✅ with no flag, no computed value flagged: **passed** |
| Development (16 + 3) | ✅ 15, ⚠️ 1 (Run 38) | ✅ 14, ⚠️ 2, ❌ 0; 3/3 | ✅ 15 or more, no ❌: not met (D06) |
| First holdout, lectures (21 + 3) | ✅ 19, ⚠️ 2 (Run 38) | ✅ 19, ⚠️ 1, ❌ 1; 3/3 | ✅ 18 or more, no ❌: not met (GC2) |
| Second holdout, papers (21 + 3) | ✅ 20, ❌ 1 (Run 38, after repeats) | ✅ 20, ⚠️ 1, ❌ 0; 3/3 | ✅ 18 or more: passed |
| Third holdout, long papers (24 + 3) | ✅ 19, ⚠️ 4, ❌ 1 (Run 38, after repeats) | ✅ 20, ⚠️ 3, ❌ 1; 3/3 | ✅ 18 or more, SA8 and RA11 ✅: passed |
| Fourth holdout, papers with equations (19 + 2) | ✅ 17, ⚠️ 1, ❌ 1 (Run 38, BS3 regraded) | ✅ 18, ⚠️ 0, ❌ 1; 2/2 | ✅ 16 or more: passed |
| Equations (18) | ✅ 17, ⚠️ 1 (Runs 39-40) | ✅ 16, ⚠️ 1, ❌ 1 | ✅ 16 or more: passed |
| Fifth holdout, RISC-V paper (16 + 3) | ✅ 11, ⚠️ 5 (Run 41) | ✅ 11, ⚠️ 5, ❌ 0; 3/3 | ✅ 11 or more, no ❌: passed |

"Not in the document" checks: 20/20. Cases whose key facts, warnings and flags were unchanged were
checked by spot reading; every case with a change was read in full.

Changes against the last run of each set:

| Case | Before | Run 45 | Notes |
|---|---|---|---|
| TB1 | ⚠️ | ✅ | 19.48 corrected to 19.50 by code across paragraphs; no flag |
| TC2 | ✅ | ⚠️ | The chart reading had both loss quarters; the answer gave only 2Q '26 |
| GC2 (lectures and equations) | ✅ | ❌ | The positional-encoding formulas exist only as a picture. The new page-reading prompt returned [none] for the slide, and the retry asked for charts. Systematic, not run-to-run variation |
| D06 | ✅ | ⚠️ | Base station ID, frequency and synchronization information right; PSS, SSS and PBCH left out |
| GA6 | ⚠️ | ✅ | Iris recognition now named correctly |
| PA10 | ✅ | ⚠️ | Another point from the Discussion instead of the stated limitations (as in Runs 30-32) |
| VA1 | ❌ | ✅ | First time right: CIC 16, then 2, 2, 2, total 128 = 6.144 MHz / 48 kHz; the number check flagged the correct 128 (a product of four numbers) |
| RA6 | ⚠️ | ✅ | "Reconfigurable" this time |
| BS9 | ⚠️ | ✅ | Cited to the right page now |
| RV1 | ⚠️ | ⚠️ | The confirmed reading is used now, but one sentence is cited to the wrong page (flagged) |

Predictions: TB1 ✅ (yes); TD3 and SC3 stay ❌ (yes); lecture decks unchanged (no: GC2, because the
page-reading prompt change reached a formula slide); paper sets unchanged (yes, within run-to-run
variation).

Speed: the equation set took 13.3 minutes (64 in Run 39) and the fifth holdout 11.8 minutes (51.8 in
Run 41) on the same kind of code path: Runs 39 and 41 had the same slowdown as the first half of Run 45.

### Fix after Run 45

| Problem | Fix | Kind |
|---|---|---|
| A figure page that is not a chart page, read as [none], was asked again for charts (GC2) | Chart pages are asked again for charts; any other figure page with [none] is asked again with a prompt that names equations, tables, charts and diagrams and has no [none] answer. The prompt is part of the cache version, so pages stored as empty are read again | Code and prompt |

Check before closing the stage: GC2 in both sets once (the cause is systematic), D06, TC2 and PA10
three times each (one-case drops are counted only when repeats confirm them).

### Check after the fix (2026-11-16)

Code 251e890. GC2 once in each set, D06, TC2 and PA10 three times each.

| Case | Run 45 | Check | Counted |
|---|---|---|---|
| GC2 (lectures) | ❌ | ✅ both positional-encoding formulas, read from the picture by the new retry prompt | ✅ |
| GC2 (equations) | ❌ | ✅ the same reading, from the cache | ✅ |
| D06 | ⚠️ | ✅ 3 of 3: PSS, SSS, PBCH and the information carried | ✅ |
| TC2 | ⚠️ | ✅ 3 of 3: 2Q '26 −0.7 and 3Q '26 −0.6 | ✅ |
| PA10 | ⚠️ | ⚠️ 3 of 3: other points from the Discussion, not the stated limitations | ⚠️ |

Counted results after the check: tables ✅ 20, ⚠️ 1, ❌ 2 (87%); development ✅ 15, ⚠️ 1; lectures
✅ 20, ⚠️ 1; equations ✅ 17, ⚠️ 1; the other sets as in the Run 45 table. **Every gate is met.**

Stage 6 result on the development set: 48% (Run 42) → 87%, with no wrong "not in the document"
answer. The two remaining wrong answers are chart readings of the vision model (TD3, SC3). The short
holdout on unseen financial documents is run once on this code and recorded below.
