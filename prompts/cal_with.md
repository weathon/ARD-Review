Use comparative scoring to calibrate your final score against human-reviewed anchors. Retrieval is iterative: first a wide bracketing pass to find which score range the paper plausibly sits in, then one or two narrowing passes to anchor inside that range.

`calibration_search` schema: pass `queries: list[{query: str, n: int, low_score?: float, high_score?: float}]`. Default n=4 if unsure. The tool runs all queries in parallel and returns concatenated results grouped by query, each with avg human score and ~1000 chars of preview.

Before any `calibration_search` call, first finish filtering the Harsh Critic and Strength Finder inputs into a draft review. Then call `draft_review` exactly once with that draft. The draft should include the kept strengths, kept weaknesses with severity tiers, removed points, novel insights, and suggestions. Do not include calibration anchors or a final calibrated score in this draft. After `draft_review` returns, start Round 1.

## Round 1 — Bracketing

Make one `calibration_search` call with a couple queries that anchor each score band on a topic similar to the paper. Filters are strict: `low_score` is exclusive lower bound (avg > low_score) and `high_score` is exclusive upper bound (avg < high_score). 
- "<topic>" with `high_score=1.5` (Strong reject anchors)
- "<topic>" with `low_score=1.5, high_score=3.5`
- "<topic>" with `low_score=3.5, high_score=5.5`
- "<topic>" with `low_score=5.5, high_score=7.5`
- "<topic>" with `low_score=7.5, high_score=8.5`
- "<topic>" with `low_score=8.5`


Strong reject anchors are used for matching, if the reviewed paper matches it, do NOT be afraid to strong reject it. 

You should find MORE papers on the two end than middle and be careful to score a paper in the middle. 

If nothing topically similar exists in a band, still take whatever the tool returned for that band as your anchor.

Use `read_file` on a small number of anchors (typically 1–2 per band) to inspect the full reviews. Now form an initial bracket: based on these comparisons, what is the narrowest plausible score range for this paper (e.g., "between 4 and 6", "between 6.5 and 8")? State this bracket explicitly before round 2.


## Scoring rules

- Score distribution: extreme scores are rare but valid. If the paper is truly exceptional or truly weak, give an extreme score even if most retrieved anchors sit in the middle.
- Do NOT cluster scores around 5. The score should be relative to retrieval samples, calibrated to where the paper actually sits.
- The number of weaknesses listed is not a signal for a bad paper — focus on weakness content and anchor scores.
- The nice to have SHOULD be considered as weakness in comparsion

## Reporting

When reporting your score, list every anchor paper retrieved across all rounds (not just the ones you read in full). For each anchor give the path, its avg human score, the round it came from, and one sentence on how it compares to the paper under review. State the round-1 bracket explicitly, then explain how round 2 (and 3, if used) narrowed it to the final score.
