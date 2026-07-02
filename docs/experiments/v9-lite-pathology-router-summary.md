# V9-lite Pathology Router Summary

| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |
|---|---:|---:|---:|---:|---:|---:|
| V6 safe | 100/100 | 128023649.58 | 20021963.28 | 22305.21 | 51.772783 | 49.355086 |
| V9 lite | 100/100 | 128016095.07 | 20014455.10 | 22304.05 | 50.335065 | 37.306840 |

Composite change vs V6: -0.016200%.
Strict improved/regressed/mixed/equal: 25/0/0/75.
Accepted solver improvements: 24.
Verification verdict: FAIL.

## Router

- tail: trigger=35, run=35, accept=0, cases=none
- memory: trigger=100, run=100, accept=23, cases=case001.in,case005.in,case006.in,case007.in,case008.in,case011.in,case012.in,case018.in,case021.in,case024.in,case029.in,case030.in,case032.in,case033.in,case035.in,case036.in,case038.in,case039.in,case048.in,case051.in,case053.in,case056.in,case066.in
- shape: trigger=92, run=92, accept=1, cases=case025.in
- blocker: trigger=1, run=3, accept=0, cases=none
- rejected wait/memory/finish/proxy/illegal/timeout: 80/190/43/125/0/0
- skipped due to time: 0

## Accepted Solver Deltas

| solver | cases | avg delta wait | avg delta memory | avg delta finish | avg runtime cost | proxy gain/sec |
|---|---:|---:|---:|---:|---:|---:|
| tail | 0 | 0 | 0 | 0 | 0 | 0 |
| memory | 23 | 0.00 | -24515.13 | 0.00 | 0.139789 | 0.131776 |
| shape | 1 | -1451.00 | -46070.00 | 0.00 | 0.026044 | 2.806433 |
| blocker | 0 | 0 | 0 | 0 | 0 | 0 |

## Controls

- case036.in: selected=memory_window_repack, blocker_trigger=1, blocker_accept=0.
- case035.in: selected=memory_window_repack, blocker_trigger=0, blocker_accept=0.
- case038.in: selected=memory_window_repack, blocker_trigger=0, blocker_accept=0.
- case080.in: selected=v6_safe_baseline, blocker_trigger=0, blocker_accept=0.
