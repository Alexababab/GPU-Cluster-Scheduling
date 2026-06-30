#!/usr/bin/env python3
"""Compare the V2.2 portfolio baseline with V3 repair candidates."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CaseMetrics:
    case: str
    legal: bool
    elapsed: float
    wait: float
    memory: float
    finish: float
    selected: str
    valid_candidates: str


def read_cases(path: Path) -> dict[str, CaseMetrics]:
    result: dict[str, CaseMetrics] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            case = row["case"]
            result[case] = CaseMetrics(
                case=case,
                legal=row["is_legal"].strip().lower() in {"1", "true"},
                elapsed=float(row["elapsed_sec"]),
                wait=float(row["E_wait"]),
                memory=float(row["E_memory_new"]),
                finish=float(row["E_finish"]),
                selected=row.get("selected_config", "").strip(),
                valid_candidates=row.get("valid_candidates", "").strip(),
            )
    return result


def aggregate(cases: dict[str, CaseMetrics]) -> dict[str, float]:
    legal = [case for case in cases.values() if case.legal]
    return {
        "legal": float(len(legal)),
        "count": float(len(cases)),
        "wait": sum(case.wait for case in legal) / len(legal),
        "memory": sum(case.memory for case in legal) / len(legal),
        "finish": sum(case.finish for case in legal) / len(legal),
        "max_runtime": max(case.elapsed for case in cases.values()),
        "case100_runtime": cases["case100.in"].elapsed,
    }


def strict_counts(
    baseline: dict[str, CaseMetrics],
    candidate: dict[str, CaseMetrics],
) -> tuple[int, int, int]:
    improved = regressed = mixed = 0
    for case_name in sorted(set(baseline) & set(candidate)):
        old = baseline[case_name]
        new = candidate[case_name]
        deltas = (
            new.wait - old.wait,
            new.memory - old.memory,
            new.finish - old.finish,
        )
        if all(delta <= 0.0 for delta in deltas) and any(
            delta < 0.0 for delta in deltas
        ):
            improved += 1
        elif all(delta >= 0.0 for delta in deltas) and any(
            delta > 0.0 for delta in deltas
        ):
            regressed += 1
        else:
            mixed += 1
    return improved, regressed, mixed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--v3", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selections", type=Path, required=True)
    args = parser.parse_args()

    baseline = read_cases(args.baseline)
    v3 = read_cases(args.v3)
    baseline_stats = aggregate(baseline)
    v3_stats = aggregate(v3)
    improved, regressed, mixed = strict_counts(baseline, v3)
    composite = 100.0 * sum(
        v3_stats[field] / baseline_stats[field] - 1.0
        for field in ("wait", "memory", "finish")
    ) / 3.0
    counts = Counter(case.selected for case in v3.values())
    expected_candidates = {
        "v2.2_baseline",
        "repair_wait_top",
        "repair_memory_top",
        "repair_finish_tail",
        "repair_combo",
    }
    all_candidates_valid = sum(
        set(case.valid_candidates.split(",")) == expected_candidates
        for case in v3.values()
    )

    lines = [
        "# V3 Repair Candidate Summary",
        "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | "
        "max runtime (s) | case100 (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| V2.2 baseline | {int(baseline_stats['legal'])}/"
            f"{int(baseline_stats['count'])} | {baseline_stats['wait']:.2f} | "
            f"{baseline_stats['memory']:.2f} | {baseline_stats['finish']:.2f} | "
            f"{baseline_stats['max_runtime']:.6f} | "
            f"{baseline_stats['case100_runtime']:.6f} |"
        ),
        (
            f"| V3 memory_safe | {int(v3_stats['legal'])}/"
            f"{int(v3_stats['count'])} | {v3_stats['wait']:.2f} | "
            f"{v3_stats['memory']:.2f} | {v3_stats['finish']:.2f} | "
            f"{v3_stats['max_runtime']:.6f} | "
            f"{v3_stats['case100_runtime']:.6f} |"
        ),
        "",
        f"Composite change vs V2.2: {composite:+.6f}% (lower is better).",
        (
            "Average metric changes: "
            f"E_wait {(v3_stats['wait'] / baseline_stats['wait'] - 1.0) * 100:+.6f}%, "
            f"E_memory_new {(v3_stats['memory'] / baseline_stats['memory'] - 1.0) * 100:+.6f}%, "
            f"E_finish {(v3_stats['finish'] / baseline_stats['finish'] - 1.0) * 100:+.6f}%."
        ),
        f"Strict improved: {improved}.",
        f"Strict regressed: {regressed}.",
        f"Mixed/tied: {mixed}.",
        (
            "All five candidates validated successfully in "
            f"{all_candidates_valid}/{len(v3)} cases."
        ),
        "",
        "## Candidate Selection Counts",
        "",
    ]
    for name in (
        "v2.2_baseline",
        "repair_wait_top",
        "repair_memory_top",
        "repair_finish_tail",
        "repair_combo",
    ):
        lines.append(f"- {name}: {counts.get(name, 0)}")
    lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    args.selections.parent.mkdir(parents=True, exist_ok=True)
    with args.selections.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "case",
                "selected_candidate",
                "E_wait",
                "E_memory_new",
                "E_finish",
                "runtime_sec",
            ]
        )
        for case_name in sorted(v3):
            case = v3[case_name]
            writer.writerow(
                [
                    case.case,
                    case.selected,
                    case.wait,
                    case.memory,
                    case.finish,
                    case.elapsed,
                ]
            )

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
