# Rank Push Portfolio Scheduler

The `portfolio` profile evaluates fourteen deterministic greedy
schedulers for one input instance:

- `v1b`
- `v1c`
- `v1d_light`
- `v1d_strong`
- `wait_first`
- `memory_first`
- `finish_balanced`
- `scarcity_first`
- `short_job_first`
- `heavy_area_first`
- `wait_memory_balance`
- `finish_aggressive`
- `low_reserve_v1c`
- `high_reserve_v1c`

Each candidate is validated before selection. Invalid or failed candidates are
discarded. The remaining schedules are scored with per-instance min-max
normalization:

```text
score = norm(E_wait) + norm(E_memory_new) + norm(E_finish)
```

V2.2 also supports `rank_sum`, `wait_safe`, `memory_safe`, `finish_safe`, and
`no_regret_guard`. Set `SCHEDULER_PORTFOLIO_SELECTOR` to select one. The tuned
default is `memory_safe`; `equal_sum` remains available for V2 comparisons.

The lowest score wins. If the portfolio cannot produce a valid candidate, it
falls back to V1c. `SCHEDULER_TRACE_SELECTION=1` emits the selected profile to
stderr for local batch analysis without changing schedule stdout.

The repository `run.sh` defaults to `portfolio` but honors an existing
`SCHEDULER_CONFIG` environment value, so every baseline remains selectable.
