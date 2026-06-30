# V3 Repair Candidate Summary

| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime (s) | case100 (s) |
|---|---:|---:|---:|---:|---:|---:|
| V2.2 baseline | 100/100 | 127982656.49 | 20134109.56 | 22329.69 | 20.808133 | 14.300309 |
| V3 memory_safe | 100/100 | 128210394.50 | 20082066.40 | 22320.57 | 45.593385 | 42.073506 |

Composite change vs V2.2: -0.040460% (lower is better).
Average metric changes: E_wait +0.177944%, E_memory_new -0.258483%, E_finish -0.040842%.
Strict improved: 17.
Strict regressed: 0.
Mixed/tied: 83.
All five candidates validated successfully in 100/100 cases.

## Candidate Selection Counts

- v2.2_baseline: 55
- repair_wait_top: 6
- repair_memory_top: 28
- repair_finish_tail: 2
- repair_combo: 9
