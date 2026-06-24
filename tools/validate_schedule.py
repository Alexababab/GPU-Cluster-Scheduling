#!/usr/bin/env python3
"""Validate one GPU scheduling output against one input instance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Server:
    gpu_count: int
    gpu_memory: int
    cpu_cores: int
    memory: int


@dataclass(frozen=True)
class Task:
    release_time: int
    duration: int
    min_gpu: int
    total_gpu_memory: int
    cpu_cores: int
    memory: int
    weight: int


@dataclass(frozen=True)
class Assignment:
    task_id: int
    server_id: int
    start_time: int
    gpu_count: int
    finish_time: int


def parse_instance(path: Path) -> tuple[list[Server], list[Task]]:
    values = [int(token) for token in path.read_text().split()]
    cursor = 0

    server_count, task_count = values[cursor : cursor + 2]
    cursor += 2

    servers = []
    for _ in range(server_count):
        servers.append(Server(*values[cursor : cursor + 4]))
        cursor += 4

    tasks = []
    for _ in range(task_count):
        tasks.append(Task(*values[cursor : cursor + 7]))
        cursor += 7

    if cursor != len(values):
        raise ValueError("input contains unexpected trailing fields")
    return servers, tasks


def parse_schedule(path: Path) -> list[Assignment]:
    assignments = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(
                f"output line {line_number} must contain exactly 5 integers"
            )
        assignments.append(Assignment(*(int(field) for field in fields)))
    return assignments


def validate(
    servers: list[Server],
    tasks: list[Task],
    assignments: list[Assignment],
) -> None:
    if len(assignments) != len(tasks):
        raise ValueError(
            f"expected {len(tasks)} output lines, got {len(assignments)}"
        )

    by_task: dict[int, Assignment] = {}
    events: list[list[tuple[int, int, int, int, int]]] = [
        [] for _ in servers
    ]

    for assignment in assignments:
        if not 1 <= assignment.task_id <= len(tasks):
            raise ValueError(f"invalid task id {assignment.task_id}")
        if assignment.task_id in by_task:
            raise ValueError(f"duplicate task id {assignment.task_id}")
        if not 1 <= assignment.server_id <= len(servers):
            raise ValueError(
                f"task {assignment.task_id}: invalid server id"
            )

        task = tasks[assignment.task_id - 1]
        server = servers[assignment.server_id - 1]

        if assignment.start_time < task.release_time:
            raise ValueError(
                f"task {assignment.task_id}: starts before release"
            )
        if assignment.finish_time != assignment.start_time + task.duration:
            raise ValueError(
                f"task {assignment.task_id}: inconsistent finish time"
            )
        if assignment.gpu_count < task.min_gpu:
            raise ValueError(
                f"task {assignment.task_id}: insufficient GPU count"
            )
        if assignment.gpu_count > server.gpu_count:
            raise ValueError(
                f"task {assignment.task_id}: GPU count exceeds server"
            )
        if assignment.gpu_count * server.gpu_memory < task.total_gpu_memory:
            raise ValueError(
                f"task {assignment.task_id}: insufficient GPU memory"
            )
        if task.cpu_cores > server.cpu_cores or task.memory > server.memory:
            raise ValueError(
                f"task {assignment.task_id}: server is individually infeasible"
            )

        by_task[assignment.task_id] = assignment
        server_events = events[assignment.server_id - 1]
        server_events.append(
            (
                assignment.start_time,
                1,
                assignment.gpu_count,
                task.cpu_cores,
                task.memory,
            )
        )
        server_events.append(
            (
                assignment.finish_time,
                0,
                -assignment.gpu_count,
                -task.cpu_cores,
                -task.memory,
            )
        )

    for server_id, (server, server_events) in enumerate(
        zip(servers, events), 1
    ):
        used_gpu = used_cpu = used_memory = 0
        # Finish events (kind 0) must be applied before starts at the same time.
        for _, _, gpu_delta, cpu_delta, memory_delta in sorted(server_events):
            used_gpu += gpu_delta
            used_cpu += cpu_delta
            used_memory += memory_delta
            if min(used_gpu, used_cpu, used_memory) < 0:
                raise ValueError(
                    f"server {server_id}: resources released before use"
                )
            if (
                used_gpu > server.gpu_count
                or used_cpu > server.cpu_cores
                or used_memory > server.memory
            ):
                raise ValueError(
                    f"server {server_id}: concurrent resources exceeded"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("instance", type=Path)
    parser.add_argument("schedule", type=Path)
    args = parser.parse_args()

    servers, tasks = parse_instance(args.instance)
    assignments = parse_schedule(args.schedule)
    validate(servers, tasks, assignments)
    print("VALID")


if __name__ == "__main__":
    main()
