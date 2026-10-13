# Local models as the adjudicator (overnight 2026-10-13)

Can a model on the laptop replace Claude Sonnet 4.6 as the adjudicator, the step that decides between a field's
current name and a name the reviewer proposes, from a crop of the page?

**Answer: Underdog can. It was as accurate as Sonnet on all three forms (90 / 97 / 88% against 100 / 95 / 88%), at
about 28 seconds a case against 3.** Granite Vision 4.1 and MiniCPM-V 4.5 failed the first form and stopped there.

Unlike the page classifier (`docs/LOCAL_VISION_MODELS_2026-10-13.md`, about 10 minutes a page), this speed is usable:
a form sends the adjudicator a handful of contested renames, not every box.

## The task

The adjudicator (`petey/validate/adjudicate.py`) sees a crop of the page around one box (outlined in red), the box's
tooltip, the field's current name with its description and type, a proposed name and the reviewer's reason. It
answers current, proposed or unclear.

## The test

Past adjudications could not be replayed (the reviewer's reasons are not stored, and Sonnet's verdicts would only
measure agreement with Sonnet), so the cases come from hand review, where the right answer is known
(`eval/local_vlm/adjudicate_test.py`):

- **Slip cases**, from fields Andrew looked at and accepted: the true name against a nearby field's name, the slip a
  reviewer proposes. Either the true name is current and the neighbour's is proposed (answer: current), or the
  reverse (answer: proposed). The current name brings its own description and type, so only the crop and the
  tooltip point to the answer.

- **Real cases** (ACORD 25): Andrew's 2026-10-13 hand corrections; current = the wrong name, proposed = his fix.

- Three forms from different issuers: DD 1155 (DoD), DV-130 (California courts), ACORD 25 (insurance). Up to 40
  cases each, **exactly half 'current' and half 'proposed'**, so a model that always gives one answer scores 50%.

- The same neutral reviewer reason on every case. Andrew's rule: a model under 75% on the first form stops there.

## Results

| model | DD 1155 | DV-130 | ACORD 25 | median per case |
|---|---|---|---|---|
| Claude Sonnet 4.6 (today) | **100%** | 95% | **88%** (real fixes 16/20) | **3.2 s** |
| **Underdog-Saluki-27B** (IQ2 + Q8 vision, thinking off) | 90% | **97%** | **88%** (real fixes 16/20) | 28 s |
| Granite Vision 4.1 4B | 70%, stopped | - | - | 8 s |
| MiniCPM-V 4.5 8B | 60%, stopped | - | - | 11 s |

- **Underdog against Sonnet, case by case (119 cases):** the same verdict on 106. Both right on 104, only Sonnet
  right on 8, only Underdog right on 5, both wrong on 2. The 2 both-wrong cases look like test cases that are
  themselves ambiguous: `protected_person_name` against `protected_person_name_continued` (DV-130), and
  `umbrella_other_limit_desc_txt` against `umbrella_other_limit_amt` (ACORD 25).

- **Total time:** Sonnet 6.8 minutes for all 119 cases, Underdog 58 minutes.

- **Granite and MiniCPM-V lean one way.** Granite kept the current name almost always (keep cases 20/20, fixes 8/20).
  MiniCPM-V almost always renamed (fixes 20/20, keeps 4/20). Neither judges the crop; each has a default answer. The
  single crop did not rescue them, although it removes the numbered-box problem they failed on as page classifiers.

- No model answered "unclear" or failed to return valid JSON.

## What it means

- Underdog is a real local replacement for the adjudicator: same accuracy, and the step is called rarely enough
  that 30 seconds a case is acceptable (a form with 10 contested renames: 5 minutes).

- With the page classifier also matching Sonnet (but at 10 minutes a page), Underdog now covers two of the vision
  steps. The small document models (Granite, MiniCPM-V) fail both.

- Not shown here: how Underdog does inside the loop, where its verdicts change what the reviewer's renames do.
  That needs a full run with `PETEY_MODEL_ADJUDICATOR=local-underdog-iq2-q8vision-nothink`.

## Next

- The reader (exact match against the synthetic values), the other step with a clean score. A small text-only model
  is a fair candidate there, since the reader gets text, not images.

- A full loop run on one form with Underdog as the adjudicator.

## Files

- `eval/local_vlm/adjudicate_test.py` (cases and scoring), `eval/local_vlm/adjudicate_overnight.sh` (the run).

- Answers: `runs/local_vlm/adjudicate/<model>.jsonl`; `summary.txt`, `overnight.log`, server logs alongside.

- Granite and MiniCPM-V were downloaded again for this test and deleted again afterwards; `models/llm/` keeps
  Underdog and llama.cpp b11574.
