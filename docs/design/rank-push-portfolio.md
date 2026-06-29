# Rank Push Portfolio Scheduler

The `portfolio` profile evaluates at most eight deterministic greedy
schedulers for one input instance:

- `v1b`
- `v1c`
- `v1d_light`
- `v1d_mid`
- `v1d_strong`
- `wait_first`
- `memory_first`
- `finish_balanced`

Each candidate is validated before selection. Invalid or failed candidates are
discarded. The remaining schedules are scored with per-instance min-max
normalization:

```text
score = norm(E_wait) + norm(E_memory_new) + norm(E_finish)
```

The lowest score wins. If the portfolio cannot produce a valid candidate, it
falls back to V1c. `SCHEDULER_TRACE_SELECTION=1` emits the selected profile to
stderr for local batch analysis without changing schedule stdout.

The repository `run.sh` defaults to `portfolio` but honors an existing
`SCHEDULER_CONFIG` environment value, so every baseline remains selectable.
