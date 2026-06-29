# V1d New Memory-Aware Score

V1d keeps the V1c task ordering, Filter + Score selection, fragmentation
control, and task-size isolation as its baseline. It adds one optional server
score term for the revised competition memory metric.

For a feasible placement:

```text
allocated_memory = gpu_count * server_gpu_memory
waste_ratio = (allocated_memory - task_total_gpu_memory) / allocated_memory
duration_factor = 1 + duration_log_scale * log(1 + duration)
duration_memory_waste_cost = waste_ratio * duration_factor
```

The normalized ratio keeps this term on the same scale as the existing score.
The duration factor makes an inefficient placement increasingly expensive for
long tasks without allowing extreme durations to dominate every other term.

Profiles remain independently selectable with `SCHEDULER_CONFIG`:

- `v1c`: fragmentation isolation baseline.
- `v1d`: V1c plus duration-weighted GPU-memory fit.

Custom configs may use `memory_aware_enabled`,
`w_duration_memory_waste`, and `duration_log_scale`.

## Public Dataset Result

The final preset uses `w_duration_memory_waste=10.0` and
`duration_log_scale=0.20`. On the 100 public instances, V1c and V1d were both
100/100 legal. Relative to V1c, V1d produced:

- revised `E_memory`: -10.62% on average; 86 improved, 8 regressed, 6 tied;
- `E_wait`: -18,332.25 on average; 24 improved, 35 regressed, 41 tied;
- `E_finish`: -2.41 on average; 28 improved, 20 regressed, 52 tied;
- average scheduler runtime: 0.102 seconds in the final V1d run.

V1d remains available as a standalone baseline. The rank-push branch defaults
to the portfolio profile, which includes V1d variants among its candidates.
