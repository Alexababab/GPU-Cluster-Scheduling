# V4 Reservation-aware Backfilling + Multi-round Repair

| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime (s) | case100 (s) |
|---|---:|---:|---:|---:|---:|---:|
| V2.2 | 100/100 | 127982656.49 | 20134109.56 | 22329.69 | 20.808133 | 14.300309 |
| V3 | 100/100 | 128210394.50 | 20082066.40 | 22320.57 | 45.593385 | 42.073506 |
| V4 | 100/100 | 128242753.38 | 20074492.16 | 22318.02 | 38.982512 | 31.893866 |

Composite change vs V3: -0.007967% (lower is better).
Composite change vs V2.2: -0.048379% (lower is better).
Strict improved/regressed/mixed vs V3: 12/0/88.
Strict improved/regressed/mixed vs V2.2: 21/0/79.
All six V4 candidates validated in 100/100 cases.

## Candidate Selection Counts

- repair_combo_round2: 8
- repair_memory_round2: 24
- repair_wait_memory_round2: 1
- reservation_backfill: 2
- reservation_repair_combo: 0
- v3_baseline: 65

Reservation-selected cases: case092.in, case094.in.

Multi-round-repair-selected cases: case001.in, case003.in, case005.in, case007.in, case009.in, case011.in, case013.in, case015.in, case017.in, case019.in, case021.in, case023.in, case026.in, case027.in, case032.in, case033.in, case036.in, case041.in, case047.in, case048.in, case053.in, case054.in, case055.in, case060.in, case066.in, case069.in, case072.in, case073.in, case078.in, case084.in, case086.in, case089.in, case093.in.
