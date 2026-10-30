# SIA block selection: compression ranking review

2026-10-28. Another chat's critique of SIA (`petey/validate/block_discovery.py`), and my read of it against the code
and `docs/STRUCTURE_ERRORS.md`. Nothing built; a check proposed before anything is.

## The critique

The weakest point is larger-first selection: it is greedy, so a wrong large block takes boxes from correct small ones
and nothing revisits it. Two replacements, both for selection only (candidate generation stays):

- **Compression ranking.** Score each candidate by boxes covered x (copies - 1), minus the cost of describing it, and
  pick in that order (COSIATEC).
- **Weighted set packing.** Pick the non-overlapping set of candidates with the highest total score, exactly (ILP or
  exact solver; a few dozen candidates a page; TWIX solved similar in milliseconds).

It also asked how the caption rule treats the lower rows of a grid whose only captions are column headers, and
suggested tuning the settings (minimum fields per copy, size tolerance, box-model threshold, caption rule) against the
benchmark, with per-pattern scores.

## Verdict

Mostly sound. Compression ranking fits our error log better than the other chat may know, but it fixes one class of
error only, and the caption question is mostly answered already. Worth a measured try after one check (below).

## Greedy selection: true, and already patched once

- `cover` (block_discovery.py, ~line 205) sorts patterns by boxes per copy, most first; each takes its copies among
  fields not yet taken.
- `_glued` (~line 189) is a patch for exactly the greedy failure: fl__sd_252381, six page-sized copies beat eighteen
  wines, so "a big pattern made of smaller ones gives way" was added.
- Compression ranking would replace that patch rather than add another rule:
  - wines: 7 x 17 = 119 beats page-sized 20 x 5 = 100;
  - "two blocks that should be four": four copies of N score ~3N, two copies of 2N score 2N.
- That second case is the "Blocks holding two copies" list in STRUCTURE_ERRORS.md: bm__sd_6286157 p3,
  bm__sd_6512368 p4, lib__n400 p13, bm__sd_7015625 p4, bm__sd_5318548 BT1-1.
- The change is small: the sort key in `cover`, about ten lines. Measurable with the finder numbers (151 je__/lib__
  forms with saved types: right / wrong / unjudged per field) and replay (751 saved copies held out).

## Caveats

- **Lockstep runs after selection.** STRUCTURE_ERRORS.md suspects the lockstep merge (two patterns whose copies move
  together become one) for some "holding two copies" cases. Re-ranking would not touch those.
- **Selection only chooses among what was generated.** Several logged errors are generation misses:

  - bm__sd_6399018 BT1: SIA never proposed the pattern (detect found BT1-2 once BT1-1 was drawn);
  - bm__sd_3856391 p4: the 4 pt shift bins split the votes, so only one pair of copies reached 3 boxes.

  The "fixed distances keep missing" thread in the log is a generation problem.
- **Exact packing (ILP) only if needed.** Try compression ranking first; go to the exact solver only if it still
  leaves conflicts. Bigger change, unmeasured gain.

## The caption rule and grids

- The grid finder runs first, and since 7b93e5f a field in a grid is in no block, so a found grid never reaches SIA.
- As I read `captions_agree` (~line 175): a position counts only when 2+ copies have a caption. A pattern whose lower
  rows have no captions has nothing to judge and is rejected. That is the right result: it is the grid finder's job.
- Where the rule actually strains (both in the log):

  - a grid the grid finder misses: nothing catches it afterwards ("Grids the finder missed", four cases);
  - rows of one table captioned by their own subject: they fail "captions repeat".

## Tuning against the benchmark

Agreed: that is what the benchmark is for, and per-pattern scores would show which rule helps which pattern. Limit:
scores are only as good as the answer keys, so only forms with validated blocks count (today the 151 je__/lib__ forms
with saved types, plus whichever benchmark forms have been reviewed).

## Next steps

1. Check which step made each "holding two copies" case: selection or lockstep.
2. If selection made most of them, try compression ranking in `cover` (dropping `_glued` if it is subsumed), measured
   on finder and replay; log the result in STRUCTURE_ERRORS.md.
3. Exact packing only if step 2 leaves conflicts.
