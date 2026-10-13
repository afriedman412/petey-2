# Local vision models as the page classifier (2026-10-12 / 13)

Can a model running on the laptop replace Claude Sonnet 4.6 as the page classifier? One step of blueprint
generation, tested on its own, before any full-pipeline run.

**Answer: one model can (Underdog), at about 10 minutes a page against Sonnet's 40 seconds. It works, but the time
makes it barely useful.** Every smaller or faster model tried fails the task in the same way.

## The task

The page classifier (`petey/synth/classify.py`) gets a picture of the blank page with a numbered red box drawn on
every fillable box. For each box it returns the caption it reads, a class (person name, date, amount, checkbox,
signature...), whose value it is, and which checkboxes answer one question together. It never sees the AcroForm
names or tooltips. Its output feeds the synthetic values used to fill a blank in the loop, and the class check and
classifier witness on names.

## Setup

- Forms: three single-page forms new to the test set, DD 1155 (87 boxes), IA-1 (100) and OSHA 301 (23).

- Machine: this laptop, M1 Pro, 16 GB. llama.cpp release b11574, one model at a time, nothing else heavy running.

- Thinking off for every local model (see Underdog below).

- Scoring, against the reviewed blueprints rather than against Sonnet:

  - **Captions:** for each text box, does the model's caption describe the blueprint's field name for that box
    (text-match model, P >= 0.5)?

  - **Type contradictions:** boxes whose class contradicts the blueprint's type (`class_check`, tier 1); fewer is
    better.

  - **Groups:** blueprint option groups (Andrew's groupings) the model reproduced exactly.

## Results

Captions that describe the blueprint's name:

| model | DD 1155 | IA-1 | OSHA 301 |
|---|---|---|---|
| Claude Sonnet 4.6 (today's classifier) | 83% | 83% | 95% |
| **Underdog-Saluki-27B** (IQ2, 7.9 GB + 0.6 GB vision) | **89%** | **86%** | **100%** |
| Granite Vision 4.1 4B (Q8, 3.6 + 1.2 GB) | 12% | 49% | 10% |
| MiniCPM-V 4.5 8B (Q6_K, 6.7 + 1.1 GB) | 6% | 65% | 22% |
| Gemma 4 26B-A4B (IQ2_M, 10 + 1.2 GB) | 11% | failed | 10% |

Time per page, type contradictions and groups:

| model | DD 1155 | IA-1 | OSHA 301 | type contradictions (all three) | groups exactly right (DD 1155 / IA-1) |
|---|---|---|---|---|---|
| Sonnet 4.6 | 42 s | 40 s | 14 s | 15 | 5/5, 3/11 |
| Underdog | 9.6 min | 10.6 min | 2.9 min | 13 | 3/5, 2/11 |
| Granite Vision 4.1 | 1.4 min | 1.7 min | 27 s | 59 | 0/5, 0/11 |
| MiniCPM-V 4.5 | 2.4 min | 2.9 min | 41 s | 33 | 0/5, 0/11 |
| Gemma 4 26B-A4B | 14.5 min | failed | 3.3 min | 33 (two forms) | 0/5, - |

No model grouped any OSHA 301 checkbox, Sonnet included; that looks like the box finder, not the models.

## Per model

- **Underdog-Saluki-27B** (a fine-tune of Qwen3.8-27B). Captions as good as Sonnet's or slightly better, type
  contradictions about the same, but it over-groups checkboxes (on DD 1155 it puts unrelated boxes in a group:
  precision 61% against Sonnet's 92%). About 13x slower than Sonnet. Generation at 5.6 tokens/s, page reading at
  56 tokens/s; the EC2 base M1 managed 3.9 and 32-48.

- **Gemma 4 26B-A4B.** Too big for the laptop's GPU: macOS lets the GPU use about 10.7 GB of the 16, and 10 GB of
  weights plus 1.2 GB of vision add-on ran out of Metal memory. It ran only with every expert on the CPU and the
  prompt read in 512-token chunks, which made llama.cpp cut the page image to 512 tokens. At that resolution it
  could not read the box numbers, and with the experts on the CPU it was slower than Underdog.

- **Granite Vision 4.1 4B.** Built for document extraction (tables, charts, key-value pairs), fully on the GPU,
  7x faster than Underdog. It reads the form, but not our numbered boxes: captions land on the wrong box numbers.
  Its model card warns the task-specific training limits open-ended prompts, and that is what happened.

- **MiniCPM-V 4.5 8B.** Fast (2-3 min a page), fails the same way; it also left most OSHA 301 captions empty.

- **MiniCPM-V 4.7.** Released 2026-10-12. The 1B was stopped before a result (if the 8B fails, the 1B will not
  pass); the 35B-A3B was not tried (smallest build 15.5 GB, and its on-device speed needs OpenBMB's llama.cpp fork).

## What we learned

- **Reading the numbered boxes is the hard part.** The two models that do it, Sonnet and Underdog, are general
  models. The document-specialist and smaller models read the page well enough but attach captions to the wrong
  numbers. A small model would need a different prompt (for example: list label / value pairs with positions, and
  let code match them to boxes) or fine-tuning on this task.

- **Thinking hurt, twice.** llama-server's `--reasoning-budget 0` did not stop Underdog thinking; the request has
  to say `enable_thinking: false` (now done for local page calls, `generate.py`, d615045). With thinking on, DD 1155
  took a 5,755-token essay, the reply was cut at exactly 16,384 characters (one brace short, unparsable, so the
  classifier's retry ran: 19 of 28 minutes wasted), and the recovered answer was worse: captions matching Sonnet
  47 of 87 against 74 without thinking, because the essay narrated the form in reading order instead of reading
  the box numbers. The 16,384 cut itself is not explained yet.

- **16 GB caps the model size, not the disk.** About 10.7 GB is usable by the GPU; past that, offloading to the CPU
  costs both speed and (through the image cap) accuracy.

- **10 minutes a page is about the limit of useful.** Blueprints are built once per form and cached, so it is not
  ruled out, but a 15-page form would take 2.5 hours for this one step.

## Caveats

- Three forms, one run per model; differences of a few points are noise.

- Captions are graded by the text-match model against blueprint names, text fields only; option groups are graded
  separately.

- Sonnet's IA-1 answer is from its cache (2026-09-30, same prompt version and box finder).

## Not tried yet

- Local models on the other steps: reader (exact match against the synthetic values), adjudicator (against
  Sonnet's 142 forms of verdicts), page check, then labeler and reviewer in a full loop. Planned in that order; it
  needs the `model-swap` branch merged.

- A key-value prompt for the small document models.

- Faster hardware (an M-series Max or Ultra would roughly double or triple Underdog's speed).

## Files

- Scripts: `eval/local_vlm/` (`classify_run.py` runs one model over the three forms; `grade_vs_blueprint.py`,
  `groups_vs_blueprint.py` and `compare.py` score; `*_three.sh` start llama-server for each model).

- Results: classifier caches in `runs/_gen_cache/classify/`, keyed by model label:
  `claude-sonnet-4-6`, `local-underdog-iq2-q8vision-nothink`, `local-granite-vision-4.1-4b-q8`,
  `local-minicpm-v-4.5-q6k-nothink`, `local-gemma4-26b-a4b-iq2m-f16vision-nothink`
  (`local-underdog-iq2-q8vision` holds the with-thinking DD 1155 run). Timings in `runs/local_vlm/times.jsonl`,
  server logs in `runs/local_vlm/`.

- Model files: only Underdog and llama.cpp b11574 are kept, in `models/llm/` (gitignored); the four that failed
  were deleted and can be downloaded again from their Hugging Face repositories.
