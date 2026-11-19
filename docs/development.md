# Development notes

How the code is organised, the tools the agent can call, the run profiles, and the commands that test each
part. For using the agent, see the [README](../README.md).

## Code layout

```
main.py                     session: routes each question to an agent and prints the answer
config.toml                 models, profiles, device settings
agent/
  loop.py, tools.py, llm.py   agent loop, tool registry (schemas from type hints), Ollama client
  time_tools.py, math_tools.py, builtin_tools.py
  vision_tools.py, image_planner.py            image questions
  document_tools.py, document_planner.py       documents: page and passage search, cited answers
  formula_tools.py, table_tools.py             equations; tables, statements and charts
  device/
    sources/                readers: battery, power, chip (powermetrics), thermal, load, memory, storage, models
    readings.py, store.py   one record format for every reading; SQLite store
    sampler.py, capture.py  background sampling; per-second capture for a diagnosis
    router.py               keyword rules, a small model only on a tie
    diagnosis.py            battery and performance reports: facts and findings, by code
    answer.py               the answer writer and its checks (numbers, stray words, reasoning)
    agent.py                the device agent
    power_policy.py         energy mode by job on battery; energy measurement
    speed_check.py, bench.py    is the Mac as fast as normal; memory and SSD transfer speeds
    workloads.py            synthetic everyday workloads (set W)
    controller.py           PI power controller
scripts/                    test sets, measurements, tools
tests/                      offline tests (no Ollama needed); fixtures/ holds recorded hardware outputs
evals/                      test sets, expected answers, results and published runs
```

## Tools the model can call

| Group | Tools |
|---|---|
| Time and date (`agent/time_tools.py`) | `get_current_time`, `convert_timezone`, `add_to_date`, `date_difference`, `date_info`, `resolve_date` |
| Math (`agent/math_tools.py`) | `calculator` (engineering functions, lists, sequences, decibels, complex numbers, number bases, physical constants), `convert_units`, `calculate_with_units` (formulas with units) |
| Vision (`agent/vision_tools.py`) | `describe_image`: a separate vision model answers a question about an image; with a focus, the part is located, cropped and enlarged first. `read_text_in_image`: one piece of text is located and read twice at two zoom levels, and code compares the readings (confirmed / uncertain). Images are converted (GIF, WebP, transparent PNG, rotated phone photos) and fitted to a pixel budget |
| Documents (`agent/document_tools.py`, `agent/document_planner.py`) | `read_document`: PDF and PowerPoint text page by page, with tables and speaker notes, headers and footers removed. Questions that name a document go to the document planner, which answers with page citations |
| Formulas (`agent/formula_tools.py`) | `read_equation`: an equation is located from the text layer (or, without a number, from its layout), cropped twice, read twice by the vision model, compared after normalising the LaTeX, and checked against the image by a third call |
| Files (`agent/builtin_tools.py`) | `list_files`, `read_file` (sandboxed to the workspace folder) |

## Document and image pipeline

```
user input
   |
   +-- a document path (.pdf, .pptx)? --> document planner
   |        pages extracted as text; the planner picks pages (slides) or passages (papers);
   |        pages with equations, figures or charts are read by the vision model;
   |        totals and calculations by code; the answer cites [p.N] and code checks citations and numbers;
   |        "not in the document" only after a second search
   |
   +-- an image path? --> image question planner
   |        plan parts (JSON schema), one vision call per part, check every part was answered
   v
agent loop --> Ollama --> tool calls --> tool registry --> result back to the model --> answer
```

## Profiles

Defined in `config.toml`.

| Command | Profile |
|---|---|
| `python main.py --fast` | `qwen3:8b` main model; images planned by `qwen3:14b`. Use this for real work |
| `python main.py` | `qwen3:14b` main model |
| `python main.py --accurate` | Experiment: second looks with a majority vote, tile scans, the thinking vision model. In Run 24 it was 3-4× slower and less accurate; kept for the record ([benchmarks.md](benchmarks.md)) |

## Safety

- File tools are sandboxed to the workspace folder; tools that change something ask for confirmation.
- Device readers are read-only. The only command that changes a setting is the battery energy mode
  (`pmset -b powermode 0/1/2`), allowed without a password by a sudoers rule limited to exactly those three
  commands.
- Every rule enforced in code, with the run that motivated it: [guardrails.md](guardrails.md).

## Tests and measurements

```bash
python -m unittest discover -s tests -v                    # 375 offline tests, no Ollama needed

# answer quality
python scripts/run_eval_set.py --set documents --fast      # documents
python scripts/run_eval_set.py --set documents --cases evals/documents/equations.toml --fast
python scripts/run_eval_set.py --set documents --cases evals/documents/tables.toml --fast
python scripts/run_formula_set.py                          # equation transcription, graded by code
python scripts/run_vision_set.py --fast                    # images (about 7 minutes)
python scripts/run_vision_set.py --compare                 # model size x checking method
python scripts/run_device_set.py                           # questions about the Mac: recorded and live states

# the Mac
python scripts/probe_device.py                             # which hardware readings this Mac allows
taskpolicy -b python scripts/run_sampler.py                # background readings on the efficiency cores
python scripts/speed_check.py                              # is this Mac as fast as normal? (20 s)
python scripts/measure_job_energy.py --job heavy           # one job in each energy mode on battery
python scripts/run_workloads.py --tier 2                   # synthetic everyday workloads
python scripts/run_controller_test.py                      # the power controller holding training at a set power (5 min)
python scripts/profile_calls.py                            # where the time of the model calls went

# Wi-Fi and Bluetooth (Stage 8; `sudo -v` first)
python scripts/wifi_experiment.py                          # W1: how long to measure
python scripts/wifi_walk.py --plan logs/home/plan.json     # coverage walk at the floor plan's points
python scripts/coverage_report.py                          # coverage maps and the model check
python scripts/coverage_paths.py logs/home/walk_*.jsonl    # through the walls or around them: four models compared
python scripts/wifi_trial.py --label PLACE --rank-only     # which home network is best here (no disconnection)
python scripts/wifi_trial.py --label PLACE                 # ... and a join-and-measure test of the candidates
python scripts/wifi_choice_check.py WALK.jsonl --current SSID   # replay a walk through the network choice
```

Long test-set runs start with the speed check and stop with a warning if the Mac is far below its normal speed
(`--no-speed-check` to skip). Reports go to `logs/` (not published: they hold this machine's personal state).
