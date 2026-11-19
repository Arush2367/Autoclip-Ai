# Milestone 2.1 — Highlight selection quality

- Changed overlap filtering from a 40% overlap tolerance to strict zero-overlap selection.
- Added `overlap_policy: strict_non_overlapping` to the selector result.
- Updated the explanatory note to state that selected clips do not reuse source footage.
- Added a regression test that verifies consecutive selected clips do not overlap.

Ranking remains a local transcript heuristic. It does not use a semantic language model and its scores are not view or monetization predictions.
