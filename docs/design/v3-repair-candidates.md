# V3 Repair Candidates

V3 keeps the complete V2.2 portfolio result as a mandatory baseline candidate.
It analyzes that schedule and boosts the worst five percent of tasks by
weighted wait cost, duration-weighted GPU-memory waste, finish time, or their
normalized sum.

The final candidate set is:

- `v2.2_baseline`
- `repair_wait_top`
- `repair_memory_top`
- `repair_finish_tail`
- `repair_combo`

Boosts affect only pending-task ordering. Every repair is independently
validated and a failed repair is discarded. The existing selector system then
chooses among the valid schedules, with `memory_safe` remaining the default.

Profiles:

- `portfolio`: default V3 path.
- `portfolio_v3`: explicit V3 path.
- `portfolio_v2_2`: V2.2 fallback without repairs.
