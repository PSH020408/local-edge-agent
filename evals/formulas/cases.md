# Formula reading set — results

Author: PARK, SEHO

28 numbered equations from six papers in `evals/documents/files`, transcribed from the page images (not by the vision model) (`cases.toml`). Each reading is graded by code against that transcription after normalisation: **exact**, **close** (token similarity ≥ 0.9) or **wrong**.

Two methods:
- **page**: the whole page goes to the vision model once, asked for equation (n). This is how Stage 4 read equations.
- **crop2**: the equation is located by its number in the text layer, read from two crops of different size, and the two readings are compared by code (confirmed / close / disagree).

## Run 34 — first run (2026-11-08)

`python scripts/run_formula_set.py`, 56 readings in 8.2 minutes.

| Method | Exact | Close | Wrong | Mean seconds |
|---|---|---|---|---|
| page | 17 | 7 | 4 | 5.5 |
| crop2 | 20 | 3 | 5 | 11.9 |

Agreement status of crop2 against the grade:

| Status | Exact | Close | Wrong |
|---|---|---|---|
| confirmed | 18 | 1 | 2 |
| close | 0 | 2 | 1 |
| disagree | 2 | 0 | 2 |

Reading the wrong ones:

| Case | What happened | Cause |
|---|---|---|
| F05 (page), F06 (both), F15 (crop2 close) | The readings were right: `G_{\max}` against `G_{max}`, `...` against `\dots` | Grading: function names, dots and `\mid` were not normalised |
| F11, F12 (crop2) | Both crops cut off the left half of the equation; F11 was "confirmed" because both crops were cut the same way | The one-column page was taken for two columns: the test sampled every third character and counted those crossing the exact middle |
| F16 (31), crop2 | Three printed lines with the number on the last; the narrow crop held the last two lines only | A band of fixed height around the number |
| F19 (3), both | Two printed lines, the number between them; the second line (D = E{...}) was left out by both methods | The same, and by the page reading |
| F25 (55), page | The second line ("s.t. ...") left out | Page reading; crop2 was exact |

So crop2 was ahead of page reading only after the crop errors are set aside, and "confirmed" did not mean correct when both crops were wrong in the same way. Agreement between two readings only checks the reading; it cannot check a crop both readings share.

### Fixes after Run 34

| Fix | Kind |
|---|---|
| Function names (`\max`, `\log`, `\Pr` ...), `...` and `\mid` normalised before comparing | Grading and comparison |
| Two columns detected from the text near the equation only: a 1%-wide strip between 45% and 55% of the width with far fewer characters than its neighbours; the crop keeps the column of the equation number. A two-column page can hold a full-width table, so the whole page is not used | Code |
| The crop covers the whole displayed equation: text lines above and below the number are added while they are not prose (four words in a row) and not far away; both crops then add a margin around that, 1 and 3 line heights | Code |

All 28 crops were checked by eye after the fix: F11, F12, F16, F19 and F25 now hold the whole equation.

## Run 35 — after the crop fixes (2026-11-08)

56 readings in 7.5 minutes.

| Method | Exact | Close | Wrong | Mean seconds |
|---|---|---|---|---|
| page | 19 | 7 | 2 | 5.0 |
| crop2 | 23 | 2 | 3 | 11.0 |

| Status (crop2) | Exact | Close | Wrong |
|---|---|---|---|
| confirmed | 23 | 0 | 1 |
| close | 0 | 2 | 1 |
| disagree | 0 | 0 | 1 |

A "confirmed" reading was exact in 23 of 24 cases. Every reading that was not exact, except one, was marked close or disagree.

| Case | What happened |
|---|---|
| F14 (27) | Both readings left out the middle part, "(1 + SNR) =": marked close only because one reading also dropped "bit/s". The page reading had it |
| F19 (3) | The first reading left out the second line (D = E{...}), the second had it; the first was kept. Marked disagree |
| F25 (55) | Both readings left out the constraint line "s.t. ‖X‖² = LP_T" and agreed: confirmed and wrong. The page reading left it out too |
| F18 (57), F22 (22) | One reading wrong in one symbol (\tilde for \bar; a square root closed too late): marked close |

What two readings cannot catch is a part both of them leave out. Two changes:

| Fix | Kind |
|---|---|
| When one reading is the other with parts added and nothing changed, the more complete one is kept (F19) | Code |
| A third call shows the vision model the larger crop and the chosen transcription and asks whether anything in the image is missing or wrong; any answer other than COMPLETE withdraws a confirmation (status check_failed) | Code + model |

Whether the check catches F14 and F25 without raising false alarms on the 23 exact readings is measured in the next run.

## Run 36 — more complete reading kept, check against the image (2026-11-08)

`run_formula_set.py --method crop2`, 28 formulas in 6.0 minutes (12.9 s per formula).

| Method | Exact | Close | Wrong |
|---|---|---|---|
| crop2 | 26 | 2 | 0 |

| Status | Exact | Close | Wrong |
|---|---|---|---|
| confirmed | 23 | 0 | 0 |
| close | 0 | 2 | 0 |
| disagree | 3 | 0 | 0 |

- F14, F19 and F25 were exact because one of the two readings had the part the other left out, and the more complete one was kept. In Run 35 both readings of F14 and F25 had left the same part out, so this depends on the two readings differing; it varies between runs.
- The check against the image answered COMPLETE for 26 readings, including the 23 confirmed ones (all exact: no false alarm there) and F18, whose reading still has w for ω (a miss). It answered MISSING twice: F22, which is wrong in one symbol, though the reason it gave was partly wrong, and F25, which was exact (a false alarm; the status was already disagree). No confirmed reading was wrong in this run, so whether the check catches shared omissions is still unmeasured. It stays as a safety net that can only withdraw a confirmation, and it is measured again on the holdout.

Over Runs 35 and 36 a confirmed reading was exact 46 times out of 47.
