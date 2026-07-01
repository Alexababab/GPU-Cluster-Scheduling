# V7 Plan Repair Summary

| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |
|---|---:|---:|---:|---:|---:|---:|
| V6 safe | 100/100 | 128023649.58 | 20021963.28 | 22305.21 | 51.772783 | 49.355086 |
| V7 | 100/100 | 128023540.52 | 20013550.96 | 22304.15 | 44.467390 | 38.426114 |

Composite change vs V6: -0.015618%.
Strict improved/regressed/mixed: 20/6/74.
Accepted/rejected repairs: 652/442.
Average destroy set size per attempted repair: 12.06.
Average beam width: 8.52.
Guard-triggered cases: 44.
Operator selections: [212, 184, 177, 177, 174, 170].
Operator successes: [95, 120, 110, 100, 118, 109].

Result: V7 did not meet replacement thresholds; default remains V6 safe-anytime.
