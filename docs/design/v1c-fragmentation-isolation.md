# V1c Fragmentation Isolation

V1c keeps the V1b Kubernetes-style Filter + Score framework and adds
placement costs inspired by modified first fit dynamic bin packing.

## Profile

Select the profile with:

```sh
SCHEDULER_CONFIG=v1c ./build/scheduler < case.in
```

or with the batch runner:

```sh
python tools/batch_runner/run_all.py DATASET_DIR \
  --scheduler build/scheduler.exe \
  --validator build/validator.exe \
  --scheduler-config v1c
```

The default profile remains `v1b`, so V1b is still the configurable baseline.

## Added Scores

V1c enables three extra score components:

- residual imbalance: penalizes uneven GPU, CPU, and memory leftovers after a
  placement;
- high-capacity reserve: discourages small tasks from opening an empty 8-GPU
  server;
- class isolation: discourages mixing large and small tasks on the same server
  while giving a small affinity bonus for placing a task with the same class.

Large tasks are currently tasks whose placement uses at least 4 GPUs, or whose
declared minimum GPU count is at least 4. High-capacity servers are servers with
at least 8 GPUs. Both thresholds and all new weights can be tuned through the
`custom` scheduler config file.

## Rationale

V1b best-fit scoring can place a long small task on a high-capacity server and
leave the server fragmented for later large tasks. V1c tries to concentrate
small tasks on already-fragmented or small-capacity machines and keep complete
high-capacity servers available for large tasks.

If the full public-data comparison shows overall regression, keep this profile
available for ablation but leave `v1b` as the default.
