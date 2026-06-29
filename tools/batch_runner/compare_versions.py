#!/usr/bin/env python3
"""Compare two batch-run summaries.

Usage:
  python tools/batch_runner/compare_versions.py old.csv new.csv
  python tools/batch_runner/compare_versions.py old_results_dir new_results_dir
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class InstanceMetrics:
    case_name: str
    elapsed_sec: float = 0.0
    is_legal: bool = False
    e_wait: float | None = None
    e_memory: float | None = None
    e_finish: float | None = None


@dataclass
class DiffEntry:
    case_name: str
    old: InstanceMetrics
    new: InstanceMetrics
    delta_wait: float | None = None
    delta_memory: float | None = None
    delta_finish: float | None = None
    delta_time: float = 0.0

    @property
    def improved(self) -> bool:
        if not self.old.is_legal and self.new.is_legal:
            return True
        return any(
            delta is not None and delta < 0.0
            for delta in (
                self.delta_wait,
                self.delta_memory,
                self.delta_finish,
            )
        )

    @property
    def regressed(self) -> bool:
        if self.old.is_legal and not self.new.is_legal:
            return True
        return any(
            delta is not None and delta > 0.0
            for delta in (
                self.delta_wait,
                self.delta_memory,
                self.delta_finish,
            )
        )


def parse_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def read_csv(path: Path) -> dict[str, InstanceMetrics]:
    metrics: dict[str, InstanceMetrics] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            case_name = row.get("case", "").strip()
            if not case_name:
                continue
            metrics[case_name] = InstanceMetrics(
                case_name=case_name,
                elapsed_sec=float(row.get("elapsed_sec") or 0.0),
                is_legal=parse_bool(row.get("is_legal")),
                e_wait=parse_float(row.get("E_wait")),
                e_memory=parse_float(row.get("E_memory")),
                e_finish=parse_float(row.get("E_finish")),
            )
    return metrics


def read_meta_dir(path: Path) -> dict[str, InstanceMetrics]:
    metrics: dict[str, InstanceMetrics] = {}
    for meta_path in sorted(path.glob("*.meta")):
        fields: dict[str, str] = {}
        with meta_path.open("r", encoding="utf-8") as source:
            for line in source:
                if "=" not in line:
                    continue
                key, value = line.rstrip("\n").split("=", 1)
                fields[key] = value

        case_name = fields.get("case", f"{meta_path.stem}.in")
        metrics[case_name] = InstanceMetrics(
            case_name=case_name,
            elapsed_sec=float(fields.get("elapsed_sec") or 0.0),
            is_legal=parse_bool(fields.get("is_legal")),
            e_wait=parse_float(fields.get("E_wait")),
            e_memory=parse_float(fields.get("E_memory")),
            e_finish=parse_float(fields.get("E_finish")),
        )
    return metrics


def read_metrics(path: Path) -> dict[str, InstanceMetrics]:
    if path.is_file():
        return read_csv(path)
    if path.is_dir():
        csv_path = path / "batch_summary.csv"
        if csv_path.is_file():
            return read_csv(csv_path)
        return read_meta_dir(path)
    raise FileNotFoundError(path)


def diff_metric(old: float | None, new: float | None) -> float | None:
    if old is None or new is None:
        return None
    return new - old


def compare(
    old_metrics: dict[str, InstanceMetrics],
    new_metrics: dict[str, InstanceMetrics],
) -> list[DiffEntry]:
    diffs: list[DiffEntry] = []
    for case_name in sorted(set(old_metrics) & set(new_metrics)):
        old = old_metrics[case_name]
        new = new_metrics[case_name]
        diffs.append(
            DiffEntry(
                case_name=case_name,
                old=old,
                new=new,
                delta_wait=diff_metric(old.e_wait, new.e_wait),
                delta_memory=diff_metric(old.e_memory, new.e_memory),
                delta_finish=diff_metric(old.e_finish, new.e_finish),
                delta_time=new.elapsed_sec - old.elapsed_sec,
            )
        )
    return diffs


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def fmt_delta(value: float | None) -> str:
    return "-" if value is None else f"{value:+.4f}"


def print_summary(diffs: list[DiffEntry]) -> None:
    if not diffs:
        print("No comparable cases.")
        return

    legal_old = sum(diff.old.is_legal for diff in diffs)
    legal_new = sum(diff.new.is_legal for diff in diffs)
    wait_deltas = [d.delta_wait for d in diffs if d.delta_wait is not None]
    memory_deltas = [
        d.delta_memory for d in diffs if d.delta_memory is not None
    ]
    finish_deltas = [
        d.delta_finish for d in diffs if d.delta_finish is not None
    ]
    time_deltas = [d.delta_time for d in diffs]
    improved = [diff for diff in diffs if diff.improved]
    regressed = [diff for diff in diffs if diff.regressed]

    print("=" * 78)
    print("Batch Comparison")
    print("=" * 78)
    print(f"cases:                 {len(diffs)}")
    print(f"legal instances:       {legal_old} -> {legal_new}")
    print(f"E_wait avg delta:      {avg(wait_deltas):+.4f}")
    print(f"E_memory avg delta:    {avg(memory_deltas):+.4f}")
    print(f"E_finish avg delta:    {avg(finish_deltas):+.4f}")
    print(f"runtime avg delta:     {avg(time_deltas):+.6f}s")
    print(f"improved cases:        {len(improved)}")
    print(f"regressed cases:       {len(regressed)}")
    changed_cases = {diff.case_name for diff in improved + regressed}
    print(f"unchanged/mixed cases: {len(diffs) - len(changed_cases)}")
    print()
    print(
        f"{'case':<18} {'old':>5} {'new':>5} "
        f"{'d_wait':>12} {'d_memory':>12} {'d_finish':>12} {'d_time':>10}"
    )
    print("-" * 78)
    for diff in diffs:
        print(
            f"{diff.case_name:<18} "
            f"{int(diff.old.is_legal):>5} {int(diff.new.is_legal):>5} "
            f"{fmt_delta(diff.delta_wait):>12} "
            f"{fmt_delta(diff.delta_memory):>12} "
            f"{fmt_delta(diff.delta_finish):>12} "
            f"{diff.delta_time:+.6f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old_metrics = read_metrics(args.old)
    new_metrics = read_metrics(args.new)
    print_summary(compare(old_metrics, new_metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
