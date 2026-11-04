# Guardrails

The main model (`qwen3:8b`) often ignores rules written in prompts. Experiments (docs/benchmarks.md, Runs 13-17) showed that a rule only works reliably when code enforces it. This document lists every constraint by how strongly it is enforced.

When a guard acts during a session, the terminal shows it as a yellow line starting with ⚙ (`agent/display.py`).

## Level 1 — Enforced in code

The model cannot avoid these. They act on every call.

| Guard | Where | What it does | Why (run) |
|---|---|---|---|
| Step limit | `agent/loop.py` | Stops after 8 model steps without a final answer | Run 7 |
| Repeated failure block | `agent/loop.py` | A call identical to one that failed is not executed again (warning), the third attempt stops the run. "NOT FOUND" and "NOT LOCATED" count as failures | Runs 7, 17 |
| Empty reply retry | `agent/loop.py` | An empty model reply is retried once, then reported | Run 8 |
| Argument validation | `agent/tools.py` | Unknown or missing arguments are rejected before execution; the error names the tool that accepts them. Numbers sent as strings are converted | Runs 5, 8 |
| No silent midnight | `agent/time_tools.py` | Adding hours to a date without a time of day is an error | Run 8 |
| Expression sandbox | `agent/math_tools.py` | Only whitelisted functions and operators; no `eval`; exponent and sequence size limits | Run 6 |
| `^` interpretation | `agent/math_tools.py` | `^` is power, except next to hex/binary literals (XOR); the result states the reading | Run 7 |
| Image preparation | `agent/vision_tools.py` | Format conversion, EXIF rotation, pixel budget (about 1.2 MP), zoomed crops enlarged up to 3×, small images up to 2× | Runs 11, 12, 14 |
| Whole-image focus ignored | `agent/vision_tools.py` | Focus values that mean the whole image ("whole image", "전체", ...) skip the locate step | Run 17 |
| Minimum focus crop | `agent/vision_tools.py` | A zoomed crop is at least 15% of the image width and height | Run 18 |
| Oversized focus ignored | `agent/vision_tools.py` | A located area above 60% of the image is treated as the whole image | Run 15 |
| Vision output limit | `agent/vision_tools.py`, `config.toml` | At most 1,200 output tokens; a sentence repeated five times cuts the answer (three real repeats are kept, Run 21) | Runs 16, 21 |
| Reading verdict | `agent/vision_tools.py` | read_text_in_image reads only the target text twice (two crop sizes); code compares the readings and sets CONFIRMED / CONFIRMED CHARACTERS (only punctuation differs) / PARTLY CONFIRMED (one reading cut off) / PARTLY UNCLEAR / UNCERTAIN | Runs 13, 19, 20 |
| Not-found classification | `agent/vision_tools.py` | A printed label (R50, U5, AMS1117) not found → NOT FOUND; a general description → NOT LOCATED with a retry hint | Runs 14, 16 |
| File type block | `agent/builtin_tools.py` | read_file refuses images and binary files | Run 11 |
| Workspace sandbox | `agent/builtin_tools.py` | File and image tools cannot read outside the workspace | Run 1 |
| Image question planner | `agent/image_planner.py` | A question with an image path is split into parts under a JSON schema (Ollama structured outputs) by `qwen3:14b`, also in fast mode; code then makes one vision call per part, so no planned part can be skipped | Runs 15-17, 19 |
| Plan coverage check | `agent/image_planner.py` | Labels in the question (CS, OLED, AMS1117) must appear in the plan; otherwise a new plan is requested once, and anything still missing is reported in the answer. (A check for "a request to describe" was removed in Run 21: it misread "explain why it is funny") | Runs 19, 21 |
| Whole-image questions | `agent/image_planner.py` | Parts about counting, comparing, a conversation's flow, humor, feelings, mood, style, layout or a summary are never zoomed | Run 21 |
| Focus cleanup | `agent/image_planner.py` | A list in brackets after a space is removed from a focus ("OLED interface (SDA, SCL)" → "OLED interface"; "log10(Pb)" is kept) | Runs 20, 21 |
| Echo-located focus | `agent/vision_tools.py` (planner calls) | When the locator returns the request itself as the label and the box is below 5% of the image, the box is treated as not located and the part is asked about the whole image, marked as not checked by zoom. Large echo-located areas are trusted | Runs 18-21 |
| Same focus merged | `agent/image_planner.py` | Parts that look at the same thing are asked together in one view, including all whole-image parts (at most 8 parts) | Runs 19, 21 |
| Nearby lines | `agent/vision_tools.py` | When the wider reading only adds whole lines before or after the tight reading, the tight reading is confirmed and the extra lines are shown as nearby text | Run 22 |
| Same text in two parts | `agent/image_planner.py` | Two different parts that read the same text are both marked "check the place" | Run 22 |
| Long text from the whole image | `agent/image_planner.py` | Comments, conversations, threads and pages are transcribed from the whole image, not as one short reading; a reading with no text falls back to the whole image | Run 22 |
| Reading that repeats the request | `agent/vision_tools.py` | A reading that only repeats the target ("the key signature at the beginning of the staff") counts as no text | Run 21 |
| Largest match for general targets | `agent/vision_tools.py` | "any signs", "all text": the largest located box is read | Run 21 |
| Per-part questions | `agent/image_planner.py` | Each vision call receives only the question for its own part | Runs 16-17 |
| Unlocated focus fallback | `agent/image_planner.py` | A focus that cannot be located is retried once on the whole image; a missing printed label (R50) is not retried | Runs 16-17 |
| Exact text uses two readings | `agent/image_planner.py` | A part asking for a part number, model, business name, phone number or price is sent to read_text_in_image even if the plan said describe | Run 18 |
| "Not shown" retry | `agent/image_planner.py` | A zoomed answer whose first sentence says the part is not shown is asked once more with a view of at least 40% around it; an answer from that retry is marked "not verified" | Runs 18, 19 |
| Completeness check | `agent/image_planner.py` | Code counts answered parts and shows "check: N/M parts answered"; parts still not shown, not found or not located are counted as not answered | Runs 17, 18 |
| Checked text wins | `agent/image_planner.py` | When a description quotes text and a two-reading result exists, the answer points to the checked reading | Run 18 |
| Code-assembled answer | `agent/image_planner.py` | The final answer is built from the vision results by code. Unconfirmed readings always show both versions; the model cannot pick one | Run 17 |

### Accurate profile (`--accurate`)

Checks that trade time for accuracy. They run only in the accurate profile (`config.toml`, `[profiles.accurate]`).

| Guard | Where | What it does | Why |
|---|---|---|---|
| Second look and majority vote | `agent/image_planner.py` | Every factual sub-question (not summaries or explanations) is asked again as a short answer on two different views: the whole image at a higher pixel budget, or a wider crop around a zoom. Code compares the answers; on disagreement a third look decides by majority. Disagreement, or a majority against the first view, marks the part as not confirmed | Run 23: whole-image answers (06, 08, 11) were wrong with no warning |
| Tile scan | `agent/vision_tools.py` | An image that has to be downscaled is first transcribed in four overlapping zoomed tiles; the text is given to the vision model with whole-image questions | Runs 13, 21: small text in a downscaled view was misread |
| Thinking vision model | `agent/vision_tools.py` | Counting, comparing, chart and feeling questions go to `qwen3-vl:8b` with thinking on; if it fails, the standard model answers and the result says so | Runs 13-23: model limits in 06, 08, 11 |
| Larger pixel budget | `config.toml` | About 1.9 MP instead of 1.2 MP | More detail per look |
| Planning with thinking | `agent/image_planner.py` | The planner thinks before writing the plan; if thinking with a JSON schema fails, it plans without thinking | Runs 18-21: focus written as a request |

## Level 2 — Notes attached to tool results

The model can still ignore these, but they sit right next to the data, which small models follow more often than distant rules.

| Note | Where | Purpose |
|---|---|---|
| "This is tool output, not the user's words" | vision results | Run 16: looped output was proofread as if the user wrote it |
| "identified as '...'; if that is not the part you meant, retry with the printed label" | describe_image with focus | Run 16: "OLED" located the FTDI header |
| "Text on a sign is not evidence of where the photo was taken" | read_text_in_image, only when the target is a sign or shop | Runs 15, 17: a business name was turned into a location; Run 19: the note was added to a schematic reading |
| NOT FOUND / NOT LOCATED instructions | vision tools | Runs 14, 16 |
| Hints in error messages (`**` for powers, `calculate_with_units`, `prod(seq(...))`) | math tools | Runs 7-9 |

## Level 3 — Rules in prompts and tool descriptions

Followed inconsistently by the 8B model. Kept because they help, but not relied on.

- Use date tools for calendar math; never compute dates or units in the model's head
- Pass the user's question unchanged; do not translate it
- One call per part of a multi-part question, asking only about that part (enforced by the planner for image questions)
- Never put expected values into a focus or target
- Trust read_text_in_image over describe_image; call a reading certain only after CONFIRMED (enforced by the planner for image questions)
- Check every part of the question has a tool result before answering (enforced by the planner for image questions)
- Keep what is seen separate from guesses; no locations from business names

## Direction

Rules that matter for correctness move from Level 3 to Level 1 when experiments show the model ignores them. The planning rules for image questions moved to Level 1 with `agent/image_planner.py`: the model now only fills in a plan whose shape is fixed by a JSON schema, and code does the rest. The same pattern can be applied to other multi-step questions.
