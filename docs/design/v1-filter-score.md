# V1 Task Ordering and Filter + Score

## Profiles

- `v0`: preserves the V0 pending order and lexicographic best-fit.
- `v1a`: enables configurable pending-task scoring while preserving V0 placement.
- `v1b`: enables task scoring and weighted server scoring.

The profile is selected with the `SCHEDULER_CONFIG` environment variable.

## Task features

For every task, the scheduler precomputes:

- number of permanently feasible servers (`fit_count`);
- scarcity (`1 / fit_count`);
- minimum feasible GPU count;
- logarithmic GPU-time area;
- inverse duration.

At every release or finish event, pending tasks are ordered by:

```text
priority weight
+ weighted waiting time
+ scarcity
- logarithmic GPU-time area
+ short-job preference
```

The V0 profile disables this ordering and therefore keeps the original
release-time/task-id order.

## Filter stage

Permanent feasibility is precomputed from:

- GPU count and per-GPU memory;
- CPU capacity;
- system memory capacity.

At the current event time, candidate servers are filtered again using their
remaining GPU, CPU, and memory.

## Score stage

V1b minimizes a weighted sum of normalized placement costs:

```text
GPU count fragmentation
+ allocated GPU-memory waste
+ remaining CPU ratio
+ remaining system-memory ratio
```

Ties are deterministic and use server id. Opportunity cost, size isolation,
and backfilling remain separate follow-up strategies.

## Initial public-data result

All three profiles produced legal schedules for all 100 public instances.
Compared with V0, the initial V1b weights improved weighted waiting time on
66 instances and worsened it on 4; average raw `E_wait` decreased. These
weights are an initial experiment point, not the final V1-best configuration.
